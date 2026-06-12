"""飞书消息 → Agent LLM 处理器

独立模块，供 bot.py 和 routers/feishu.py 共用。
"""

import logging

logger = logging.getLogger("feishu.handler")


def create_message_handler():
    """创建飞书消息处理器：飞书消息 → Agent → 回复文本

    Returns:
        async function(sender_id: str, text: str) -> str
    """
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
                context.append({
                    "role": "user",
                    "content": f"[来自飞书用户 {sender_id}]\n{text}"
                })

                # 获取 LLM 配置
                async with db.execute("SELECT key, value FROM settings") as cursor:
                    rows = await cursor.fetchall()
                    llm_config = {row[0]: row[1] for row in rows}

                llm_client = LLMClient.from_config(llm_config)

                # Agent 模式流式收集
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

    return handle_feishu_message
