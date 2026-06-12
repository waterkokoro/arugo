"""质量门禁测试"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.quality_gate import QualityGate, GateStatus


def test_pre_flight_pass():
    """常规操作应通过"""
    gate = QualityGate()
    r = gate.pre_flight_check("read_file", "tools.py")
    assert r.status == GateStatus.PASS
    assert r.risk_level == "low"


def test_pre_flight_warn_sensitive():
    """修改敏感文件应产生警告"""
    gate = QualityGate()
    r = gate.pre_flight_check("write_file", "main.py")
    assert r.status == GateStatus.WARN
    assert r.risk_level == "high"


def test_pre_flight_add_tool():
    """添加工具应产生警告"""
    gate = QualityGate()
    r = gate.pre_flight_check("add_tool_to_self", "new_tool")
    assert r.status == GateStatus.WARN
    assert r.risk_level in ("medium", "high")


def test_inline_safe_code():
    """安全代码应通过"""
    gate = QualityGate()
    r = gate.inline_check("def hello(): return 'world'")
    assert r.status == GateStatus.PASS


def test_inline_dangerous_code():
    """危险代码应被阻断"""
    gate = QualityGate()
    r = gate.inline_check("os.system('rm -rf /')")
    assert r.status in (GateStatus.WARN, GateStatus.BLOCK)
    assert r.risk_level in ("high", "critical")


def test_inline_hardcoded_credential():
    """硬编码凭证应被阻断"""
    gate = QualityGate()
    r = gate.inline_check("api_key = 'sk-abc123secret'")
    assert r.status == GateStatus.BLOCK
    assert r.risk_level == "critical"


def test_inline_bare_except():
    """裸 except 应被标记"""
    gate = QualityGate()
    r = gate.inline_check("try:\n    foo()\nexcept:\n    pass")
    assert r.status == GateStatus.WARN


def test_post_flight_success():
    """成功操作应通过"""
    gate = QualityGate()
    r = gate.post_flight_check("write_file", "成功写入文件: /tmp/test.py (100 字符)")
    assert r.status == GateStatus.PASS


def test_post_flight_error():
    """错误结果应警告"""
    gate = QualityGate()
    r = gate.post_flight_check("edit_file", "error: content not found in file")
    assert r.status == GateStatus.WARN


def test_full_gate_pass():
    """完整门禁通过"""
    gate = QualityGate()
    result = gate.full_gate_check(
        operation="read_file",
        target="tools.py",
        code="",
        result="文件读取成功",
        auto_snapshot=False,  # 测试中不创建快照
    )
    assert result["verdict"] == "pass"


def test_full_gate_warn():
    """完整门禁警告"""
    gate = QualityGate()
    result = gate.full_gate_check(
        operation="write_file",
        target="main.py",
        code="",
        result="写入成功",
        auto_snapshot=False,
    )
    assert result["verdict"] == "warn"


def test_full_gate_block():
    """完整门禁阻断"""
    gate = QualityGate()
    result = gate.full_gate_check(
        operation="add_tool_to_self",
        target="dangerous_tool",
        code="api_key = 'sk-secret'\nos.system('rm -rf /')",
        result="",
        auto_snapshot=False,
    )
    assert result["verdict"] == "block"


def test_gate_result_serialization():
    """GateResult 应正确序列化"""
    gate = QualityGate()
    r = gate.pre_flight_check("read_file", "test.py")
    d = r.to_dict()
    assert "status" in d
    assert "summary" in d
    assert "check_id" in d
    assert len(d["check_id"]) == 10
