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
        settings_dict = {row[0]: row[1] for row in rows}

        return Settings(
            api_key=settings_dict.get("api_key", ""),
            base_url=settings_dict.get("base_url", "https://api.openai.com/v1"),
            model_name=settings_dict.get("model_name", "gpt-3.5-turbo"),
            system_prompt=settings_dict.get("system_prompt", "You are a helpful assistant."),
            context_window_size=int(settings_dict.get("context_window_size", "500")),
            workspace_dir=settings_dict.get("workspace_dir", ""),
            allowed_commands=settings_dict.get("allowed_commands", "ls,cat,head,tail,grep,find,git status,git diff,git log,git add,git commit,python,pip,npm,node,pytest"),
            search_provider=settings_dict.get("search_provider", "auto"),
            search_api_keys=settings_dict.get("search_api_keys", "{}"),
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
        "workspace_dir": settings.workspace_dir,
        "allowed_commands": settings.allowed_commands,
        "search_provider": settings.search_provider,
        "search_api_keys": settings.search_api_keys,
    }

    for key, value in settings_dict.items():
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )

    await db.commit()
    return settings


@router.post("/verify-search-key")
async def verify_search_key(request: VerifyKeyRequest):
    """验证搜索 API Key 是否有效"""
    from agent.web_search import verify_search_key
    valid = await verify_search_key(request.provider, request.api_key)
    return {"valid": valid}
