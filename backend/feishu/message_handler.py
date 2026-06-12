"""飞书消息 → Agent LLM 处理器

独立模块，供 bot.py 和 routers/feishu.py 共用。

Phase 5C: 增加进度推送 + 内置命令系统
Phase 5E: 群聊维度滑动窗口记忆（FeishuGroupContext）
Phase 5G: FeishuGroupContext 文件持久化（跨重启保留群聊记忆）
"""

import asyncio
import hashlib
import json
import logging
import os
from collections import deque
from datetime import datetime, timedelta
from typing import Callable, Awaitable, Optional

logger = logging.getLogger("feishu.handler")


# ================================================================
# 群聊滑动窗口记忆（Phase 5G: 文件持久化）
# ================================================================

def _get_storage_dir() -> str:
    """获取飞书群聊记忆存储目录"""
    # 与 short_term_memory 同级：memory_store/feishu_groups/
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dir_path = os.path.join(base, "memory_store", "feishu_groups")
    os.makedirs(dir_path, exist_ok=True)
    return dir_path


def _chat_id_to_filename(chat_id: str) -> str:
    """将 chat_id 转为安全的文件名（SHA256 前16位）"""
    h = hashlib.sha256(chat_id.encode()).hexdigest()[:16]
    return f"{h}.json"


