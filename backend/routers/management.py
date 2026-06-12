"""
管理 REST API —— Phase 5 UI 改造

为前端管理页面提供以下能力的 CRUD 接口：
- /api/templates   → Agent 角色模板（DB 持久化）
- /api/agents      → 子Agent 管理（agent_factory）
- /api/goals       → 目标与里程碑（goal_manager）
- /api/snapshots   → 快照管理（sandbox）
- /api/memories    → 持久记忆（memory）
- /api/evolution   → 进化事件日志
"""

import json as _json
import os
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api", tags=["management"])


# ============================================================
# 辅助：获取 agent db 连接
# ============================================================

import aiosqlite

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "agent.db")


async def _get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


# ============================================================
# 1. Agent 角色模板 API
# ============================================================

class TemplateCreate(BaseModel):
    id: str
    name: str
    description: str = ""
    system_prompt: str
    tools: list[str] = []


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    tools: Optional[list[str]] = None


@router.get("/templates")
async def list_templates():
    """列出所有 Agent 角色模板"""
    db = await _get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT * FROM agent_templates ORDER BY is_builtin DESC, name ASC"
        )
        templates = []
        for row in rows:
            d = dict(row)
            try:
                d["tools"] = _json.loads(d.get("tools", "[]"))
            except Exception:
                d["tools"] = []
            templates.append(d)
        return templates
    finally:
        await db.close()


@router.get("/templates/{template_id}")
async def get_template(template_id: str):
    """获取单个模板详情"""
    db = await _get_db()
    try:
        row = await db.execute_fetchall(
            "SELECT * FROM agent_templates WHERE id = ?", (template_id,)
        )
        if not row:
            raise HTTPException(status_code=404, detail="模板不存在")
        d = dict(row[0])
        try:
            d["tools"] = _json.loads(d.get("tools", "[]"))
        except Exception:
            d["tools"] = []
        return d
    finally:
        await db.close()


@router.post("/templates")
async def create_template(data: TemplateCreate):
    """创建新模板"""
    db = await _get_db()
    try:
        existing = await db.execute_fetchall(
            "SELECT id FROM agent_templates WHERE id = ?", (data.id,)
        )
        if existing:
            raise HTTPException(status_code=409, detail="模板 ID 已存在")
        await db.execute(
            "INSERT INTO agent_templates (id, name, description, system_prompt, tools, is_builtin) VALUES (?, ?, ?, ?, ?, 0)",
            (data.id, data.name, data.description, data.system_prompt, _json.dumps(data.tools)),
        )
        await db.commit()
        return {"status": "ok", "id": data.id}
    finally:
        await db.close()


@router.put("/templates/{template_id}")
async def update_template(template_id: str, data: TemplateUpdate):
    """更新模板"""
    db = await _get_db()
    try:
        existing = await db.execute_fetchall(
            "SELECT * FROM agent_templates WHERE id = ?", (template_id,)
        )
        if not existing:
            raise HTTPException(status_code=404, detail="模板不存在")

        updates = []
        values = []
        if data.name is not None:
            updates.append("name = ?")
            values.append(data.name)
        if data.description is not None:
            updates.append("description = ?")
            values.append(data.description)
        if data.system_prompt is not None:
            updates.append("system_prompt = ?")
            values.append(data.system_prompt)
        if data.tools is not None:
            updates.append("tools = ?")
            values.append(_json.dumps(data.tools))

        if updates:
            updates.append("updated_at = ?")
            values.append(datetime.now().isoformat())
            values.append(template_id)
            await db.execute(
                f"UPDATE agent_templates SET {', '.join(updates)} WHERE id = ?",
                values,
            )
            await db.commit()

        return {"status": "ok"}
    finally:
        await db.close()


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str):
    """删除模板（内置模板不可删除）"""
    db = await _get_db()
    try:
        row = await db.execute_fetchall(
            "SELECT is_builtin FROM agent_templates WHERE id = ?", (template_id,)
        )
        if not row:
            raise HTTPException(status_code=404, detail="模板不存在")
        if row[0]["is_builtin"]:
            raise HTTPException(status_code=403, detail="内置模板不可删除")
        await db.execute("DELETE FROM agent_templates WHERE id = ?", (template_id,))
        await db.commit()
        return {"status": "ok"}
    finally:
        await db.close()


# ============================================================
# 2. 子Agent 管理 API
# ============================================================

@router.get("/agents")
async def list_agents():
    """列出所有子Agent"""
    from agent.agent_factory import get_agent_factory
    factory = get_agent_factory()
    agents = factory.list_all()
    return [a.to_dict() for a in agents]


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """删除子Agent"""
    from agent.agent_factory import get_agent_factory
    factory = get_agent_factory()
    if not factory.delete(agent_id):
        raise HTTPException(status_code=404, detail="子Agent不存在")
    return {"status": "ok"}


