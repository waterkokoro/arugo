from typing import List, Dict, Optional
import asyncio
import aiosqlite
from datetime import datetime
from agent.memory import PersistentMemoryManager
from agent.goal_manager import get_goal_manager


class ContextManager:
    """滑动窗口上下文管理器 + 持久记忆注入"""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db
        self._memory_manager: Optional[PersistentMemoryManager] = None

    @property
    def memory(self) -> PersistentMemoryManager:
        """延迟初始化持久记忆管理器"""
        if self._memory_manager is None:
            self._memory_manager = PersistentMemoryManager()
        return self._memory_manager

    async def get_context_window_size(self) -> int:
        """获取上下文窗口大小配置"""
        async with self.db.execute(
            "SELECT value FROM settings WHERE key = ?",
            ("context_window_size",)
        ) as cursor:
            row = await cursor.fetchone()
            return int(row[0]) if row else 500

    async def get_messages(self, limit: int = None) -> List[Dict[str, str]]:
        """获取历史消息，应用滑动窗口"""
        if limit is None:
            limit = await self.get_context_window_size()

        async with self.db.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            # 反转为时间正序
            messages = [{"role": row[0], "content": row[1]} for row in reversed(rows)]
            return messages

    async def add_message(self, role: str, content: str):
        """添加消息到数据库"""
        await self.db.execute(
            "INSERT INTO messages (role, content) VALUES (?, ?)",
            (role, content)
        )
        await self.db.commit()

    async def build_context(self, system_prompt: str, inject_memory: bool = True, inject_goals: bool = True) -> List[Dict[str, str]]:
        """构建完整的上下文（system prompt + 持久记忆 + 活跃目标 + 历史消息）

        Args:
            system_prompt: 系统提示词
            inject_memory: 是否注入持久记忆（默认 True）
            inject_goals: 是否注入活跃进化目标（默认 True）
        """
        messages = []

        # 1. System prompt（注入持久记忆和活跃目标）
        enriched_prompt = system_prompt
        extra_sections = []

        if inject_memory:
            memory_context = self.memory.get_context_injection()
            if memory_context:
                extra_sections.append(memory_context)

        if inject_goals:
            goal_context = get_goal_manager().get_context_injection()
            if goal_context:
                extra_sections.append(goal_context)

        if extra_sections:
            enriched_prompt = f"{system_prompt}\n\n---\n" + "\n\n".join(extra_sections)

        messages.append({"role": "system", "content": enriched_prompt})

        # 2. 历史消息
        history = await self.get_messages()
        messages.extend(history)

        # 3. 检查窗口是否接近满载，自动触发摘要保存
        window_size = await self.get_context_window_size()
        current_count = await self._count_messages()

        # 从 DB 读取自动摘要阈值
        from agent.config import get_agent_config_float
        threshold = await get_agent_config_float("context_auto_summarize_threshold", 0.8)

        if current_count > window_size * threshold:
            # 异步触发摘要保存（不阻塞当前请求）
            asyncio.create_task(self._auto_summarize(current_count, window_size))

        return messages

    async def _auto_summarize(self, current_count: int, window_size: int):
        """自动保存会话摘要（窗口接近满载时触发）"""
        try:
            summary = (
                f"自动摘要 - 会话消息数 {current_count}/{window_size}\n"
                f"触发时间: {datetime.now().isoformat()}\n"
                f"原因: 滑动窗口使用率超过 80%，自动保存以防止信息丢失。"
            )
            self.memory.end_session(summary)
            self.memory.log_evolution(
                event_type="auto_summarize",
                description=f"窗口 {current_count}/{window_size}，自动保存摘要",
            )
            print(f"[Context] 自动摘要已保存 ({current_count}/{window_size})")
        except Exception as e:
            print(f"[Context] 自动摘要失败: {e}")

    async def end_session(self, summary: str = None):
        """结束会话，保存摘要到持久记忆"""
        if summary:
            self.memory.end_session(summary)
        # 记录进化：会话结束
        self.memory.log_evolution(
            event_type="session_end",
            description=f"会话结束，共 {await self._count_messages()} 条消息",
        )

    async def _count_messages(self) -> int:
        """获取当前会话消息数"""
        async with self.db.execute("SELECT COUNT(*) FROM messages") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    def get_memory_manager(self) -> PersistentMemoryManager:
        """获取持久记忆管理器（供外部使用）"""
        return self.memory

    def add_evolution_event(self, event_type: str, description: str, metadata: dict = None):
        """记录进化事件到持久存储"""
        self.memory.log_evolution(event_type, description, metadata)
