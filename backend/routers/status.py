"""Agent 状态 SSE 端点

前端通过 EventSource 连接此端点，实时接收 Agent 活动事件：
  - 工具调用 (tool_call / tool_result)
  - 差异变更 (diff)
  - 子Agent 活动 (sub_agent)
  - 错误 (error)
  - 完成 (done)

用法:
    const es = new EventSource('/api/agent/status/stream')
    es.onmessage = (e) => { console.log(JSON.parse(e.data)) }
"""

import asyncio
import json
import logging
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agent.event_bus import get_or_create_session, get_all_sessions, cleanup_stale_sessions
from agent.llm_client import AgentEvent

logger = logging.getLogger("status_router")
router = APIRouter(prefix="/api", tags=["agent_status"])


@router.get("/agent/status/stream")
async def agent_status_stream():
    """SSE 端点：实时推送 Agent 活动事件

    Events:
        event: agent_event  - AgentEvent JSON (tool_call, tool_result, error, done 等)
        event: heartbeat     - 每 15 秒保活心跳
        event: summary       - 初始连接时发送当前状态摘要

    重连: 客户端应在断开后自动重连 (EventSource 默认行为)
    """

    async def generate():
        session_id = "default"
        session = get_or_create_session(session_id)
        q = session.subscribe()

        try:
            # 发送初始摘要
            summary = session.get_summary()
            summary["type"] = "summary"
            yield f"event: summary\ndata: {json.dumps(summary, ensure_ascii=False)}\n\n"

            # 发送当前活跃会话列表
            all_sessions = get_all_sessions()
            yield f"event: sessions\ndata: {json.dumps(all_sessions, ensure_ascii=False)}\n\n"

            last_heartbeat = time.time()

            while True:
                try:
                    # 等待事件（最多 5 秒，用于定期心跳）
                    event = await asyncio.wait_for(q.get(), timeout=5.0)
                    data = json.dumps(event.to_dict(), ensure_ascii=False)
                    yield f"event: agent_event\ndata: {data}\n\n"
                    last_heartbeat = time.time()

                except asyncio.TimeoutError:
                    # 发送心跳
                    now = time.time()
                    if now - last_heartbeat >= 15:
                        yield f"event: heartbeat\ndata: {{\"ts\": {now}}}\n\n"
                        last_heartbeat = now

                    # 定期清理超时会话
                    cleanup_stale_sessions()

        except asyncio.CancelledError:
            pass
        finally:
            session.unsubscribe(q)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )


@router.get("/agent/status/summary")
async def agent_status_summary():
    """获取当前 Agent 状态摘要（非流式，适合轮询）"""
    sessions = get_all_sessions()
    cleanup_stale_sessions()
    return {
        "sessions": sessions,
        "active_count": sum(1 for s in sessions if s["is_active"]),
    }
