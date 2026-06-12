"""测试质量门禁系统"""

import os
import sys
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from agent.quality_gate import QualityGate, GateResult, GateStatus


class TestGateResult:
    """GateResult 数据类测试"""

    def test_gate_result_ok(self):
        r = GateResult(
            status=GateStatus.PASS,
            summary="OK",
        )
        assert r.status == GateStatus.PASS
        assert r.risk_level == "low"

    def test_gate_result_high_risk(self):
        r = GateResult(
            status=GateStatus.WARN,
            summary="高风险操作",
            risk_level="high",
        )
        assert r.status == GateStatus.WARN
        assert r.risk_level == "high"

    def test_gate_result_to_dict(self):
        r = GateResult(
            status=GateStatus.PASS,
            summary="通过",
        )
        d = r.to_dict()
        assert d["status"] == "pass"
        assert d["summary"] == "通过"


class TestQualityGate:
    """质量门禁测试"""

    def test_init(self):
        gate = QualityGate()
        assert gate is not None

    def test_pre_flight_write_file(self):
        """写文件前检查"""
        gate = QualityGate()
        r = gate.pre_flight_check("write_file", "backend/agent/tools.py")
        assert r.status in (GateStatus.PASS, GateStatus.WARN)

    def test_pre_flight_self_modification(self):
        """修改自身代码应有警告"""
        gate = QualityGate()
        r = gate.pre_flight_check("write_file", "backend/agent/tools.py")
        assert r.risk_level in ("medium", "high")

    def test_pre_flight_git_commit(self):
        """Git 提交应通过"""
        gate = QualityGate()
        r = gate.pre_flight_check("git_commit", "evolution")
        assert r.status == GateStatus.PASS

    def test_pre_flight_add_tool(self):
        """添加工具应有警告"""
        gate = QualityGate()
        r = gate.pre_flight_check("add_tool_to_self", "test_tool")
        assert r.risk_level in ("medium", "high")

    def test_post_flight_success(self):
        """操作后检查 - 成功"""
        gate = QualityGate()
        r = gate.post_flight_check("write_file", "写入成功: test.py (100 字符)")
        assert r.status == GateStatus.PASS

    def test_post_flight_error(self):
        """操作后检查 - 错误信号"""
        gate = QualityGate()
        r = gate.post_flight_check("write_file", "error: permission denied")
        assert r.risk_level == "high"

    def test_inline_check_safe_code(self):
        """内联检查 - 安全代码"""
        gate = QualityGate()
        code = '''
@tool
def my_tool() -> str:
    """A safe tool."""
    return "hello"
'''
        r = gate.inline_check(code)
        assert r.status == GateStatus.PASS

    def test_inline_check_dangerous_code(self):
        """内联检查 - 危险代码"""
        gate = QualityGate()
        code = 'os.system("rm -rf /")'
        r = gate.inline_check(code)
        assert r.risk_level in ("high", "critical")

    def test_full_gate_check(self):
        """完整门禁检查"""
        gate = QualityGate()
        full = gate.full_gate_check(
            operation="write_file",
            target="test.py",
            code='print("hello")',
            result="写入成功",
        )
        assert "pre" in full
        assert "inline" in full
        assert "post" in full
        assert full["verdict"] in ("pass", "warn")

    def test_unknown_operation(self):
        """未知操作类型处理"""
        gate = QualityGate()
        r = gate.pre_flight_check("unknown_op", "test")
        assert r.status in (GateStatus.PASS, GateStatus.WARN)

    def test_max_risk_ordering(self):
        """风险等级比较"""
        assert QualityGate._max_risk("low", "medium") == "medium"
        assert QualityGate._max_risk("high", "low") == "high"
        assert QualityGate._max_risk("critical", "high") == "critical"


class TestQualityGateSingleton:
    """单例测试"""

    def test_get_quality_gate_singleton(self):
        from agent.quality_gate import get_quality_gate
        g1 = get_quality_gate()
        g2 = get_quality_gate()
        assert g1 is g2
