"""飞书机器人 — WebSocket 收 + REST API 发

架构决策（基于飞书 3 秒超时约束）：
    WebSocket 长连接   →  仅用于接收消息（3秒内推入队列即返回）
    REST API           →  用于发送回复（无超时限制，支持长文本分段）

参考:
    https://open.feishu.cn/document/server-docs/im-v1/message/reply
    https://github.com/larksuite/oapi-sdk-python
"""

import asyncio
import json
import logging
import os
import re
from typing import Optional, Callable, Awaitable

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    ReplyMessageRequest, ReplyMessageRequestBody,
    CreateMessageReactionRequest, CreateMessageReactionRequestBody,
)
from lark_oapi.api.im.v1 import Reaction as ReactionType

from .config import FeishuConfig

logger = logging.getLogger("feishu_bot")

# 跨进程状态文件（解决 uvicorn reload 多进程导致单例不共享）
_STATUS_FILE = "/tmp/arugo_feishu_status.json"


def _write_status(connected: bool, app_id: str = ""):
    """写入状态文件（供 API 端点跨进程读取）"""
    try:
        with open(_STATUS_FILE, "w") as f:
            json.dump({"connected": connected, "app_id": app_id[:10]}, f)
    except Exception:
        pass


def _read_status() -> dict:
    """读取状态文件"""
    try:
        with open(_STATUS_FILE) as f:
            return json.load(f)
    except Exception:
        return {"connected": False, "app_id": ""}


