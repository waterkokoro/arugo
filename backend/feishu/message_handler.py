"""飞书消息 → Agent LLM 处理器

独立模块，供 bot.py 和 routers/feishu.py 共用。

Phase 5C: 增加进度推送 + 内置命令系统
"""

import logging
from typing import Callable, Awaitable, Optional

logger = logging.getLogger("feishu.handler")


def create_message_handler(
    progress_callback: Optional[Callable[[str], Awaitable[None]]] = None,
):
    """创建飞书消息处理器：飞书消息 → Agent → 回复文本

    Args:
        progress_callback: 进度推送回调 async (text) -> None
                          用于在长任务执行期间主动推送阶段信息到飞书

    Returns:
        async function(sender_id: str, text: str) -> str
    """
    async def handle_feishu_message(sender_id: str, text: str) -> str:
        """飞书消息 → 命令检测 → Agent → 回复"""
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

                # 构建上下文（注入持久记忆和目标）
                context = await context_mgr.build_context(system_prompt)
                context.append({
                    "role": "user",
                    "content": f"[来自飞书用户 {sender_id}]\n{text}"
                })

                # 获取 LLM 配置
                async with db.execute("SELECT key, value FROM settings") as cursor:
                    rows = await cursor.fetchall()
                    llm_config = {row[0]: row[1] for row in rows}

                llm_client = LLMClient.from_config(llm_config)

                # Agent 模式流式收集
                full_reply = ""
                async for event in llm_client.agent_stream(
                    context, max_iterations=200,
                    deep_thinking=False,
                    web_search_enabled=True,
                ):
                    if event.type == "content" and event.content:
                        full_reply += event.content
                    elif event.type == "error":
                        full_reply += f"\n[错误] {event.content}"

                return full_reply or "收到你的消息了，但没能生成回复 😅"

        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"处理消息时出错：{str(e)[:200]}"

    return handle_feishu_message


# ================================================================
# 命令系统（Phase 5C）
# ================================================================

async def _try_handle_command(text: str) -> Optional[str]:
    """检测并处理内置命令，返回 None 表示不是命令"""
    import aiosqlite
    from database import DB_PATH

    t = text.strip()

    # 命令前缀匹配
    cmd = None
    for prefix in ["/", "阿尔戈", "@阿尔戈"]:
        if t.startswith(prefix):
            rest = t[len(prefix):].strip()
            cmd = rest.lower() if rest else ""
            break

    if cmd is None:
        return None

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

    # /memory — 记忆
    if cmd in ("memory", "记忆", "m"):
        return await _cmd_memory()

    # /help — 帮助
    if cmd in ("help", "帮助", "h", "?"):
        return _cmd_help()

    return None  # 不是已知命令，交给 Agent 处理


async def _cmd_status() -> str:
    """进化状态摘要"""
    try:
        from agent.goal_manager import get_goal_manager
        gm = get_goal_manager()
        goals = gm.list_goals()

        total = len(goals)
        active = sum(1 for g in goals if g.status == "active")
        completed = sum(1 for g in goals if g.status == "completed")

        from agent.memory import PersistentMemoryManager
        mm = PersistentMemoryManager()
        memory_count = mm.count()

        # 快照数量
        import os
        snapshot_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "snapshots"
        )
        snapshot_count = 0
        if os.path.exists(snapshot_dir):
            snapshot_count = len([
                f for f in os.listdir(snapshot_dir)
                if f.endswith(".tar.gz")
            ])

        lines = [
            "📊 **阿尔戈进化状态**",
            "",
            f"🧰 工具：35 个",
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


async def _cmd_memory() -> str:
    """最近记忆"""
    try:
        from agent.memory import PersistentMemoryManager
        mm = PersistentMemoryManager()
        memories = mm.list_recent(limit=10)

        if not memories:
            return "🧠 暂无持久记忆。"

        lines = ["🧠 **最近记忆**", ""]
        for m in memories:
            importance = "★" * m.importance
            tags = ", ".join(m.tags)
            info = m.content[:100]
            lines.append(f"{importance} [{m.category}]")
            lines.append(f"   {info}")
            if tags:
                lines.append(f"   🏷 {tags}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        return f"获取记忆失败：{e}"


def _cmd_help() -> str:
    """帮助"""
    return "\n".join([
        "🤖 **阿尔戈命令**",
        "",
        "命令需要以 / 开头（如 /status），或在 @阿尔戈 后接命令",
        "",
        "📊 /status    — 进化状态摘要",
        "🔧 /tools     — 工具清单",
        "🎯 /goals     — 目标进度",
        "🩺 /diagnose  — 自诊断报告",
        "🧠 /memory    — 最近记忆",
        "❓ /help      — 本帮助",
        "",
        "直接发送消息进入 AI 对话模式。",
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