class FeishuGroupContext:
    """按群聊/会话维度的短期滑动窗口记忆（文件持久化）。

    每个 chat_id 维护独立的消息队列，Agent 处理消息时
    自动注入该群最近 N 条对话历史。

    持久化策略：
    - 内存：deque 快速读写（Agent 上下文注入不用等 IO）
    - 磁盘：每次 add_message 同步写 JSON 文件（重启不丢失）
    - 启动时自动加载所有未过期的群聊文件
    - 清理过期群聊时同时删除磁盘文件
    """

    # 默认每群保留的消息条数
    DEFAULT_MAX_MESSAGES = 30
    # 超过此时间（分钟）无新消息的群，自动清理上下文
    TTL_MINUTES = 60
    # 定时清理间隔
    CLEANUP_INTERVAL = 300  # 5 分钟

    def __init__(self, max_messages: int = None):
        self._max_messages = max_messages or self.DEFAULT_MAX_MESSAGES
        # chat_id → deque of {"role": ..., "content": ..., "time": ...}
        self._groups: dict[str, deque] = {}
        self._last_active: dict[str, datetime] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._storage_dir = _get_storage_dir()
        # 启动时从磁盘加载已有群聊
        self._load_all_from_disk()

    # ================================================================
    # 磁盘持久化
    # ================================================================

    def _filepath(self, chat_id: str) -> str:
        return os.path.join(self._storage_dir, _chat_id_to_filename(chat_id))

    def _save_group(self, chat_id: str):
        """将指定群聊的消息写入 JSON 文件"""
        if chat_id not in self._groups:
            return
        try:
            data = {
                "chat_id": chat_id,
                "last_active": self._last_active.get(chat_id, datetime.now()).isoformat(),
                "messages": list(self._groups[chat_id]),
            }
            filepath = self._filepath(chat_id)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[GroupCtx] 保存群聊 {chat_id[:15]}... 失败: {e}")

    def _load_group(self, filepath: str) -> Optional[str]:
        """从 JSON 文件加载群聊，返回 chat_id（失败返回 None）"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            chat_id = data.get("chat_id", "")
            if not chat_id:
                return None

            messages_data = data.get("messages", [])
            if not messages_data:
                return None

            # 检查是否过期
            last_active_str = data.get("last_active", "")
            if last_active_str:
                try:
                    last_active = datetime.fromisoformat(last_active_str)
                    if datetime.now() - last_active > timedelta(minutes=self.TTL_MINUTES):
                        logger.info(f"[GroupCtx] 跳过过期群聊: {chat_id[:15]}...")
                        os.remove(filepath)  # 清理过期文件
                        return None
                except ValueError:
                    pass

            # 恢复到内存
            dq = deque(maxlen=self._max_messages)
            for m in messages_data[-self._max_messages:]:
                dq.append(m)

            self._groups[chat_id] = dq
            if last_active_str:
                try:
                    self._last_active[chat_id] = datetime.fromisoformat(last_active_str)
                except ValueError:
                    self._last_active[chat_id] = datetime.now()
            else:
                self._last_active[chat_id] = datetime.now()

            logger.info(
                f"[GroupCtx] 已加载群聊: {chat_id[:15]}... "
                f"（{len(dq)} 条消息）"
            )
            return chat_id

        except Exception as e:
            logger.warning(f"[GroupCtx] 加载文件 {os.path.basename(filepath)} 失败: {e}")
            return None

    def _load_all_from_disk(self):
        """启动时加载所有未过期的群聊文件"""
        if not os.path.isdir(self._storage_dir):
            return

        loaded = 0
        for fname in os.listdir(self._storage_dir):
            if fname.endswith(".json"):
                filepath = os.path.join(self._storage_dir, fname)
                if self._load_group(filepath):
                    loaded += 1

        if loaded > 0:
            logger.info(f"[GroupCtx] 从磁盘恢复了 {loaded} 个群聊的上下文")
        else:
            logger.info("[GroupCtx] 无历史群聊上下文（首次启动或全部过期）")

    def _delete_group_file(self, chat_id: str):
        """删除指定群聊的磁盘文件"""
        try:
            filepath = self._filepath(chat_id)
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass

    # ================================================================
    # 生命周期
    # ================================================================

    async def start(self):
        """启动定时清理"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        """停止定时清理"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None

    async def _cleanup_loop(self):
        """定期清理超时的群聊上下文"""
        while True:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL)
                self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    def _cleanup_expired(self):
        """清理超时未活跃的群聊（内存 + 磁盘）"""
        now = datetime.now()
        expired = []
        for chat_id, last_time in self._last_active.items():
            if now - last_time > timedelta(minutes=self.TTL_MINUTES):
                expired.append(chat_id)
        for chat_id in expired:
            del self._groups[chat_id]
            del self._last_active[chat_id]
            self._delete_group_file(chat_id)
            logger.info(f"[GroupCtx] 清理超时群聊: {chat_id[:15]}...")

    # ================================================================
    # 消息操作
    # ================================================================

    def add_message(self, chat_id: str, role: str, content: str):
        """向指定群聊的上下文添加一条消息（内存 + 磁盘）"""
        if not chat_id:
            return
        if chat_id not in self._groups:
            self._groups[chat_id] = deque(maxlen=self._max_messages)

        self._groups[chat_id].append({
            "role": role,
            "content": content,
            "time": datetime.now().isoformat(),
        })
        self._last_active[chat_id] = datetime.now()

        # 同步写入磁盘
        self._save_group(chat_id)

    def get_context(self, chat_id: str) -> list[dict]:
        """获取指定群聊的最近消息（不含 system prompt）"""
        if not chat_id or chat_id not in self._groups:
            return []
        return list(self._groups[chat_id])

    def get_context_injection(self, chat_id: str, max_recent: int = 10) -> str:
        """生成可注入 LLM 上下文的群聊历史摘要。

        Args:
            chat_id: 群聊 ID
            max_recent: 最多注入最近的 N 条消息

        Returns:
            格式化的历史文本，若为空则返回空字符串
        """
        if not chat_id or chat_id not in self._groups:
            return ""

        messages = list(self._groups[chat_id])
        if not messages:
            return ""

        # 只取最近 N 条
        recent = messages[-max_recent:]

        lines = ["**本群最近对话历史：**"]
        for m in recent:
            role_name = "用户" if m["role"] == "user" else "阿尔戈"
            content_preview = m["content"][:300]
            lines.append(f"- {role_name}: {content_preview}")

        return "\n".join(lines)

    def clear(self, chat_id: str = None):
        """清空指定群聊上下文（不指定则清空全部）"""
        if chat_id:
            self._groups.pop(chat_id, None)
            self._last_active.pop(chat_id, None)
            self._delete_group_file(chat_id)
        else:
            self._groups.clear()
            self._last_active.clear()
            # 清空全部磁盘文件
            if os.path.isdir(self._storage_dir):
                for fname in os.listdir(self._storage_dir):
                    if fname.endswith(".json"):
                        try:
                            os.remove(os.path.join(self._storage_dir, fname))
                        except Exception:
                            pass

    @property
    def group_count(self) -> int:
        return len(self._groups)


# 全局单例
_group_context: Optional[FeishuGroupContext] = None


def get_group_context() -> FeishuGroupContext:
    """获取群聊上下文单例"""
    global _group_context
    if _group_context is None:
        _group_context = FeishuGroupContext()
    return _group_context


# ================================================================
# 消息处理器工厂
# ================================================================

