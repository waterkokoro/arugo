"""
Phase 5A: 自动化测试运行器

提供 AI 可自我触发的测试能力：
- run_all_tests(): 运行全部测试套件
- run_module_tests(module): 运行指定模块测试
- quick_smoke_test(): 快速烟雾测试（5秒内完成）
- get_test_summary(): 获取最近的测试摘要
"""

import os
import json
import subprocess
import sys
from datetime import datetime
from typing import Optional

# 测试目录
TESTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests")

# 测试结果缓存
_RESULTS_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "memory_store",
    "last_test_results.json",
)


def run_pytest(args: list[str] = None, timeout: int = 120) -> dict:
    """执行 pytest 并返回结构化结果

    Args:
        args: 传递给 pytest 的额外参数
        timeout: 超时秒数

    Returns:
        {
            "success": bool,
            "passed": int,
            "failed": int,
            "errors": int,
            "duration": float,
            "output": str,
            "timestamp": str,
        }
    """
    if args is None:
        args = []

    # 构建命令：所有测试
    cmd = [
        sys.executable, "-m", "pytest",
        TESTS_DIR,
        "-v",
        "--tb=short",
        "--no-header",
        "-p", "no:warnings",
    ] + args

    start = datetime.now()
    try:
        result = subprocess.run(
            cmd,
            cwd=os.path.dirname(TESTS_DIR),  # backend/
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = (datetime.now() - start).total_seconds()
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "duration": timeout,
            "output": f"测试超时（>{timeout}秒）",
            "timestamp": datetime.now().isoformat(),
        }

    output = result.stdout + "\n" + result.stderr if result.stderr else result.stdout

    # 解析 pytest 输出
    passed = 0
    failed = 0
    errors = 0

    for line in output.split("\n"):
        if " passed" in line and "=" in line:
            # 格式: "====== 20 passed in 1.23s ======"
            try:
                parts = line.strip("= ")
                # e.g. "20 passed in 1.23s"
                for part in parts.split(","):
                    part = part.strip()
                    if "passed" in part:
                        passed = int(part.split()[0])
                    elif "failed" in part:
                        failed = int(part.split()[0])
                    elif "error" in part:
                        errors = int(part.split()[0])
            except (ValueError, IndexError):
                pass

    success = result.returncode == 0

    test_result = {
        "success": success,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "duration": round(duration, 2),
        "output": output.strip(),
        "timestamp": datetime.now().isoformat(),
        "exit_code": result.returncode,
    }

    # 缓存结果
    _cache_results(test_result)

    return test_result


def run_module_tests(module: str, timeout: int = 60) -> dict:
    """运行指定测试模块

    Args:
        module: 模块名，如 "quality_gate", "sandbox", "memory", "goals", "tools"
        timeout: 超时秒数
    """
    module_map = {
        "quality_gate": "test_quality_gate.py",
        "sandbox": "test_sandbox.py",
        "memory": "test_memory.py",
        "goals": "test_goals.py",
        "tools": "test_tools_structure.py",
    }

    test_file = module_map.get(module)
    if not test_file:
        return {
            "success": False,
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "duration": 0,
            "output": f"未知测试模块: {module}。可用: {', '.join(module_map.keys())}",
            "timestamp": datetime.now().isoformat(),
        }

    test_path = os.path.join(TESTS_DIR, test_file)
    if not os.path.isfile(test_path):
        return {
            "success": False,
            "output": f"测试文件不存在: {test_file}",
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "duration": 0,
            "timestamp": datetime.now().isoformat(),
        }

    return run_pytest([test_path], timeout=timeout)


def quick_smoke_test() -> dict:
    """快速烟雾测试：只跑最重要的结构性测试（<5秒）"""
    return run_pytest(
        [
            os.path.join(TESTS_DIR, "test_tools_structure.py"),
            "-k", "test_tools_py_is_valid_syntax or test_get_tools_function",
            "--tb=line",
        ],
        timeout=15,
    )


def _cache_results(result: dict):
    """缓存最近一次测试结果"""
    try:
        os.makedirs(os.path.dirname(_RESULTS_CACHE_FILE), exist_ok=True)
        with open(_RESULTS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_last_results() -> Optional[dict]:
    """获取最近的测试结果"""
    if os.path.exists(_RESULTS_CACHE_FILE):
        try:
            with open(_RESULTS_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return None


def format_test_summary(result: dict) -> str:
    """格式化测试结果为可读报告"""
    if result["success"]:
        icon = "✅"
        verdict = "全部通过"
    else:
        icon = "❌"
        verdict = "存在失败"

    lines = [
        f"{icon} 测试结果: {verdict}",
        f"   通过: {result['passed']} | 失败: {result['failed']} | 错误: {result['errors']}",
        f"   耗时: {result['duration']}秒",
        f"   时间: {result['timestamp'][:19]}",
    ]

    # 提取失败的测试名称
    output = result.get("output", "")
    if output and ("FAILED" in output or "ERROR" in output):
        lines.append(f"\n📋 详情:")
        for line in output.split("\n"):
            if "FAILED" in line or "ERROR" in line:
                lines.append(f"   {line.strip()}")

    return "\n".join(lines)
