"""飞书机器人配置 API"""

import asyncio
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from database import DB_PATH
from feishu.config import get_feishu_config, save_feishu_config
from feishu.bot import get_feishu_bot, reset_feishu_bot, is_bot_connected

logger = logging.getLogger("feishu_api")
router = APIRouter(prefix="/api/feishu", tags=["feishu"])


class FeishuSettings(BaseModel):
    """飞书配置请求体"""
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""            # 保存时传入，获取时返回 ***
    verification_token: str = ""    # 保存时传入，获取时返回 ***


class FeishuStatus(BaseModel):
    """飞书机器人状态"""
    enabled: bool
    app_id: str
    has_secret: bool
    has_verification_token: bool
    connected: bool
    event_types: list


@router.get("/config", response_model=FeishuStatus)
async def get_config():
    """获取飞书配置（跨进程安全：状态从文件读取）"""
    config = await get_feishu_config()
    return FeishuStatus(
        enabled=config.enabled,
        app_id=config.app_id[:10] + "..." if config.app_id else "",
        has_secret=bool(config.app_secret),
        has_verification_token=bool(config.verification_token),
        connected=is_bot_connected(),  # 跨进程安全
        event_types=["im.message.receive_v1"],
    )


@router.put("/config", response_model=FeishuStatus)
async def update_config(settings: FeishuSettings):
    """更新飞书配置 + 自动重启 Bot"""
    config = await get_feishu_config()

    config.enabled = settings.enabled
    config.app_id = settings.app_id.strip()

    if settings.app_secret and settings.app_secret != "***":
        config.app_secret = settings.app_secret.strip()
    if settings.verification_token and settings.verification_token != "***":
        config.verification_token = settings.verification_token.strip()

    if config.enabled and (not config.app_id or not config.app_secret):
        raise ValueError("启用飞书机器人需要填写 App ID 和 App Secret")

    await save_feishu_config(config)

    # 重启 Bot（同步等待连接建立或超时）
    reset_feishu_bot()
    bot = get_feishu_bot(config)

    if bot and config.enabled:
        # 注入消息处理器
        from feishu.message_handler import create_message_handler
        bot.set_message_handler(create_message_handler())

        try:
            await asyncio.wait_for(bot.connect(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning("[FeishuAPI] Bot 连接超时（15s），可能稍后连上")
        except Exception as e:
            logger.error(f"[FeishuAPI] Bot 连接失败: {e}")

    return FeishuStatus(
        enabled=config.enabled,
        app_id=config.app_id[:10] + "..." if config.app_id else "",
        has_secret=bool(config.app_secret),
        has_verification_token=bool(config.verification_token),
        connected=is_bot_connected(),
        event_types=["im.message.receive_v1"],
    )


@router.post("/restart")
async def restart_bot():
    """手动重启飞书机器人"""
    config = await get_feishu_config()

    if not config.enabled:
        return {"status": "disabled", "message": "飞书机器人未启用"}

    reset_feishu_bot()
    bot = get_feishu_bot(config)

    if bot:
        from feishu.message_handler import create_message_handler
        bot.set_message_handler(create_message_handler())

        try:
            await asyncio.wait_for(bot.connect(), timeout=15.0)
        except asyncio.TimeoutError:
            return {"status": "timeout", "message": "连接超时，请检查配置或查看日志"}
        except Exception as e:
            return {"status": "error", "message": str(e)[:200]}

    return {"status": "connected" if is_bot_connected() else "unknown"}


@router.get("/status")
async def get_status():
    """获取飞书机器人运行状态（跨进程安全）"""
    config = await get_feishu_config()
    return {
        "enabled": config.enabled,
        "configured": bool(config.app_id and config.app_secret),
        "connected": is_bot_connected(),
        "app_id": config.app_id[:10] + "..." if config.app_id else "",
    }
