from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import init_db
from routers import settings, chat, feishu


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    await init_db()

    # 启动飞书机器人（如果已配置）
    from feishu.config import get_feishu_config
    from feishu.bot import FeishuBot, reset_feishu_bot
    from feishu.message_handler import create_message_handler

    feishu_config = await get_feishu_config()
    bot = None

    if feishu_config.enabled and feishu_config.app_id and feishu_config.app_secret:
        reset_feishu_bot()
        bot = FeishuBot(feishu_config)
        bot.set_message_handler(create_message_handler())

        try:
            await bot.connect()
            print(f"[Lifespan] ✅ 飞书机器人已启动 (app_id={feishu_config.app_id[:10]}...)")
        except Exception as e:
            print(f"[Lifespan] ⚠️ 飞书机器人启动失败: {e}")

    yield

    # 关闭时的清理操作
    if bot and bot.is_running:
        bot.stop()
        print("[Lifespan] 飞书机器人已停止")


app = FastAPI(
    title="AI Agent API",
    description="基于 LangChain 的 AI Agent 对话系统",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由
app.include_router(settings.router)
app.include_router(chat.router)
app.include_router(feishu.router)


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
