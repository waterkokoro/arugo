"""
Agent 工厂 - 子Agent生成和管理能力

允许AI：
1. 创建专门用途的子Agent（带特定system_prompt和工具集）
2. 委托任务给子Agent（完整 Tool Calling 循环）
3. 管理子Agent的生命周期
4. 子Agent间的结果汇总
5. 角色模板：一键创建专业 Agent（财务、工程师、研究员等）
6. 每个 Agent 拥有独立持久记忆

这是AI自我扩展为"多智能体系统"的基础设施。

模板现在从 agent.db 的 agent_templates 表加载，
支持通过 UI 创建/修改/删除自定义模板。
"""

import os
import json
import uuid
import asyncio
from datetime import datetime
from typing import Optional
from pathlib import Path


# 子Agent存储目录
AGENT_DIR = os.path.join(os.path.dirname(__file__), "sub_agents")
os.makedirs(AGENT_DIR, exist_ok=True)


# ============================================================
# 角色模板 — 硬编码 fallback（DB 不可用时使用）
# ============================================================

ROLE_TEMPLATES = {
    "finance_agent": {
        "name": "财务专家",
        "description": "财务分析、预算编制、成本核算、税务筹划",
        "system_prompt": """你是一名专业的财务 Agent，负责财务分析、预算编制、成本核算等任务。

核心能力：
1. 财务报表分析（利润表、资产负债表、现金流量表）
2. 预算编制与执行跟踪
3. 成本核算与利润分析
4. 税务筹划建议
5. 现金流预测

工作规则：
- 使用 read_file 读取财务数据文件
- 使用 write_file 输出分析报告
- 使用 run_command 执行计算脚本
- 使用 web_search 查询最新财税政策
- 所有金额精确到两位小数
- 遇到不确定的税务问题，明确标注"仅供参考，请咨询专业税务师"
- 报告使用 Markdown 格式，含表格和关键指标""",
        "tools": ["read_file", "write_file", "edit_file", "list_directory", "run_command", "web_search", "remember", "recall_memory"],
    },
    "code_engineer": {
        "name": "软件工程师",
        "description": "全栈开发、架构设计、代码实现、技术选型",
        "system_prompt": """你是一名全栈软件工程师 Agent，负责代码开发、架构设计和技术实现。

核心能力：
1. 全栈开发（Python/FastAPI + Vue3/TypeScript）
2. 系统架构设计与评审
3. 代码实现与重构
4. 技术方案编写
5. 依赖管理与环境配置

工作规则：
- 使用全部文件操作和命令执行工具
- 修改代码前先 read_file 理解上下文
- 重大改动使用 create_snapshot 创建快照
- 提交代码使用 git_commit_evolution
- 代码风格遵循 PEP 8 (Python) / ESLint (TS)
- 不确定的技术决策列出 pros/cons""",
        "tools": [],
    },
    "code_reviewer": {
        "name": "代码审查员",
        "description": "代码审查、质量检查、安全审计、最佳实践建议",
        "system_prompt": """你是一名代码审查 Agent，负责审查代码质量、安全性和最佳实践。

核心能力：
1. 代码质量审查（可读性、可维护性、性能）
2. 安全漏洞检测（注入、XSS、敏感信息泄露）
3. 最佳实践检查
4. 测试覆盖率评估

工作规则：
- 使用 read_file 读取待审查代码
- 使用 run_command 运行 linter 和测试
- 审查结果分三级：🔴 阻断 / 🟡 建议 / 🟢 通过
- 每个问题给出具体代码位置和修改建议
- 不直接修改代码，只输出审查报告""",
        "tools": ["read_file", "list_directory", "run_command", "web_search"],
    },
    "test_writer": {
        "name": "测试工程师",
        "description": "测试用例生成、自动化测试、覆盖率提升",
        "system_prompt": """你是一名测试工程师 Agent，负责编写测试用例和自动化测试。

核心能力：
1. 单元测试（pytest）
2. 集成测试
3. 测试覆盖率分析
4. 边界条件与异常路径测试

工作规则：
- 使用 read_file 理解被测代码
- 使用 write_file 创建测试文件
- 使用 run_command 执行 pytest
- 测试覆盖正常路径、边界条件、异常路径
- 测试文件命名：test_{module_name}.py
- 使用 run_self_tests 运行现有测试套件""",
        "tools": ["read_file", "write_file", "edit_file", "list_directory", "run_command", "run_self_tests"],
    },
    "researcher": {
        "name": "研究员",
        "description": "信息检索、技术调研、竞品分析、文档整理",
        "system_prompt": """你是一名研究员 Agent，负责信息检索、技术调研和知识整理。

核心能力：
1. 多源信息检索（web_search）
2. 技术趋势分析
3. 竞品对比研究
4. 调研报告撰写

工作规则：
- 使用 web_search 进行多轮关键词搜索
- 交叉验证信息来源
- 使用 write_file 输出结构化调研报告（Markdown）
- 标注信息来源和时间
- 区分"事实"与"观点" """,
        "tools": ["read_file", "write_file", "web_search", "remember", "recall_memory"],
    },
    "devops_engineer": {
        "name": "运维工程师",
        "description": "部署管理、环境配置、服务监控、日志分析",
        "system_prompt": """你是一名 DevOps 运维 Agent，负责部署管理和服务运维。

核心能力：
1. 服务部署与配置管理
2. 系统监控与告警
3. 日志分析与故障排查
4. 性能优化建议

工作规则：
- 使用 run_command 执行运维操作（需在白名单内）
- 使用 read_file 检查配置文件和日志
- 使用 health_check / run_self_diagnostics 检查服务状态
- 操作前评估风险，高风险操作先 create_snapshot
- 不要在生产环境直接执行危险命令""",
        "tools": ["read_file", "write_file", "edit_file", "list_directory", "run_command", "health_check", "run_self_diagnostics", "create_snapshot"],
    },
    "product_manager": {
        "name": "产品经理",
        "description": "需求分析、功能规划、用户故事、优先级排序",
        "system_prompt": """你是一名产品经理 Agent，负责需求分析和功能规划。

核心能力：
1. 需求分析与拆解
2. 用户故事编写
3. 功能优先级排序（RICE/MoSCoW）
4. PRD 文档撰写

工作规则：
- 使用 write_file 输出 PRD 文档（Markdown）
- 使用 create_goal / add_milestone 创建开发目标
- 每个功能需求附带验收标准
- 优先级使用 P0/P1/P2/P3 标记
- P0=阻断上线, P1=核心体验, P2=提升体验, P3=锦上添花""",
        "tools": ["read_file", "write_file", "web_search", "create_goal", "add_milestone", "list_goals", "remember", "recall_memory"],
    },
}