def create_message_handler(
    progress_callback: Optional[Callable[[str], Awaitable[None]]] = None,
):
    """创建飞书消息处理器：飞书消息 → Agent → 回复文本

    Args:
        progress_callback: 进度推送回调 async (text) -> None
                          用于在长任务执行期间主动推送阶段信息到飞书

    Returns:
        async function(sender_id: str, text: str, chat_id: str) -> str
    """
    # 确保清理循环已启动
    group_ctx = get_group_context()
    if group_ctx._cleanup_task is None:
        asyncio.create_task(group_ctx._cleanup_loop())

    async def handle_feishu_message(sender_id: str, text: str, chat_id: str = "", message_id: str = "") -> str:
        """飞书消息 → 命令检测 → Agent → 回复（含群聊上下文注入）"""
        import aiosqlite
        from database import DB_PATH
        from agent.context import ContextManager
        from agent.llm_client import LLMClient

        # ── 命令检测（不经过 Agent，直接返回）──
        command_result = await _try_handle_command(text)
        if command_result is not None:
            return command_result

        try:
            async with aiosqlite.connect(DB_PATH) as db:
                context_mgr = ContextManager(db)

                # 获取 system_prompt
                async with db.execute(
                    "SELECT value FROM settings WHERE key = ?", ("system_prompt",)
                ) as cursor:
                    row = await cursor.fetchone()
                    system_prompt = row[0] if row else "You are a helpful assistant."

                # ── Phase 5E: 群聊上下文注入 ──
                chat_history_text = ""
                if chat_id:
                    chat_history_text = group_ctx.get_context_injection(chat_id)

                # 构建上下文
                context = await context_mgr.build_context(system_prompt)

                # 注入群聊历史（在 system prompt 之后，用户消息之前）
                if chat_history_text:
                    context.append({
                        "role": "system",
                        "content": chat_history_text,
                    })

                context.append({
                    "role": "user",
                    "content": f"[来自飞书用户 {sender_id}]\n{text}"
                })

                # ── 将用户消息存入群聊上下文 ──
                if chat_id:
                    group_ctx.add_message(chat_id, "user", text)

                # 获取 LLM 配置
                async with db.execute("SELECT key, value FROM settings") as cursor:
                    rows = await cursor.fetchall()
                    llm_config = {row[0]: row[1] for row in rows}

                llm_client = LLMClient.from_config(llm_config)

                # ── Phase 5F: Agent 流式处理 + 动态进度推送 + 执行追踪 ──
                full_reply = ""
                trace_events: list[dict] = []  # 完整执行追踪（用于循环文件存储）
                pending_tool: str = ""          # 当前等待结果的工具名
                tool_count = 0
                tool_start_time = None

                import time as _time
                from agent.config import get_agent_config_int, get_agent_config_bool
                max_iter = await get_agent_config_int("agent_max_iterations", 200)
                deep = await get_agent_config_bool("agent_deep_thinking_default", False)
                web = await get_agent_config_bool("agent_web_search_default", True)

                async for event in llm_client.agent_stream(
                    context, max_iterations=max_iter,
                    deep_thinking=deep,
                    web_search_enabled=web,
                ):
                    # ── 记录事件到追踪 ──
                    trace_events.append(event.to_dict())

                    if event.type == "thinking":
                        # 思考过程：仅在第一个 thinking 事件时推送一次
                        if not pending_tool and tool_count == 0:
                            if progress_callback:
                                await progress_callback("🧠 正在思考...")

                    elif event.type == "tool_call":
                        tool_count += 1
                        pending_tool = event.tool
                        tool_start_time = _time.time()
                        # 人性化工具描述
                        desc = _tool_description(event.tool, event.tool_args)
                        if progress_callback:
                            await progress_callback(f"🔧 [{tool_count}] {desc}")

                    elif event.type == "tool_result":
                        elapsed = ""
                        if tool_start_time:
                            elapsed = f" ({_time.time() - tool_start_time:.1f}s)"
                        # 截断结果用于展示
                        result_preview = event.tool_result[:80].replace('\n', ' ')
                        status = "✅" if "失败" not in event.tool_result and "错误" not in event.tool_result else "❌"
                        if progress_callback:
                            await progress_callback(
                                f"   {status} {pending_tool or event.tool} → {result_preview}{elapsed}"
                            )
                        pending_tool = ""
                        tool_start_time = None

                    elif event.type == "content" and event.content:
                        full_reply += event.content

                    elif event.type == "error":
                        full_reply += f"\n[错误] {event.content}"
                        if progress_callback:
                            await progress_callback(f"❌ {event.content[:150]}")

                # ── 保存执行追踪到循环文件 ──
                try:
                    from feishu.execution_log import save_execution
                    save_execution({
                        "message_id": message_id,
                        "sender_id": sender_id,
                        "chat_id": chat_id,
                        "text": text[:500],
                        "reply": (full_reply or "")[:2000],
                        "tool_count": tool_count,
                        "events": trace_events,
                    })
                except Exception:
                    pass  # 存储失败不影响主流程

                reply = full_reply or "收到你的消息了，但没能生成回复 😅"

                # ── 将助手回复存入群聊上下文 ──
                if chat_id and reply:
                    group_ctx.add_message(chat_id, "assistant", reply)

                return reply

        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"处理消息时出错：{str(e)[:200]}"

    return handle_feishu_message


# ================================================================
# 命令系统（Phase 5C）
# ================================================================

