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
    from feishu.bot import FeishuBot, get_feishu_bot, reset_feishu_bot

    feishu_config = await get_feishu_config()
    bot = None

    if feishu_config.enabled and feishu_config.app_id and feishu_config.app_secret:
        reset_feishu_bot()
        bot = FeishuBot(feishu_config)

        # 注入消息处理器：将飞书消息路由到 Agent
        async def handle_feishu_message(sender_id: str, text: str) -> str:
            """飞书消息 → Agent → 回复"""
            import aiosqlite
            from database import DB_PATH
            from agent.context import ContextManager
            from agent.llm_client import LLMClient

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
                    # 追加飞书用户消息
                    context.append({
                        "role": "user",
                        "content": f"[来自飞书用户 {sender_id}]\n{text}"
                    })

                    # 获取 LLM 配置
                    async with db.execute("SELECT key, value FROM settings") as cursor:
                        rows = await cursor.fetchall()
                        llm_config = {row[0]: row[1] for row in rows}

                    llm_client = LLMClient.from_config(llm_config)

                    # Agent 模式：收集完整回复
                    full_reply = ""
                    async for event in llm_client.agent_stream(
                        context, max_iterations=15,
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

        bot.set_message_handler(handle_feishu_message)
        await bot.start()
        print(f"[Lifespan] 飞书机器人已启动 (app_id={feishu_config.app_id[:10]}...)")

    yield

    # 关闭时的清理操作
    if bot and bot.is_running:
        await bot.stop()
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