async def _load_templates_from_db() -> dict:
    """从 agent_templates 表加载模板（异步）"""
    import aiosqlite
    global ROLE_TEMPLATES
    db_path = os.path.join(os.path.dirname(__file__), "..", "agent.db")
    try:
        db = await aiosqlite.connect(db_path)
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall("SELECT * FROM agent_templates")
        await db.close()
        if rows:
            loaded = {}
            for row in rows:
                d = dict(row)
                try:
                    tools = json.loads(d.get("tools", "[]"))
                except Exception:
                    tools = []
                loaded[d["id"]] = {
                    "name": d["name"],
                    "description": d.get("description", ""),
                    "system_prompt": d["system_prompt"],
                    "tools": tools,
                }
            if loaded:
                ROLE_TEMPLATES = loaded
        return ROLE_TEMPLATES
    except Exception:
        return ROLE_TEMPLATES


def list_role_templates() -> str:
    """列出所有可用的角色模板"""
    lines = ["[Agent 角色模板]", ""]
    for key, tmpl in ROLE_TEMPLATES.items():
        tool_count = len(tmpl["tools"]) if tmpl["tools"] else "全部"
        lines.append(f"  🎭 {key}")
        lines.append(f"     名称: {tmpl['name']}")
        lines.append(f"     描述: {tmpl['description']}")
        lines.append(f"     工具: {tool_count}")
        lines.append("")
    return "\n".join(lines)


