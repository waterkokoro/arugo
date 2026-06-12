"""Agent 工具集：文件操作、命令执行、记忆管理、自我进化"""

import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional
from langchain_core.tools import tool
import aiosqlite

from agent.tool_registry import get_tool_registry, ToolDef
from agent.memory import PersistentMemoryManager, MemoryEntry


# ============================================================
# 安全配置
# ============================================================

BLOCKED_COMMANDS = [
    "rm -rf", "rm -r", "sudo", "chmod 777", "chmod -R 777",
    "mkfs", "dd if=", "> /dev/sda", ":(){ :|:& };:", "wget", "curl",
]


def get_workspace_dir(db_config: dict) -> str:
    workspace = db_config.get("workspace_dir", "")
    if workspace and os.path.isdir(workspace):
        return os.path.abspath(workspace)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def validate_path(path: str, workspace_dir: str) -> tuple[bool, str]:
    try:
        abs_path = os.path.abspath(path)
        if not abs_path.startswith(workspace_dir):
            return False, f"路径 {path} 不在允许的工作目录 {workspace_dir} 内"
        return True, abs_path
    except Exception as e:
        return False, f"路径验证失败: {str(e)}"


def validate_command(command: str, allowed_commands: str) -> tuple[bool, str]:
    for blocked in BLOCKED_COMMANDS:
        if blocked in command.lower():
            return False, f"命令包含被禁止的操作: {blocked}"
    base_cmd = command.split()[0] if command.split() else ""
    allowed_list = [cmd.strip() for cmd in allowed_commands.split(",")]
    for allowed in allowed_list:
        if command.startswith(allowed) or base_cmd == allowed:
            return True, ""
    return False, f"命令 {base_cmd} 不在允许的列表中。允许的命令: {allowed_commands}"


_tool_config: dict = {}


def set_tool_config(config: dict):
    global _tool_config
    _tool_config = config


def get_tool_config() -> dict:
    return _tool_config


# ============================================================
# 基础文件操作工具
# ============================================================

@tool
def read_file(path: str) -> str:
    """读取指定路径的文件内容。

    Args:
        path: 文件路径（相对于工作目录或绝对路径）
    """
    config = get_tool_config()
    workspace_dir = get_workspace_dir(config)
    if not os.path.isabs(path):
        path = os.path.join(workspace_dir, path)
    valid, result = validate_path(path, workspace_dir)
    if not valid:
        return f"错误: {result}"
    if not os.path.exists(result):
        return f"错误: 文件不存在: {result}"
    if not os.path.isfile(result):
        return f"错误: 不是文件: {result}"
    try:
        with open(result, "r", encoding="utf-8") as f:
            content = f.read()
        return content
    except Exception as e:
        return f"错误: 读取文件失败: {str(e)}"


@tool
def write_file(path: str, content: str) -> str:
    """写入内容到指定文件（会覆盖已有内容）。

    Args:
        path: 文件路径（相对于工作目录或绝对路径）
        content: 要写入的文件内容
    """
    config = get_tool_config()
    workspace_dir = get_workspace_dir(config)
    if not os.path.isabs(path):
        path = os.path.join(workspace_dir, path)
    valid, result = validate_path(path, workspace_dir)
    if not valid:
        return f"错误: {result}"
    try:
        os.makedirs(os.path.dirname(result), exist_ok=True)
        with open(result, "w", encoding="utf-8") as f:
            f.write(content)
        return f"成功写入文件: {result} ({len(content)} 字符)"
    except Exception as e:
        return f"错误: 写入文件失败: {str(e)}"


@tool
def edit_file(path: str, old_content: str, new_content: str) -> str:
    """基于搜索替换修改文件中的指定内容。

    Args:
        path: 文件路径（相对于工作目录或绝对路径）
        old_content: 要被替换的原始内容
        new_content: 替换后的新内容
    """
    config = get_tool_config()
    workspace_dir = get_workspace_dir(config)
    if not os.path.isabs(path):
        path = os.path.join(workspace_dir, path)
    valid, result = validate_path(path, workspace_dir)
    if not valid:
        return f"错误: {result}"
    if not os.path.exists(result):
        return f"错误: 文件不存在: {result}"
    try:
        with open(result, "r", encoding="utf-8") as f:
            file_content = f.read()
        if old_content not in file_content:
            return f"错误: 在文件中未找到要替换的内容"
        new_file_content = file_content.replace(old_content, new_content, 1)
        with open(result, "w", encoding="utf-8") as f:
            f.write(new_file_content)
        return f"成功编辑文件: {result}"
    except Exception as e:
        return f"错误: 编辑文件失败: {str(e)}"


