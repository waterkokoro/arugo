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
        self._message_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._worker_task: Optional[asyncio.Task] = None
        self._message_handler: Optional[Callable[[str, str], Awaitable[str]]] = None

    # ================================================================
    # 公共接口
    # ================================================================

    @property
    def is_running(self) -> bool:
        return self._running

    def set_message_handler(self, handler: Callable[[str, str], Awaitable[str]]):
        """设置消息处理器: async (sender_id, text) -> reply_text"""
        self._message_handler = handler

    async def connect(self):
        """建立 WebSocket + 启动后台 Worker"""
        if not self.config.enabled:
            logger.info("[FeishuBot] 未启用，跳过")
            return
        if not self.config.app_id or not self.config.app_secret:
            logger.warning("[FeishuBot] 缺少 App ID/Secret，跳过")
            return

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

                logger.info(
                    f"[FeishuBot] 收到: sender={sender_id[:20]}..., "
                    f"msg={message_id[:10]}..., text={text[:60]}..."
                )

                if not message_id:
                    logger.warning("[FeishuBot] 无法获取 message_id，无法回复")
                    return

                # 推入队列（非阻塞；队列满了丢弃并告知用户）
                try:
                    self._message_queue.put_nowait({
                        "message_id": message_id,
                        "sender_id": sender_id,
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
        """后台循环：从队列取消息 → Agent 处理 → REST 回复"""
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
            text = msg.get("text", "")

            try:
                if self._message_handler:
                    reply = await self._message_handler(sender_id, text)
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

    async def _add_reaction(self, message_id: str, emoji_type: str = "OK"):
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
        """通过飞书 REST API 回复消息，自动分段"""
        if not self._client or not message_id:
            return

        # 长文本分段发送
        chunks = self._split_text(text)
        for i, chunk in enumerate(chunks):
            prefix = f"[{i+1}/{len(chunks)}]\n" if len(chunks) > 1 else ""
            try:
                content = json.dumps({"text": prefix + chunk})
                request = (
                    ReplyMessageRequest.builder()
                    .message_id(message_id)
                    .request_body(
                        ReplyMessageRequestBody.builder()
                        .msg_type("text")
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
    def _split_text(text: str, max_len: int = 1800) -> list:
        """将长文本按最大长度分段"""
        if len(text) <= max_len:
            return [text]
        return [text[i:i+max_len] for i in range(0, len(text), max_len)]


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
