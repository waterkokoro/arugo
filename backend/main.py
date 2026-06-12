import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
from database import init_db
from routers import settings, chat, feishu, management, status, shadow


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    await init_db()

    # 影子模式：跳过飞书 Bot，避免两个实例同时连接飞书
    is_shadow = os.environ.get("ARUGO_SHADOW", "").lower() in ("true", "1", "yes")

    # 启动飞书机器人（如果已配置且非影子模式）
    from feishu.config import get_feishu_config
    from feishu.bot import FeishuBot, reset_feishu_bot
    from feishu.message_handler import create_message_handler

    feishu_config = await get_feishu_config()
    bot = None
    bot_task = None

    if is_shadow:
        print("[Lifespan] 🔷 影子模式：跳过飞书机器人连接")
    elif feishu_config.enabled and feishu_config.app_id and feishu_config.app_secret:
        reset_feishu_bot()
        bot = FeishuBot(feishu_config)
        bot.set_handler_factory(create_message_handler)

        # WebSocket connect 是阻塞调用，放入后台任务避免阻塞 HTTP 服务启动
        bot_task = asyncio.create_task(bot.connect())
        print(f"[Lifespan] 飞书机器人正在后台连接 (app_id={feishu_config.app_id[:10]}...)")

    yield

    # 关闭时的清理操作
    if bot and bot.is_running:
        await bot.stop()
        print("[Lifespan] 飞书机器人已停止")
    if bot_task and not bot_task.done():
        bot_task.cancel()


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
app.include_router(management.router)
app.include_router(shadow.router)


@app.get("/api/health")
async def health_check():
    """健康检查（含工具数量、Agent就绪状态）"""
    import os
    tool_count = 0
    try:
        from agent.tools import get_tools
        tools = await get_tools()
        tool_count = len(tools)
    except Exception:
        pass

    is_shadow = os.environ.get("ARUGO_SHADOW", "").lower() in ("true", "1", "yes")

    return {
        "status": "ok",
        "tool_count": tool_count,
        "agent_ready": tool_count > 0,
        "mode": "shadow" if is_shadow else "main",
        "port": 8001 if is_shadow else 8000,
        "feishu_skipped": is_shadow,  # 影子模式跳过飞书
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
