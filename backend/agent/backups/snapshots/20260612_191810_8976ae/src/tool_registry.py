"""
动态工具注册表 - 支持运行时扩展工具能力

允许：
1. 从代码文件动态加载新工具
2. 从配置文件（YAML/JSON）定义工具
3. 工具热注册/注销
4. 工具能力自检和报告

这是 AI 自我扩展能力的核心基础设施。
"""

import os
import json
import importlib
import inspect
from typing import Callable, Optional
from pathlib import Path


# 工具定义的数据结构
class ToolDef:
    """工具定义 - 描述一个工具但不一定是 @tool 装饰的"""
    def __init__(
        self,
        name: str,
        description: str,
        func: Callable = None,
        source: str = "code",  # "code" | "config" | "generated"
        category: str = "general",
        parameters: dict = None,
    ):
        self.name = name
        self.description = description
        self.func = func
        self.source = source
        self.category = category
        self.parameters = parameters or {}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "category": self.category,
        }


class ToolRegistry:
    """动态工具注册表"""

    def __init__(self):
        # 存储所有注册的工具定义
        self._tools: dict[str, ToolDef] = {}
        # 工具配置文件目录
        self._config_dir = os.path.join(os.path.dirname(__file__), "tool_configs")
        os.makedirs(self._config_dir, exist_ok=True)
        # 自动加载配置定义的额外工具
        self._load_from_configs()

    def register(self, tool_def: ToolDef):
        """注册一个工具"""
        self._tools[tool_def.name] = tool_def
        print(f"[ToolRegistry] 注册工具: {tool_def.name} (来源: {tool_def.source})")

    def unregister(self, name: str) -> bool:
        """注销一个工具"""
        if name in self._tools:
            del self._tools[name]
            print(f"[ToolRegistry] 注销工具: {name}")
            return True
        return False

    def get(self, name: str) -> Optional[ToolDef]:
        """获取工具定义"""
        return self._tools.get(name)

    def list_all(self) -> list[ToolDef]:
        """列出所有工具"""
        return list(self._tools.values())

    def list_by_category(self, category: str) -> list[ToolDef]:
        """按类别列出工具"""
        return [t for t in self._tools.values() if t.category == category]

    def merge_with_langchain_tools(self, langchain_tools: list) -> list:
        """
        将注册表中的工具与 LangChain 工具列表合并。
        
        如果注册表中的工具提供了 func，则创建 LangChain 兼容的工具；
        如果只有定义（无 func），则跳过（仅用于文档/规划）。
        """
        merged = list(langchain_tools)  # 保留原有工具

        existing_names = set()
        for t in langchain_tools:
            if hasattr(t, 'name'):
                existing_names.add(t.name)

        for name, tool_def in self._tools.items():
            if name in existing_names:
                continue  # 不覆盖已有工具
            if tool_def.func:
                merged.append(tool_def.func)
                print(f"[ToolRegistry] 合并工具: {name} -> LangChain 列表")

        return merged

    def generate_tool_code(self, name: str, description: str, category: str = "generated") -> str:
        """
        生成一个新工具的代码模板。
        
        AI 可以调用此方法生成工具代码，然后通过 write_file 写入，
        再通过此注册表加载。
        """
        code = f'''"""自动生成的工具: {name}"""

from langchain_core.tools import tool


@tool
def {name}() -> str:
    """{description}"""
    # TODO: 实现工具逻辑
    return "工具 {name} 执行成功"


# 元数据
TOOL_META = {{
    "name": "{name}",
    "description": "{description}",
    "category": "{category}",
}}
'''
        return code

    def _load_from_configs(self):
        """从 tool_configs 目录加载 JSON 配置的工具定义"""
        if not os.path.isdir(self._config_dir):
            return
        for filename in os.listdir(self._config_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(self._config_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    if isinstance(config, list):
                        for tool_cfg in config:
                            self._register_from_config(tool_cfg)
                    elif isinstance(config, dict):
                        self._register_from_config(config)
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"[ToolRegistry] 加载配置失败 {filename}: {e}")

    def _register_from_config(self, config: dict):
        """从配置字典注册工具（仅定义，无函数体）"""
        name = config.get("name", "")
        if not name or name in self._tools:
            return
        tool_def = ToolDef(
            name=name,
            description=config.get("description", ""),
            source="config",
            category=config.get("category", "general"),
            parameters=config.get("parameters", {}),
        )
        self._tools[name] = tool_def

    def save_tool_config(self, name: str, description: str, category: str = "generated"):
        """保存工具配置到文件（用于尚未实现代码的工具规划）"""
        config = {
            "name": name,
            "description": description,
            "category": category,
            "parameters": {},
        }
        filepath = os.path.join(self._config_dir, f"{name}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        self._register_from_config(config)
        return filepath

    def get_registry_report(self) -> str:
        """生成工具注册表报告"""
        tools = self.list_all()
        lines = ["[工具注册表报告]", f"总计: {len(tools)} 个工具\n"]
        
        by_source = {}
        for t in tools:
            src = t.source
            if src not in by_source:
                by_source[src] = []
            by_source[src].append(t)

        for source, tool_list in by_source.items():
            lines.append(f"## 来源: {source} ({len(tool_list)} 个)")
            for t in tool_list:
                func_status = " ✅可执行" if t.func else " 📝仅定义"
                lines.append(f"  - {t.name}{func_status}: {t.description[:60]}")
            lines.append("")

        return "\n".join(lines)


# 全局单例
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表单例"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def reload_tools() -> dict:
    """
    热加载工具模块：重新导入 tools.py，使新添加的工具立即可用，无需重启服务。
    
    这是 AI 自我进化的关键基础设施——打破"改代码→重启"的闭环断点。
    
    Returns:
        dict: {"status": "ok"/"partial"/"error", "tools_before": int, "tools_after": int, "message": str}
    """
    import importlib
    import agent.tools as tools_module
    
    registry = get_tool_registry()
    
    # 记录重载前的工具数量
    try:
        old_tools = tools_module.get_tools()
        old_count = len(old_tools)
    except Exception:
        old_count = 0
    
    try:
        # 重新加载 tools 模块
        importlib.reload(tools_module)
        
        # 重新设置工具配置（reload 后全局变量会丢失）
        from agent.tools import set_tool_config
        try:
            from agent.tools import _tool_config
            if _tool_config:
                set_tool_config(_tool_config)
        except Exception:
            pass
        
        # 获取新的工具列表
        new_tools = tools_module.get_tools()
        new_count = len(new_tools)
        new_names = [t.name for t in new_tools]
        
        print(f"[ToolRegistry] 热加载完成: {old_count} → {new_count} 个工具")
        print(f"[ToolRegistry] 当前工具: {new_names}")
        
        return {
            "status": "ok",
            "tools_before": old_count,
            "tools_after": new_count,
            "new_tools": [n for n in new_names if n not in [t.name for t in (old_tools if isinstance(old_tools, list) else [])]],
            "message": f"热加载成功: {old_count} → {new_count} 个工具"
        }
    except SyntaxError as e:
        print(f"[ToolRegistry] 热加载失败 - 语法错误: {e}")
        return {
            "status": "error",
            "tools_before": old_count,
            "tools_after": old_count,
            "message": f"语法错误，热加载失败: {str(e)}。请检查 tools.py 后重试。"
        }
    except Exception as e:
        print(f"[ToolRegistry] 热加载失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "tools_before": old_count,
            "tools_after": old_count,
            "message": f"热加载失败: {str(e)}"
        }


def validate_tool_code(code: str) -> tuple[bool, str]:
    """
    验证工具代码的语法正确性，在写入文件前使用。
    
    Args:
        code: 完整的工具函数代码（含 @tool 装饰器）
    
    Returns:
        (is_valid, message)
    """
    import ast
    
    # 1. 基础语法检查
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Python 语法错误: {str(e)}"
    
    # 2. 检查是否包含函数定义
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    if not functions:
        return False, "代码中没有找到函数定义"
    
    func_names = [f.name for f in functions]
    
    # 3. 检查是否有 @tool 装饰器（简单字符串匹配）
    if "@tool" not in code:
        return False, "函数缺少 @tool 装饰器"
    
    # 4. 检查是否包含危险操作
    dangerous_patterns = [
        "import os", "import subprocess", "import sys",
        "os.system", "os.popen", "subprocess.call", "subprocess.Popen",
        "shutil.rmtree", "os.remove", "os.unlink", "os.rmdir",
        "__import__", "eval(", "exec(", "compile(",
    ]
    found_dangerous = []
    for pattern in dangerous_patterns:
        if pattern in code:
            found_dangerous.append(pattern)
    
    if found_dangerous:
        return False, f"代码包含潜在危险操作: {', '.join(found_dangerous)}。如需这些操作，请在现有工具基础上扩展。"
    
    return True, f"验证通过：找到 {len(functions)} 个函数: {', '.join(func_names)}"
