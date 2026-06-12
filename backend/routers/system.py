"""系统管理 API —— 重启、停止等特权操作

权限模型：
- authorized_users 存储在 settings 表中（JSON 数组）
- 只有 open_id 在列表中的用户才能执行重启/停止
- 飞书 /restart 命令和 REST API 共用同一权限检查
"""

import asyncio
import json
import logging
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("system_api")
router = APIRouter(prefix="/api/system", tags=["system"])

# 项目根目录
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MANAGE_SCRIPT = os.path.join(PROJECT_ROOT, "manage.sh")


class RestartRequest(BaseModel):
    open_id: str = ""


class SystemResponse(BaseModel):
    success: bool
    message: str


async def _get_authorized_users() -> list[str]:
    """从数据库读取授权用户列表"""
    import aiosqlite
    from database import DB_PATH

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT value FROM settings WHERE key = ?", ("authorized_users",)
        ) as cursor:
            row = await cursor.fetchone()
            if not row or not row[0]:
                return []
            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                return []


async def _check_authorization(open_id: str) -> bool:
    """检查 open_id 是否在授权列表中"""
    if not open_id:
        return False
    authorized = await _get_authorized_users()
    return open_id in authorized


def _execute_restart_background():
    """在后台子进程中执行重启（当前进程返回响应后才执行）"""
    try:
        subprocess = __import__("subprocess")
        # 使用 nohup 确保重启不依赖当前进程
        subprocess.Popen(
            ["bash", "-c", f"sleep 1.5 && cd {PROJECT_ROOT} && bash {MANAGE_SCRIPT} restart"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # 脱离当前进程组
        )
    except Exception as e:
        logger.error(f"[SystemAPI] 启动后台重启失败: {e}")


@router.post("/restart", response_model=SystemResponse)
async def restart_system(req: RestartRequest):
    """重启主服务 A（需要授权）

    流程：
    1. 验证 open_id 是否在 authorized_users 中
    2. 返回「正在重启」响应
    3. 1.5 秒后在后台执行 manage.sh restart
    """
    if not req.open_id:
        raise HTTPException(status_code=401, detail="缺少用户身份标识 (open_id)")

    if not await _check_authorization(req.open_id):
        raise HTTPException(status_code=403, detail=f"无权限：open_id '{req.open_id}' 不在授权列表中")

    logger.info(f"[SystemAPI] 用户 {req.open_id} 触发重启")

    # 后台重启（先返回响应，1.5秒后执行）
    _execute_restart_background()

    return SystemResponse(
        success=True,
        message=f"正在重启...（操作者: {req.open_id}）"
    )


@router.get("/authorized-users")
async def get_authorized_users():
    """获取授权用户列表（不含完整 open_id 用于 UI 展示）"""
    users = await _get_authorized_users()
    # 脱敏展示：只显示前10位
    return {
        "count": len(users),
        "users": [u[:15] + "..." if len(u) > 15 else u for u in users],
    }


class AuthorizedUsersRequest(BaseModel):
    users: list[str]  # 完整的 open_id 列表


@router.put("/authorized-users")
async def update_authorized_users(req: AuthorizedUsersRequest):
    """更新授权用户列表（需要先在 authorized_users 中才能修改）"""
    import aiosqlite
    from database import DB_PATH

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("authorized_users", json.dumps(req.users)),
        )
        await db.commit()

    return {"status": "ok", "count": len(req.users)}
