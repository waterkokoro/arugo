"""
联网搜索模块：支持多搜索服务商自动降级
Provider 层 + 自动降级链 + 统一结果格式
"""

import asyncio
import json
import traceback
from typing import Literal
from dataclasses import dataclass, field

import httpx


# ============================================================
# 数据模型
# ============================================================

@dataclass
class SearchResult:
    title: str
    url: str
    content: str


@dataclass
class SearchAttempt:
    provider: str
    status: Literal["ok", "empty", "error"]
    result_count: int = 0
    error: str = ""


@dataclass
class SearchPayload:
    query: str
    results: list[SearchResult] = field(default_factory=list)
    provider: str = "none"
    attempts: list[SearchAttempt] = field(default_factory=list)


# ============================================================
# 超时配置
# ============================================================

SEARCH_TIMEOUT = 30.0  # 秒


# ============================================================
# Provider 层：各搜索服务商 API 调用
# ============================================================

async def search_tavily(query: str, max_results: int, api_key: str) -> list[SearchResult]:
    """Tavily: AI 原生搜索，英文覆盖优"""
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={"query": query, "max_results": max_results},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if resp.status_code in (429, 402):
            raise RuntimeError(f"Tavily API 速率限制: {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
        results = []
        for r in data.get("results", []):
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
            ))
        return results


async def search_serper(query: str, max_results: int, api_key: str) -> list[SearchResult]:
    """Serper: Google 搜索，中文覆盖最好"""
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
        resp = await client.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": max_results},
            headers={"X-API-KEY": api_key},
        )
        if resp.status_code in (429, 402):
            raise RuntimeError(f"Serper API 速率限制: {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
        results = []
        for r in data.get("organic", [])[:max_results]:
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("link", ""),
                content=r.get("snippet", ""),
            ))
        return results


async def search_brave(query: str, max_results: int, api_key: str) -> list[SearchResult]:
    """Brave: 独立索引，隐私友好"""
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": max_results},
            headers={"X-Subscription-Token": api_key},
        )
        if resp.status_code in (429, 402):
            raise RuntimeError(f"Brave API 速率限制: {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
        results = []
        for r in data.get("web", {}).get("results", [])[:max_results]:
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("description", ""),
            ))
        return results


async def search_anysearch_free(query: str, max_results: int) -> list[SearchResult]:
    """AnySearch Free: 匿名免费，无需认证，兜底方案"""
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
        resp = await client.post(
            "https://api.anysearch.com/v1/search",
            json={"q": query, "num": max_results},
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for r in data.get("results", [])[:max_results]:
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", r.get("description", r.get("snippet", ""))),
            ))
        return results


# ============================================================
# Provider 注册表
# ============================================================

PROVIDER_NAMES = ["tavily", "serper", "brave", "anysearch_free"]

PROVIDER_LABELS = {
    "auto": "自动（推荐）",
    "tavily": "Tavily",
    "serper": "Serper (Google)",
    "brave": "Brave",
    "anysearch_free": "AnySearch Free",
}


async def run_provider(
    provider: str, query: str, max_results: int, api_keys: dict
) -> list[SearchResult]:
    """运行指定 Provider 的搜索"""
    if provider == "tavily":
        return await search_tavily(query, max_results, api_keys.get("tavily", ""))
    elif provider == "serper":
        return await search_serper(query, max_results, api_keys.get("serper", ""))
    elif provider == "brave":
        return await search_brave(query, max_results, api_keys.get("brave", ""))
    elif provider == "anysearch_free":
        return await search_anysearch_free(query, max_results)
    else:
        raise ValueError(f"未知 Provider: {provider}")


# ============================================================
# 自动降级链
# ============================================================

async def auto_search(
    query: str,
    max_results: int = 10,
    provider: str = "auto",
    api_keys: dict | None = None,
) -> SearchPayload:
    """
    联网搜索入口，支持 auto 模式和指定 Provider 模式。
    auto 模式：过滤已配置 Key 的 Provider，依次尝试，AnySearch Free 兜底。
    """
    if api_keys is None:
        api_keys = {}

    payload = SearchPayload(query=query)

    if provider == "auto":
        # 构建降级链：有 Key 的 Provider + anysearch_free
        chain = [p for p in PROVIDER_NAMES if p != "anysearch_free" and api_keys.get(p)]
        chain.append("anysearch_free")
    else:
        # 指定 Provider
        chain = [provider]
        # 如果指定 Provider 没有 Key，降级到 auto
        if provider != "anysearch_free" and not api_keys.get(provider):
            chain = [p for p in PROVIDER_NAMES if p != "anysearch_free" and api_keys.get(p)]
            chain.append("anysearch_free")

    for p in chain:
        attempt = SearchAttempt(provider=p, status="error")
        try:
            results = await run_provider(p, query, max_results, api_keys)
            if results:
                attempt.status = "ok"
                attempt.result_count = len(results)
                payload.attempts.append(attempt)
                payload.results = results
                payload.provider = p
                print(f"[WebSearch] {p} 成功，返回 {len(results)} 条结果")
                return payload
            else:
                attempt.status = "empty"
                attempt.result_count = 0
                print(f"[WebSearch] {p} 返回空结果，尝试下一个")
        except Exception as e:
            attempt.status = "error"
            attempt.error = str(e)
            print(f"[WebSearch] {p} 失败: {e}")
        payload.attempts.append(attempt)

    # 全部失败
    payload.provider = "none"
    print(f"[WebSearch] 所有 Provider 均失败")
    return payload


# ============================================================
# API Key 验证
# ============================================================

async def verify_search_key(provider: str, api_key: str) -> bool:
    """验证搜索 API Key 是否有效"""
    if provider == "anysearch_free":
        return True
    try:
        await run_provider(provider, "test", 1, {provider: api_key})
        return True
    except Exception:
        return False


# ============================================================
# 格式化：将搜索结果转为 LLM 可理解的文本
# ============================================================

def format_search_results(payload: SearchPayload) -> str:
    """将搜索结果格式化为编号列表，供 LLM 上下文使用"""
    if not payload.results:
        return "未找到相关搜索结果。"

    lines = [f"[联网搜索结果 (来源: {payload.provider})]\n"]
    for i, r in enumerate(payload.results[:10], 1):
        lines.append(f"{i}. **{r.title}**\n{r.url}\n{r.content}\n")
    return "\n".join(lines)