class FeishuBot:
    """飞书机器人管理器

    架构:
        ┌─────────────┐     ┌──────────────┐     ┌───────────┐
        │ WebSocket    │ ──▶ │ asyncio      │ ──▶ │ Agent     │
        │ (只收消息)   │     │ Queue (解耦) │     │ LLM 处理  │
        └─────────────┘     └──────────────┘     └─────┬─────┘
                                                       │
        ┌─────────────┐                               │
        │ REST API     │ ◀─────────────────────────────┘
        │ (独立发送)   │
        └─────────────┘
    """

    def __init__(self, config: FeishuConfig):
        self.config = config
        self._channel = None          # WebSocket channel（只收）
        self._client: Optional[lark.Client] = None  # REST client（只发）
        self._running = False
        self._message_queue: asyncio.Queue = None   # 延迟创建，从 DB 读取容量
        self._worker_task: Optional[asyncio.Task] = None
        # 消息处理器工厂: (sender_id, text, progress_callback) -> reply
        self._handler_factory: Optional[Callable] = None

    # ================================================================
    # 公共接口
    # ================================================================

    @property
    def is_running(self) -> bool:
        return self._running

    def set_handler_factory(self, factory):
        """设置消息处理器工厂: 返回 async (sender_id, text, progress_callback) -> reply_text"""
        self._handler_factory = factory

    async def connect(self):
        """建立 WebSocket + 启动后台 Worker"""
        if not self.config.enabled:
            logger.info("[FeishuBot] 未启用，跳过")
            return
        if not self.config.app_id or not self.config.app_secret:
            logger.warning("[FeishuBot] 缺少 App ID/Secret，跳过")
            return

        # 从 DB 读取队列容量和分段大小
        from agent.config import get_agent_config_int
        queue_size = await get_agent_config_int("feishu_queue_maxsize", 100)
        self._chunk_size = await get_agent_config_int("feishu_text_chunk_size", 15000)
        self._message_queue = asyncio.Queue(maxsize=queue_size)
        logger.info(f"[FeishuBot] 消息队列容量: {queue_size}, 分段大小: {self._chunk_size}")

        from lark_oapi.channel import FeishuChannel

        # ── REST API client（独立发送回复）──
        self._client = (
            lark.Client.builder()
            .app_id(self.config.app_id)
            .app_secret(self.config.app_secret)
            .build()
        )

        # ── WebSocket channel（只接收消息）──
        self._channel = FeishuChannel(
            app_id=self.config.app_id,
            app_secret=self.config.app_secret,
        )

        self._register_handlers()
        self._running = True

        # 启动后台消息处理 Worker
        self._worker_task = asyncio.create_task(self._message_worker())

        # 使用 start_background（异步友好），不阻塞事件循环
        logger.info("[FeishuBot] 正在建立 WebSocket 长连接...")
        try:
            await self._channel.start_background(timeout=15.0)
            _write_status(True, self.config.app_id)
            logger.info("[FeishuBot] ✅ WebSocket 已连接，等待消息...")
        except asyncio.TimeoutError:
            logger.warning("[FeishuBot] 连接超时（15s），可能稍后连上")
        except Exception as e:
            self._running = False
            _write_status(False)
            logger.error(f"[FeishuBot] 连接失败: {e}")
            raise

    async def stop(self):
        """断开连接，停止 Worker"""
        self._running = False
        _write_status(False)
        if self._worker_task:
            self._worker_task.cancel()
            self._worker_task = None
        if self._channel:
            try:
                await self._channel.stop_background()
            except Exception:
                pass
            try:
                await self._channel.disconnect()
            except Exception:
                pass
        logger.info("[FeishuBot] 已断开")

    # ================================================================
    # WebSocket 事件处理（必须在 3 秒内返回！）
    # ================================================================

    def _register_handlers(self):
        channel = self._channel

        async def on_message(msg):
            """收到飞书消息 → 快速提取 → 推入队列 → 3秒内返回"""
            try:
                # 提取文本
                text = self._extract_text(msg)
                if not text:
                    return

                # 提取 message_id（用于 REST API 回复）
                message_id = self._extract_message_id(msg)
                sender_id = self._extract_sender_id(msg)
                chat_id = self._extract_chat_id(msg)

                logger.info(
                    f"[FeishuBot] 收到: sender={sender_id[:20]}..., "
                    f"msg={message_id[:10]}..., chat={chat_id[:10]}..., text={text[:60]}..."
                )

                if not message_id:
                    logger.warning("[FeishuBot] 无法获取 message_id，无法回复")
                    return

                # 推入队列（非阻塞；队列满了丢弃并告知用户）
                try:
                    self._message_queue.put_nowait({
                        "message_id": message_id,
                        "sender_id": sender_id,
                        "chat_id": chat_id,
                        "text": text,
                    })
                except asyncio.QueueFull:
                    logger.warning("[FeishuBot] 队列已满，丢弃消息")
                    await self._reply_via_rest(message_id, "消息太多了，请稍后再试～")
                    return

                # 给用户消息添加表情回复（替代文字"收到，正在思考..."）
                await self._add_reaction(message_id)

            except Exception as e:
                logger.error(f"[FeishuBot] on_message 异常: {e}", exc_info=True)

        channel.on("message", on_message)
        logger.info("[FeishuBot] 事件处理器已注册")

    # ================================================================
    # 后台 Worker：Agent LLM 处理 + REST API 回复
    # ================================================================

    async def _message_worker(self):
        """后台循环：从队列取消息 → Agent 处理（含进度推送）→ REST 回复"""
        logger.info("[FeishuBot] Worker 已启动")
        while self._running:
            try:
                # 等待消息（1 秒超时，便于检查 _running）
                msg = await asyncio.wait_for(self._message_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            message_id = msg.get("message_id", "")
            sender_id = msg.get("sender_id", "")
            chat_id = msg.get("chat_id", "")
            text = msg.get("text", "")

            try:
                if self._handler_factory:
                    # 飞书端不推送中间过程（thinking / tool_call / tool_result）
                    # progress_callback 传 None，handler 内部分支自动跳过
                    handler = self._handler_factory(None)
                    reply = await handler(sender_id, text, chat_id, message_id)
                else:
                    reply = "机器人还未配置消息处理器。"

                await self._reply_via_rest(message_id, reply or "收到你的消息了 😊")

            except Exception as e:
                logger.error(f"[FeishuBot] Worker 处理失败: {e}", exc_info=True)
                await self._reply_via_rest(
                    message_id, f"处理出错了：{str(e)[:200]}"
                )

        logger.info("[FeishuBot] Worker 已停止")

    # ================================================================
    # REST API 发送
    # ================================================================

    async def _add_reaction(self, message_id: str, emoji_type: str = "Typing"):
        """给消息添加表情回复（替代"收到，正在思考..."文字）"""
        if not self._client or not message_id:
            return
        try:
            reaction = ReactionType.builder().emoji_type(emoji_type).build()
            body = CreateMessageReactionRequestBody.builder().reaction_type(reaction).build()
            request = (
                CreateMessageReactionRequest.builder()
                .message_id(message_id)
                .request_body(body)
                .build()
            )
            response = await self._client.im.v1.message_reaction.acreate(request)
            if not response.success():
                logger.warning(
                    f"[FeishuBot] 表情回复失败: code={response.code}, msg={response.msg}"
                )
        except Exception as e:
            logger.warning(f"[FeishuBot] 表情回复异常: {e}")

    async def _reply_via_rest(self, message_id: str, text: str):
        """通过飞书 REST API 回复消息，使用 Markdown 交互卡片"""
        if not self._client or not message_id:
            return

        # Phase 5D: 飞书卡片不支持 LaTeX / 注脚 / HTML，预处理转换
        text = self._sanitize_for_feishu(text)

        chunks = self._split_markdown(text)
        for i, chunk in enumerate(chunks):
            prefix = f"**[{i+1}/{len(chunks)}]**\n" if len(chunks) > 1 else ""
            try:
                content = json.dumps({
                    "schema": "2.0",
                    "config": {"enable_forward": True},
                    "body": {
                        "elements": [
                            {"tag": "markdown", "content": prefix + chunk}
                        ]
                    }
                })
                request = (
                    ReplyMessageRequest.builder()
                    .message_id(message_id)
                    .request_body(
                        ReplyMessageRequestBody.builder()
                        .msg_type("interactive")
                        .content(content)
                        .build()
                    )
                    .build()
                )
                response = await self._client.im.v1.message.areply(request)
                if not response.success():
                    logger.error(
                        f"[FeishuBot] REST 回复失败: code={response.code}, "
                        f"msg={response.msg}"
                    )
            except Exception as e:
                logger.error(f"[FeishuBot] REST 回复异常: {e}")

    # ================================================================
    # 消息字段提取（兼容多种属性名）
    # ================================================================

    @staticmethod
    def _extract_text(msg) -> str:
        """提取消息文本"""
        text = getattr(msg, 'content_text', None)
        if not text:
            text = getattr(msg, 'text', '')
        if not text:
            # content 可能是 JSON 字符串
            content = getattr(msg, 'content', '')
            if content:
                try:
                    obj = json.loads(content) if isinstance(content, str) else content
                    text = obj.get('text', '')
                except (json.JSONDecodeError, TypeError):
                    text = ''
        text = str(text).strip() if text else ''
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        return text[:8000]

    @staticmethod
    def _extract_message_id(msg) -> str:
        """提取 message_id（用于 REST API 回复）"""
        # 尝试多种可能的属性路径
        for attr in ['message_id', 'id', 'msg_id']:
            val = getattr(msg, attr, None)
            if val:
                return str(val)

        # 尝试嵌套: msg.event.message.message_id
        event = getattr(msg, 'event', None)
        if event:
            message = getattr(event, 'message', None)
            if message:
                mid = getattr(message, 'message_id', None)
                if mid:
                    return str(mid)

        return ''

    @staticmethod
    def _extract_sender_id(msg) -> str:
        """提取发送者 ID"""
        sender = getattr(msg, 'sender', None)
        if sender:
            sid = getattr(sender, 'id', None) or getattr(sender, 'sender_id', None)
            if sid:
                return str(sid)
            return str(sender)
        return 'unknown'

    @staticmethod
    def _extract_chat_id(msg) -> str:
        """提取群聊/会话 ID（用于按群分组记忆）"""
        # 尝试: msg.event.message.chat_id
        event = getattr(msg, 'event', None)
        if event:
            message = getattr(event, 'message', None)
            if message:
                cid = getattr(message, 'chat_id', None)
                if cid:
                    return str(cid)

        # 尝试: msg.chat_id
        cid = getattr(msg, 'chat_id', None)
        if cid:
            return str(cid)

        # 尝试从原始 JSON 提取
        raw = getattr(msg, '_raw', None) or getattr(msg, 'raw', None)
        if raw:
            try:
                import json
                obj = json.loads(raw) if isinstance(raw, str) else raw
                cid = (
                    (obj.get('event', {}) or {}).get('message', {}) or {}
                ).get('chat_id', '')
                if cid:
                    return str(cid)
            except Exception:
                pass

        return ''

    @staticmethod
    def _sanitize_for_feishu(text: str) -> str:
        """将 LLM 输出的 Markdown 转为飞书卡片支持的语法子集。

        飞书 interactive 卡片的 markdown 组件是 CommonMark 子集，不支持：
          - LaTeX 数学公式 ($...$ / $$...$$)    → 转为行内代码 / 代码块
          - Markdown 注脚 ([^1])                → 转为 [1] 引用 + 底部附录
          - HTML 标签 (部分)                    → 剥离或转为 Markdown 等价

        已在飞书正常渲染的语法不受影响（加粗、斜体、列表、表格、代码块等）。
        """
        # ── Step 0: 保护已有的飞书兼容代码块和行内代码 ──
        protected: dict[str, str] = {}
        counter = [0]

        def _protect(pattern: str, text: str) -> str:
            """将匹配内容替换为占位符，存到 protected dict"""
            def _replacer(m):
                key = f"\x00PROTECTED{counter[0]}\x00"
                counter[0] += 1
                protected[key] = m.group(0)
                return key
            return re.sub(pattern, _replacer, text, flags=re.DOTALL)

        text = _protect(r'```[^`]*```', text)           # 围栏代码块
        text = _protect(r'`[^`]+`', text)               # 行内代码

        # ── Step 1: LaTeX 数学公式 ──
        # 块级公式 $$...$$ → 代码块（先处理，避免与行内冲突）
        def _replace_block_math(m):
            formula = m.group(1).strip()
            return f"\n```latex\n{formula}\n```\n"

        text = re.sub(r'\$\$\s*(.+?)\s*\$\$', _replace_block_math, text, flags=re.DOTALL)

        # 行内公式 $...$ → 行内代码
        text = re.sub(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)', r'`\1`', text)

        # ── Step 2: Markdown 注脚 ──
        # 收集所有注脚定义 [^n]: definition
        footnote_defs: dict[str, str] = {}

        def _collect_footnote_def(m):
            key = m.group(1)
            definition = m.group(2).strip()
            footnote_defs[key] = definition
            return ""  # 移除定义行

        text = re.sub(r'^\[\^(\S+)\]:\s*(.+?)(?=\n\[|\n\n|\Z)',
                      _collect_footnote_def, text, flags=re.MULTILINE | re.DOTALL)

        # 替换注脚引用 [^n] → [n]
        def _replace_footnote_ref(m):
            key = m.group(1)
            return f"[{key}]"

        text = re.sub(r'\[\^([^\]]+)\]', _replace_footnote_ref, text)

        # 如果有注脚定义，在文本末尾追加
        if footnote_defs:
            lines = ["\n\n---\n\n**脚注：**"]
            for key in sorted(footnote_defs.keys()):
                lines.append(f"[{key}] {footnote_defs[key]}")
            text = text.rstrip() + "\n" + "\n".join(lines)

        # ── Step 3: HTML 标签 → Markdown 等价 ──
        # <br> / <br/> → 换行
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        # <strong> / <b> → **
        text = re.sub(r'<(?:strong|b)>(.*?)</(?:strong|b)>', r'**\1**', text, flags=re.IGNORECASE)
        # <em> / <i> → *
        text = re.sub(r'<(?:em|i)>(.*?)</(?:em|i)>', r'*\1*', text, flags=re.IGNORECASE)
        # <code> → `
        text = re.sub(r'<code>(.*?)</code>', r'`\1`', text, flags=re.IGNORECASE)
        # <a href="url">text</a> → [text](url)
        text = re.sub(r'<a\s+href="([^"]*)"\s*>(.*?)</a>', r'[\2](\1)', text, flags=re.IGNORECASE)
        # <pre> → 代码块
        text = re.sub(r'<pre>(.*?)</pre>', r'\n```\n\1\n```\n', text, flags=re.IGNORECASE | re.DOTALL)
        # 其他 HTML 标签：剥离标签保留内容
        text = re.sub(r'<[^>]+>', '', text)

        # ── Step 4: 还原被保护的内容 ──
        for key, value in protected.items():
            text = text.replace(key, value)

        return text

    def _split_markdown(self, text: str) -> list:
        """将 Markdown 文本按段落边界智能分段，避免打断代码块/表格"""
        max_len = getattr(self, '_chunk_size', 15000)
        if len(text) <= max_len:
            return [text]

        chunks = []
        remaining = text
        while len(remaining) > max_len:
            # 在 max_len 范围内找最佳切割点
            search_range = remaining[:max_len]

            # 优先级: 段落边界 > 行边界 > 句子边界 > 硬切割
            cut = None
            # 1) 找最近的代码块结束 ```
            for marker in ['\n```\n', '\n---\n', '\n\n']:
                pos = search_range.rfind(marker)
                if pos > max_len * 0.6:
                    cut = pos + len(marker)
                    break

            # 2) 段落边界
            if cut is None:
                pos = search_range.rfind('\n\n')
                if pos > max_len * 0.6:
                    cut = pos + 2

            # 3) 行边界
            if cut is None:
                pos = search_range.rfind('\n')
                if pos > max_len * 0.6:
                    cut = pos + 1

            # 4) 句子边界
            if cut is None:
                for punct in ['. ', '。', '！', '？', '\n']:
                    pos = search_range.rfind(punct)
                    if pos > max_len * 0.6:
                        cut = pos + len(punct)
                        break

            # 5) 硬切割
            if cut is None or cut < max_len * 0.3:
                cut = max_len

            chunks.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()

        if remaining:
            chunks.append(remaining)

        return chunks


# ================================================================
# 状态查询（跨进程安全：通过文件读取）
# ================================================================

def is_bot_connected() -> bool:
    """检查 Bot 是否已连接（跨进程安全）"""
    return _read_status().get("connected", False)


# 保留旧接口兼容性
_bot_instance: Optional[FeishuBot] = None


def get_feishu_bot(config: FeishuConfig = None) -> Optional[FeishuBot]:
    """获取当前进程的 Bot 单例"""
    global _bot_instance
    if _bot_instance is None and config is not None:
        _bot_instance = FeishuBot(config)
    return _bot_instance


def reset_feishu_bot():
    """重置 Bot 单例"""
    global _bot_instance
    _bot_instance = None
    _write_status(False)
