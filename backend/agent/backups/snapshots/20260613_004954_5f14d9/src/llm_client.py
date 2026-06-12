"""基于 LangChain 的 LLM 客户端，支持 Tool Calling、Agent Loop 和 DeepSeek 思考模式"""

from typing import AsyncGenerator, Literal
from dataclasses import dataclass, field
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from openai import AsyncOpenAI
import aiosqlite
import json
import uuid
import asyncio
import traceback

from agent.tools import get_tools, set_tool_config


# ============================================================
# 停止控制器 - 用于中止正在进行的 Agent 流
# ============================================================

_active_streams: dict[str, asyncio.Event] = {}


def get_stop_event(session_id: str = "default") -> asyncio.Event:
    """获取或创建停止事件"""
    if session_id not in _active_streams:
        _active_streams[session_id] = asyncio.Event()
    return _active_streams[session_id]


def stop_stream(session_id: str = "default") -> bool:
    """停止指定会话的流"""
    if session_id in _active_streams:
        _active_streams[session_id].set()
        return True
    return False


def reset_stream(session_id: str = "default"):
    """重置停止事件（开始新对话时调用）"""
    _active_streams[session_id] = asyncio.Event()


# Agent 事件类型
@dataclass
class AgentEvent:
    """Agent 执行过程中的事件"""
    type: Literal["content", "thinking", "tool_call", "tool_result", "diff", "error", "done", "working"]
    content: str = ""
    tool: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_result: str = ""
    call_id: str = ""
    diff_old: str = ""
    diff_new: str = ""
    diff_path: str = ""
    iteration: int = 0          # 当前 LLM 轮次（tool_call / tool_result 时有效）
    total_tool_calls: int = 0   # 累计已调用工具数

    def to_dict(self) -> dict:
        """转换为字典，过滤空字段"""
        d = {
            "type": self.type,
            "content": self.content,
        }
        if self.tool:
            d["tool"] = self.tool
        if self.tool_args:
            d["tool_args"] = self.tool_args
        if self.tool_result:
            d["tool_result"] = self.tool_result
        if self.call_id:
            d["call_id"] = self.call_id
        if self.diff_old:
            d["diff_old"] = self.diff_old
        if self.diff_new:
            d["diff_new"] = self.diff_new
        if self.diff_path:
            d["diff_path"] = self.diff_path
        if self.iteration:
            d["iteration"] = self.iteration
        if self.total_tool_calls:
            d["total_tool_calls"] = self.total_tool_calls
        return d


