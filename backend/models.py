from pydantic import BaseModel, ConfigDict
from typing import Optional


class Settings(BaseModel):
    """配置模型"""
    model_config = ConfigDict(protected_namespaces=())

    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-3.5-turbo"
    system_prompt: str = "You are a helpful assistant."
    # ── 上下文 ──
    context_window_size: int = 500  # 消息历史窗口大小
    context_auto_summarize_threshold: float = 0.8  # 触发自动摘要的窗口占用比例
    # ── Agent 工具安全配置 ──
    workspace_dir: str = ""  # 允许操作的工作目录，空则使用项目根目录
    allowed_commands: str = "ls,cat,head,tail,grep,find,git status,git diff,git log,git add,git commit,python,pip,npm,node,pytest,git init,git remote,git branch,git push,curl"  # 命令白名单
    # ── Agent Loop 参数 ──
    agent_max_iterations: int = 200  # Agent 工具调用最大轮次
    agent_temperature: float = 0.7  # LLM 温度参数
    agent_deep_thinking_default: bool = False  # 默认是否开启深度思考
    agent_web_search_default: bool = True  # 默认是否开启联网搜索
    # ── 联网搜索配置 ──
    search_provider: str = "auto"  # auto / tavily / serper / brave / anysearch_free
    search_api_keys: str = "{}"  # JSON 字符串: {"tavily": "tvly-xxx", "serper": "xxx", "brave": "xxx"}
    # ── 沙盒快照 ──
    snapshot_max_count: int = 20  # 最多保留快照数
    # ── 飞书 ──
    feishu_text_chunk_size: int = 1800  # 飞书回复分段大小
    feishu_queue_maxsize: int = 100  # 飞书消息队列容量
    # ── 质量门禁 ──
    quality_gate_auto_snapshot: bool = True  # 高风险操作前自动快照


class Message(BaseModel):
    """消息模型"""
    id: Optional[int] = None
    role: str
    content: str
    created_at: Optional[str] = None


class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str