async def _try_handle_command(text: str) -> Optional[str]:
    """检测并处理内置命令，返回 None 表示不是命令

    命令格式：
        /<cmd> [subcmd] [args...]
        阿尔戈 <cmd> [subcmd] [args...]
        @阿尔戈 <cmd> [subcmd] [args...]
    """
    import aiosqlite
    from database import DB_PATH

    t = text.strip()

    # 命令前缀匹配
    rest = None
    for prefix in ["/", "阿尔戈", "@阿尔戈"]:
        if t.startswith(prefix):
            rest = t[len(prefix):].strip()
            break

    if rest is None:
        return None

    if not rest:
        return _cmd_help()

    # 提取命令（第一个词，小写匹配）和参数（保留原样）
    parts = rest.split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    # /status — 进化状态
    if cmd in ("status", "状态", "s"):
        return await _cmd_status()

    # /tools — 工具清单
    if cmd in ("tools", "工具", "t"):
        return await _cmd_tools()

    # /goals — 目标进度
    if cmd in ("goals", "目标", "g"):
        return await _cmd_goals()

    # /diagnose — 自诊断
    if cmd in ("diagnose", "诊断", "d", "check", "体检"):
        return await _cmd_diagnose()

    # /memory — 记忆管理（含子命令）
    if cmd in ("memory", "记忆", "m"):
        return await _cmd_memory_dispatch(args)

    # /exec — 执行历史
    if cmd in ("exec", "执行记录", "history", "e"):
        return await _cmd_exec_history(args)

    # /help — 帮助
    if cmd in ("help", "帮助", "h", "?"):
        return _cmd_help()

    return None  # 不是已知命令，交给 Agent 处理


async def _cmd_status() -> str:
    """进化状态摘要"""
    try:
        from agent.goal_manager import get_goal_manager
        from agent.tools import get_tools
        from agent.memory import PersistentMemoryManager
        from agent.sandbox import get_snapshot_manager

        gm = get_goal_manager()
        goals = gm.list_goals()

        total = len(goals)
        active = sum(1 for g in goals if g.status == "active")
        completed = sum(1 for g in goals if g.status == "completed")

        mm = PersistentMemoryManager()
        memory_count = mm.count()

        tools = get_tools(web_search_enabled=False)
        tool_count = len(tools)

        mgr = get_snapshot_manager()
        snapshots = mgr.list_snapshots()
        snapshot_count = len(snapshots)

        lines = [
            "📊 **阿尔戈进化状态**",
            "",
            f"🧰 工具：{tool_count} 个",
            f"🧠 持久记忆：{memory_count} 条",
            f"🎯 目标进度：{completed}/{total} 已完成（{active} 活跃）",
            f"📸 沙盒快照：{snapshot_count} 个",
            f"🔗 飞书连接：🟢 已连接",
            "",
            "输入 /goals 查看目标详情",
            "输入 /tools 查看工具清单",
            "输入 /diagnose 运行自诊断",
        ]
        return "\n".join(lines)

    except Exception as e:
        return f"获取状态失败：{e}"


async def _cmd_tools() -> str:
    """工具清单"""
    try:
        from agent.tools import get_tools
        tools = get_tools(web_search_enabled=False)
        # 按类别分组
        categories: dict[str, list] = {}
        for t in tools:
            cat = getattr(t, 'category', 'other') or 'other'
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(t.name)

        lines = ["🔧 **工具清单**", ""]
        for cat, names in sorted(categories.items()):
            lines.append(f"▸ {cat}（{len(names)}）:")
            for n in names:
                lines.append(f"    • {n}")
            lines.append("")

        lines.append(f"共 {len(tools)} 个工具")
        return "\n".join(lines)

    except Exception as e:
        return f"获取工具清单失败：{e}"


async def _cmd_goals() -> str:
    """目标进度"""
    try:
        from agent.goal_manager import get_goal_manager
        gm = get_goal_manager()
        goals = gm.list_goals()

        if not goals:
            return "🎯 暂无进化目标。输入 /help 了解如何创建目标。"

        lines = ["🎯 **进化目标**", ""]
        for g in goals:
            status_icon = {
                "active": "🟢", "paused": "🟡",
                "completed": "✅", "abandoned": "❌"
            }.get(g.status, "❓")

            desc = g.description[:80] if g.description else ""
            priority = "★" * g.priority

            lines.append(
                f"{status_icon} {g.title}  [{priority}]"
            )
            if desc:
                lines.append(f"     {desc}")

            for m in g.milestones:
                m_status = {
                    "pending": "⬜", "in_progress": "🔄", "completed": "✅"
                }.get(m.status, "⬜")
                progress = m.progress if hasattr(m, 'progress') else 0
                lines.append(
                    f"     {m_status} {m.title} ({progress}%)"
                )
            lines.append("")

        lines.append("输入 /help 查看所有命令")
        return "\n".join(lines)

    except Exception as e:
        return f"获取目标失败：{e}"


