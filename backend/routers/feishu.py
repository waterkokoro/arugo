"""飞书机器人配置 API"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
import aiosqlite
from database import get_db
from feishu.config import get_feishu_config, save_feishu_config, FeishuConfig
from feishu.bot import get_feishu_bot, reset_feishu_bot

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
    """获取飞书配置（敏感信息脱敏）"""
    config = await get_feishu_config()
    bot = get_feishu_bot()
    config.connected = bot.is_running if bot else False
    return FeishuStatus(**config.to_dict())


@router.put("/config", response_model=FeishuStatus)
async def update_config(settings: FeishuSettings):
    """更新飞书配置"""
    config = await get_feishu_config()

    # 更新字段
    config.enabled = settings.enabled
    config.app_id = settings.app_id.strip()

    # 只有传入了非空值且不是脱敏值时才更新
    if settings.app_secret and settings.app_secret != "***":
        config.app_secret = settings.app_secret.strip()
    if settings.verification_token and settings.verification_token != "***":
        config.verification_token = settings.verification_token.strip()

    # 验证必要字段
    if config.enabled and (not config.app_id or not config.app_secret):
        raise ValueError("启用飞书机器人需要填写 App ID 和 App Secret")

    await save_feishu_config(config)

    # 重置 bot 单例，下次访问时使用新配置
    reset_feishu_bot()

    bot = get_feishu_bot()
    config.connected = bot.is_running if bot else False

    return FeishuStatus(**config.to_dict())


@router.post("/restart")
async def restart_bot():
    """重启飞书机器人（配置更新后使用）"""
    config = await get_feishu_config()

    if not config.enabled:
        return {"status": "disabled", "message": "飞书机器人未启用"}

    # 停止旧 bot
    bot = get_feishu_bot()
    if bot and bot.is_running:
        await bot.stop()

    # 重置并启动新 bot
    reset_feishu_bot()

    # 需要外部触发启动（main.py 的 lifespan）
    return {"status": "restart_pending", "message": "已重置，将在服务重启时自动启动"}


@router.get("/status")
async def get_status():
    """获取飞书机器人运行状态"""
    bot = get_feishu_bot()
    config = await get_feishu_config()

    return {
        "enabled": config.enabled,
        "configured": bool(config.app_id and config.app_secret),
        "connected": bot.is_running if bot else False,
        "app_id": config.app_id[:10] + "..." if config.app_id else "",
    }
