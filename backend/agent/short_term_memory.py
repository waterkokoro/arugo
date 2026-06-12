"""
短期记忆系统 —— 滑动窗口的文件持久化

将当前会话的滑动窗口以可读的 Markdown 文件形式持久化，
随时可查看、删除。解决纯内存滑动窗口重启丢失的问题。

三层记忆架构（更新后）：
1. 短期记忆：当前会话滑动窗口 → memory_store/short_term/current.md（本模块）
2. 持久记忆：跨会话结构化记忆 → memory_store/main.jsonl
3. 元记忆：进化事件日志 → memory_store/evolution_log.jsonl

存储位置：memory_store/short_term/
- current.md: 始终反映当前滑动窗口（实时镜像）
- YYYY-MM-DD_HHMMSS.md: 归档快照（窗口满载或会话结束时自动归档）
"""

import os
import glob
from datetime import datetime
from typing import List, Dict, Optional

# 存储目录
MEMORY_DIR = os.path.join(os.path.dirname(__file__), "memory_store")
SHORT_TERM_DIR = os.path.join(MEMORY_DIR, "short_term")


def _ensure_dir():
    """确保短期记忆目录存在"""
    os.makedirs(SHORT_TERM_DIR, exist_ok=True)


class ShortTermMemory:
    """短期记忆管理器 —— MD 文件持久化的滑动窗口

    用法：
        stm = ShortTermMemory()
        stm.update_current_window(messages, window_size)  # 每次 build_context 时
        stm.archive_current()                               # 窗口满载或会话结束时
    """

    def __init__(self):
        _ensure_dir()

    # ────────────────────────────────────────────
    # 实时镜像
    # ────────────────────────────────────────────

    @property
    def current_path(self) -> str:
        """当前滑动窗口的 MD 文件路径"""
        return os.path.join(SHORT_TERM_DIR, "current.md")

    def update_current_window(self, messages: List[Dict[str, str]], window_size: int):
        """将当前滑动窗口写入 current.md

        Args:
            messages: 当前上下文消息列表（不含 system prompt）
            window_size: 滑动窗口大小配置
        """
        _ensure_dir()

        # 过滤掉 system 消息
        dialog = [m for m in messages if m.get("role") != "system"]

        with open(self.current_path, "w", encoding="utf-8") as f:
            f.write(f"# 短期记忆（滑动窗口）\n\n")
            f.write(f"> 更新时间: {datetime.now().isoformat()}\n")
            f.write(f"> 窗口配置: {window_size} 条 | 当前消息: {len(dialog)} 条\n")
            f.write(f"> 使用率: {len(dialog) / max(window_size, 1) * 100:.0f}%\n\n")
            f.write(f"---\n\n")

            if not dialog:
                f.write("*(窗口为空)*\n")
                return

            for msg in dialog:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                # 截断过长的消息
                if len(content) > 3000:
                    content = content[:3000] + "\n\n*(内容过长，已截断...)*"

                emoji = {"user": "👤", "assistant": "🤖", "tool": "🔧"}.get(role, "❓")
                f.write(f"### {emoji} [{role}]\n\n{content}\n\n")

    def append_message(self, role: str, content: str, window_size: int = 50):
        """向 current.md 追加一条消息（用于飞书等外部渠道的实时同步）

        流式追加策略：
        1. 如果 current.md 不存在 → 创建新窗口
        2. 如果存在 → 读取现有消息列表，追加后重写（保持窗口上限）

        Args:
            role: 消息角色 (user/assistant/tool)
            content: 消息内容
            window_size: 窗口上限，默认 50
        """
        _ensure_dir()

        # 读取现有消息
        existing = []
        if os.path.exists(self.current_path):
            # 从 MD 文件回解析消息（尽量恢复）
            existing = self._parse_messages_from_md()

        # 追加新消息
        existing.append({"role": role, "content": content})

        # 保持窗口上限
        if len(existing) > window_size:
            existing = existing[-window_size:]

        # 重写 current.md
        with open(self.current_path, "w", encoding="utf-8") as f:
            f.write(f"# 短期记忆（滑动窗口）\n\n")
            f.write(f"> 更新时间: {datetime.now().isoformat()}\n")
            f.write(f"> 窗口配置: {window_size} 条 | 当前消息: {len(existing)} 条\n")
            f.write(f"> 使用率: {len(existing) / max(window_size, 1) * 100:.0f}%\n\n")
            f.write(f"---\n\n")

            if not existing:
                f.write("*(窗口为空)*\n")
                return

            for msg in existing:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if len(content) > 3000:
                    content = content[:3000] + "\n\n*(内容过长，已截断...)*"

                emoji = {"user": "👤", "assistant": "🤖", "tool": "🔧"}.get(role, "❓")
                f.write(f"### {emoji} [{role}]\n\n{content}\n\n")

    def _parse_messages_from_md(self) -> List[Dict[str, str]]:
        """从 current.md 反向解析消息列表（尽力而为）

        解析 Markdown 中的 `### {emoji} [role]` 格式。
        失败则返回空列表。
        """
        if not os.path.exists(self.current_path):
            return []

        try:
            with open(self.current_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return []

        import re
        messages = []
        # 匹配 ### {emoji} [role] 后面的内容直到下一个 ### 或 EOF
        pattern = r'### [^\n]+ \[(\w+)\]\n\n(.*?)(?=\n### |\Z)'
        for match in re.finditer(pattern, content, re.DOTALL):
            role = match.group(1)
            msg_content = match.group(2).strip()
            if msg_content and msg_content != "*(窗口为空)*":
                messages.append({"role": role, "content": msg_content})

        return messages

    def load_current(self) -> Optional[str]:
        """读取 current.md 内容"""
        if not os.path.exists(self.current_path):
            return None
        with open(self.current_path, "r", encoding="utf-8") as f:
            return f.read()

    def clear_current(self):
        """清空 current.md（开始新窗口）"""
        if os.path.exists(self.current_path):
            os.remove(self.current_path)

    # ────────────────────────────────────────────
    # 归档快照
    # ────────────────────────────────────────────

    def archive_current(self, label: str = "") -> Optional[str]:
        """将 current.md 归档为带时间戳的快照文件

        Args:
            label: 归档标签（如 "auto_summarize", "session_end"），会写入文件名

        Returns:
            归档文件路径，如果 current.md 不存在则返回 None
        """
        if not os.path.exists(self.current_path):
            return None

        _ensure_dir()
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        label_part = f"_{label}" if label else ""
        filename = f"{timestamp}{label_part}.md"
        dest = os.path.join(SHORT_TERM_DIR, filename)

        # 读取 current.md，修改标题并写入归档
        with open(self.current_path, "r", encoding="utf-8") as src:
            content = src.read()

        # 在标题下添加归档信息
        content = content.replace(
            "# 短期记忆（滑动窗口）",
            f"# 短期记忆快照\n\n> 📦 归档时间: {datetime.now().isoformat()}\n> 🏷️ 标签: {label or '未标记'}",
        )

        with open(dest, "w", encoding="utf-8") as dst:
            dst.write(content)

        # 归档后清空 current.md
        self.clear_current()

        return dest

    # ────────────────────────────────────────────
    # 文件管理
    # ────────────────────────────────────────────

    def list_snapshots(self) -> List[dict]:
        """列出所有短期记忆文件（不含 current.md）

        Returns:
            文件信息列表，按时间倒序
        """
        _ensure_dir()
        files = []
        for f in glob.glob(os.path.join(SHORT_TERM_DIR, "*.md")):
            basename = os.path.basename(f)
            if basename == "current.md":
                continue
            stat = os.stat(f)
            files.append({
                "filename": basename,
                "path": f,
                "size_bytes": stat.st_size,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        files.sort(key=lambda x: x["modified"], reverse=True)

        # 如果 current.md 存在，放在最前面
        if os.path.exists(self.current_path):
            stat = os.stat(self.current_path)
            files.insert(0, {
                "filename": "current.md",
                "path": self.current_path,
                "size_bytes": stat.st_size,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "is_current": True,
            })

        return files

    def read_snapshot(self, filename: str) -> Optional[str]:
        """读取指定短期记忆文件

        Args:
            filename: 文件名（如 "current.md" 或 "2026-06-13_143000.md"）
        """
        # 安全检查：防止路径遍历
        safe_name = os.path.basename(filename)
        if safe_name != filename:
            return None

        filepath = os.path.join(SHORT_TERM_DIR, safe_name)
        if not os.path.isfile(filepath):
            return None

        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    def delete_snapshot(self, filename: str) -> bool:
        """删除指定短期记忆文件

        Args:
            filename: 文件名（不能删除 current.md）
        """
        safe_name = os.path.basename(filename)
        if safe_name != filename or safe_name == "current.md":
            return False

        filepath = os.path.join(SHORT_TERM_DIR, safe_name)
        if not os.path.isfile(filepath):
            return False

        os.remove(filepath)
        return True

    def delete_all_snapshots(self) -> int:
        """删除所有归档快照（保留 current.md）

        Returns:
            删除的文件数
        """
        _ensure_dir()
        count = 0
        for f in glob.glob(os.path.join(SHORT_TERM_DIR, "*.md")):
            if os.path.basename(f) == "current.md":
                continue
            os.remove(f)
            count += 1
        return count

    def get_stats(self) -> dict:
        """获取短期记忆统计"""
        _ensure_dir()
        snapshots = self.list_snapshots()
        has_current = any(s.get("is_current") for s in snapshots)
        archived = [s for s in snapshots if not s.get("is_current")]
        total_size = sum(s["size_bytes"] for s in snapshots)

        return {
            "total_files": len(snapshots),
            "archived_snapshots": len(archived),
            "has_current": has_current,
            "total_size_kb": round(total_size / 1024, 1),
            "files": snapshots[:20],  # 最近 20 个
        }


# 全局单例
_short_term_memory: Optional[ShortTermMemory] = None


def get_short_term_memory() -> ShortTermMemory:
    """获取短期记忆管理器单例"""
    global _short_term_memory
    if _short_term_memory is None:
        _short_term_memory = ShortTermMemory()
    return _short_term_memory