async def _cmd_diagnose() -> str:
    """自诊断"""
    import os
    import sys

    lines = ["🩺 **自诊断报告**", ""]

    try:
        # 磁盘空间
        stat = os.statvfs(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        free_gb = stat.f_bavail * stat.f_frsize / (1024**3)
        total_gb = stat.f_blocks * stat.f_frsize / (1024**3)
        lines.append(f"💾 磁盘: {free_gb:.1f}G / {total_gb:.1f}G 可用")

        # Python 版本
        lines.append(f"🐍 Python: {sys.version.split()[0]}")

        # 记忆数量
        try:
            from agent.memory import PersistentMemoryManager
            mm = PersistentMemoryManager()
            lines.append(f"🧠 持久记忆: {mm.count()} 条")
        except Exception:
            lines.append("🧠 持久记忆: 获取失败")

        # 目标
        try:
            from agent.goal_manager import get_goal_manager
            gm = get_goal_manager()
            lines.append(f"🎯 目标: {len(gm.list_goals())} 个")
        except Exception:
            lines.append("🎯 目标: 获取失败")

        # 快照
        snapshot_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "snapshots"
        )
        if os.path.exists(snapshot_dir):
            snapshots = [f for f in os.listdir(snapshot_dir) if f.endswith(".tar.gz")]
            lines.append(f"📸 快照: {len(snapshots)} 个")
        else:
            lines.append("📸 快照: 0 个")

        # Git 状态
        import subprocess
        try:
            result = subprocess.run(
                ["git", "status", "--short"], capture_output=True, text=True,
                cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            )
            if result.stdout.strip():
                lines.append(f"📝 Git: 有未提交变更")
            else:
                lines.append(f"📝 Git: 干净")
        except Exception:
            lines.append("📝 Git: 检查失败")

        # 飞书
        try:
            from feishu import is_bot_connected
            connected = is_bot_connected()
            lines.append(f"🔗 飞书: {'🟢 已连接' if connected else '🔴 未连接'}")
        except Exception:
            lines.append("🔗 飞书: 状态未知")

        lines.append("")
        lines.append("✅ 核心模块全部正常")

    except Exception as e:
        lines.append(f"⚠️ 诊断异常: {e}")

    return "\n".join(lines)


# ================================================================
# 记忆管理命令（/memory 子命令系统）
# ================================================================

async def _cmd_memory_dispatch(args: str) -> str:
    """/memory 子命令调度

    用法:
        /memory                  → 最近记忆
        /memory add <内容>       → 添加记忆（自动提取 #标签 和 importance=N）
        /memory search <查询>    → 搜索记忆
        /memory delete <ID>      → 删除记忆
        /memory detail <ID>      → 查看记忆详情
        /memory tags             → 标签列表
        /memory categories       → 类别列表
        /memory stats            → 统计概览
        /memory clean            → 清空全部记忆（需二次确认）
    """
    if not args:
        return await _cmd_memory_list()

    parts = args.split(maxsplit=1)
    subcmd = parts[0].lower()
    sub_args = parts[1] if len(parts) > 1 else ""

    try:
        if subcmd in ("add", "添加", "记", "a"):
            return await _cmd_memory_add(sub_args)
        elif subcmd in ("search", "搜索", "查", "find", "s"):
            return await _cmd_memory_search(sub_args)
        elif subcmd in ("delete", "删除", "del", "rm", "d"):
            return await _cmd_memory_delete(sub_args)
        elif subcmd in ("detail", "详情", "show", "view", "v"):
            return await _cmd_memory_detail(sub_args)
        elif subcmd in ("tags", "标签", "tag"):
            return await _cmd_memory_tags()
        elif subcmd in ("categories", "类别", "分类", "cats", "c"):
            return await _cmd_memory_categories()
        elif subcmd in ("stats", "统计", "stat"):
            return await _cmd_memory_stats()
        elif subcmd in ("clean", "清空", "clear", "wipe"):
            return await _cmd_memory_clean(sub_args)
        else:
            # 未知子命令 → 当作搜索关键词
            return await _cmd_memory_search(args)
    except Exception as e:
        return f"❌ 记忆操作失败：{e}"


async def _cmd_memory_list() -> str:
    """列出最近记忆"""
    from agent.memory import PersistentMemoryManager
    mm = PersistentMemoryManager()
    memories = mm.list_recent(limit=8)

    if not memories:
        return "🧠 暂无持久记忆。\n\n发送 `/memory add 内容` 开始记录。"

    lines = ["🧠 **持久记忆**（最近 8 条）", ""]
    for i, m in enumerate(memories, 1):
        stars = "★" * m.importance
        tags = f" `#{' #'.join(m.tags)}`" if m.tags else ""
        info = m.content[:120]
        lines.append(f"{i}. {stars} `{m.id}` [{m.category}]{tags}")
        lines.append(f"   {info}")
        lines.append("")

    lines.append("---")
    lines.append("`/memory stats` 统计 | `search <词>` 搜索 | `add <内容>` 添加 | `delete <ID>` 删除")
    return "\n".join(lines)


