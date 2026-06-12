"""
影子代理模块 (Shadow Broker)
实现蓝绿部署：A(8000) 面向用户，B(8001) 影子验证。
A 改代码 → 重启 B → 测试 B → 通过后 B 重启 A。
"""

import asyncio
import subprocess
import os
import json
import httpx
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANAGE_SCRIPT = PROJECT_ROOT / "manage.sh"


@dataclass
class ShadowStatus:
    """影子服务状态"""
    running: bool = False
    pid: int = 0
    port: int = 8001
    startup_time: str = ""
    last_test_time: str = ""
    last_test_passed: bool = False


_shadow_status = ShadowStatus()


async def _run_manage(cmd: str, timeout: int = 30) -> tuple[bool, str]:
    """执行 manage.sh 命令"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", str(MANAGE_SCRIPT), cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(PROJECT_ROOT)
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        output = stdout.decode().strip() + "\n" + stderr.decode().strip()
        return proc.returncode == 0, output
    except asyncio.TimeoutError:
        return False, f"命令超时 ({timeout}s): {cmd}"
    except Exception as e:
        return False, f"执行失败: {e}"


async def start_shadow() -> dict:
    """启动影子服务 B (8001)"""
    global _shadow_status

    # 先检查是否已在运行
    ok, output = await _run_manage("shadow-status")
    if ok and "运行中" in output:
        _shadow_status.running = True
        return {
            "success": True,
            "message": "影子服务已在运行",
            "port": 8001,
            "output": output
        }

    ok, output = await _run_manage("start-shadow", timeout=60)

    if ok:
        _shadow_status.running = True
        _shadow_status.port = 8001
        _shadow_status.startup_time = datetime.now().isoformat()
        # 等待服务就绪
        await asyncio.sleep(3)
        return {
            "success": True,
            "message": "影子服务已启动",
            "port": 8001,
            "url": "http://localhost:8001",
            "output": output
        }
    else:
        _shadow_status.running = False
        return {
            "success": False,
            "message": "影子服务启动失败",
            "output": output
        }


async def stop_shadow() -> dict:
    """停止影子服务 B"""
    global _shadow_status

    ok, output = await _run_manage("stop-shadow")
    _shadow_status.running = False
    return {
        "success": ok,
        "message": "影子服务已停止" if ok else "停止影子服务失败",
        "output": output
    }


async def test_shadow(test_messages: list[str] = None) -> dict:
    """对影子服务 B 运行核心测试"""
    global _shadow_status

    if test_messages is None:
        test_messages = [
            "你好，请简短回复",
            "列出你能使用的工具",
            "1+1等于几",
        ]

    results = []
    all_passed = True

    # 测试1: 健康检查
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("http://localhost:8001/api/health")
            health_ok = resp.status_code == 200 and resp.json().get("status") == "ok"
            results.append({
                "test": "健康检查 /api/health",
                "passed": health_ok,
                "detail": f"HTTP {resp.status_code}: {resp.json()}"
            })
            if not health_ok:
                all_passed = False
    except Exception as e:
        results.append({
            "test": "健康检查 /api/health",
            "passed": False,
            "detail": f"连接失败: {e}"
        })
        all_passed = False

    # 测试2: 对话功能
    for i, msg in enumerate(test_messages):
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "http://localhost:8001/api/chat",
                    json={"message": msg, "stream": False}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    reply = data.get("reply", "")
                    results.append({
                        "test": f"对话测试 #{i+1}: '{msg}'",
                        "passed": len(reply) > 0,
                        "detail": f"回复: {reply[:200]}..."
                    })
                    if not reply:
                        all_passed = False
                else:
                    results.append({
                        "test": f"对话测试 #{i+1}: '{msg}'",
                        "passed": False,
                        "detail": f"HTTP {resp.status_code}"
                    })
                    all_passed = False
        except Exception as e:
            results.append({
                "test": f"对话测试 #{i+1}: '{msg}'",
                "passed": False,
                "detail": f"请求失败: {e}"
            })
            all_passed = False

    # 测试3: 工具列表
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("http://localhost:8001/api/tools")
            if resp.status_code == 200:
                tools = resp.json()
                tool_count = len(tools) if isinstance(tools, list) else tools.get("count", 0)
                results.append({
                    "test": "工具列表 /api/tools",
                    "passed": tool_count > 0,
                    "detail": f"{tool_count} 个工具可用"
                })
                if tool_count == 0:
                    all_passed = False
            else:
                results.append({
                    "test": "工具列表 /api/tools",
                    "passed": False,
                    "detail": f"HTTP {resp.status_code}"
                })
                all_passed = False
    except Exception as e:
        results.append({
            "test": "工具列表 /api/tools",
            "passed": False,
            "detail": f"请求失败: {e}"
        })
        all_passed = False

    _shadow_status.last_test_time = datetime.now().isoformat()
    _shadow_status.last_test_passed = all_passed

    return {
        "success": all_passed,
        "all_passed": all_passed,
        "passed_count": sum(1 for r in results if r["passed"]),
        "total_count": len(results),
        "results": results,
        "verdict": "✅ 所有测试通过，可以升级" if all_passed else "❌ 存在失败测试，需要修复"
    }


async def promote_shadow() -> dict:
    """B 验证通过 → 重启 A 完成升级"""
    # 先确认 B 测试通过
    test_result = await test_shadow()
    if not test_result["all_passed"]:
        return {
            "success": False,
            "message": "影子服务测试未通过，无法升级",
            "test_result": test_result
        }

    # 重启 A 服务
    ok, output = await _run_manage("restart", timeout=30)

    if ok:
        return {
            "success": True,
            "message": "已重启主服务 A (8000)，升级完成",
            "output": output
        }
    else:
        return {
            "success": False,
            "message": "重启主服务 A 失败！请手动检查",
            "output": output
        }


def get_shadow_status() -> dict:
    """获取影子服务状态"""
    return {
        "running": _shadow_status.running,
        "port": _shadow_status.port,
        "startup_time": _shadow_status.startup_time,
        "last_test_time": _shadow_status.last_test_time,
        "last_test_passed": _shadow_status.last_test_passed,
    }
