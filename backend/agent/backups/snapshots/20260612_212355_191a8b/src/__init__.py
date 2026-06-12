"""Agent 模块 - 包含对话管理、工具、记忆、Agent工厂、目标、沙盒快照、自我诊断和统一配置"""

from agent.context import ContextManager
from agent.llm_client import LLMClient, AgentEvent, stop_stream, reset_stream, get_stop_event
from agent.tools import get_tools, set_tool_config
from agent.memory import PersistentMemoryManager, MemoryStore, SessionSummary
from agent.tool_registry import ToolRegistry, get_tool_registry, reload_tools, validate_tool_code
from agent.agent_factory import AgentFactory, SubAgent, get_agent_factory
from agent.goal_manager import GoalManager, Goal, Milestone, get_goal_manager
from agent.sandbox import SnapshotManager, SnapshotEntry, get_snapshot_manager
from agent.self_diagnostics import SelfDiagnostics, DiagnosticResult, get_diagnostics
from agent.config import (
    get_agent_config, get_agent_config_int, get_agent_config_float,
    get_agent_config_bool, get_all_agent_config, AGENT_CONFIG_DEFAULTS,
)

__all__ = [
    "ContextManager",
    "LLMClient",
    "AgentEvent",
    "stop_stream",
    "reset_stream",
    "get_stop_event",
    "get_tools",
    "set_tool_config",
    "PersistentMemoryManager",
    "MemoryStore",
    "SessionSummary",
    "ToolRegistry",
    "get_tool_registry",
    "reload_tools",
    "validate_tool_code",
    "AgentFactory",
    "SubAgent",
    "get_agent_factory",
    "GoalManager",
    "Goal",
    "Milestone",
    "get_goal_manager",
    "SnapshotManager",
    "SnapshotEntry",
    "get_snapshot_manager",
    "SelfDiagnostics",
    "DiagnosticResult",
    "get_diagnostics",
    "get_agent_config",
    "get_agent_config_int",
    "get_agent_config_float",
    "get_agent_config_bool",
    "get_all_agent_config",
    "AGENT_CONFIG_DEFAULTS",
]