async def _cmd_memory_add(args: str) -> str:
    """添加持久记忆。格式：/memory add <内容> [#标签] [importance=N]"""
    import re

    if not args:
        return (
            "📝 **添加记忆**\n\n"
            "格式：`/memory add <内容> [#标签1] [#标签2] [importance=3]`\n\n"
            "示例：\n"
            "• `/memory add 用户喜欢深色主题 #偏好 #UI importance=5`\n"
            "• `/memory add Phase 4 飞书集成已完成 #项目`"
        )

    # 提取 importance
    importance = 3
    imp_match = re.search(r'\bimportance\s*=\s*(\d)\b', args, re.IGNORECASE)
    if imp_match:
        importance = max(1, min(5, int(imp_match.group(1))))
        args = args[:imp_match.start()] + args[imp_match.end():]
        args = args.strip()

    # 提取 #标签
    tags = re.findall(r'#(\w+)', args)
    content = re.sub(r'#\w+', '', args).strip()

    if not content:
        return "❌ 记忆内容不能为空。用法：`/memory add <内容>`"

    from agent.memory import PersistentMemoryManager
    mm = PersistentMemoryManager()
    entry_id = mm.add_memory(content, importance=importance, tags=tags)

    stars = "★" * importance
    tags_str = f" #{' #'.join(tags)}" if tags else ""
    return (
        f"✅ 记忆已保存！\n\n"
        f"   {stars} `{entry_id}`\n"
        f"   {content}{tags_str}\n\n"
        f"`/memory detail {entry_id}` 查看详情 | `/memory search` 搜索"
    )


async def _cmd_memory_search(args: str) -> str:
    """搜索记忆"""
    if not args:
        return "🔍 用法：`/memory search <关键词>`\n\n也支持：`/memory search cat=learned` `tag=偏好` `imp>=4`"

    # 解析高级搜索语法
    query = args
    category = None
    tag_filter = None
    min_importance = 0

    import re
    cat_match = re.search(r'\bcat(?:egory)?\s*=\s*(\w+)', query, re.IGNORECASE)
    if cat_match:
        category = cat_match.group(1)
        query = query[:cat_match.start()] + query[cat_match.end():]
        query = query.strip()

    tag_match = re.search(r'\btag\s*=\s*(\w+)', query, re.IGNORECASE)
    if tag_match:
        tag_filter = tag_match.group(1)
        query = query[:tag_match.start()] + query[tag_match.end():]
        query = query.strip()

    imp_match = re.search(r'\bimp\s*>=\s*(\d)\b', query, re.IGNORECASE)
    if imp_match:
        min_importance = int(imp_match.group(1))
        query = query[:imp_match.start()] + query[imp_match.end():]
        query = query.strip()

    from agent.memory import PersistentMemoryManager
    mm = PersistentMemoryManager()

    results = mm.search_memory(
        query=query,
        category=category,
        tags=[tag_filter] if tag_filter else None,
        min_importance=min_importance,
        limit=8,
    )

    if not results:
        return f"🔍 未找到匹配「{args}」的记忆。"

    lines = [f"🔍 **记忆搜索：{args}**  （{len(results)} 条）", ""]
    for i, m in enumerate(results, 1):
        stars = "★" * m.importance
        tags = f" `#{' #'.join(m.tags)}`" if m.tags else ""
        info = m.content[:100]
        lines.append(f"{i}. {stars} `{m.id}` [{m.category}]{tags}")
        lines.append(f"   {info}")
        lines.append("")

    lines.append(f"`/memory detail <ID>` 查看完整内容 | `delete <ID>` 删除")
    return "\n".join(lines)


async def _cmd_memory_delete(args: str) -> str:
    """删除记忆"""
    if not args:
        return "🗑️ 用法：`/memory delete <记忆ID>`\n\n先 `/memory` 查看记忆列表获取 ID。"

    entry_id = args.strip().split()[0]  # 取第一个词作为 ID

    from agent.memory import PersistentMemoryManager
    mm = PersistentMemoryManager()

    existing = mm.get_memory(entry_id)
    if not existing:
        return f"❌ 未找到记忆 `{entry_id}`。用 `/memory` 查看可用 ID。"

    if mm.delete_memory(entry_id):
        return f"🗑️ 已删除记忆 `{entry_id}`：{existing.content[:80]}..."
    return "❌ 删除失败"