# ============================================================
# 3. 目标与里程碑 API
# ============================================================

class GoalCreate(BaseModel):
    title: str
    description: str = ""
    priority: int = 3
    deadline: Optional[str] = None
    tags: list[str] = []


class GoalUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    status: Optional[str] = None
    deadline: Optional[str] = None
    tags: Optional[list[str]] = None


class MilestoneCreate(BaseModel):
    title: str
    completion_criteria: str = ""


class MilestoneUpdate(BaseModel):
    status: Optional[str] = None
    progress: Optional[int] = None


@router.get("/goals")
async def list_goals_api(status: str = ""):
    """列出所有目标"""
    from agent.goal_manager import get_goal_manager
    gm = get_goal_manager()
    goals = gm.list_goals(status=status if status else None)
    return [g.to_dict() for g in goals]


@router.get("/goals/{goal_id}")
async def get_goal(goal_id: str):
    """获取单个目标"""
    from agent.goal_manager import get_goal_manager
    gm = get_goal_manager()
    g = gm.get_goal(goal_id)
    if not g:
        raise HTTPException(status_code=404, detail="目标不存在")
    return g.to_dict()


@router.post("/goals")
async def create_goal_api(data: GoalCreate):
    """创建目标"""
    from agent.goal_manager import get_goal_manager
    gm = get_goal_manager()
    g = gm.create_goal(
        title=data.title,
        description=data.description,
        priority=data.priority,
        deadline=data.deadline,
        tags=data.tags,
    )
    return g.to_dict()


@router.put("/goals/{goal_id}")
async def update_goal_api(goal_id: str, data: GoalUpdate):
    """更新目标"""
    from agent.goal_manager import get_goal_manager
    gm = get_goal_manager()
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    if not kwargs:
        raise HTTPException(status_code=400, detail="无更新字段")
    g = gm.update_goal(goal_id, **kwargs)
    if not g:
        raise HTTPException(status_code=404, detail="目标不存在")
    return g.to_dict()


@router.delete("/goals/{goal_id}")
async def delete_goal_api(goal_id: str):
    """删除目标"""
    from agent.goal_manager import get_goal_manager
    gm = get_goal_manager()
    if not gm.delete_goal(goal_id):
        raise HTTPException(status_code=404, detail="目标不存在")
    return {"status": "ok"}


@router.post("/goals/{goal_id}/milestones")
async def add_milestone_api(goal_id: str, data: MilestoneCreate):
    """添加里程碑"""
    from agent.goal_manager import get_goal_manager
    gm = get_goal_manager()
    m = gm.add_milestone(goal_id, data.title, data.completion_criteria)
    if not m:
        raise HTTPException(status_code=404, detail="目标不存在")
    return m.to_dict()


@router.put("/goals/{goal_id}/milestones/{milestone_id}")
async def update_milestone_api(goal_id: str, milestone_id: str, data: MilestoneUpdate):
    """更新里程碑"""
    from agent.goal_manager import get_goal_manager
    gm = get_goal_manager()
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    if not kwargs:
        raise HTTPException(status_code=400, detail="无更新字段")
    m = gm.update_milestone(goal_id, milestone_id, **kwargs)
    if not m:
        raise HTTPException(status_code=404, detail="目标或里程碑不存在")
    return m.to_dict()


@router.delete("/goals/{goal_id}/milestones/{milestone_id}")
async def delete_milestone_api(goal_id: str, milestone_id: str):
    """删除里程碑"""
    from agent.goal_manager import get_goal_manager
    gm = get_goal_manager()
    if not gm.delete_milestone(goal_id, milestone_id):
        raise HTTPException(status_code=404, detail="目标或里程碑不存在")
    return {"status": "ok"}


# ============================================================
# 4. 快照管理 API
# ============================================================

@router.get("/snapshots")
async def list_snapshots_api():
    """列出所有快照"""
    from agent.sandbox import get_snapshot_manager
    mgr = get_snapshot_manager()
    snapshots = mgr.list_snapshots()
    return [s.to_dict() for s in snapshots]


@router.post("/snapshots")
async def create_snapshot_api(name: str = "", description: str = ""):
    """创建快照"""
    from agent.sandbox import get_snapshot_manager
    mgr = get_snapshot_manager()
    entry = mgr.create_snapshot(name=name, description=description, trigger="manual")
    return entry.to_dict()


@router.post("/snapshots/{snapshot_id}/restore")
async def restore_snapshot_api(snapshot_id: str):
    """恢复快照"""
    from agent.sandbox import get_snapshot_manager
    mgr = get_snapshot_manager()
    success, message = mgr.restore_snapshot(snapshot_id)
    if not success:
        raise HTTPException(status_code=404, detail=message)
    return {"status": "ok", "message": message}


