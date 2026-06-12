"""影子代理 API 路由

提供影子服务 B 的启动/停止/测试/升级 REST 接口。
"""

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
