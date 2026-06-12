"""
Agent 工厂 - 子Agent生成和管理能力

允许AI：
1. 创建专门用途的子Agent（带特定system_prompt和工具集）
2. 委托任务给子Agent
3. 管理子Agent的生命周期
4. 子Agent间的结果汇总

这是AI自我扩展为"多智能体系统"的基础设施。
"""

import os
import json
import uuid
from datetime import datetime
from typing import Optional
from pathlib import Path


# 子Agent存储目录
AGENT_DIR = os.path.join(os.path.dirname(__file__), "sub_agents")
os.makedirs(AGENT_DIR, exist_ok=True)


class SubAgent:
    """子Agent定义 - 一个专门用途的AI代理"""

    def __init__(
        self,
        name: str,
        system_prompt: str,
        description: str = "",
        tools: list = None,  # 工具名称列表
        parent_id: str = None,
    ):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.system_prompt = system_prompt
        self.description = description
        self.tools = tools or []
        self.parent_id = parent_id
        self.created_at = datetime.now().isoformat()
        self.last_used = None
        self.use_count = 0
        self.status = "idle"  # idle, running, completed, error

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "parent_id": self.parent_id,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "use_count": self.use_count,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SubAgent":
        agent = cls(
            name=data["name"],
            system_prompt=data["system_prompt"],
            description=data.get("description", ""),
            tools=data.get("tools", []),
            parent_id=data.get("parent_id"),
        )
        agent.id = data.get("id", agent.id)
        agent.created_at = data.get("created_at", agent.created_at)
        agent.last_used = data.get("last_used")
        agent.use_count = data.get("use_count", 0)
        agent.status = data.get("status", "idle")
        return agent


class AgentFactory:
    """Agent工厂 - 管理子Agent的创建、存储和检索"""

    def __init__(self):
        self._agent_store_path = os.path.join(AGENT_DIR, "registry.json")
        self._agents: dict[str, SubAgent] = {}
        self._load()

    def _load(self):
        """从磁盘加载已注册的子Agent"""
        if os.path.exists(self._agent_store_path):
            try:
                with open(self._agent_store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for agent_data in data.get("agents", []):
                    agent = SubAgent.from_dict(agent_data)
                    self._agents[agent.id] = agent
            except (json.JSONDecodeError, KeyError):
                pass

    def _save(self):
        """保存子Agent注册表"""
        data = {
            "updated_at": datetime.now().isoformat(),
            "total": len(self._agents),
            "agents": [a.to_dict() for a in self._agents.values()],
        }
        with open(self._agent_store_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def create(
        self,
        name: str,
        system_prompt: str,
        description: str = "",
        tools: list = None,
    ) -> SubAgent:
        """创建一个新的子Agent"""
        agent = SubAgent(
            name=name,
            system_prompt=system_prompt,
            description=description,
            tools=tools or [],
        )
        self._agents[agent.id] = agent
        self._save()
        return agent

    def get(self, agent_id: str) -> Optional[SubAgent]:
        """获取子Agent"""
        return self._agents.get(agent_id)

    def find_by_name(self, name: str) -> Optional[SubAgent]:
        """按名称查找子Agent"""
        for agent in self._agents.values():
            if agent.name == name:
                return agent
        return None

    def list_all(self) -> list[SubAgent]:
        """列出所有子Agent"""
        return list(self._agents.values())

    def delete(self, agent_id: str) -> bool:
        """删除子Agent"""
        if agent_id in self._agents:
            del self._agents[agent_id]
            self._save()
            return True
        return False

    def mark_used(self, agent_id: str):
        """标记子Agent被使用"""
        if agent_id in self._agents:
            self._agents[agent_id].last_used = datetime.now().isoformat()
            self._agents[agent_id].use_count += 1
            self._save()

    def generate_agent_config(
        self,
        purpose: str,
        expertise: str,
        tools_needed: list = None,
    ) -> str:
        """
        生成子Agent的配置建议（供AI使用以规划子Agent）。
        
        Args:
            purpose: 子Agent的用途
            expertise: 需要的专长领域
            tools_needed: 建议的工具列表
        """
        lines = [
            "# 子Agent配置建议",
            "",
            f"## 用途: {purpose}",
            f"## 专长: {expertise}",
            "",
            "## 建议的 System Prompt:",
            "```",
            f"你是一个专注于 {expertise} 的AI子代理。",
            f"你的任务是: {purpose}",
            "",
            "规则:",
            "1. 只使用分配给你的工具",
            "2. 完成后输出结构化结果",
            "3. 遇到无法处理的情况，明确报告而不是猜测",
            "```",
            "",
        ]
        if tools_needed:
            lines.append("## 建议工具:")
            for t in tools_needed:
                lines.append(f"  - {t}")
        else:
            lines.append("## 建议工具: 使用基础工具集 (read_file, write_file, run_command)")

        return "\n".join(lines)

    def get_factory_report(self) -> str:
        """生成Agent工厂报告"""
        agents = self.list_all()
        if not agents:
            return "[Agent工厂] 当前没有子Agent。使用 create_sub_agent 来创建。"
        
        lines = [f"[Agent工厂] 共 {len(agents)} 个子Agent:\n"]
        for a in agents:
            status_icon = {"idle": "💤", "running": "🟢", "completed": "✅", "error": "❌"}.get(a.status, "❓")
            lines.append(f"  {status_icon} {a.name} (ID: {a.id})")
            lines.append(f"     描述: {a.description[:60]}")
            lines.append(f"     工具: {', '.join(a.tools) if a.tools else '基础工具集'}")
            lines.append(f"     使用次数: {a.use_count}")
            lines.append("")
        return "\n".join(lines)


# 全局单例
_factory: Optional[AgentFactory] = None


def get_agent_factory() -> AgentFactory:
    """获取全局Agent工厂单例"""
    global _factory
    if _factory is None:
        _factory = AgentFactory()
    return _factory
