"""飞书配置管理 - 存储在 agent.db 的 settings 表中"""

import aiosqlite
import json
from dataclasses import dataclass, field
from database import DB_PATH


@dataclass
class FeishuConfig:
    """飞书机器人配置"""
    enabled: bool = False                # 是否启用飞书机器人
    app_id: str = ""                     # 飞书应用 App ID (cli_xxx)
    app_secret: str = ""                 # 飞书应用 App Secret
    verification_token: str = ""         # 验证 Token（长连接模式可选）
    event_types: list = field(default_factory=lambda: [
        "im.message.receive_v1",         # 接收消息
    ])
    # 连接状态（不持久化）
    connected: bool = False

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "app_id": self.app_id,
            "app_secret": "***" if self.app_secret else "",
            "has_secret": bool(self.app_secret),
            "verification_token": "***" if self.verification_token else "",
            "has_verification_token": bool(self.verification_token),
            "event_types": self.event_types,
            "connected": self.connected,
        }

    @classmethod
    def from_db_row(cls, row) -> "FeishuConfig":
        """从数据库行构建配置"""
        try:
            data = json.loads(row) if isinstance(row, str) else row
        except (json.JSONDecodeError, TypeError):
            data = {}

        return cls(
            enabled=data.get("enabled", False),
            app_id=data.get("app_id", ""),
            app_secret=data.get("app_secret", ""),
            verification_token=data.get("verification_token", ""),
            event_types=data.get("event_types", ["im.message.receive_v1"]),
        )

    def to_db_value(self) -> str:
        """序列化为数据库存储值"""
        return json.dumps({
            "enabled": self.enabled,
            "app_id": self.app_id,
            "app_secret": self.app_secret,
            "verification_token": self.verification_token,
            "event_types": self.event_types,
        }, ensure_ascii=False)


async def get_feishu_config() -> FeishuConfig:
    """从数据库获取飞书配置"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT value FROM settings WHERE key = ?", ("feishu_config",)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return FeishuConfig.from_db_row(row[0])
    return FeishuConfig()


async def save_feishu_config(config: FeishuConfig):
    """保存飞书配置到数据库"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("feishu_config", config.to_db_value())
        )
        await db.commit()
