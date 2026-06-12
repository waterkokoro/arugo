"""影子代理 API 路由

提供影子服务 B 的启动/停止/测试/升级 REST 接口。
"""

import os
import httpx
from fastapi import APIRouter
from pydantic import BaseModel
from shadow_broker import (
    start_shadow,
    stop_shadow,
    test_shadow,
    promote_shadow,
    get_shadow_status,
)

router = APIRouter(prefix="/api/shadow", tags=["shadow"])


class TestRequest(BaseModel):
    test_messages: list[str] | None = None


@router.post("/start")
async def api_start_shadow():
    """启动影子服务 B (8001)"""
    result = await start_shadow()
    return result


@router.post("/stop")
async def api_stop_shadow():
    """停止影子服务 B"""
    result = await stop_shadow()
    return result


@router.post("/test")
async def api_test_shadow(req: TestRequest = TestRequest()):
    """对影子服务 B 运行核心测试"""
    result = await test_shadow(req.test_messages)
    return result


@router.post("/promote")
async def api_promote_shadow():
    """B 验证通过 → 重启 A 完成升级"""
    result = await promote_shadow()
    return result


@router.get("/status")
async def api_shadow_status():
    """获取影子服务状态"""
    return get_shadow_status()


# ─────────── 主/影子双系统状态查询 ───────────

async def _probe_service(port: int, timeout: float = 3.0) -> dict:
    """探测指定端口上的服务，返回其健康状态"""
    result = {
        "port": port,
        "reachable": False,
        "status": "stopped",
        "tool_count": 0,
        "feishu_connected": False,
        "agent_ready": False,
        "version": "",
        "error": "",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"http://localhost:{port}/api/health")
            if resp.status_code == 200:
                data = resp.json()
                result["reachable"] = True
                result["status"] = data.get("status", "ok")
                result["tool_count"] = data.get("tool_count", 0)
                result["agent_ready"] = data.get("agent_ready", False)

                # 飞书连接状态（仅主服务 8000 有）
                if port == 8000:
                    try:
                        fs_resp = await client.get(f"http://localhost:{port}/api/feishu/status")
                        if fs_resp.status_code == 200:
                            fs_data = fs_resp.json()
                            result["feishu_connected"] = fs_data.get("connected", False)
                    except Exception:
                        pass
    except httpx.ConnectError:
        result["error"] = "连接被拒绝"
    except httpx.TimeoutException:
        result["error"] = "连接超时"
    except Exception as e:
        result["error"] = str(e)[:100]

    return result


@router.get("/dual-status")
async def api_dual_status():
    """获取主服务 A (8000) 和影子服务 B (8001) 的综合状态"""
    is_shadow = os.environ.get("ARUGO_SHADOW", "").lower() in ("true", "1", "yes")

    # 探测自身（当前进程所在端口）
    own_port = 8001 if is_shadow else 8000
    own_status = await _probe_service(own_port)

    # 探测对方
    other_port = 8000 if is_shadow else 8001
    other_status = await _probe_service(other_port)

    return {
        "current_mode": "shadow" if is_shadow else "main",
        "current_port": own_port,
        "main": own_status if own_port == 8000 else other_status,
        "shadow": own_status if own_port == 8001 else other_status,
    }

