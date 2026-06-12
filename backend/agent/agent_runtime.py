"""
Agent 运行时 — 让子 Agent 拥有完整的 Tool Calling 循环

与主 Agent 的 agent_stream 不同，AgentRuntime：
- 为子 Agent 独立运行工具调用循环
- 可配置专属工具集（而非全量工具）
- 自动注入 Agent 专属记忆
- 结果自动记录到 AgentMemory
"""

import json
import uuid
import asyncio
import traceback
from typing import AsyncGenerator, Optional
from dataclasses import dataclass, field
from openai import AsyncOpenAI

from agent.tools import get_tools, get_tool_config
from agent.agent_memory import get_agent_memory


@dataclass
class AgentEvent:
    """Agent 执行事件"""
    type: str  # content, thinking, tool_call, tool_result, error, done
    content: str = ""
    tool: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_result: str = ""
    call_id: str = ""

    def to_dict(self) -> dict:
        d = {"type": self.type, "content": self.content}
        if self.tool:
            d["tool"] = self.tool
        if self.tool_args:
            d["tool_args"] = self.tool_args
        if self.tool_result:
            d["tool_result"] = self.tool_result
        if self.call_id:
            d["call_id"] = self.call_id
        return d


class AgentRuntime:
    """子 Agent 运行时 — 完整工具调用循环"""

    def __init__(
        self,
        agent_name: str,
        agent_id: str,
        system_prompt: str,
        tool_names: list[str] = None,
        max_iterations: int = 50,
    ):
        self.agent_name = agent_name
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.tool_names = tool_names or []  # 空列表 = 全量工具
        self.max_iterations = max_iterations
        self.memory = get_agent_memory(agent_id)

    def _build_system_prompt(self) -> str:
        """构建完整的 system prompt（含记忆注入）"""
        parts = [self.system_prompt]

        # 注入 Agent 专属记忆
        memory_context = self.memory.get_context_injection()
        if memory_context:
            parts.append(memory_context)

        return "\n\n---\n".join(parts)

    def _get_tools(self, web_search_enabled: bool = True) -> list:
        """获取子 Agent 的工具集"""
        all_tools = get_tools(web_search_enabled=web_search_enabled)
        tool_map = {t.name: t for t in all_tools}

        if not self.tool_names:
            # 空列表 = 使用全部工具
            return all_tools

        # 按名称筛选
        selected = []
        for name in self.tool_names:
            if name in tool_map:
                selected.append(tool_map[name])
        return selected

    async def run(self, task: str, config: dict = None) -> AsyncGenerator[AgentEvent, None]:
        """运行 Agent 工具调用循环

        Args:
            task: 委派给子 Agent 的任务
            config: LLM 配置（api_key, base_url, model_name），默认使用主配置
        """
        if config is None:
            config = get_tool_config()

        system_prompt = self._build_system_prompt()
        tools = self._get_tools()
        tool_map = {t.name: t for t in tools}

        print(f"[AgentRuntime:{self.agent_name}] 启动，工具: {[t.name for t in tools]}")

        # 构建 OpenAI 工具定义
        openai_tools = []
        for tool in tools:
            try:
                schema = tool.args_schema.schema() if hasattr(tool, 'args_schema') else {}
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": schema,
                    }
                })
            except Exception as e:
                print(f"[AgentRuntime] 工具 schema 失败: {tool.name}: {e}")

        # 初始消息
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        # 创建 LLM 客户端
        client = AsyncOpenAI(
            api_key=config.get("api_key", ""),
            base_url=config.get("base_url", "https://api.openai.com/v1"),
        )

        iteration = 0
        final_result = ""

        while iteration < self.max_iterations:
            iteration += 1
            print(f"[AgentRuntime:{self.agent_name}] 第 {iteration} 轮...")

            try:
                stream = await client.chat.completions.create(
                    model=config.get("model_name", "gpt-3.5-turbo"),
                    messages=messages,
                    tools=openai_tools if openai_tools else None,
                    stream=True,
                    temperature=0.7,
                )

                # 收集响应
                content = ""
                tool_calls = []

                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta

                    if delta.content:
                        content += delta.content

                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            while len(tool_calls) <= tc.index:
                                tool_calls.append({"id": "", "function": {"name": "", "arguments": ""}})
                            if tc.id:
                                tool_calls[tc.index]["id"] = tc.id
                            if tc.function and tc.function.name:
                                tool_calls[tc.index]["function"]["name"] += tc.function.name
                            if tc.function and tc.function.arguments:
                                tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments

                # 构建 assistant 消息
                assistant_msg = {"role": "assistant", "content": content}
                if tool_calls:
                    assistant_msg["tool_calls"] = [
                        {"id": tc["id"], "type": "function", "function": tc["function"]}
                        for tc in tool_calls
                    ]
                messages.append(assistant_msg)

                # 没有工具调用 = Agent 认为任务完成
                if not tool_calls:
                    final_result = content
                    if content:
                        yield AgentEvent(type="content", content=content)
                    yield AgentEvent(type="done")
                    break

                # 执行工具调用
                for tc in tool_calls:
                    tool_name = tc["function"]["name"]
                    call_id = tc["id"] or str(uuid.uuid4())

                    try:
                        tool_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        tool_args = {}

                    print(f"[AgentRuntime:{self.agent_name}] 调用: {tool_name}")

                    yield AgentEvent(
                        type="tool_call",
                        tool=tool_name,
                        tool_args=tool_args,
                        call_id=call_id,
                    )

                    # 执行工具
                    if tool_name in tool_map:
                        try:
                            tool = tool_map[tool_name]
                            result = await tool.ainvoke(tool_args)
                            yield AgentEvent(
                                type="tool_result",
                                tool=tool_name,
                                tool_result=str(result)[:2000],
                                call_id=call_id,
                            )
                            messages.append({
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": str(result),
                            })
                        except Exception as e:
                            error_msg = f"工具执行失败: {str(e)}"
                            print(f"[AgentRuntime] {tool_name} 失败: {e}")
                            traceback.print_exc()
                            yield AgentEvent(
                                type="tool_result",
                                tool=tool_name,
                                tool_result=error_msg,
                                call_id=call_id,
                            )
                            messages.append({
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": error_msg,
                            })
                    else:
                        error_msg = f"未知工具: {tool_name}"
                        yield AgentEvent(
                            type="tool_result",
                            tool=tool_name,
                            tool_result=error_msg,
                            call_id=call_id,
                        )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": error_msg,
                        })

            except Exception as e:
                error_msg = f"Agent 执行异常: {str(e)}"
                print(f"[AgentRuntime:{self.agent_name}] {error_msg}")
                traceback.print_exc()
                yield AgentEvent(type="error", content=error_msg)
                yield AgentEvent(type="done")
                # 记录失败交互
                self.memory.log_interaction(task, error_msg, success=False)
                return

        # 达到上限
        if iteration >= self.max_iterations:
            yield AgentEvent(
                type="error",
                content=f"工具调用轮次超过上限 ({self.max_iterations})",
            )

        # 记录交互
        self.memory.log_interaction(task, final_result[:300] if final_result else "(无文本输出)", success=True)
        yield AgentEvent(type="done")
