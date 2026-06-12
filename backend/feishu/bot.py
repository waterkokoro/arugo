"""飞书机器人 - WebSocket 长连接模式，消息路由到 Agent"""

import asyncio
import logging
from typing import Optional, Callable, Awaitable

from .config import FeishuConfig

logger = logging.getLogger("feishu_bot")


class FeishuBot:
    """飞书机器人 WebSocket 长连接管理器

    使用 lark_oapi.channel.FeishuChannel 实现长连接，
    接收消息后路由到 Agent 处理，再将回复发回飞书。

    Usage:
        bot = FeishuBot(config)
        bot.on_message = my_agent_handler  # 注入消息处理函数
        await bot.start()
    """

    def __init__(self, config: FeishuConfig):
        self.config = config
        self._channel = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # 消息处理器（由外部注入，将消息文本路由到 Agent）
        self._message_handler: Optional[Callable[[str, str], Awaitable[str]]] = None

        # 内部回调
        self._on_connect: Optional[Callable[[], Awaitable[None]]] = None
        self._on_disconnect: Optional[Callable[[], Awaitable[None]]] = None
        self._on_error: Optional[Callable[[str], Awaitable[None]]] = None

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def set_message_handler(self, handler: Callable[[str, str], Awaitable[str]]):
        """设置消息处理器

        Args:
            handler: async function(sender_id: str, message_text: str) -> str
                     接收发送者ID和消息文本，返回回复文本
        """
        self._message_handler = handler

    def set_callbacks(
        self,
        on_connect: Optional[Callable[[], Awaitable[None]]] = None,
        on_disconnect: Optional[Callable[[], Awaitable[None]]] = None,
        on_error: Optional[Callable[[str], Awaitable[None]]] = None,
    ):
        """设置连接状态回调"""
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._on_error = on_error

    async def start(self):
        """启动飞书机器人（WebSocket 长连接）"""
        if not self.config.enabled:
            logger.info("[FeishuBot] 飞书机器人未启用，跳过启动")
            return

        if not self.config.app_id or not self.config.app_secret:
            logger.warning("[FeishuBot] App ID 或 App Secret 未配置，跳过启动")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_channel())

        if self._on_connect:
            try:
                await self._on_connect()
            except Exception:
                pass

        logger.info("[FeishuBot] 飞书机器人已启动")

    async def stop(self):
        """停止飞书机器人"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self._on_disconnect:
            try:
                await self._on_disconnect()
            except Exception:
                pass

        logger.info("[FeishuBot] 飞书机器人已停止")

    # ================================================================
    # 输入验证
    # ================================================================

    @staticmethod
    def _validate_input(text: str) -> str:
        """验证并清理输入"""
        import re
        if not text or not isinstance(text, str):
            return ""
        # 移除不可见控制字符（保留常用空白）
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        return text.strip()[:8000]  # 限制 8000 字符

    async def _run_channel(self):
        """运行 WebSocket 长连接通道"""
        from lark_oapi.channel import FeishuChannel

        self._channel = FeishuChannel(
            app_id=self.config.app_id,
            app_secret=self.config.app_secret,
        )

        # 获取当前事件循环
        loop = asyncio.get_event_loop()

        # 创建队列用于消息处理
        message_queue: asyncio.Queue = asyncio.Queue()

        # 启动消息处理协程
        processor_task = asyncio.create_task(
            self._process_messages(message_queue)
        )

        # 注册事件处理器
        @self._channel.on_message
        async def handle_message(message, context):
            """处理收到的消息事件"""
            if not self._running:
                return

            try:
                # 提取消息内容
                msg_type = getattr(message, 'message_type', 'text')
                content = getattr(message, 'content', '')
                sender_id = getattr(message, 'sender_id', 'unknown')
                message_id = getattr(message, 'message_id', '')

                # 只处理文本消息
                if msg_type != 'text':
                    # 转发回复告诉用户支持文本
                    try:
                        await context.reply_text("目前只支持文本消息哦，请发送文字 😊")
                    except Exception:
                        pass
                    return

                # 提取文本
                text = self._validate_input(content)
                if not text:
                    return

                logger.info(f"[FeishuBot] 收到消息: sender={sender_id}, text={text[:50]}...")

                # 放入处理队列
                await message_queue.put({
                    "sender_id": sender_id,
                    "text": text,
                    "message_id": message_id,
                    "context": context,
                })

            except Exception as e:
                logger.error(f"[FeishuBot] 消息处理异常: {e}")

        # 启动 Channel（阻塞直到连接断开）
        try:
            logger.info("[FeishuBot] 正在建立 WebSocket 连接...")
            await self._channel.start()

        except asyncio.CancelledError:
            logger.info("[FeishuBot] Channel 被取消")
        except Exception as e:
            logger.error(f"[FeishuBot] Channel 异常: {e}")
            if self._on_error:
                try:
                    await self._on_error(str(e))
                except Exception:
                    pass
        finally:
            self._running = False
            processor_task.cancel()
            try:
                await processor_task
            except asyncio.CancelledError:
                pass

            if self._on_disconnect:
                try:
                    await self._on_disconnect()
                except Exception:
                    pass

    async def _process_messages(self, queue: asyncio.Queue):
        """串行处理消息队列（3秒超时）"""
        while self._running:
            try:
                # 等待消息，超时 1 秒检查运行状态
                message_data = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                sender_id = message_data["sender_id"]
                text = message_data["text"]
                context = message_data["context"]

                # 调用注入的消息处理器（3 秒超时，飞书要求）
                if self._message_handler:
                    try:
                        reply = await asyncio.wait_for(
                            self._message_handler(sender_id, text),
                            timeout=3.0
                        )
                    except asyncio.TimeoutError:
                        reply = "处理超时，请稍后再试 😅"
                    except Exception as e:
                        logger.error(f"[FeishuBot] 消息处理失败: {e}")
                        reply = f"处理出错了：{str(e)[:100]}"
                else:
                    reply = "机器人还没有配置消息处理器，请联系管理员。"

                # 发送回复（如果 reply 过长，分段发送）
                if reply:
                    if len(reply) <= 2000:
                        try:
                            await context.reply_text(reply)
                        except Exception as e:
                            logger.error(f"[FeishuBot] 回复发送失败: {e}")
                    else:
                        # 分段发送（飞书消息限制约 2000 字符）
                        chunks = [reply[i:i+1800] for i in range(0, len(reply), 1800)]
                        for i, chunk in enumerate(chunks):
                            prefix = f"[{i+1}/{len(chunks)}]\n" if len(chunks) > 1 else ""
                            try:
                                await context.reply_text(prefix + chunk)
                            except Exception as e:
                                logger.error(f"[FeishuBot] 分段回复发送失败: {e}")
                                break

            except Exception as e:
                logger.error(f"[FeishuBot] 消息队列处理异常: {e}")


# ================================================================
# 全局单例
# ================================================================

_bot_instance: Optional[FeishuBot] = None


def get_feishu_bot(config: FeishuConfig = None) -> FeishuBot:
    """获取飞书机器人单例"""
    global _bot_instance
    if _bot_instance is None and config is not None:
        _bot_instance = FeishuBot(config)
    return _bot_instance


def reset_feishu_bot():
    """重置飞书机器人单例（配置更新后使用）"""
    global _bot_instance
    _bot_instance = None