async def _cmd_memory_detail(args: str) -> str:
    """查看记忆详情"""
    if not args:
        return "🔍 用法：`/memory detail <记忆ID>`"

    entry_id = args.strip().split()[0]

    from agent.memory import PersistentMemoryManager
    mm = PersistentMemoryManager()

    entry = mm.get_memory(entry_id)
    if not entry:
        return f"❌ 未找到记忆 `{entry_id}`"

    stars = "★" * entry.importance
    tags = f" #{' #'.join(entry.tags)}" if entry.tags else ""

    return "\n".join([
        f"🧠 **记忆详情**",
        "",
        f"   ID: `{entry.id}`",
        f"   重要性: {stars} ({entry.importance}/5)",
        f"   类别: `{entry.category}`",
        f"   标签: {tags if tags else '（无）'}",
        f"   创建时间: {entry.timestamp[:19]}",
        f"   来源会话: {entry.source_session or '（未知）'}",
        "",
        f"   {entry.content}",
        "",
        f"`/memory delete {entry.id}` 删除 | `search` 搜索",
    ])


async def _cmd_memory_tags() -> str:
    """列出所有标签"""
    from agent.memory import PersistentMemoryManager
    mm = PersistentMemoryManager()
    tags = mm.get_all_tags()

    if not tags:
        return "🏷️ 暂无标签。添加记忆时使用 `#标签名` 创建。"

    stats = mm.get_stats()
    tag_counts = stats.get("tags", {})

    lines = [f"🏷️ **记忆标签**（共 {len(tags)} 个）", ""]
    for tag in sorted(tags):
        count = tag_counts.get(tag, 0)
        lines.append(f"   `#{tag}` — {count} 条")

    lines.append("")
    lines.append("`/memory search tag=<标签>` 搜索指定标签")
    return "\n".join(lines)


async def _cmd_memory_categories() -> str:
    """列出所有类别"""
    from agent.memory import PersistentMemoryManager
    mm = PersistentMemoryManager()
    cats = mm.get_all_categories()

    if not cats:
        return "📂 暂无类别。"

    stats = mm.get_stats()
    cat_counts = stats.get("categories", {})

    lines = [f"📂 **记忆类别**（共 {len(cats)} 个）", ""]
    for cat in sorted(cats):
        count = cat_counts.get(cat, 0)
        lines.append(f"   `{cat}` — {count} 条")

    lines.append("")
    lines.append("`/memory search cat=<类别>` 按类别搜索")
    return "\n".join(lines)


async def _cmd_memory_stats() -> str:
    """记忆统计"""
    from agent.memory import PersistentMemoryManager
    mm = PersistentMemoryManager()
    s = mm.get_stats()

    if s["total"] == 0:
        return "🧠 记忆库为空。"

    lines = [
        "📊 **记忆统计**",
        "",
        f"   总数: {s['total']} 条",
        f"   平均重要性: {s['avg_importance']}/5",
        f"   最早: {s['oldest']}",
        f"   最新: {s['newest']}",
        "",
    ]

    if s["categories"]:
        lines.append("📂 **类别分布**")
        for cat, count in sorted(s["categories"].items(), key=lambda x: x[1], reverse=True):
            bar = "█" * min(count, 20)
            lines.append(f"   `{cat}`: {bar} {count}")
        lines.append("")

    if s["tags"]:
        lines.append("🏷️ **热门标签**")
        for tag, count in s["tags"]:
            lines.append(f"   `#{tag}`: {count} 条")
        lines.append("")

    lines.append("`/memory` 查看记忆 | `search` 搜索 | `add` 添加")
    return "\n".join(lines)


async def _cmd_memory_clean(args: str = "") -> str:
    """清空全部记忆（需二次确认）"""
    if args.strip().lower() in ("confirm", "确认", "yes", "y"):
        from agent.memory import PersistentMemoryManager
        mm = PersistentMemoryManager()
        count = mm.count()
        if count == 0:
            return "🧠 记忆库已经是空的。"
        mm.store.clear()
        return f"🗑️ 已清空全部 {count} 条记忆。"

    from agent.memory import PersistentMemoryManager
    mm = PersistentMemoryManager()
    count = mm.count()
    return (
        f"⚠️ **清空全部 {count} 条记忆？**\n\n"
        "此操作不可撤销！发送 `/memory clean confirm` 确认清空。\n\n"
        "`/memory stats` 查看当前数据量"
    )


