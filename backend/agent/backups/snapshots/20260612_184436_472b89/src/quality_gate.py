"""
质量门禁系统 - AI 自我审查与风险管理

在关键操作（代码修改、Agent创建、系统配置变更）前后进行验证，
防止错误累积和系统退化。

三阶段检查：
1. PRE-FLIGHT: 操作前的风险评估
2. INLINE: 代码/内容的静态分析
3. POST-FLIGHT: 操作后的健康验证
"""

import json
import hashlib
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class GateStatus(Enum):
    PASS = "pass"        # 通过，可以执行
    WARN = "warn"        # 警告，建议人工确认
    BLOCK = "block"      # 阻断，禁止执行


@dataclass
class GateResult:
    """质量门禁检查结果"""
    status: GateStatus
    summary: str                              # 一句话总结
    issues: list[str] = field(default_factory=list)       # 发现的问题
    suggestions: list[str] = field(default_factory=list)  # 改进建议
    risk_level: str = "low"                   # low / medium / high / critical
    check_id: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.check_id:
            raw = f"{self.timestamp}-{self.summary[:80]}"
            self.check_id = hashlib.md5(raw.encode()).hexdigest()[:10]

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "status": self.status.value,
            "summary": self.summary,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "risk_level": self.risk_level,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GateResult":
        return cls(
            status=GateStatus(data["status"]),
            summary=data["summary"],
            issues=data.get("issues", []),
            suggestions=data.get("suggestions", []),
            risk_level=data.get("risk_level", "low"),
            check_id=data.get("check_id", ""),
            timestamp=data.get("timestamp", ""),
        )