class LLMClient:
    """基于 LangChain 的 LLM 客户端，支持 Tool Calling 和 DeepSeek 思考模式"""

    def __init__(self, db: aiosqlite.Connection = None):
        self.db = db
        self._config: dict | None = None

    @classmethod
    def from_config(cls, config: dict) -> "LLMClient":
        """从预获取的配置创建 LLMClient（不需要数据库连接）"""
        client = cls(db=None)
        client._config = {
            "api_key": config.get("api_key", ""),
            "base_url": config.get("base_url", "https://api.openai.com/v1"),
            "model_name": config.get("model_name", "gpt-3.5-turbo"),
            "system_prompt": config.get("system_prompt", "You are a helpful assistant."),
            "workspace_dir": config.get("workspace_dir", ""),
            "allowed_commands": config.get("allowed_commands", ""),
            "restrict_paths": config.get("restrict_paths", "true").lower() in ("true", "1", "yes"),
        }
        return client

    async def _get_config(self) -> dict:
        """获取 LLM 配置（优先使用预设配置）"""
        if self._config:
            return self._config
        async with self.db.execute("SELECT key, value FROM settings") as cursor:
            rows = await cursor.fetchall()
            config = {row[0]: row[1] for row in rows}
            return {
                "api_key": config.get("api_key", ""),
                "base_url": config.get("base_url", "https://api.openai.com/v1"),
                "model_name": config.get("model_name", "gpt-3.5-turbo"),
                "system_prompt": config.get("system_prompt", "You are a helpful assistant."),
                "workspace_dir": config.get("workspace_dir", ""),
                "allowed_commands": config.get("allowed_commands", ""),
                "restrict_paths": config.get("restrict_paths", "true").lower() in ("true", "1", "yes"),
            }

    def _build_messages(self, context: list) -> list:
        """将上下文转换为 LangChain 消息格式"""
        messages = []
        for msg in context:
            if msg["role"] == "system":
                messages.append(SystemMessage(content=msg["content"]))
            elif msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        return messages

    def _build_openai_messages(self, context: list) -> list:
        """将上下文转换为 OpenAI API 消息格式（用于思考模式）"""
        messages = []
        for msg in context:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })
        return messages

    async def chat_stream(self, context: list, deep_thinking: bool = False) -> AsyncGenerator[str, None]:
        """简单流式对话（向后兼容）"""
        config = await self._get_config()

        if deep_thinking:
            # 使用原生 OpenAI 客户端支持 DeepSeek 思考模式
            client = AsyncOpenAI(
                api_key=config["api_key"],
                base_url=config["base_url"],
            )
            messages = self._build_openai_messages(context)
            
            print(f"[Chat] 深度思考模式已开启 (使用 OpenAI 客户端)")
            
            try:
                stream = await client.chat.completions.create(
                    model=config["model_name"],
                    messages=messages,
                    stream=True,
                    reasoning_effort="high",
                    extra_body={"thinking": {"type": "enabled"}},
                )
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
            except Exception as e:
                print(f"[Chat] 思考模式调用失败: {e}")
                yield f"调用失败: {str(e)}"
        else:
            # 使用 LangChain
            from agent.config import get_agent_config_float
            temp = await get_agent_config_float("agent_temperature", 0.7)
            llm = ChatOpenAI(
                model=config["model_name"],
                api_key=config["api_key"],
                base_url=config["base_url"],
                streaming=True,
                temperature=temp,
            )
            messages = self._build_messages(context)
            async for chunk in llm.astream(messages):
                if chunk.content:
                    yield chunk.content

    async def agent_stream(
        self, context: list, max_iterations: int = None, deep_thinking: bool = None,
        stop_event: asyncio.Event = None, web_search_enabled: bool = None
    ) -> AsyncGenerator[AgentEvent, None]:
        """Agent Loop：支持 Tool Calling 和 DeepSeek 思考模式的多轮对话

        结束条件由 AI 自主决定：当 LLM 不再返回 tool_calls 时自动结束。
        max_iterations 仅作为防止无限循环的安全阀。

        Args:
            context: 对话上下文
            max_iterations: 安全上限（默认 200），仅在 AI 持续调用工具时防止无限循环
            deep_thinking: 是否开启深度思考（DeepSeek 思考模式）
            stop_event: 停止事件，用于外部中止流
            web_search_enabled: 是否注入联网搜索工具
        """
        if stop_event is None:
            stop_event = asyncio.Event()
        config = await self._get_config()

        # 从 DB 读取未显式传入的参数
        from agent.config import get_agent_config_int, get_agent_config_float, get_agent_config_bool
        if max_iterations is None:
            max_iterations = await get_agent_config_int("agent_max_iterations", 200)
        if deep_thinking is None:
            deep_thinking = await get_agent_config_bool("agent_deep_thinking_default", False)
        if web_search_enabled is None:
            web_search_enabled = await get_agent_config_bool("agent_web_search_default", True)
        temperature = await get_agent_config_float("agent_temperature", 0.7)

        # 设置工具配置
        set_tool_config(config)

        # 获取工具列表
        tools = get_tools(web_search_enabled=web_search_enabled)
        
        print(f"[Agent] 已加载 {len(tools)} 个工具: {[t.name for t in tools]}")
        print(f"[Agent] 使用模型: {config['model_name']}")
        print(f"[Agent] 深度思考: {deep_thinking}")

        # 构建初始消息（OpenAI 格式，支持思考模式）
        messages = self._build_openai_messages(context)

        # 工具名称到工具对象的映射
        tool_map = {tool.name: tool for tool in tools}

        # 转换工具定义为 OpenAI 格式
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
                print(f"[Agent] 工具 {getattr(tool, 'name', '?')} schema 生成失败: {e}")
                traceback.print_exc()

        # 创建 OpenAI 客户端
        client = AsyncOpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"],
        )

        # ── 事件总线集成：发布事件到全局总线 ──
        from agent.event_bus import get_or_create_session

        session_id = "default"  # 可扩展为 per-request session
        bus_session = get_or_create_session(session_id)

        async def _emit(event: AgentEvent):
            """同时 yield 和发布到事件总线"""
            await bus_session.publish(event)

        iteration = 0
        while iteration < max_iterations:
            # 检查停止信号
            if stop_event.is_set():
                print(f"[Agent] 收到停止信号，结束流")
                done_event = AgentEvent(type="done", content="[已停止]")
                await _emit(done_event)
                yield done_event
                return

            iteration += 1
            print(f"[Agent] 第 {iteration} 轮调用 LLM...")

            # 发送"工作中"事件，通知前端当前轮次
            wk_event = AgentEvent(type="working", content=f"第 {iteration} 轮推理", iteration=iteration)
            await _emit(wk_event)
            yield wk_event

            try:
                # 构建请求参数
                request_kwargs = {
                    "model": config["model_name"],
                    "messages": messages,
                    "tools": openai_tools if openai_tools else None,
                    "stream": True,
                }
                
                # 深度思考模式参数
                if deep_thinking:
                    request_kwargs["reasoning_effort"] = "high"
                    request_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
                else:
                    request_kwargs["temperature"] = temperature

                try:
                    stream = await client.chat.completions.create(**request_kwargs)
                except Exception as e:
                    print(f"[Agent] LLM 调用失败: {e}")
                    traceback.print_exc()
                    err_event = AgentEvent(type="error", content=f"LLM 调用失败: {str(e)}")
                    await _emit(err_event)
                    yield err_event
                    done_event = AgentEvent(type="done")
                    await _emit(done_event)
                    yield done_event
                    return

                # 收集流式响应
                reasoning_content = ""
                content = ""
                tool_calls = []
                finish_reason = None

                async for chunk in stream:
                    # 检查停止信号
                    if stop_event.is_set():
                        print(f"[Agent] 收到停止信号，中断流处理")
                        yield AgentEvent(type="done", content="[已停止]")
                        return

                    if not chunk.choices:
                        continue
                        
                    delta = chunk.choices[0].delta
                    finish_reason = chunk.choices[0].finish_reason

                    # 处理思考内容（DeepSeek 特有）
                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        reasoning_content += delta.reasoning_content
                        # 实时推送思考内容
                        yield AgentEvent(type="thinking", content=delta.reasoning_content)

                    # 处理正常内容
                    if delta.content:
                        content += delta.content

                    # 处理工具调用
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            # 初始化工具调用
                            while len(tool_calls) <= tc.index:
                                tool_calls.append({"id": "", "function": {"name": "", "arguments": ""}})
                            
                            if tc.id:
                                tool_calls[tc.index]["id"] = tc.id
                            if tc.function.name:
                                tool_calls[tc.index]["function"]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments

                # 打印响应信息用于调试
                print(f"[Agent] 响应 - tool_calls: {len(tool_calls)}, reasoning: {len(reasoning_content)} chars, content: {content[:100] if content else 'None'}...")

                # 构建 assistant 消息（包含 reasoning_content 以支持后续工具调用）
                assistant_message = {
                    "role": "assistant",
                    "content": content,
                }
                if deep_thinking and reasoning_content:
                    assistant_message["reasoning_content"] = reasoning_content
                if tool_calls:
                    assistant_message["tool_calls"] = [
                        {"id": tc["id"], "type": "function", "function": tc["function"]}
                        for tc in tool_calls
                    ]
                
                messages.append(assistant_message)

                # 发送最终内容（如果没有工具调用）
                if not tool_calls:
                    if content:
                        ct_event = AgentEvent(type="content", content=content)
                        await _emit(ct_event)
                        yield ct_event
                    done_event = AgentEvent(type="done")
                    await _emit(done_event)
                    yield done_event
                    return

                # 处理工具调用
                tool_call_count = 0
                for tc in tool_calls:
                    tool_name = tc["function"]["name"]
                    call_id = tc["id"] or str(uuid.uuid4())
                    tool_call_count += 1
                    
                    try:
                        tool_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        tool_args = {}
                    
                    print(f"[Agent] 调用工具: {tool_name}, 参数: {list(tool_args.keys())}")

                    # 发送工具调用事件（含轮次信息）
                    tc_event = AgentEvent(
                        type="tool_call",
                        tool=tool_name,
                        tool_args=tool_args,
                        call_id=call_id,
                        iteration=iteration,
                        total_tool_calls=tool_call_count,
                    )
                    await _emit(tc_event)
                    yield tc_event

                    # 执行工具
                    if tool_name in tool_map:
                        try:
                            tool = tool_map[tool_name]
                            result = await tool.ainvoke(tool_args)
                            print(f"[Agent] 工具 {tool_name} 执行成功")

                            # 如果是 edit_file，额外发送 diff 信息
                            if tool_name == "edit_file" and "path" in tool_args:
                                diff_event = AgentEvent(
                                    type="diff",
                                    diff_path=tool_args.get("path", ""),
                                    diff_old=tool_args.get("old_content", ""),
                                    diff_new=tool_args.get("new_content", ""),
                                    iteration=iteration,
                                )
                                await _emit(diff_event)
                                yield diff_event

                            # 发送工具结果事件（含轮次信息）
                            tr_event = AgentEvent(
                                type="tool_result",
                                tool=tool_name,
                                tool_result=str(result)[:2000],
                                call_id=call_id,
                                iteration=iteration,
                            )
                            await _emit(tr_event)
                            yield tr_event

                            # 将工具结果添加到消息历史
                            messages.append({
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": str(result),
                            })
                        except Exception as e:
                            error_msg = f"工具执行失败: {str(e)}"
                            print(f"[Agent] 工具 {tool_name} 执行失败: {e}")
                            traceback.print_exc()
                            tr_err_event = AgentEvent(
                                type="tool_result",
                                tool=tool_name,
                                tool_result=error_msg,
                                call_id=call_id,
                                iteration=iteration,
                            )
                            await _emit(tr_err_event)
                            yield tr_err_event
                            messages.append({
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": error_msg,
                            })
                    else:
                        error_msg = f"未知工具: {tool_name}"
                        print(f"[Agent] {error_msg}")
                        unk_event = AgentEvent(
                            type="tool_result",
                            tool=tool_name,
                            tool_result=error_msg,
                            call_id=call_id,
                            iteration=iteration,
                        )
                        await _emit(unk_event)
                        yield unk_event
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": error_msg,
                        })

            except Exception as e:
                # 全局异常捕获：防止任何未预期异常导致 SSE 流静默断开
                error_msg = f"Agent 执行异常: {str(e)}"
                print(f"[Agent] {error_msg}")
                traceback.print_exc()
                err_event = AgentEvent(type="error", content=error_msg)
                await _emit(err_event)
                yield err_event
                done_event = AgentEvent(type="done")
                await _emit(done_event)
                yield done_event
                return

        # 达到安全上限（仅当 AI 持续调用工具超过 max_iterations 轮时触发）
        print(f"[Agent] 达到安全上限 {max_iterations} 轮，强制结束")
        limit_event = AgentEvent(
            type="error",
            content=f"工具调用轮次超过安全上限 ({max_iterations})，已强制结束。如需更多轮次，请拆分任务。",
        )
        await _emit(limit_event)
        yield limit_event
        done_event = AgentEvent(type="done")
        await _emit(done_event)
        yield done_event