@tool
def list_directory(path: str = ".", recursive: bool = False) -> str:
    """列出指定目录的内容。

    Args:
        path: 目录路径（相对于工作目录或绝对路径），默认为工作目录
        recursive: 是否递归列出子目录，默认为 False
    """
    config = get_tool_config()
    workspace_dir = get_workspace_dir(config)
    if not os.path.isabs(path):
        path = os.path.join(workspace_dir, path)
    valid, result = validate_path(path, workspace_dir)
    if not valid:
        return f"错误: {result}"
    if not os.path.exists(result):
        return f"错误: 目录不存在: {result}"
    if not os.path.isdir(result):
        return f"错误: 不是目录: {result}"
    try:
        lines = []
        if recursive:
            for root, dirs, files in os.walk(result):
                dirs[:] = [d for d in dirs if d not in ["node_modules", ".git", "__pycache__", ".venv", "venv"]]
                level = root.replace(result, "").count(os.sep)
                indent = " " * 2 * level
                lines.append(f"{indent}{os.path.basename(root)}/")
                subindent = " " * 2 * (level + 1)
                for file in files:
                    lines.append(f"{subindent}{file}")
        else:
            for item in sorted(os.listdir(result)):
                item_path = os.path.join(result, item)
                if os.path.isdir(item_path):
                    lines.append(f"{item}/")
                else:
                    lines.append(item)
        return "\n".join(lines) if lines else "(空目录)"
    except Exception as e:
        return f"错误: 列出目录失败: {str(e)}"


@tool
async def run_command(command: str) -> str:
    """在工作目录中执行 shell 命令。

    Args:
        command: 要执行的 shell 命令
    """
    config = get_tool_config()
    workspace_dir = get_workspace_dir(config)
    allowed_commands = config.get("allowed_commands", "")
    valid, error_msg = validate_command(command, allowed_commands)
    if not valid:
        return f"错误: {error_msg}"
    try:
        result = await _run_command_async(command, workspace_dir)
        return result
    except Exception as e:
        return f"错误: 命令执行失败: {str(e)}"


