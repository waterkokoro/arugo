"""工具结构完整性测试"""

import sys
import os
import ast
import importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _get_tools_module():
    """动态导入 tools 模块"""
    return importlib.import_module("agent.tools")


class TestToolsExist:
    """验证所有核心工具存在"""

    def test_get_tools_function(self):
        """get_tools() 应存在且返回非空列表"""
        tools_mod = _get_tools_module()
        tools = tools_mod.get_tools()
        assert len(tools) > 0, "get_tools() 返回空列表"
        assert len(tools) >= 20, f"工具数量过少: {len(tools)}"

    def test_get_tools_are_langchain_tools(self):
        """返回的应该是 langchain Tool 对象"""
        tools_mod = _get_tools_module()
        tools = tools_mod.get_tools()
        for t in tools:
            assert hasattr(t, "name"), f"工具缺少 name 属性"
            assert hasattr(t, "func") or hasattr(t, "_run"), f"工具 {t.name} 缺少可调用方法"

    def test_all_tool_lists(self):
        """所有工具列表应可迭代"""
        tools_mod = _get_tools_module()
        lists = [
            "_BUILTIN_TOOLS",
            "_MEMORY_TOOLS",
            "_AGENT_FACTORY_TOOLS",
            "_EVOLUTION_TOOLS",
            "_SNAPSHOT_TOOLS",
            "_GOAL_TOOLS",
            "_SEARCH_TOOLS",
            "_ALL_TOOLS",
        ]
        for list_name in lists:
            assert hasattr(tools_mod, list_name), f"缺少工具列表: {list_name}"
            tool_list = getattr(tools_mod, list_name)
            assert isinstance(tool_list, list), f"{list_name} 不是列表"
            assert len(tool_list) > 0, f"{list_name} 为空"


class TestToolStructure:
    """验证工具函数结构"""

    def test_tools_have_docstrings(self):
        """每个工具函数应有文档字符串"""
        tools_mod = _get_tools_module()
        all_tools = tools_mod._ALL_TOOLS
        for t in all_tools:
            name = getattr(t, "name", str(t))
            # LangChain @tool 装饰的函数通过 func 访问
            func = getattr(t, "func", None)
            if func:
                assert func.__doc__, f"工具 {name} 缺少文档字符串"

    def test_no_tool_name_collisions(self):
        """工具名称不应重复"""
        tools_mod = _get_tools_module()
        all_tools = tools_mod._ALL_TOOLS
        names = []
        for t in all_tools:
            name = getattr(t, "name", str(t))
            names.append(name)
        assert len(names) == len(set(names)), f"工具名称重复: {[n for n in names if names.count(n) > 1]}"


class TestToolsPYIntegrity:
    """tools.py 源码完整性"""

    def test_tools_py_is_valid_syntax(self):
        """tools.py 应能通过 AST 解析"""
        tools_path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "tools.py"
        )
        with open(tools_path, "r", encoding="utf-8") as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"tools.py 语法错误: {e}")

    def test_tools_py_has_all_tools(self):
        """tools.py 应包含 _ALL_TOOLS 定义"""
        tools_path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "tools.py"
        )
        with open(tools_path, "r", encoding="utf-8") as f:
            source = f.read()
        assert "_ALL_TOOLS" in source, "tools.py 缺少 _ALL_TOOLS"
        assert "def get_tools(" in source, "tools.py 缺少 get_tools()"

    def test_quality_gate_py_valid(self):
        """quality_gate.py 语法检查"""
        path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "quality_gate.py"
        )
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"quality_gate.py 语法错误: {e}")

    def test_sandbox_py_valid(self):
        """sandbox.py 语法检查"""
        path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "sandbox.py"
        )
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"sandbox.py 语法错误: {e}")


# 为了在缺少 pytest 时 test_goals 模块能引用
try:
    import pytest
except ImportError:
    pass
