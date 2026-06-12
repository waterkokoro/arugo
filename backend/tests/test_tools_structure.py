"""测试 tools.py 结构完整性"""

import os
import ast
import sys


TOOLS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agent", "tools.py")


def test_tools_py_exists():
    """tools.py 文件存在"""
    assert os.path.isfile(TOOLS_PATH), f"tools.py 不存在: {TOOLS_PATH}"


def test_tools_py_is_valid_syntax():
    """tools.py 语法有效"""
    with open(TOOLS_PATH, "r") as f:
        code = f.read()
    try:
        ast.parse(code)
    except SyntaxError as e:
        pytest.fail(f"tools.py 语法错误: {e}")


def test_get_tools_function_exists():
    """get_tools() 函数存在"""
    with open(TOOLS_PATH, "r") as f:
        code = f.read()
    assert "def get_tools(" in code, "get_tools() 函数不存在"


def test_all_tools_list_exists():
    """_ALL_TOOLS 列表存在"""
    with open(TOOLS_PATH, "r") as f:
        code = f.read()
    assert "_ALL_TOOLS" in code, "_ALL_TOOLS 列表不存在"


def test_at_least_20_tools():
    """至少有 20 个 @tool 装饰的函数"""
    with open(TOOLS_PATH, "r") as f:
        code = f.read()
    count = code.count("@tool")
    assert count >= 20, f"@tool 数量不足: {count} (预期 >= 20)"


def test_essential_tools_present():
    """核心工具都存在"""
    with open(TOOLS_PATH, "r") as f:
        code = f.read()
    essential = [
        "read_file", "write_file", "edit_file", "list_directory",
        "run_command", "remember", "recall_memory",
        "add_tool_to_self", "git_commit_evolution",
        "create_sub_agent", "invoke_sub_agent",
        "create_goal", "list_goals",
        "create_snapshot", "restore_snapshot",
        "quality_gate_check",
        "run_self_tests", "run_self_diagnostics", "health_check",
    ]
    for func_name in essential:
        assert f"def {func_name}(" in code, f"核心工具缺失: {func_name}"


def test_no_compile_errors_in_tool_functions():
    """检查 @tool 函数的 def 行语法（避免常见错误）"""
    with open(TOOLS_PATH, "r") as f:
        lines = f.readlines()
    errors = []
    in_multiline_def = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("def "):
            if ":" not in stripped and not stripped.endswith(","):
                # 单行定义缺少冒号且不是参数续行
                in_multiline_def = True
            elif ":" in stripped:
                in_multiline_def = False
            continue
        if in_multiline_def:
            if ":" in stripped:
                in_multiline_def = False
            elif stripped.startswith("def ") or stripped.startswith("@") or not stripped:
                # 异常：没有冒号就结束了
                errors.append(f"第{i}行附近: 跨行定义可能缺少冒号")
                in_multiline_def = False
    assert len(errors) == 0, f"函数定义可能有语法问题:\n" + "\n".join(errors)
