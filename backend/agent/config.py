"""
统一配置读取层 — 所有模块通过此模块从 SQLite settings 表获取参数。

设计原则：
- 零依赖：仅依赖 aiosqlite + database.DB_PATH
- 轻量：每次调用独立连接，无连接池
- 防错：所有函数都有默认值，DB 异常时返回默认值
- 单点：所有硬编码参数集中管理

Usage:
    from agent.config import get_agent_config, AGENT_CONFIG_KEYS

    max_iter = await get_agent_config("agent_max_iterations", 200)
"""

import aiosqlite
import os

# DB_PATH 相对于 backend/database.py
_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agent.db")

# ── 全局缓存（避免每次调用都读 DB）──
_cache: dict = {}
_cache_loaded = False


async def _load_all_settings() -> dict:
    """一次性加载所有 settings 到内存缓存"""
    global _cache, _cache_loaded
    try:
        async with aiosqlite.connect(_DB_PATH) as db:
            async with db.execute("SELECT key, value FROM settings") as cursor:
                rows = await cursor.fetchall()
                _cache = {row[0]: row[1] for row in rows}
        _cache_loaded = True
    except Exception:
        if not _cache_loaded:
            _cache = {}
    return _cache


def _invalidate_cache():
    """使缓存失效（配置更新后调用）"""
    global _cache_loaded
    _cache_loaded = False


# ── 配置键定义与默认值 ──

AGENT_CONFIG_DEFAULTS = {
    # Agent Loop
    "agent_max_iterations": "200",           # Agent 工具调用最大轮次
    "agent_temperature": "0.7",              # LLM 温度参数
    "agent_deep_thinking_default": "false",  # 默认是否开启深度思考
    "agent_web_search_default": "true",      # 默认是否开启联网搜索

    # 上下文与记忆
    "context_window_size": "500",            # 消息历史窗口大小
    "context_auto_summarize_threshold": "0.8",  # 触发自动摘要的窗口占用比例

    # 沙盒快照
    "snapshot_max_count": "20",              # 最多保留快照数

    # 飞书
    "feishu_text_chunk_size": "1800",        # 飞书回复分段大小
    "feishu_queue_maxsize": "100",           # 飞书消息队列容量

    # 质量门禁
    "quality_gate_auto_snapshot": "true",    # 高风险操作前自动快照
}

# ── 公共 API ──


async def get_agent_config(key: str, default=None):
    """获取单个配置值（带默认值）

    Args:
        key: 配置键名，如 "agent_max_iterations"
        default: 默认值（从 AGENT_CONFIG_DEFAULTS 取）

    Returns:
        str: 配置值（始终为字符串，调用方自行转换类型）
    """
    if not _cache_loaded:
        await _load_all_settings()

    if default is None:
        default = AGENT_CONFIG_DEFAULTS.get(key, "")

    return _cache.get(key, default)


async def get_agent_config_int(key: str, default: int = 0) -> int:
    """获取整数配置"""
    val = await get_agent_config(key)
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


async def get_agent_config_float(key: str, default: float = 0.0) -> float:
    """获取浮点数配置"""
    val = await get_agent_config(key)
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


async def get_agent_config_bool(key: str, default: bool = False) -> bool:
    """获取布尔配置"""
    val = await get_agent_config(key)
    return val.lower() in ("true", "1", "yes", "on")


async def get_all_agent_config() -> dict:
    """获取所有 Agent 配置（用于 Settings API）"""
    result = {}
    for key in AGENT_CONFIG_DEFAULTS:
        result[key] = await get_agent_config(key)
    return result
