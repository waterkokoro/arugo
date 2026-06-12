"""
Agent 独立记忆系统 — 每个子 Agent 拥有自己的持久记忆

与全局 PersistentMemoryManager 不同，AgentMemory 是 per-agent 的：
- 每个 Agent 一个 JSON 文件，存储在 sub_agents/memories/{agent_id}.json
- 自动注入到 Agent 的 system_prompt 中
- 记录每次交互的摘要，形成 Agent 的"经验积累"
"""

import os
import json
from datetime import datetime
from typing import Optional


class AgentMemory:
    """单个子 Agent 的持久记忆"""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._mem_dir = os.path.join(os.path.dirname(__file__), "sub_agents", "memories")
        os.makedirs(self._mem_dir, exist_ok=True)
        self._file = os.path.join(self._mem_dir, f"{agent_id}.json")
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {
            "agent_id": self.agent_id,
            "created_at": datetime.now().isoformat(),
            "facts": [],          # 关键事实
            "interactions": [],   # 交互历史摘要
            "learned_skills": [], # 学到的技能/知识
        }

    def _save(self):
        self._data["updated_at"] = datetime.now().isoformat()
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def remember(self, content: str, importance: int = 3, category: str = "fact") -> str:
        """记住一条信息"""
        entry = {
            "content": content,
            "importance": min(5, max(1, importance)),
            "category": category,
            "timestamp": datetime.now().isoformat(),
        }
        self._data.setdefault("facts", []).append(entry)
        # 只保留最近 50 条
        if len(self._data["facts"]) > 50:
            self._data["facts"] = self._data["facts"][-50:]
        self._save()
        return f"[AgentMemory:{self.agent_id}] 已记住 ({'★' * importance})"

    def recall(self, query: str = "", limit: int = 10) -> list:
        """搜索记忆"""
        facts = self._data.get("facts", [])
        if not query:
            return facts[-limit:]
        query_lower = query.lower()
        matched = [f for f in facts if query_lower in f["content"].lower()]
        return matched[-limit:]

    def log_interaction(self, task: str, result_summary: str, success: bool = True):
        """记录一次交互"""
        entry = {
            "task": task[:200],
            "result": result_summary[:300],
            "success": success,
            "timestamp": datetime.now().isoformat(),
        }
        self._data.setdefault("interactions", []).append(entry)
        # 只保留最近 30 条交互记录
        if len(self._data["interactions"]) > 30:
            self._data["interactions"] = self._data["interactions"][-30:]
        self._save()

    def learn_skill(self, skill: str, description: str):
        """记录学到的技能"""
        entry = {
            "skill": skill,
            "description": description,
            "timestamp": datetime.now().isoformat(),
        }
        self._data.setdefault("learned_skills", []).append(entry)
        self._save()

    def get_context_injection(self) -> str:
        """生成注入到 system prompt 的记忆上下文"""
        facts = self._data.get("facts", [])
        interactions = self._data.get("interactions", [])
        learned = self._data.get("learned_skills", [])

        if not facts and not interactions and not learned:
            return ""

        lines = [f"\n[持久记忆 - Agent {self.agent_id}]"]

        if facts:
            important_facts = sorted(facts, key=lambda f: f["importance"], reverse=True)[:5]
            lines.append(f"  关键事实 ({len(facts)} 条):")
            for f in important_facts:
                lines.append(f"    {'★' * f['importance']} [{f['category']}] {f['content']}")

        if learned:
            lines.append(f"  已学技能 ({len(learned)} 项):")
            for s in learned[-5:]:
                lines.append(f"    - {s['skill']}: {s['description']}")

        if interactions:
            recent = interactions[-3:]
            lines.append(f"  最近交互 ({len(interactions)} 次):")
            for i in recent:
                status = "✅" if i["success"] else "❌"
                lines.append(f"    {status} {i['task'][:60]}")

        return "\n".join(lines)

    def get_stats(self) -> dict:
        """获取记忆统计"""
        return {
            "facts_count": len(self._data.get("facts", [])),
            "interactions_count": len(self._data.get("interactions", [])),
            "learned_skills_count": len(self._data.get("learned_skills", [])),
            "created_at": self._data.get("created_at", ""),
            "updated_at": self._data.get("updated_at", ""),
        }


# 全局缓存
_memory_cache: dict[str, AgentMemory] = {}


def get_agent_memory(agent_id: str) -> AgentMemory:
    """获取 Agent 记忆实例（带缓存）"""
    if agent_id not in _memory_cache:
        _memory_cache[agent_id] = AgentMemory(agent_id)
    return _memory_cache[agent_id]


def delete_agent_memory(agent_id: str):
    """删除 Agent 记忆文件"""
    if agent_id in _memory_cache:
        del _memory_cache[agent_id]
    mem_file = os.path.join(os.path.dirname(__file__), "sub_agents", "memories", f"{agent_id}.json")
    if os.path.exists(mem_file):
        os.remove(mem_file)
