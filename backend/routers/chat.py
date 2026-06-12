"""聊天路由：支持 Agent 模式的 SSE 流式响应"""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
import aiosqlite
import json
import traceback
from pydantic import BaseModel
from database import get_db, DB_PATH
from models import ChatRequest, Message
from agent.context import ContextManager
from agent.llm_client import LLMClient, stop_stream, reset_stream, get_stop_event

router = APIRouter(prefix="/api", tags=["chat"])


class ChatModeRequest(BaseModel):
    """聊天请求，支持 agent 模式和深度思考"""
    message: str
    mode: str = "chat"  # "chat" 或 "agent"
    deep_thinking: bool = False
    web_search_enabled: bool = True  # 是否注入联网搜索工具


@router.post("/chat")
async def chat(request: ChatRequest, db: aiosqlite.Connection = Depends(get_db)):
    """发送消息并流式接收 AI 回复（简单模式，向后兼容）"""
    return await _chat_handler(request.message, "chat", False, db)


@router.post("/chat/agent")
async def chat_agent(request: ChatModeRequest, db: aiosqlite.Connection = Depends(get_db)):
    """发送消息并流式接收 Agent 回复（支持 Tool Calling）"""
    # 开始新对话，重置停止事件
    reset_stream("default")
    return await _chat_handler(request.message, request.mode, request.deep_thinking, db, request.web_search_enabled)


@router.post("/chat/stop")
async def chat_stop():
    """停止当前正在进行的 AI 回复"""
    success = stop_stream("default")
    return {"stopped": success}


async def _chat_handler(message: str, mode: str, deep_thinking: bool, db: aiosqlite.Connection, web_search_enabled: bool = True):
    """统一的聊天处理函数
    
    注意：由于 FastAPI 依赖注入的 db 连接在返回 StreamingResponse 后会被关闭，
    我们在返回前先完成数据库操作，然后在流式生成器内部创建新连接用于保存消息。
    """
    context_manager = ContextManager(db)

    # 获取系统提示词（在返回前完成）
    async with db.execute(
        "SELECT value FROM settings WHERE key = ?", ("system_prompt",)
    ) as cursor:
        row = await cursor.fetchone()
        system_prompt = row[0] if row else "You are a helpful assistant."

    # 添加用户消息（在返回前完成）
    await context_manager.add_message("user", message)

    # 构建上下文（在返回前完成）
    context = await context_manager.build_context(system_prompt)

    # 预先获取配置（在返回前完成）
    async with db.execute("SELECT key, value FROM settings") as cursor:
        rows = await cursor.fetchall()
        config = {row[0]: row[1] for row in rows}

    if mode == "agent":
        # Agent 模式：支持 Tool Calling
        async def generate_agent():
            # 在生成器内创建独立的数据库连接用于保存消息
            try:
                async with aiosqlite.connect(DB_PATH) as stream_db:
                    stream_context_manager = ContextManager(stream_db)
                    # 创建 LLM client，传入预获取的配置
                    llm_client = LLMClient.from_config(config)
                    
                    # 获取停止事件
                    stop_event = get_stop_event("default")

                    full_response = ""
                    async for event in llm_client.agent_stream(context, deep_thinking=deep_thinking, stop_event=stop_event, web_search_enabled=web_search_enabled):
                        if event.type == "content":
                            full_response += event.content
                        # 发送 SSE 事件
                        yield f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n"

                    # 保存 AI 回复到数据库（如果被停止则不保存）
                    if full_response and not stop_event.is_set():
                        await stream_context_manager.add_message("assistant", full_response)
            except Exception as e:
                # 生成器异常时发送错误事件，防止 SSE 流静默断开
                error_msg = f"Agent 流异常: {str(e)}"
                print(f"[Chat] {error_msg}")
                traceback.print_exc()
                yield f"data: {json.dumps({'type': 'error', 'content': error_msg}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(generate_agent(), media_type="text/event-stream")
    else:
        # 简单模式：纯文本对话（向后兼容）
        async def generate():
            try:
                async with aiosqlite.connect(DB_PATH) as stream_db:
                    stream_context_manager = ContextManager(stream_db)
                    llm_client = LLMClient.from_config(config)
                    
                    # 获取停止事件
                    stop_event = get_stop_event("default")

                    full_response = ""
                    async for chunk in llm_client.chat_stream(context, deep_thinking=deep_thinking):
                        # 检查停止信号
                        if stop_event.is_set():
                            yield f"data: {json.dumps({'type': 'done', 'content': '[已停止]'}, ensure_ascii=False)}\n\n"
                            return

                        full_response += chunk
                        yield f"data: {json.dumps({'type': 'content', 'content': chunk}, ensure_ascii=False)}\n\n"

                    if full_response and not stop_event.is_set():
                        await stream_context_manager.add_message("assistant", full_response)
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
            except Exception as e:
                error_msg = f"Chat 流异常: {str(e)}"
                print(f"[Chat] {error_msg}")
                traceback.print_exc()
                yield f"data: {json.dumps({'type': 'error', 'content': error_msg}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/messages", response_model=list[Message])
async def get_messages(
    limit: int = 100,
    offset: int = 0,
    db: aiosqlite.Connection = Depends(get_db)
):
    """获取历史消息"""
    async with db.execute(
        "SELECT id, role, content, created_at FROM messages ORDER BY id DESC LIMIT ? OFFSET ?",
        (limit, offset)
    ) as cursor:
        rows = await cursor.fetchall()
        messages = [
            Message(id=row[0], role=row[1], content=row[2], created_at=row[3])
            for row in reversed(rows)
        ]
        return messages


@router.delete("/messages")
async def clear_messages(db: aiosqlite.Connection = Depends(get_db)):
    """清空对话历史"""
    await db.execute("DELETE FROM messages")
    await db.commit()
    return {"message": "对话历史已清空"}