class SubAgent:
    """子Agent定义 - 一个专门用途的AI代理"""

    def __init__(
        self,
        name: str,
        system_prompt: str,
        description: str = "",
        tools: list = None,  # 工具名称列表，空列表 = 全量工具
        parent_id: str = None,
        role_template: str = "",  # 角色模板名称
        persistent: bool = True,  # 是否跨会话保持记忆
    ):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.system_prompt = system_prompt
        self.description = description
        self.tools = tools or []
        self.parent_id = parent_id
        self.role_template = role_template
        self.persistent = persistent
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
            "role_template": self.role_template,
            "persistent": self.persistent,
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
            role_template=data.get("role_template", ""),
            persistent=data.get("persistent", True),
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
        # 异步加载 DB 模板（fire-and-forget，模板可用后再用）
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(_load_templates_from_db())
            else:
                loop.run_until_complete(_load_templates_from_db())
        except RuntimeError:
            pass

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
        role_template: str = "",
        persistent: bool = True,
    ) -> SubAgent:
        """创建一个新的子Agent"""
        agent = SubAgent(
            name=name,
            system_prompt=system_prompt,
            description=description,
            tools=tools or [],
            role_template=role_template,
            persistent=persistent,
        )
        self._agents[agent.id] = agent
        self._save()
        return agent

    def create_from_template(self, template_name: str, custom_name: str = "") -> Optional[SubAgent]:
        """从角色模板创建 Agent"""
        template = ROLE_TEMPLATES.get(template_name)
        if not template:
            return None
        name = custom_name or template["name"]
        agent = self.create(
            name=name,
            system_prompt=template["system_prompt"],
            description=template["description"],
            tools=template["tools"],
            role_template=template_name,
            persistent=True,
        )
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
        """删除子Agent（同时清理记忆）"""
        if agent_id in self._agents:
            del self._agents[agent_id]
            self._save()
            # 清理记忆文件
            from agent.agent_memory import delete_agent_memory
            delete_agent_memory(agent_id)
            return True
        return False

    def mark_used(self, agent_id: str):
        """标记子Agent被使用"""
        if agent_id in self._agents:
            self._agents[agent_id].last_used = datetime.now().isoformat()
            self._agents[agent_id].use_count += 1
            self._agents[agent_id].status = "idle"  # 重置状态
            self._save()

    def get_agent_memory_stats(self, agent_id: str) -> dict:
        """获取 Agent 记忆统计"""
        from agent.agent_memory import get_agent_memory
        mem = get_agent_memory(agent_id)
        return mem.get_stats()

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
        """生成Agent工厂报告（含记忆统计）"""
        agents = self.list_all()
        if not agents:
            return "[Agent工厂] 当前没有子Agent。使用 create_sub_agent 来创建。"
        
        from agent.agent_memory import get_agent_memory
        
        lines = [f"[Agent工厂] 共 {len(agents)} 个子Agent:\n"]
        for a in agents:
            status_icon = {"idle": "💤", "running": "🟢", "completed": "✅", "error": "❌"}.get(a.status, "❓")
            role_badge = f" 🎭{a.role_template}" if a.role_template else ""
            lines.append(f"  {status_icon} {a.name} (ID: {a.id}){role_badge}")
            lines.append(f"     描述: {a.description[:60]}")
            tool_label = ', '.join(a.tools) if a.tools else '全部工具'
            lines.append(f"     工具: {tool_label}")
            lines.append(f"     使用次数: {a.use_count} | 持久记忆: {'✅' if a.persistent else '❌'}")
            
            # 记忆统计
            if a.persistent:
                mem = get_agent_memory(a.id)
                stats = mem.get_stats()
                lines.append(f"     记忆: {stats['facts_count']}条事实, {stats['interactions_count']}次交互")
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
