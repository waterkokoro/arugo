import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "agent.db")


async def get_db():
    """获取数据库连接"""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    """初始化数据库表"""
    async with aiosqlite.connect(DB_PATH) as db:
        # 设置表（key-value 存储）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # 消息表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 插入默认配置
        defaults = {
            "api_key": "",
            "base_url": "https://api.openai.com/v1",
            "model_name": "gpt-3.5-turbo",
            "system_prompt": "You are a helpful assistant.",
            "context_window_size": "500",
            "workspace_dir": "",
            "allowed_commands": "ls,cat,head,tail,grep,find,git status,git diff,git log,git add,git commit,python,pip,npm,node,pytest",
            # 联网搜索默认配置
            "search_provider": "auto",
            "search_api_keys": "{}",
            # 飞书机器人默认配置
            "feishu_config": '{"enabled": false, "app_id": "", "app_secret": "", "verification_token": "", "event_types": ["im.message.receive_v1"]}',
        }

        for key, value in defaults.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )

        await db.commit()
