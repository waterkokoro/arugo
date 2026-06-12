"""pytest 配置 & fixtures"""

import sys
import os
import pytest
import tempfile
import shutil

# 确保 backend/ 在 sys.path 中
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


@pytest.fixture
def temp_agent_dir():
    """创建临时 agent 目录用于测试"""
    tmp = tempfile.mkdtemp(prefix="arugo_test_")
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def sample_tool_code():
    """返回一个合法的 @tool 函数代码示例"""
    return '''
@tool
def sample_test_tool(query: str) -> str:
    """A sample tool for testing.

    Args:
        query: a test query
    """
    return f"Result: {query}"
'''


@pytest.fixture
def bad_tool_code_syntax():
    """返回一个有语法错误的代码"""
    return '''
@tool
def bad_tool(query: str -> str:  # 语法错误
    """Bad tool"""
    return query
'''


@pytest.fixture
def bad_tool_code_dangerous():
    """返回一个包含危险操作的代码"""
    return '''
@tool
def dangerous_tool(cmd: str) -> str:
    """Dangerous tool"""
    import os
    os.system(f"rm -rf {cmd}")
    return "done"
'''
