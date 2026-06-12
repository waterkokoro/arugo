"""
目标与里程碑管理器 - Phase 2 核心模块

实现跨会话的进化目标追踪：
- Goal: 长期进化目标，含优先级、截止时间、状态
- Milestone: 目标下的里程碑，可追踪进度
- GoalManager: 统一管理器，JSON 持久化

存储位置：backend/agent/goal_store/
"""

import os
import json
import hashlib
from datetime import datetime
from typing import Optional

GOAL_DIR = os.path.join(os.path.dirname(__file__), "goal_store")


def _ensure_goal_dir():
    os.makedirs(GOAL_DIR, exist_ok=True)


class Milestone:
    """单个里程碑"""

    def __init__(self, title: str, completion_criteria: str = "", status: str = "pending"):
        self.title = title
        self.status = status  # pending | in_progress | completed
        self.progress = 0  # 0-100
        self.completion_criteria = completion_criteria
        self.created_at = datetime.now().isoformat()
        self.completed_at = None
        self.id = self._gen_id()

    def _gen_id(self) -> str:
        raw = f"{datetime.now().isoformat()}-{self.title}"
        return hashlib.md5(raw.encode()).hexdigest()[:10]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "progress": self.progress,
            "completion_criteria": self.completion_criteria,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Milestone":
        m = cls(
            data["title"],
            data.get("completion_criteria", ""),
            data.get("status", "pending"),
        )
        m.id = data.get("id", m.id)
        m.progress = data.get("progress", 0)
        m.created_at = data.get("created_at", m.created_at)
        m.completed_at = data.get("completed_at")
        return m


class Goal:
    """单个进化目标"""

    def __init__(
        self,
        title: str,
        description: str = "",
        priority: int = 3,
        deadline: str = None,
        tags: list = None,
    ):
        self.title = title
        self.description = description
        self.priority = priority  # 1-5
        self.status = "active"  # active | paused | completed | abandoned
        self.deadline = deadline
        self.tags = tags or []
        self.milestones: list[Milestone] = []
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self.id = self._gen_id()

    def _gen_id(self) -> str:
        raw = f"{datetime.now().isoformat()}-{self.title}"
        return hashlib.md5(raw.encode()).hexdigest()[:10]

    @property
    def progress(self) -> int:
        """自动计算目标进度（取所有里程碑进度的平均值）"""
        if not self.milestones:
            # 无里程碑时，根据状态判断
            if self.status == "completed":
                return 100
            return 0
        return sum(m.progress for m in self.milestones) // len(self.milestones)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "deadline": self.deadline,
            "tags": self.tags,
            "milestones": [m.to_dict() for m in self.milestones],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Goal":
        g = cls(
            data["title"],
            data.get("description", ""),
            data.get("priority", 3),
            data.get("deadline"),
            data.get("tags", []),
        )
        g.id = data.get("id", g.id)
        g.status = data.get("status", "active")
        g.created_at = data.get("created_at", g.created_at)
        g.updated_at = data.get("updated_at", g.updated_at)
        g.milestones = [Milestone.from_dict(m) for m in data.get("milestones", [])]
        return g


