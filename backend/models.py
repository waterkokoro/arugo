from pydantic import BaseModel, ConfigDict
from typing import Optional


class Settings(BaseModel):
    """配置模型"""
    model_config = ConfigDict(protected_namespaces=())

    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-3.5-turbo"
    system_prompt: str = "You are a helpful assistant."
    context_window_size: int = 500
    # Agent 工具安全配置
    workspace_dir: str = ""  # 允许操作的工作目录，空则使用项目根目录
    allowed_commands: str = "ls,cat,head,tail,grep,find,git status,git diff,git log,git add,git commit,python,pip,npm,node,pytest"  # 命令白名单
    # 联网搜索配置
    search_provider: str = "auto"  # auto / tavily / serper / brave / anysearch_free
    search_api_keys: str = "{}"  # JSON 字符串: {"tavily": "tvly-xxx", "serper": "xxx", "brave": "xxx"}


class Message(BaseModel):
    """消息模型"""
    id: Optional[int] = None
    role: str
    content: str
    created_at: Optional[str] = None


class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str