async def _cmd_exec_history(args: str) -> str:
    """查看执行记录

    /exec          → 最近 5 条摘要
    /exec <N>      → 第 N 条记录详情（含完整事件流）
    /exec stats    → 存储统计
    """
    from feishu.execution_log import list_executions, get_execution, get_stats

    if args.strip().lower() in ("stats", "统计", "stat"):
        s = get_stats()
        return "\n".join([
            "📋 **执行记录存储**",
            "",
            f"   文件数: {s['file_count']}/{s['max_files']}",
            f"   存储大小: {s['total_size_kb']} KB",
            f"   目录: `{s['dir']}`",
        ])

    # 查看特定记录详情
    try:
        record_id = int(args.strip())
        record = get_execution(record_id)
        if not record:
            return f"❌ 未找到第 {record_id} 条记录。"

        events_lines = []
        for ev in record.get("events", []):
            t = ev.get("type", "?")
            if t == "thinking":
                events_lines.append(f"   🧠 思考中...")
            elif t == "tool_call":
                events_lines.append(f"   🔧 调用 {ev.get('tool', '?')}")
            elif t == "tool_result":
                preview = (ev.get("tool_result", "") or "")[:60].replace('\n', ' ')
                events_lines.append(f"   ✅ {ev.get('tool', '?')} → {preview}")
            elif t == "content":
                events_lines.append(f"   💬 {ev.get('content', '')[:80]}")
            elif t == "error":
                events_lines.append(f"   ❌ {ev.get('content', '')[:80]}")

        return "\n".join([
            f"📋 **执行记录 #{record['id']}**",
            "",
            f"   时间: {record.get('timestamp', '?')[:19]}",
            f"   用户: {record.get('sender_id', '?')[:20]}...",
            f"   消息: {record.get('text', '?')[:100]}",
            f"   工具调用: {record.get('tool_count', 0)} 次",
            f"   回复: {(record.get('reply', '') or '')[:150]}",
            "",
            "**事件流：**",
        ] + (events_lines or ["   （无事件）"]) + [
            "",
            f"`/exec` 返回列表",
        ])
    except ValueError:
        pass  # 不是数字，继续看列表

    # 列表模式
    records = list_executions(limit=5)
    if not records:
        return "📋 暂无执行记录。在飞书 @阿尔戈 发一条消息后就会出现。"

    lines = ["📋 **最近执行记录**", ""]
    for r in records:
        ts = r.get("timestamp", "")[11:19] if r.get("timestamp") else "?"
        text_preview = (r.get("text", "") or "")[:40]
        tools = r.get("tool_count", 0)
        lines.append(
            f"   `#{r['id']:02d}` {ts} | 🔧×{tools} | {text_preview}"
        )

    lines.append("")
    lines.append("`/exec <编号>` 查看详情 | `/exec stats` 存储统计")
    return "\n".join(lines)


def _cmd_help() -> str:
    """帮助"""
    return "\n".join([
        "🤖 **阿尔戈命令**",
        "",
        "命令以 `/` 开头，或在 `@阿尔戈` 后接命令",
        "",
        "📊 `/status`     — 进化状态摘要",
        "🔧 `/tools`      — 工具清单",
        "🎯 `/goals`      — 目标进度",
        "🩺 `/diagnose`   — 自诊断报告",
        "📋 `/exec`       — 查看最近执行记录",
        "   `/exec <N>`   — 查看第 N 条记录的详情",
        "❓ `/help`       — 本帮助",
        "",
        "🧠 **记忆管理**",
        "`/memory`            — 最近记忆",
        "`/memory add <内容>`  — 添加（支持 #标签 importance=N）",
        "`/memory search <词>` — 搜索",
        "`/memory delete <ID>` — 删除",
        "`/memory tags`       — 标签列表",
        "`/memory stats`      — 统计",
        "",
        "💬 直接发送消息进入 AI 对话。",
    ])


# ================================================================
# 工具描述（人性化）
# ================================================================

def _fname(path: str) -> str:
    """从路径中提取文件名"""
    return path.split("/")[-1] if path else ""


def _tool_description(tool_name: str, args: dict) -> str:
    """将工具调用转换为人性化描述"""
    descriptions = {
        "read_file": lambda a: f"读取 {_fname(a.get('path', ''))}",
        "write_file": lambda a: f"写入 {_fname(a.get('path', ''))}",
        "edit_file": lambda a: f"编辑 {_fname(a.get('path', ''))}",
        "list_directory": lambda a: f"浏览目录 {_fname(a.get('path', ''))}",
        "run_command": lambda a: f"执行 {a.get('command', '')[:50]}",
        "web_search": lambda a: f"搜索「{a.get('query', '')[:40]}」",
        "create_snapshot": lambda a: f"创建快照 {a.get('name', '')[:30]}",
        "restore_snapshot": lambda a: f"恢复快照 {a.get('snapshot_id', '')[:20]}",
        "remember": lambda a: f"记忆: {a.get('key_info', '')[:50]}...",
        "recall_memory": lambda a: f"回忆「{a.get('query', '')[:40]}」",
        "create_goal": lambda a: f"新建目标: {a.get('title', '')[:40]}",
        "create_sub_agent": lambda a: f"创建子Agent: {a.get('name', '')}",
        "invoke_sub_agent": lambda a: f"调用子Agent: {a.get('agent_name', '')}",
        "add_tool_to_self": lambda a: f"安装新工具: {a.get('tool_name', '')}",
        "git_commit_evolution": lambda a: f"Git 提交: {a.get('message', '')[:50]}",
        "quality_gate_check": lambda a: f"质量检查: {a.get('operation', '')}",
    }

    fn = descriptions.get(tool_name)
    if fn:
        return fn(args)
    return f"调用 {tool_name}"