@router.delete("/snapshots/{snapshot_id}")
async def delete_snapshot_api(snapshot_id: str):
    """删除快照"""
    from agent.sandbox import get_snapshot_manager
    mgr = get_snapshot_manager()
    success, message = mgr.delete_snapshot(snapshot_id)
    if not success:
        raise HTTPException(status_code=404, detail=message)
    return {"status": "ok", "message": message}


# ============================================================
# 5. 持久记忆 API
# ============================================================

@router.get("/memories")
async def list_memories(
    query: str = "",
    category: str = "",
    tags: str = "",
    limit: int = 50,
):
    """搜索/列出记忆"""
    from agent.memory import PersistentMemoryManager
    mem = PersistentMemoryManager()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    results = mem.search_memory(
        query=query if query else None,
        category=category if category else None,
        tags=tag_list,
        limit=limit,
    )
    return [r.to_dict() for r in results]


@router.get("/memories/stats")
async def get_memory_stats():
    """记忆统计"""
    from agent.memory import PersistentMemoryManager
    mem = PersistentMemoryManager()
    return mem.get_stats()


@router.get("/memories/categories")
async def get_memory_categories():
    """记忆类别和标签"""
    from agent.memory import PersistentMemoryManager
    mem = PersistentMemoryManager()
    return {
        "categories": mem.get_all_categories(),
        "tags": mem.get_all_tags(),
        "total": mem.count(),
    }


@router.delete("/memories/{entry_id}")
async def delete_memory(entry_id: str):
    """删除记忆"""
    from agent.memory import PersistentMemoryManager
    mem = PersistentMemoryManager()
    if not mem.delete_memory(entry_id):
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"status": "ok"}


# ============================================================
# 6. 进化事件日志 API
# ============================================================

@router.get("/evolution")
async def get_evolution_events(limit: int = 50):
    """获取进化事件日志"""
    from agent.memory import PersistentMemoryManager
    mem = PersistentMemoryManager()
    events = mem.get_evolution_log(limit=limit)
    return events


# ============================================================
# 7. 健康检查 API（Phase 5C）
# ============================================================

@router.get("/health")
async def get_health(smoke: bool = False):
    """运行自我诊断，返回健康报告。
    
    Args:
        smoke: True 则只运行快速检查（<5秒）
    """
    import asyncio
    from agent.self_diagnostics import get_diagnostics
    
    diag = get_diagnostics()
    
    # 在线程池中运行（诊断包含 subprocess 调用）
    loop = asyncio.get_event_loop()
    if smoke:
        report = await loop.run_in_executor(None, diag.quick_health)
    else:
        report = await loop.run_in_executor(None, diag.run_all)
    
    return report


# ============================================================
# 8. 工具清单 API（Phase 5C）
# ============================================================

@router.get("/tools")
async def list_tools_api():
    """列出所有可用工具的清单（名称、描述、类别）"""
    from agent.tool_registry import get_tool_registry
    
    registry = get_tool_registry()
    all_tools = registry.list_all()
    
    # 按类别分组
    categories: dict[str, list[dict]] = {}
    for t in all_tools:
        cat = t.category or "uncategorized"
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({
            "name": t.name,
            "description": t.description or "",
            "category": cat,
            "executable": t.func is not None,
        })
    
    return {
        "total": len(all_tools),
        "executable": sum(1 for t in all_tools if t.func),
        "categories": {k: [t["name"] for t in v] for k, v in categories.items()},
        "tools": [t for cat_list in categories.values() for t in cat_list],
    }


# ============================================================
# 9. 全局概览 API（管理面板首页用）
# ============================================================

@router.get("/overview")
async def get_overview():
    """获取全局管理概览"""
    from agent.memory import PersistentMemoryManager
    from agent.goal_manager import get_goal_manager
    from agent.agent_factory import get_agent_factory
    from agent.sandbox import get_snapshot_manager
    from agent.tool_registry import get_tool_registry

    mem = PersistentMemoryManager()
    gm = get_goal_manager()
    factory = get_agent_factory()
    snap_mgr = get_snapshot_manager()
    registry = get_tool_registry()

    goals = gm.list_goals()
    agents = factory.list_all()
    snapshots = snap_mgr.list_snapshots()
    all_tools = registry.list_all()

    return {
        "memories": {
            "total": mem.count(),
            "categories": len(mem.get_all_categories()),
            "tags": len(mem.get_all_tags()),
        },
        "goals": {
            "total": len(goals),
            "active": sum(1 for g in goals if g.status == "active"),
            "completed": sum(1 for g in goals if g.status == "completed"),
        },
        "agents": {
            "total": len(agents),
            "idle": sum(1 for a in agents if a.status == "idle"),
        },
        "snapshots": {
            "total": len(snapshots),
            "total_size_kb": round(sum(s.total_size for s in snapshots) / 1024, 1),
        },
        "tools": {
            "total": len(all_tools),
            "executable": sum(1 for t in all_tools if t.func),
        },
    }
