"""Agent 事件总线 — 发布/订阅模式

所有 Agent 活动（工具调用、子Agent、LLM 回合等）通过此总线广播。
前端通过 SSE 订阅，飞书通过进度回调消费。

架构:
    agent_stream() ──yield──▶ AgentEvent ──▶ publish() ──┬── SSE subscribers (前端)
                           │                             ├── feishu progress (飞书)
                           │                             └── (future consumers)
"""

import asyncio
import json
import logging
import time
from typing import Optional

from agent.llm_client import AgentEvent

logger = logging.getLogger("event_bus")

# 活跃的 Agent 会话（session_id → SessionState）
_active_sessions: dict[str, "SessionState"] = {}


class SessionState:
    """单个 Agent 会话的状态"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.started_at = time.time()
        self.finished_at: Optional[float] = None
        self.event_count = 0
        self.tool_calls: list[dict] = []       # 最近 50 个工具调用
        self.errors: list[str] = []            # 最近 10 个错误
        self.current_step = ""                 # 当前正在做什么
        self.sub_agents_active: list[str] = []  # 活跃的子Agent名称
        # 订阅者队列
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=200)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def publish(self, event: AgentEvent):
        """向所有订阅者广播事件"""
        self.event_count += 1

        # 更新状态快照
        if event.type == "tool_call":
            self.current_step = event.tool or ""
            self.tool_calls.append({
                "tool": event.tool,
                "args": event.tool_args,
                "time": time.time(),
            })
            if len(self.tool_calls) > 50:
                self.tool_calls = self.tool_calls[-50:]

        elif event.type == "tool_result":
            if self.tool_calls:
                self.tool_calls[-1]["result"] = event.tool_result[:200]

        elif event.type == "error":
            self.errors.append(event.content[:200])
            if len(self.errors) > 10:
                self.errors = self.errors[-10:]

        elif event.type == "done":
            self.finished_at = time.time()

        # 广播给订阅者
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # 队列满：丢弃最旧事件，放入新事件
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    dead.append(q)
            except Exception:
                dead.append(q)

        for q in dead:
            self._subscribers.remove(q)

    def get_summary(self) -> dict:
        """获取会话摘要"""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed": (self.finished_at or time.time()) - self.started_at,
            "event_count": self.event_count,
            "tool_calls": self.tool_calls[-10:],   # 最近 10 个
            "errors": self.errors[-3:],            # 最近 3 个
            "current_step": self.current_step,
            "is_active": self.finished_at is None,
            "sub_agents_active": self.sub_agents_active,
        }

    def cleanup(self):
        """清理所有订阅者"""
        for q in self._subscribers:
            try:
                q.put_nowait(AgentEvent(type="done", content="[session ended]"))
            except Exception:
                pass
        self._subscribers.clear()


def get_or_create_session(session_id: str = "default") -> SessionState:
    """获取或创建会话状态"""
    if session_id not in _active_sessions:
        _active_sessions[session_id] = SessionState(session_id)
    return _active_sessions[session_id]


def get_session(session_id: str = "default") -> Optional[SessionState]:
    """获取会话状态（不创建）"""
    return _active_sessions.get(session_id)


def end_session(session_id: str = "default"):
    """结束会话"""
    state = _active_sessions.pop(session_id, None)
    if state:
        state.finished_at = state.finished_at or time.time()
        state.cleanup()


def get_all_sessions() -> list[dict]:
    """获取所有会话摘要"""
    return [s.get_summary() for s in _active_sessions.values()]


def cleanup_stale_sessions(max_age_seconds: int = 600):
    """清理超时会话（默认 10 分钟）"""
    now = time.time()
    stale = []
    for sid, state in _active_sessions.items():
        if state.finished_at and (now - state.finished_at) > max_age_seconds:
            stale.append(sid)
    for sid in stale:
        end_session(sid)
