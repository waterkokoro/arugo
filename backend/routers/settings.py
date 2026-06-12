from fastapi import APIRouter, Depends
from pydantic import BaseModel
import aiosqlite
from database import get_db
from models import Settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class VerifyKeyRequest(BaseModel):
    provider: str
    api_key: str


@router.get("", response_model=Settings)
async def get_settings(db: aiosqlite.Connection = Depends(get_db)):
    """获取所有配置"""
    async with db.execute("SELECT key, value FROM settings") as cursor:
        rows = await cursor.fetchall()
        s = {row[0]: row[1] for row in rows}

        return Settings(
            api_key=s.get("api_key", ""),
            base_url=s.get("base_url", "https://api.openai.com/v1"),
            model_name=s.get("model_name", "gpt-3.5-turbo"),
            system_prompt=s.get("system_prompt", "You are a helpful assistant."),
            context_window_size=int(s.get("context_window_size", "500")),
            context_auto_summarize_threshold=float(s.get("context_auto_summarize_threshold", "0.8")),
            workspace_dir=s.get("workspace_dir", ""),
            allowed_commands=s.get("allowed_commands", "ls,cat,head,tail,grep,find,git status,git diff,git log,git add,git commit,python,pip,npm,node,pytest"),
            agent_max_iterations=int(s.get("agent_max_iterations", "200")),
            agent_temperature=float(s.get("agent_temperature", "0.7")),
            agent_deep_thinking_default=s.get("agent_deep_thinking_default", "false").lower() in ("true", "1", "yes"),
            agent_web_search_default=s.get("agent_web_search_default", "true").lower() in ("true", "1", "yes"),
            search_provider=s.get("search_provider", "auto"),
            search_api_keys=s.get("search_api_keys", "{}"),
            snapshot_max_count=int(s.get("snapshot_max_count", "20")),
            feishu_text_chunk_size=int(s.get("feishu_text_chunk_size", "1800")),
            feishu_queue_maxsize=int(s.get("feishu_queue_maxsize", "100")),
            quality_gate_auto_snapshot=s.get("quality_gate_auto_snapshot", "true").lower() in ("true", "1", "yes"),
            restrict_paths=s.get("restrict_paths", "true").lower() in ("true", "1", "yes"),
        )


@router.put("", response_model=Settings)
async def update_settings(settings: Settings, db: aiosqlite.Connection = Depends(get_db)):
    """更新配置"""
    settings_dict = {
        "api_key": settings.api_key,
        "base_url": settings.base_url,
        "model_name": settings.model_name,
        "system_prompt": settings.system_prompt,
        "context_window_size": str(settings.context_window_size),
        "context_auto_summarize_threshold": str(settings.context_auto_summarize_threshold),
        "workspace_dir": settings.workspace_dir,
        "allowed_commands": settings.allowed_commands,
        "agent_max_iterations": str(settings.agent_max_iterations),
        "agent_temperature": str(settings.agent_temperature),
        "agent_deep_thinking_default": str(settings.agent_deep_thinking_default).lower(),
        "agent_web_search_default": str(settings.agent_web_search_default).lower(),
        "search_provider": settings.search_provider,
        "search_api_keys": settings.search_api_keys,
        "snapshot_max_count": str(settings.snapshot_max_count),
        "feishu_text_chunk_size": str(settings.feishu_text_chunk_size),
        "feishu_queue_maxsize": str(settings.feishu_queue_maxsize),
        "quality_gate_auto_snapshot": str(settings.quality_gate_auto_snapshot).lower(),
        "restrict_paths": str(settings.restrict_paths).lower(),
    }

    for key, value in settings_dict.items():
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )

    await db.commit()

    # 使 agent config 缓存失效
    from agent.config import _invalidate_cache
    _invalidate_cache()

    return settings


@router.post("/verify-search-key")
async def verify_search_key(request: VerifyKeyRequest):
    """验证搜索 API Key 是否有效"""
    from agent.web_search import verify_search_key
    valid = await verify_search_key(request.provider, request.api_key)
    return {"valid": valid}