class QualityGate:
    """
    质量门禁核心类。

    不依赖 LLM，完全基于规则和启发式检查。
    这样保证：
    1. 零延迟（不需要额外 API 调用）
    2. 确定性（相同输入始终相同输出）
    3. 不会因 LLM 幻觉而误判
    """

    # 危险模式列表（正则或关键词）
    DANGEROUS_PATTERNS = [
        ("rm -rf", "critical", "检测到递归强制删除命令"),
        ("DROP TABLE", "critical", "检测到数据库删除操作"),
        ("os.remove", "high", "检测到文件删除操作"),
        ("subprocess.call", "high", "检测到子进程调用"),
        ("eval(", "high", "检测到动态代码执行 eval()"),
        ("exec(", "high", "检测到动态代码执行 exec()"),
        ("__import__", "medium", "检测到动态导入"),
        ("while True:", "medium", "检测到无限循环（需确认有退出条件）"),
        ("time.sleep", "low", "检测到同步阻塞调用"),
    ]

    # 代码质量检查模式
    QUALITY_PATTERNS = [
        (r"except\s*:", "medium", "裸 except 会吞掉所有异常，建议指定异常类型"),
        (r"\.save\(\)", "low", "检测到 .save() 调用，确认是否为增量写入"),
        (r"open\([^)]*,\s*['\"]w['\"]", "medium", "检测到文件 w 模式写入，确认不会意外覆盖"),
        (r"import\s+\*", "low", "检测到 import *，建议显式导入"),
    ]

    def pre_flight_check(self, operation: str, target: str, context: dict = None) -> GateResult:
        """
        操作前检查。

        Args:
            operation: 操作类型（如 "write_file", "edit_file", "add_tool_to_self"）
            target: 操作目标（如文件路径、工具名）
            context: 额外上下文信息
        """
        issues = []
        suggestions = []
        risk_level = "low"

        # 检查操作是否涉及敏感文件
        sensitive_paths = [
            "main.py", "__init__.py", "llm_client.py",
            "database.py", "manage.sh", ".git"
        ]
        for sp in sensitive_paths:
            if sp in target:
                risk_level = "high"
                issues.append(f"⚠️ 操作目标涉及敏感文件: {sp}")
                suggestions.append("建议先 self_backup 创建备份")
                break

        # 检查操作类型风险
        if operation in ("edit_file", "write_file"):
            if target.endswith(".py"):
                suggestions.append("建议修改后运行 pytest 验证")
            if "agent" in target.lower():
                risk_level = max(risk_level, "medium")

        if operation == "add_tool_to_self":
            risk_level = max(risk_level, "medium")
            suggestions.append("建议先 validate_tool_syntax 验证语法")
            suggestions.append("建议添加后 hot_reload_tools 热加载")

        # 决定状态
        if risk_level == "critical":
            status = GateStatus.BLOCK
        elif risk_level == "high":
            status = GateStatus.WARN
        else:
            status = GateStatus.PASS

        return GateResult(
            status=status,
            summary=f"PRE-FLIGHT: {operation} → {target} (风险: {risk_level})",
            issues=issues,
            suggestions=suggestions,
            risk_level=risk_level,
        )

    def inline_check(self, code: str, context: dict = None) -> GateResult:
        """
        内联代码检查（静态分析）。

        Args:
            code: 要检查的代码内容
            context: 额外上下文（如文件名、操作类型）
        """
        issues = []
        suggestions = []
        risk_level = "low"

        # 检查危险模式
        for pattern, severity, description in self.DANGEROUS_PATTERNS:
            if pattern.lower() in code.lower():
                issues.append(f"🔴 {description}: 匹配到 '{pattern}'")
                risk_level = max(risk_level, severity)

        # 检查代码质量模式
        import re
        for pattern_str, severity, description in self.QUALITY_PATTERNS:
            if re.search(pattern_str, code):
                issues.append(f"🟡 {description}: 匹配到 '{pattern_str}'")
                risk_level = max(risk_level, severity)

        # 基本安全检查
        if "password" in code.lower() or "secret" in code.lower() or "api_key" in code.lower():
            issues.append("🔴 检测到可能的硬编码凭证！建议使用环境变量")
            risk_level = "critical"

        # 结构检查
        if "def " in code and "return" not in code:
            suggestions.append("💡 函数可能缺少 return 语句")

        # 决定状态
        if risk_level == "critical":
            status = GateStatus.BLOCK
        elif risk_level == "high":
            status = GateStatus.WARN
        elif issues:
            status = GateStatus.WARN
        else:
            status = GateStatus.PASS

        return GateResult(
            status=status,
            summary=f"INLINE: 扫描 {len(code)} 字符代码 (风险: {risk_level})",
            issues=issues,
            suggestions=suggestions,
            risk_level=risk_level,
        )

    def post_flight_check(self, operation: str, result: str, context: dict = None) -> GateResult:
        """
        操作后验证。

        Args:
            operation: 已执行的操作类型
            result: 操作结果描述
            context: 额外上下文
        """
        issues = []
        suggestions = []
        risk_level = "low"

        # 检查操作结果中的异常信号
        error_signals = [
            ("error", "操作结果中包含 'error' 信号"),
            ("traceback", "操作结果中包含异常堆栈"),
            ("permission denied", "权限被拒绝"),
            ("not found", "目标未找到"),
            ("failed", "操作失败信号"),
        ]
        for signal, description in error_signals:
            if signal in result.lower():
                issues.append(f"⚠️ {description}")
                risk_level = "high"

        # 操作后的健康建议
        if operation in ("write_file", "edit_file", "add_tool_to_self"):
            suggestions.append("建议运行相关测试验证修改正确性")
            suggestions.append("修改已写入磁盘，重启后生效")

        if "git" in operation:
            suggestions.append("确认 git 状态: git status && git log --oneline -3")

        if risk_level == "high":
            status = GateStatus.WARN
        else:
            status = GateStatus.PASS

        return GateResult(
            status=status,
            summary=f"POST-FLIGHT: {operation} 完成 (风险: {risk_level})",
            issues=issues,
            suggestions=suggestions,
            risk_level=risk_level,
        )

    def full_gate_check(
        self,
        operation: str,
        target: str = "",
        code: str = "",
        result: str = "",
        context: dict = None,
        auto_snapshot: bool = True,
    ) -> dict:
        """
        执行完整的三阶段质量门禁检查。

        Args:
            operation: 操作类型
            target: 操作目标
            code: 代码内容（用于 inline 检查）
            result: 操作结果（用于 post 检查）
            context: 额外上下文
            auto_snapshot: 高风险操作前是否自动创建快照（默认 True）

        Returns:
            {
                "pre": GateResult.to_dict(),
                "inline": GateResult.to_dict() | None,
                "post": GateResult.to_dict(),
                "snapshot_id": str | None,   # 自动快照 ID
                "verdict": "pass" | "warn" | "block",
                "blocked_reason": str | None,
            }
        """
        pre = self.pre_flight_check(operation, target, context)
        inline = self.inline_check(code, context) if code else None
        post = self.post_flight_check(operation, result, context)

        # 综合判定
        all_results = [pre]
        if inline:
            all_results.append(inline)
        all_results.append(post)

        # 自动快照：中等及以上风险操作前创建快照
        snapshot_id = None
        if auto_snapshot and pre.risk_level in ("medium", "high", "critical"):
            try:
                from agent.sandbox import get_snapshot_manager
                mgr = get_snapshot_manager()
                entry = mgr.pre_flight_snapshot(operation, target)
                if entry:
                    snapshot_id = entry.id
            except Exception as e:
                print(f"[QualityGate] Auto-snapshot failed: {e}")

        result_dict = {
            "pre": pre.to_dict(),
            "inline": inline.to_dict() if inline else None,
            "post": post.to_dict(),
            "snapshot_id": snapshot_id,
        }

        # 任一 BLOCK 则整体 BLOCK
        for r in all_results:
            if r.status == GateStatus.BLOCK:
                result_dict["verdict"] = "block"
                result_dict["blocked_reason"] = r.summary
                return result_dict

        # 任一 WARN 则整体 WARN
        for r in all_results:
            if r.status == GateStatus.WARN:
                result_dict["verdict"] = "warn"
                result_dict["blocked_reason"] = None
                return result_dict

        result_dict["verdict"] = "pass"
        result_dict["blocked_reason"] = None
        return result_dict


# 全局单例
_gate_instance: Optional[QualityGate] = None


def get_quality_gate() -> QualityGate:
    """获取质量门禁单例"""
    global _gate_instance
    if _gate_instance is None:
        _gate_instance = QualityGate()
    return _gate_instance