async def _run_command_async(command: str, cwd: str) -> str:
    process = await asyncio.create_subprocess_shell(
        command, cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
    except asyncio.TimeoutError:
        process.kill()
        return "错误: 命令执行超时（60秒）"
    output = ""
    if stdout:
        output += stdout.decode("utf-8", errors="replace")
    if stderr:
        output += f"\n[stderr]: {stderr.decode('utf-8', errors='replace')}"
    if process.returncode != 0:
        output += f"\n[退出码]: {process.returncode}"
    return output.strip() if output.strip() else "(命令执行成功，无输出)"


# ============================================================
# 持久记忆工具 - 突破滑动窗口
# ============================================================

_memory_manager: Optional[PersistentMemoryManager] = None


def _get_memory() -> PersistentMemoryManager:
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = PersistentMemoryManager()
    return _memory_manager


@tool
def remember(key_info: str, importance: int = 3, tags: str = "") -> str:
    """将重要信息存入持久记忆，跨会话保留。用于记住用户偏好、重要决策、项目进展等。

    Args:
        key_info: 要记住的关键信息
        importance: 重要性 1-5（1=低，5=极高），默认 3
        tags: 逗号分隔的标签，如 "用户偏好,项目A"
    """
    mem = _get_memory()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    entry_id = mem.remember(content=key_info, importance=min(5, max(1, importance)), tags=tag_list)
    return f"已记住 (ID: {entry_id}, 重要性: {'★' * min(5, max(1, importance))})"


@tool
def recall_memory(query: str = "", category: str = "", tags: str = "", limit: int = 10) -> str:
    """搜索和检索持久记忆，获取跨会话保存的信息。

    Args:
        query: 搜索关键词（匹配内容和标签）
        category: 按类别过滤（如 "learned", "user_preference", "decision"）
        tags: 按标签过滤，逗号分隔
        limit: 返回结果数量上限，默认 10
    """
    mem = _get_memory()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    results = mem.search_memory(
        query=query if query else None,
        category=category if category else None,
        tags=tag_list if tag_list else None,
        limit=limit,
    )
    if not results:
        return "未找到匹配的记忆。"
    lines = [f"找到 {len(results)} 条记忆:"]
    for e in results:
        imp = "★" * e.importance
        cat = f"[{e.category}]" if e.category else ""
        ts = e.timestamp[:19]
        lines.append(f"  {imp} {cat} [{ts}] {e.content}")
    return "\n".join(lines)


@tool
def list_memory_categories() -> str:
    """列出所有记忆类别和标签，了解持久记忆中存储了哪些类型的信息。"""
    mem = _get_memory()
    categories = mem.store.get_all_categories()
    tags = mem.store.get_all_tags()
    lines = ["[记忆目录]"]
    lines.append(f"\n类别 ({len(categories)}):")
    for c in sorted(categories):
        count = len(mem.store.search(category=c))
        lines.append(f"  - {c} ({count} 条)")
    lines.append(f"\n标签 ({len(tags)}):")
    for t in sorted(tags):
        lines.append(f"  - #{t}")
    lines.append(f"\n总计: {len(mem.store.entries)} 条记忆")
    return "\n".join(lines)


@tool
def save_session_summary(summary: str) -> str:
    """保存当前会话的关键摘要，下次对话时会自动加载。在对话趋于结束时调用。

    Args:
        summary: 本次会话的关键摘要，包含重要决策、进展和待办事项
    """
    mem = _get_memory()
    mem.end_session(summary)
    return f"会话摘要已保存，下次对话时将自动加载。"


@tool
def log_evolution_event(event_type: str, description: str) -> str:
    """记录AI进化事件，追踪能力变化和成长轨迹。

    Args:
        event_type: 事件类型，如 "tool_added", "memory_created", "code_modified", "capability_upgrade"
        description: 事件描述
    """
    mem = _get_memory()
    mem.log_evolution(event_type, description)
    return f"进化事件已记录: [{event_type}] {description}"


# ============================================================
# Agent 工厂工具 - 子Agent生成和管理
# ============================================================

from agent.agent_factory import get_agent_factory
from openai import AsyncOpenAI


@tool
async def invoke_sub_agent(agent_name: str, task: str) -> str:
    """调用一个已创建的子Agent执行特定任务。子Agent使用其专属system_prompt进行单轮推理。

    适用场景：代码审查、测试生成、文档撰写、专业分析等可委派任务。

    Args:
        agent_name: 子Agent名称或ID（通过 list_sub_agents 查看）
        task: 委派给子Agent的任务描述，越详细越好
    """
    factory = get_agent_factory()
    
    # 查找子Agent（先按名称，再按ID）
    agent = factory.find_by_name(agent_name)
    if not agent:
        agent = factory.get(agent_name)
    if not agent:
        agents = factory.list_all()
        names = ", ".join([f"{a.name}({a.id})" for a in agents]) if agents else "无"
        return f"❌ 未找到子Agent: {agent_name}\n可用: {names}"
    
    config = get_tool_config()
    
    # 创建临时客户端
    try:
        client = AsyncOpenAI(
            api_key=config.get("api_key", ""),
            base_url=config.get("base_url", "https://api.openai.com/v1"),
        )
    except Exception as e:
        return f"❌ 创建LLM客户端失败: {str(e)}"
    
    messages = [
        {"role": "system", "content": agent.system_prompt},
        {"role": "user", "content": task},
    ]
    
    try:
        response = await client.chat.completions.create(
            model=config.get("model_name", "gpt-3.5-turbo"),
            messages=messages,
            temperature=0.7,
            max_tokens=4096,
        )
        result = response.choices[0].message.content
        
        # 标记子Agent被使用
        factory.mark_used(agent.id)
        
        # 记录进化事件
        mem = _get_memory()
        mem.log_evolution(
            "sub_agent_invoked",
            f"子Agent '{agent.name}' 被调用执行任务: {task[:80]}",
        )
        
        return f"[子Agent: {agent.name} (ID: {agent.id})]\n\n{result}"
    except Exception as e:
        return f"❌ 子Agent调用失败: {str(e)}"


@tool
def create_sub_agent(name: str, system_prompt: str, description: str = "", tools: str = "") -> str:
    """创建一个专门用途的子Agent，用于委派特定任务。创建后可用 invoke_sub_agent 调用。

    Args:
        name: 子Agent名称（如 "code_reviewer", "test_writer"）
        system_prompt: 子Agent的系统提示词，定义其角色和行为
        description: 子Agent的简短描述
        tools: 分配给子Agent的工具名称列表，逗号分隔。留空则使用基础工具集。
              可用工具: read_file, write_file, edit_file, list_directory, run_command, remember, recall_memory
    """
    factory = get_agent_factory()
    tool_list = [t.strip() for t in tools.split(",") if t.strip()] if tools else []
    agent = factory.create(
        name=name,
        system_prompt=system_prompt,
        description=description,
        tools=tool_list,
    )
    return f"子Agent '{name}' 已创建 (ID: {agent.id})\n描述: {description}\n可用工具: {', '.join(tool_list) if tool_list else '基础工具集'}"


@tool
def list_sub_agents() -> str:
    """列出所有已创建的子Agent及其状态。"""
    factory = get_agent_factory()
    return factory.get_factory_report()


@tool
def delete_sub_agent(agent_id: str) -> str:
    """删除指定的子Agent。

    Args:
        agent_id: 子Agent的ID（可通过 list_sub_agents 获取）
    """
    factory = get_agent_factory()
    agent = factory.get(agent_id)
    if not agent:
        return f"未找到子Agent: {agent_id}"
    name = agent.name
    factory.delete(agent_id)
    return f"子Agent '{name}' (ID: {agent_id}) 已删除"


@tool
def generate_agent_config(purpose: str, expertise: str, tools_needed: str = "") -> str:
    """生成子Agent的配置建议（system prompt模板），供创建子Agent前预览。

    Args:
        purpose: 子Agent的用途描述
        expertise: 需要的专长领域
        tools_needed: 建议的工具列表，逗号分隔
    """
    factory = get_agent_factory()
    tool_list = [t.strip() for t in tools_needed.split(",") if t.strip()] if tools_needed else None
    return factory.generate_agent_config(purpose, expertise, tool_list)


# ============================================================
# 自我进化工具 - 能力扩展
# ============================================================

@tool
def get_evolution_status() -> str:
    """获取AI的进化状态报告：记忆数量、工具数量、子Agent数量、最近的进化事件。"""
    mem = _get_memory()
    registry = get_tool_registry()
    factory = get_agent_factory()
    
    lines = ["[进化状态报告]", ""]
    
    # 记忆统计
    total_memories = len(mem.store.entries)
    categories = mem.store.get_all_categories()
    lines.append(f"## 持久记忆: {total_memories} 条, {len(categories)} 个类别")
    
    # 工具统计
    all_tools = registry.list_all()
    executable = [t for t in all_tools if t.func]
    defined = [t for t in all_tools if not t.func]
    lines.append(f"## 工具: {len(all_tools)} 个注册 ({len(executable)} 可执行, {len(defined)} 规划中)")
    
    # 子Agent统计
    all_agents = factory.list_all()
    lines.append(f"## 子Agent: {len(all_agents)} 个")
    
    # 最近进化事件
    evolution_log = mem.get_evolution_log(limit=10)
    if evolution_log:
        lines.append(f"\n## 最近进化事件:")
        for evt in evolution_log[-5:]:
            lines.append(f"  - [{evt['type']}] {evt['description']} ({evt['timestamp'][:19]})")
    
    lines.append(f"\n{registry.get_registry_report()}")
    
    return "\n".join(lines)


@tool
def plan_new_tool(name: str, description: str, category: str = "generated") -> str:
    """规划一个新的工具（先在注册表中登记，稍后可实现代码）。

    Args:
        name: 工具名称（函数名风格，如 "search_web"）
        description: 工具功能描述
        category: 工具类别，如 "memory", "evolution", "io", "network"
    """
    registry = get_tool_registry()
    filepath = registry.save_tool_config(name, description, category)
    return f"工具 '{name}' 已规划登记。配置文件: {filepath}\n下一步：使用 generate_tool_code 生成代码，然后用 write_file 实现。"


@tool
def generate_tool_code(name: str, description: str) -> str:
    """生成一个新工具的Python代码模板，可用于 write_file 创建工具文件。

    Args:
        name: 工具函数名
        description: 工具功能描述
    """
    registry = get_tool_registry()
    code = registry.generate_tool_code(name, description)
    return code


def _backup_tools_file() -> str:
    """在修改 tools.py 前自动创建备份"""
    import shutil
    from datetime import datetime
    tools_path = os.path.join(os.path.dirname(__file__), "tools.py")
    backup_dir = os.path.join(os.path.dirname(__file__), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"tools_{timestamp}.py.bak")
    shutil.copy2(tools_path, backup_path)
    # 清理旧备份，只保留最近10个
    backups = sorted(
        [f for f in os.listdir(backup_dir) if f.endswith(".py.bak")],
        reverse=True
    )
    for old in backups[10:]:
        os.remove(os.path.join(backup_dir, old))
    return backup_path


@tool
def self_backup() -> str:
    """创建当前 tools.py 的备份，用于安全回滚。在重大修改前应调用此工具。"""
    backup_path = _backup_tools_file()
    log_evolution_event.func("backup_created", f"tools.py 备份: {os.path.basename(backup_path)}")
    return f"备份已创建: {backup_path}"


@tool
def self_restore(backup_filename: str = "") -> str:
    """从备份恢复 tools.py。不指定文件名则列出可用备份。

    Args:
        backup_filename: 备份文件名（如 tools_20250101_120000.py.bak），留空则列出所有备份
    """
    import shutil
    tools_path = os.path.join(os.path.dirname(__file__), "tools.py")
    backup_dir = os.path.join(os.path.dirname(__file__), "backups")
    
    if not os.path.isdir(backup_dir):
        return "没有找到备份目录。"
    
    backups = sorted(
        [f for f in os.listdir(backup_dir) if f.endswith(".py.bak")],
        reverse=True
    )
    
    if not backups:
        return "没有可用的备份文件。"
    
    if not backup_filename:
        lines = ["可用的备份文件:"]
        for i, b in enumerate(backups):
            stat = os.stat(os.path.join(backup_dir, b))
            size = stat.st_size
            mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
            lines.append(f"  [{i+1}] {b} ({size} bytes, {mtime})")
        return "\n".join(lines)
    
    backup_path = os.path.join(backup_dir, backup_filename)
    if not os.path.exists(backup_path):
        return f"备份文件不存在: {backup_filename}\n可用: {', '.join(backups)}"
    
    # 恢复前先备份当前版本
    _backup_tools_file()
    shutil.copy2(backup_path, tools_path)
    log_evolution_event.func("restore_performed", f"从备份恢复: {backup_filename}")
    return f"已从备份恢复 tools.py: {backup_filename}\n请重启服务: ./manage.sh restart"


@tool
def add_tool_to_self(tool_name: str, tool_code: str, category: str = "generated") -> str:
    """将一个新的 @tool 函数代码追加到 tools.py 中，扩展自身能力。
    
    这是AI自我进化的核心工具——通过此工具，AI可以将自己编写的新工具函数
    安装到自身代码中，自动热加载使其立即可用。

    Args:
        tool_name: 新工具的函数名
        tool_code: 完整的 @tool 装饰的函数代码（不含 import 语句）
        category: 工具类别，如 "memory", "evolution", "io", "network", "agent"
    """
    from agent.tool_registry import validate_tool_code, reload_tools
    
    config = get_tool_config()
    workspace_dir = get_workspace_dir(config)
    tools_path = os.path.join(os.path.dirname(__file__), "tools.py")
    
    # 0. 验证代码
    is_valid, validation_msg = validate_tool_code(tool_code)
    if not is_valid:
        return f"❌ 代码验证失败: {validation_msg}\n工具未写入。请修复问题后重试。"
    
    # 1. 修改前自动备份
    backup_path = _backup_tools_file()
    
    # 2. 检查工具是否已存在
    with open(tools_path, "r", encoding="utf-8") as f:
        existing_code = f.read()
    if f"def {tool_name}(" in existing_code:
        return f"⚠️ 工具 '{tool_name}' 已存在于 tools.py 中。请使用 edit_file 修改现有代码。"
    
    # 3. 定位插入位置
    insertion_marker = "# 所有工具\n_ALL_TOOLS"
    if insertion_marker not in existing_code:
        return f"❌ 无法在 tools.py 中定位工具列表插入位置，代码结构可能已变更。\n备份文件: {backup_path}"
    
    # 4. 构建要插入的代码块
    new_tool_block = f'''

# ============================================================
# 动态添加的工具: {tool_name}（类别: {category}）
# ============================================================

{tool_code}


# 注册到工具列表
if "{tool_name}" not in [t.name if hasattr(t, 'name') else str(t) for t in _ALL_TOOLS]:
    try:
        _ALL_TOOLS.append({tool_name})
        get_tool_registry().register(ToolDef(
            name="{tool_name}",
            description={tool_name}.description if hasattr({tool_name}, 'description') else "",
            func={tool_name},
            source="generated",
            category="{category}",
        ))
        print("[SelfEvo] 工具 \\"{tool_name}\\" 已自动注册到 _ALL_TOOLS 和 ToolRegistry")
    except Exception as e:
        print(f"[SelfEvo] 工具 \\"{tool_name}\\" 注册失败: {{e}}")
'''
    
    # 5. 写入文件
    new_code = existing_code.replace(insertion_marker, new_tool_block + "\n" + insertion_marker)
    
    with open(tools_path, "w", encoding="utf-8") as f:
        f.write(new_code)
    
    # 6. 保存配置到注册表
    registry = get_tool_registry()
    registry.save_tool_config(tool_name, tool_code[:200], category)
    
    # 7. 热加载：使新工具立即可用
    reload_result = reload_tools()
    
    log_evolution_event.func("tool_added", f"通过 add_tool_to_self 添加工具: {tool_name} (类别: {category})")
    
    result_lines = [
        f"✅ 工具 '{tool_name}' 已添加并通过热加载生效！",
        f"   验证: {validation_msg}",
        f"   热加载: {reload_result['message']}",
        f"   备份: {os.path.basename(backup_path)}",
        f"   类别: {category}",
    ]
    
    if reload_result["status"] == "error":
        result_lines.append(f"   ⚠️ 热加载失败，需要重启: ./manage.sh restart")
    elif reload_result["status"] == "partial":
        result_lines.append(f"   ⚠️ 部分工具加载失败，建议检查: ./manage.sh restart")
    
    return "\n".join(result_lines)


@tool
def git_commit_evolution(message: str) -> str:
    """将当前的代码变更提交到 git，记录进化历史。

    Args:
        message: git commit 信息（建议描述本次进化的内容）
    """
    import subprocess
    config = get_tool_config()
    workspace_dir = get_workspace_dir(config)
    
    try:
        # git add 所有变更
        result_add = subprocess.run(
            ["git", "add", "-A"],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        # git commit
        result_commit = subprocess.run(
            ["git", "commit", "-m", f"[进化] {message}"],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        output = ""
        if result_add.stdout:
            output += result_add.stdout
        if result_commit.stdout:
            output += result_commit.stdout
        if result_commit.stderr and "nothing to commit" not in result_commit.stderr:
            output += result_commit.stderr
        
        if result_commit.returncode == 0:
            log_evolution_event.func("code_committed", f"Git 提交: {message}")
            return f"Git 提交成功:\n{output.strip()}"
        elif "nothing to commit" in (result_commit.stdout + result_commit.stderr):
            return "没有需要提交的变更。"
        else:
            return f"Git 提交可能失败:\n{output.strip()}"
    except Exception as e:
        return f"Git 操作失败: {str(e)}"


# ============================================================
# 联网搜索工具
# ============================================================

@tool
async def web_search(query: str, max_results: int = 10) -> str:
    """Search the web for real-time information. Use when you need the latest news, technical docs, current events, or any external knowledge not in your training data.

    Args:
        query: search keywords
        max_results: max results, default 10
    """
    import json as _json
    from agent.web_search import auto_search, format_search_results

    config = get_tool_config()
    provider = config.get("search_provider", "auto")
    try:
        api_keys = _json.loads(config.get("search_api_keys", "{}"))
    except Exception:
        api_keys = {}

    payload = await auto_search(
        query=query,
        max_results=max_results,
        provider=provider,
        api_keys=api_keys,
    )
    return format_search_results(payload)


# ============================================================
# 工具列表汇聚
# ============================================================

# 联网搜索工具
_SEARCH_TOOLS = [
    web_search,
]

# 内置核心工具
_BUILTIN_TOOLS = [
    read_file,
    write_file,
    edit_file,
    list_directory,
    run_command,
]

# 记忆与进化工具
_MEMORY_TOOLS = [
    remember,
    recall_memory,
    list_memory_categories,
    save_session_summary,
    log_evolution_event,
    get_evolution_status,
    plan_new_tool,
    generate_tool_code,
]

# Agent 工厂工具
_AGENT_FACTORY_TOOLS = [
    create_sub_agent,
    list_sub_agents,
    delete_sub_agent,
    generate_agent_config,
    invoke_sub_agent,
]

# 自我进化工具
_EVOLUTION_TOOLS = [
    add_tool_to_self,
    git_commit_evolution,
    self_backup,
    self_restore,
]

# 动态加载的热重载工具
try:
    from agent.tool_registry import reload_tools, validate_tool_code
    
    @tool
    def hot_reload_tools() -> str:
        """热加载 tools.py 模块，使新添加的工具立即可用，无需重启服务。
        
        在 add_tool_to_self 后会自动调用，也可手动调用以修复加载问题。
        """
        result = reload_tools()
        if result["status"] == "ok":
            return f"✅ {result['message']}\n新增工具: {', '.join(result.get('new_tools', [])) or '无'}"
        else:
            return f"❌ {result['message']}"
    
    @tool
    def validate_tool_syntax(tool_code: str) -> str:
        """验证工具代码语法，在写入前检查。用于 add_tool_to_self 之前的安全检查。
        
        Args:
            tool_code: 完整的 @tool 装饰的函数代码
        """
        is_valid, message = validate_tool_code(tool_code)
        if is_valid:
            return f"✅ {message}"
        else:
            return f"❌ {message}"
    
    _EVOLUTION_TOOLS.append(hot_reload_tools)
    _EVOLUTION_TOOLS.append(validate_tool_syntax)
except ImportError:
    pass



# ============================================================
# 动态添加的工具: quality_gate_check（类别: evolution）
# ============================================================

@tool
def quality_gate_check(
    operation: str,
    target: str = "",
    code: str = "",
    result: str = "",
    stage: str = "full"
) -> str:
    """质量门禁检查——在关键操作前后进行风险评估。

    Args:
        operation: 操作类型，如 "write_file", "edit_file", "add_tool_to_self", "git_commit"
        target: 操作目标（文件路径、工具名等）
        code: 要检查的代码内容（可选，用于静态分析）
        result: 操作结果描述（可选，用于操作后验证）
        stage: 检查阶段 - "pre"(操作前), "post"(操作后), "full"(三阶段完整检查)
    """
    import json as _json

    from agent.quality_gate import get_quality_gate, GateStatus

    gate = get_quality_gate()

    if stage == "pre":
        r = gate.pre_flight_check(operation, target)
        return _json.dumps(r.to_dict(), ensure_ascii=False, indent=2)

    elif stage == "post":
        r = gate.post_flight_check(operation, result)
        return _json.dumps(r.to_dict(), ensure_ascii=False, indent=2)

    elif stage == "inline":
        r = gate.inline_check(code)
        return _json.dumps(r.to_dict(), ensure_ascii=False, indent=2)

    else:  # full
        full = gate.full_gate_check(operation, target, code, result)
        return _json.dumps(full, ensure_ascii=False, indent=2)


# 所有工具
_ALL_TOOLS = _BUILTIN_TOOLS + _SEARCH_TOOLS + _MEMORY_TOOLS + _AGENT_FACTORY_TOOLS + _EVOLUTION_TOOLS

# 动态工具注册
try:
    _ALL_TOOLS.append(quality_gate_check)
    get_tool_registry().register(ToolDef(
        name="quality_gate_check",
        description=quality_gate_check.description if hasattr(quality_gate_check, 'description') else "",
        func=quality_gate_check,
        source="generated",
        category="evolution",
    ))
    print("[SelfEvo] 工具 \"quality_gate_check\" 已注册")
except Exception as e:
    print(f"[SelfEvo] 工具 \"quality_gate_check\" 注册失败: {e}")


def get_tools(web_search_enabled: bool = True) -> list:
    """获取所有可用工具（内置 + 注册表 + 记忆工具）

    Args:
        web_search_enabled: 是否注入联网搜索工具
    """
    registry = get_tool_registry()

    # 根据联网搜索开关过滤工具
    active_tools = [t for t in _ALL_TOOLS if web_search_enabled or t not in _SEARCH_TOOLS]

    # 用注册表中的工具合并
    merged = registry.merge_with_langchain_tools(active_tools)

    return merged