class GoalManager:
    """统一目标管理器——JSON 文件持久化"""

    def __init__(self):
        _ensure_goal_dir()
        self._store_path = os.path.join(GOAL_DIR, "goals.json")
        self._goals: dict[str, Goal] = {}
        self._load()

    def _load(self):
        if os.path.exists(self._store_path):
            try:
                with open(self._store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for gd in data.get("goals", []):
                        g = Goal.from_dict(gd)
                        self._goals[g.id] = g
            except (json.JSONDecodeError, KeyError):
                self._goals = {}

    def _save(self):
        data = {
            "goals": [g.to_dict() for g in self._goals.values()],
            "updated_at": datetime.now().isoformat(),
        }
        with open(self._store_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---- Goal CRUD ----

    def create_goal(
        self,
        title: str,
        description: str = "",
        priority: int = 3,
        deadline: str = None,
        tags: list = None,
    ) -> Goal:
        g = Goal(title, description, priority, deadline, tags)
        self._goals[g.id] = g
        self._save()
        return g

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        return self._goals.get(goal_id)

    def list_goals(self, status: str = None) -> list[Goal]:
        goals = list(self._goals.values())
        if status:
            goals = [g for g in goals if g.status == status]
        goals.sort(key=lambda g: (g.priority, g.updated_at), reverse=True)
        return goals

    def update_goal(self, goal_id: str, **kwargs) -> Optional[Goal]:
        g = self._goals.get(goal_id)
        if not g:
            return None
        for key, val in kwargs.items():
            if hasattr(g, key):
                setattr(g, key, val)
        g.updated_at = datetime.now().isoformat()
        # 如果状态改为 completed，自动完成所有里程碑
        if kwargs.get("status") == "completed":
            for m in g.milestones:
                if m.status != "completed":
                    m.status = "completed"
                    m.progress = 100
                    m.completed_at = datetime.now().isoformat()
        self._save()
        return g

    def delete_goal(self, goal_id: str) -> bool:
        if goal_id in self._goals:
            del self._goals[goal_id]
            self._save()
            return True
        return False

    # ---- Milestone Management ----

    def add_milestone(
        self, goal_id: str, title: str, completion_criteria: str = ""
    ) -> Optional[Milestone]:
        g = self._goals.get(goal_id)
        if not g:
            return None
        m = Milestone(title, completion_criteria)
        g.milestones.append(m)
        g.updated_at = datetime.now().isoformat()
        self._save()
        return m

    def update_milestone(
        self, goal_id: str, milestone_id: str, **kwargs
    ) -> Optional[Milestone]:
        g = self._goals.get(goal_id)
        if not g:
            return None
        for m in g.milestones:
            if m.id == milestone_id:
                for key, val in kwargs.items():
                    if hasattr(m, key):
                        setattr(m, key, val)
                if kwargs.get("status") == "completed":
                    m.completed_at = datetime.now().isoformat()
                    m.progress = 100
                g.updated_at = datetime.now().isoformat()
                self._save()
                return m
        return None

    def delete_milestone(self, goal_id: str, milestone_id: str) -> bool:
        g = self._goals.get(goal_id)
        if not g:
            return False
        for i, m in enumerate(g.milestones):
            if m.id == milestone_id:
                g.milestones.pop(i)
                g.updated_at = datetime.now().isoformat()
                self._save()
                return True
        return False

    # ---- Context Injection ----

    def get_context_injection(self) -> str:
        """生成活跃目标摘要，用于注入 system prompt"""
        active = [g for g in self._goals.values() if g.status == "active"]
        if not active:
            return ""

        active.sort(key=lambda g: g.priority, reverse=True)
        lines = ["[活跃进化目标]"]
        for g in active[:5]:
            status_icon = (
                "🟢" if g.progress > 50 else ("🟡" if g.progress > 0 else "🔴")
            )
            ms_info = f" [{len(g.milestones)}个里程碑]" if g.milestones else ""
            lines.append(
                f"  {status_icon} #{g.id}: {g.title} "
                f"(优先级:{g.priority}, 进度:{g.progress}%){ms_info}"
            )
            # 展示未完成的里程碑（最多 3 个）
            incomplete = [m for m in g.milestones if m.status != "completed"]
            for m in incomplete[:3]:
                ms_icon = "⏳" if m.status == "in_progress" else "⬜"
                lines.append(f"     {ms_icon} {m.title} ({m.progress}%)")

        return "\n".join(lines)

    def compute_progress(self, goal_id: str) -> int:
        g = self._goals.get(goal_id)
        return g.progress if g else 0


# ============================================================
# 单例
# ============================================================

_goal_manager: Optional[GoalManager] = None


def get_goal_manager() -> GoalManager:
    """获取全局 GoalManager 单例"""
    global _goal_manager
    if _goal_manager is None:
        _goal_manager = GoalManager()
    return _goal_manager
