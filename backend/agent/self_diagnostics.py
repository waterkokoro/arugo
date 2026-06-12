"""
自我诊断系统 - Agent 健康检查与自愈建议

定期检查各模块健康状态，生成诊断报告。
诊断结果供 Agent 自身决策参考，也可供 quality_gate 调用。
"""

import os
import json
import shutil
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DiagnosticResult:
    """单次诊断检查结果"""
    check_name: str        # 检查项名称
    status: str            # "ok" | "warn" | "error"
    message: str           # 一句话总结
    details: str = ""      # 详细信息
    suggestions: list = field(default_factory=list)  # 自愈建议
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "check_name": self.check_name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "suggestions": self.suggestions,
            "timestamp": self.timestamp,
        }


class SelfDiagnostics:
    """
    自我诊断引擎。

    不依赖 LLM，完全基于文件系统和模块检查。
    所有检查项独立执行，一个失败不影响后续。
    """

    def __init__(self, workspace_dir: str = None):
        if workspace_dir is None:
            workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.workspace_dir = workspace_dir
        self.agent_dir = os.path.join(os.path.dirname(__file__))

    # ── 核心入口 ──────────────────────────────

    def run_all(self) -> dict:
        """运行全部诊断，返回聚合报告"""
        results = {}
        checks = [
            ("tool_integrity", self.check_tool_integrity),
            ("memory_health", self.check_memory_health),
            ("goal_health", self.check_goal_health),
            ("disk_space", self.check_disk_space),
            ("git_status", self.check_git_status),
            ("feishu_status", self.check_feishu_status),
            ("snapshot_count", self.check_snapshot_count),
        ]

        for name, check_fn in checks:
            try:
                results[name] = check_fn()
            except Exception as e:
                results[name] = DiagnosticResult(
                    check_name=name,
                    status="error",
                    message=f"诊断执行异常: {str(e)}",
                    details=str(e),
                )

        return self._aggregate(results)

    def quick_health(self) -> dict:
        """快速健康检查（只做 <5 秒的轻量检查）"""
        results = {}
        checks = [
            ("tool_integrity", self.check_tool_integrity),
            ("disk_space", self.check_disk_space),
            ("feishu_status", self.check_feishu_status),
        ]

        for name, check_fn in checks:
            try:
                results[name] = check_fn()
            except Exception as e:
                results[name] = DiagnosticResult(
                    check_name=name,
                    status="error",
                    message=f"诊断异常: {str(e)}",
                )

        return self._aggregate(results)

    # ── 各检查项 ──────────────────────────────

    def check_tool_integrity(self) -> DiagnosticResult:
        """检查工具完整性：@tool 函数数、可调用性、注册表一致性"""
        try:
            tools_path = os.path.join(self.agent_dir, "tools.py")
            if not os.path.exists(tools_path):
                return DiagnosticResult(
                    "tool_integrity", "error",
                    "tools.py 文件不存在！",
                    suggestions=["从 git 恢复: git checkout -- backend/agent/tools.py"]
                )

            with open(tools_path, "r") as f:
                code = f.read()

            # 统计 @tool 数量
            tool_count = code.count("@tool")
            # 统计 async def / def 函数数（粗略）
            func_count = code.count("def ")
            async_func_count = code.count("async def ")

            # 检查 _ALL_TOOLS 列表
            if "_ALL_TOOLS" not in code:
                return DiagnosticResult(
                    "tool_integrity", "error",
                    "_ALL_TOOLS 列表缺失，工具可能未正确组装",
                    suggestions=["检查 tools.py 底部 _ALL_TOOLS 定义"]
                )

            # 检查注册表
            try:
                from agent.tool_registry import get_tool_registry
                registry = get_tool_registry()
                registered = len(registry.list_all())
            except Exception:
                registered = -1

            if tool_count >= 30:
                status = "ok"
                msg = f"工具正常：{tool_count} 个 @tool，{func_count} 个函数"
            elif tool_count >= 20:
                status = "ok"
                msg = f"工具正常：{tool_count} 个 @tool"
            else:
                status = "warn"
                msg = f"工具偏少：仅 {tool_count} 个 @tool"

            return DiagnosticResult(
                "tool_integrity", status, msg,
                details=f"@tool: {tool_count}, 函数: {func_count} (async: {async_func_count}), 注册表: {registered}",
                suggestions=[] if status == "ok" else ["检查 tools.py 完整性"]
            )

        except Exception as e:
            return DiagnosticResult(
                "tool_integrity", "error", f"工具检查失败: {str(e)}"
            )

    def check_memory_health(self) -> DiagnosticResult:
        """检查持久记忆健康度"""
        try:
            memory_store = os.path.join(self.agent_dir, "memory_store")
            if not os.path.exists(memory_store):
                return DiagnosticResult(
                    "memory_health", "warn",
                    "memory_store 目录不存在",
                    suggestions=["系统会自动创建，无需手动处理"]
                )

            # 统计记忆文件
            json_files = [f for f in os.listdir(memory_store) if f.endswith(".json")]
            total_size = sum(
                os.path.getsize(os.path.join(memory_store, f))
                for f in json_files
            )

            if not json_files:
                return DiagnosticResult(
                    "memory_health", "ok",
                    "持久记忆已就绪，暂无记忆数据"
                )

            # 尝试读取
            try:
                from agent.memory import MemoryStore
                store = MemoryStore(storage_dir=memory_store)
                entry_count = len(store.entries)
                session_count = len(store.sessions)
            except Exception:
                entry_count = -1
                session_count = -1

            return DiagnosticResult(
                "memory_health", "ok",
                f"记忆健康: {entry_count} 条, {session_count} 个会话, {total_size/1024:.1f}KB",
                details=f"存储位置: {memory_store}"
            )

        except Exception as e:
            return DiagnosticResult(
                "memory_health", "error", f"记忆检查失败: {str(e)}"
            )

    def check_goal_health(self) -> DiagnosticResult:
        """检查目标系统健康度"""
        try:
            goal_store = os.path.join(self.agent_dir, "goal_store")
            if not os.path.exists(goal_store):
                return DiagnosticResult(
                    "goal_health", "warn",
                    "goal_store 目录不存在",
                    suggestions=["系统会自动创建"]
                )

            json_files = [f for f in os.listdir(goal_store) if f.endswith(".json")]
            if not json_files:
                return DiagnosticResult(
                    "goal_health", "ok",
                    "目标系统已就绪，暂无目标"
                )

            try:
                from agent.goal_manager import get_goal_manager
                gm = get_goal_manager()
                goals = gm.list_goals()
                active = [g for g in goals if g.status == "active"]
                completed = [g for g in goals if g.status == "completed"]
                msgs = []
                if active:
                    msgs.append(f"{len(active)} 活跃")
                if completed:
                    msgs.append(f"{len(completed)} 已完成")
                detail = ", ".join(msgs) if msgs else "无活跃目标"
            except Exception:
                detail = "无法解析目标数据"

            return DiagnosticResult(
                "goal_health", "ok",
                f"目标系统正常: {len(json_files)} 个目标文件 ({detail})"
            )

        except Exception as e:
            return DiagnosticResult(
                "goal_health", "error", f"目标检查失败: {str(e)}"
            )

    def check_disk_space(self) -> DiagnosticResult:
        """检查磁盘空间"""
        try:
            usage = shutil.disk_usage(self.workspace_dir)
            free_gb = usage.free / (1024 ** 3)
            total_gb = usage.total / (1024 ** 3)
            percent = usage.used / usage.total * 100

            suggestions = []
            if free_gb < 1:
                status = "error"
                msg = f"磁盘空间严重不足: {free_gb:.1f}GB 可用 / {total_gb:.1f}GB"
                suggestions = ["清理日志和旧快照", "删除 node_modules 和 __pycache__"]
            elif free_gb < 5:
                status = "warn"
                msg = f"磁盘空间偏低: {free_gb:.1f}GB 可用 / {total_gb:.1f}GB"
                suggestions = ["考虑清理旧备份和快照"]
            else:
                status = "ok"
                msg = f"磁盘空间充足: {free_gb:.1f}GB 可用 / {total_gb:.1f}GB ({percent:.0f}%已用)"

            return DiagnosticResult(
                "disk_space", status, msg,
                suggestions=suggestions
            )

        except Exception as e:
            return DiagnosticResult(
                "disk_space", "error", f"磁盘检查失败: {str(e)}"
            )

    def check_git_status(self) -> DiagnosticResult:
        """检查 Git 仓库状态"""
        git_dir = os.path.join(self.workspace_dir, ".git")
        if not os.path.exists(git_dir):
            return DiagnosticResult(
                "git_status", "warn",
                "工作目录不是 Git 仓库或 .git 已损坏",
                suggestions=["git init && git remote add origin <url>"]
            )

        try:
            import subprocess
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            lines = [l for l in result.stdout.strip().split("\n") if l]

            if lines:
                return DiagnosticResult(
                    "git_status", "warn",
                    f"{len(lines)} 个未提交的变更",
                    details="\n".join(lines[:5]),
                    suggestions=["git add -A && git commit -m '<message>'"]
                )
            else:
                return DiagnosticResult(
                    "git_status", "ok",
                    "Git 工作区干净，无未提交变更"
                )

        except Exception as e:
            return DiagnosticResult(
                "git_status", "warn",
                f"Git 检查部分失败: {str(e)}"
            )

    def check_feishu_status(self) -> DiagnosticResult:
        """检查飞书连接状态"""
        status_file = "/tmp/arugo_feishu_status.json"
        if not os.path.exists(status_file):
            return DiagnosticResult(
                "feishu_status", "warn",
                "飞书状态文件不存在，Bot 可能未启动"
            )

        try:
            with open(status_file, "r") as f:
                data = json.load(f)

            connected = data.get("connected", False)
            last_check = data.get("last_check", "")

            if connected:
                return DiagnosticResult(
                    "feishu_status", "ok",
                    f"飞书已连接 {last_check}"
                )
            else:
                return DiagnosticResult(
                    "feishu_status", "warn",
                    f"飞书已断开 ({last_check})",
                    suggestions=[
                        "在 Settings 页面检查 App ID/App Secret 是否填写正确",
                        "在飞书开放平台检查应用的「启用长连接」开关",
                        "点击「重启Bot」按钮重试连接"
                    ]
                )
        except Exception as e:
            return DiagnosticResult(
                "feishu_status", "warn",
                f"飞书状态文件解析失败: {str(e)}"
            )

    def check_snapshot_count(self) -> DiagnosticResult:
        """检查快照数量和空间"""
        snapshot_base = os.path.join(
            os.path.dirname(self.agent_dir), "snapshots"
        )
        # sandbox 里的快照目录可能在 agent/snapshots/
        alt_base = os.path.join(self.agent_dir, "snapshots")

        snap_dir = None
        for d in [snapshot_base, alt_base]:
            if os.path.exists(d):
                snap_dir = d
                break

        if not snap_dir:
            return DiagnosticResult(
                "snapshot_count", "ok",
                "暂无快照记录"
            )

        try:
            entries = [d for d in os.listdir(snap_dir)
                       if os.path.isdir(os.path.join(snap_dir, d))]
            total_size = sum(
                sum(
                    os.path.getsize(os.path.join(root, f))
                    for f in files
                )
                for entry in entries
                for root, dirs, files in os.walk(os.path.join(snap_dir, entry))
                if os.path.exists(os.path.join(snap_dir, entry))
            )

            count_msg = f"{len(entries)} 个快照, {total_size/1024:.1f}KB"
            snap_suggestions = []

            if len(entries) >= 19:
                status = "warn"
                msg = f"快照接近上限: {count_msg} (上限 20)"
                snap_suggestions = ["删除旧快照: delete_snapshot(<id>)"]
            elif len(entries) >= 10:
                status = "ok"
                msg = f"快照数量正常: {count_msg}"
            else:
                status = "ok"
                msg = f"快照空间充足: {count_msg}"

            return DiagnosticResult(
                "snapshot_count", status, msg,
                suggestions=snap_suggestions
            )

        except Exception as e:
            return DiagnosticResult(
                "snapshot_count", "warn",
                f"快照检查部分失败: {str(e)}"
            )

    # ── 聚合 ──────────────────────────────────

    def _aggregate(self, results: dict) -> dict:
        """聚合诊断结果为最终报告"""
        errors = [r for r in results.values() if r.status == "error"]
        warns = [r for r in results.values() if r.status == "warn"]
        oks = [r for r in results.values() if r.status == "ok"]

        # 综合评级
        if errors:
            overall = "error"
            verdict = f"🔴 需要关注: {len(errors)} 项错误, {len(warns)} 项警告"
        elif warns:
            overall = "warn"
            verdict = f"🟡 基本正常: {len(warns)} 项警告"
        else:
            overall = "ok"
            verdict = f"🟢 全部正常: {len(results)} 项通过"

        # 收集自愈建议
        all_suggestions = []
        for r in results.values():
            for s in r.suggestions:
                if s not in all_suggestions:
                    all_suggestions.append(s)

        checks = {k: v.to_dict() for k, v in results.items()}

        return {
            "overall": overall,
            "verdict": verdict,
            "summary": {
                "total": len(results),
                "ok": len(oks),
                "warn": len(warns),
                "error": len(errors),
            },
            "checks": checks,
            "suggestions": all_suggestions,
            "timestamp": datetime.now().isoformat(),
        }


# 全局单例
_instance: Optional[SelfDiagnostics] = None


def get_diagnostics() -> SelfDiagnostics:
    """获取诊断引擎单例"""
    global _instance
    if _instance is None:
        _instance = SelfDiagnostics()
    return _instance
