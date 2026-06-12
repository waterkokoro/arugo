"""
持久记忆系统 - 突破滑动窗口限制

实现三层记忆架构：
1. 工作记忆：当前会话（滑动窗口，由 ContextManager 管理）
2. 持久记忆：跨会话持久化的结构化记忆（本模块）
3. 元记忆：关于记忆的记忆，记录学习模式和进化轨迹

存储位置：backend/agent/memory_store/ 目录下的文件
"""

import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

# 记忆存储目录
MEMORY_DIR = os.path.join(os.path.dirname(__file__), "memory_store")


def _ensure_memory_dir():
    """确保记忆目录存在"""
    os.makedirs(MEMORY_DIR, exist_ok=True)


# ============================================================
# 记忆数据结构
# ============================================================

class MemoryEntry:
    """单条记忆条目"""
    def __init__(
        self,
        content: str,
        category: str = "general",
        importance: int = 1,  # 1-5，越高越重要
        tags: list = None,
        source_session: str = None,
    ):
        self.content = content
        self.category = category
        self.importance = importance
        self.tags = tags or []
        self.timestamp = datetime.now().isoformat()
        self.source_session = source_session
        self.id = self._generate_id()

    def _generate_id(self) -> str:
        raw = f"{self.timestamp}-{self.content[:100]}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "importance": self.importance,
            "tags": self.tags,
            "timestamp": self.timestamp,
            "source_session": self.source_session,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        entry = cls(
            content=data["content"],
            category=data.get("category", "general"),
            importance=data.get("importance", 1),
            tags=data.get("tags", []),
            source_session=data.get("source_session"),
        )
        entry.timestamp = data.get("timestamp", entry.timestamp)
        entry.id = data.get("id", entry.id)
        return entry


# ============================================================
# 记忆存储后端
# ============================================================

class MemoryStore:
    """基于文件的记忆存储"""

    def __init__(self, store_name: str = "main"):
        _ensure_memory_dir()
        self.store_path = os.path.join(MEMORY_DIR, f"{store_name}.jsonl")
        self.index_path = os.path.join(MEMORY_DIR, f"{store_name}_index.json")
        self.entries: list[MemoryEntry] = []
        self._load()

    def _load(self):
        """从磁盘加载记忆"""
        if os.path.exists(self.store_path):
            with open(self.store_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            self.entries.append(MemoryEntry.from_dict(data))
                        except json.JSONDecodeError:
                            continue

    def _save(self):
        """保存全部记忆到磁盘（全量写入，用于 delete/clear 场景）"""
        with open(self.store_path, "w", encoding="utf-8") as f:
            for entry in self.entries:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        self._update_index()

    def _append(self, entry: MemoryEntry):
        """增量追加单条记忆（高性能写入，仅追加一行）"""
        with open(self.store_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        self._incremental_update_index(entry)

    def _update_index(self):
        """全量重建索引（用于 delete/clear 后）"""
        index = {"categories": {}, "tags": {}, "total": len(self.entries)}
        for entry in self.entries:
            cat = entry.category
            if cat not in index["categories"]:
                index["categories"][cat] = []
            index["categories"][cat].append(entry.id)

            for tag in entry.tags:
                if tag not in index["tags"]:
                    index["tags"][tag] = []
                index["tags"][tag].append(entry.id)

        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def _incremental_update_index(self, entry: MemoryEntry):
        """增量更新索引（仅追加新条目，O(1)）"""
        index = {"categories": {}, "tags": {}, "total": len(self.entries)}
        if os.path.exists(self.index_path):
            with open(self.index_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
                index["categories"] = existing.get("categories", {})
                index["tags"] = existing.get("tags", {})

        index["total"] = len(self.entries)

        cat = entry.category
        if cat not in index["categories"]:
            index["categories"][cat] = []
        index["categories"][cat].append(entry.id)

        for tag in entry.tags:
            if tag not in index["tags"]:
                index["tags"][tag] = []
            index["tags"][tag].append(entry.id)

        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def add(self, entry: MemoryEntry) -> str:
        """添加记忆条目（增量写入，O(1)磁盘操作）"""
        self.entries.append(entry)
        self._append(entry)  # 高性能：仅追加一行，不重写全文件
        return entry.id

    def search(
        self,
        query: str = None,
        category: str = None,
        tags: list = None,
        min_importance: int = 0,
        limit: int = 20,
    ) -> list[MemoryEntry]:
        """搜索记忆"""
        results = self.entries

        if query:
            query_lower = query.lower()
            results = [
                e for e in results
                if query_lower in e.content.lower()
                or any(query_lower in tag.lower() for tag in e.tags)
            ]

        if category:
            results = [e for e in results if e.category == category]

        if tags:
            results = [e for e in results if any(t in e.tags for t in tags)]

        if min_importance > 0:
            results = [e for e in results if e.importance >= min_importance]

        # 按重要性降序、时间降序排列
        results.sort(key=lambda e: (e.importance, e.timestamp), reverse=True)

        return results[:limit]

    def get_by_id(self, entry_id: str) -> Optional[MemoryEntry]:
        """根据ID获取记忆"""
        for entry in self.entries:
            if entry.id == entry_id:
                return entry
        return None

    def delete(self, entry_id: str) -> bool:
        """删除记忆条目"""
        for i, entry in enumerate(self.entries):
            if entry.id == entry_id:
                self.entries.pop(i)
                self._save()
                return True
        return False

    def get_all_categories(self) -> list[str]:
        """获取所有类别"""
        return list(set(e.category for e in self.entries))

    def get_all_tags(self) -> list[str]:
        """获取所有标签"""
        all_tags = set()
        for e in self.entries:
            all_tags.update(e.tags)
        return list(all_tags)

    def summarize(self, max_items: int = 10) -> str:
        """生成记忆摘要（用于注入上下文）"""
        if not self.entries:
            return ""

        # 取最重要的记忆
        top = sorted(self.entries, key=lambda e: (e.importance, e.timestamp), reverse=True)

        lines = ["[持久记忆 - 跨会话关键信息]"]
        for entry in top[:max_items]:
            imp_stars = "★" * entry.importance
            tags_str = f" [{', '.join(entry.tags)}]" if entry.tags else ""
            lines.append(f"  {imp_stars} [{entry.category}]{tags_str}: {entry.content}")

        return "\n".join(lines)

    def clear(self):
        """清空记忆"""
        self.entries = []
        self._save()


# ============================================================
# 会话摘要管理
# ============================================================

class SessionSummary:
    """会话摘要 - 每次对话结束时的自动总结"""

    def __init__(self):
        _ensure_memory_dir()
        self.summary_path = os.path.join(MEMORY_DIR, "session_brief.md")
        self.evolution_log_path = os.path.join(MEMORY_DIR, "evolution_log.jsonl")

    def save_summary(self, content: str):
        """保存会话摘要（覆盖）"""
        with open(self.summary_path, "w", encoding="utf-8") as f:
            f.write(f"# 上次会话摘要\n\n")
            f.write(f"更新时间: {datetime.now().isoformat()}\n\n")
            f.write(content)

    def load_summary(self) -> str:
        """加载上次会话摘要"""
        if os.path.exists(self.summary_path):
            with open(self.summary_path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def log_evolution(self, event_type: str, description: str, metadata: dict = None):
        """记录进化事件"""
        _ensure_memory_dir()
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "description": description,
            "metadata": metadata or {},
        }
        with open(self.evolution_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_evolution_log(self, limit: int = 20) -> list[dict]:
        """获取进化日志"""
        if not os.path.exists(self.evolution_log_path):
            return []
        entries = []
        with open(self.evolution_log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries[-limit:]


# ============================================================
# 统一记忆管理器（供外部使用）
# ============================================================

class PersistentMemoryManager:
    """统一的持久记忆管理器"""

    def __init__(self, store_name: str = "main"):
        self.store = MemoryStore(store_name)
        self.session = SessionSummary()

    def get_context_injection(self) -> str:
        """
        获取应注入到当前会话上下文的持久记忆内容。
        
        包含：
        1. 上次会话摘要
        2. 最重要的持久记忆条目
        """
        parts = []

        # 加载上次会话摘要
        last_summary = self.session.load_summary()
        if last_summary:
            parts.append(last_summary)

        # 加载重要记忆
        memory_summary = self.store.summarize(max_items=15)
        if memory_summary:
            parts.append(memory_summary)

        return "\n\n".join(parts) if parts else ""

    def add_memory(self, content: str, category: str = "general", importance: int = 1, tags: list = None) -> str:
        """添加持久记忆"""
        entry = MemoryEntry(
            content=content,
            category=category,
            importance=importance,
            tags=tags,
        )
        return self.store.add(entry)

    def search_memory(self, query: str = None, **kwargs) -> list[MemoryEntry]:
        """搜索记忆"""
        return self.store.search(query=query, **kwargs)

    def remember(self, content: str, importance: int = 3, tags: list = None):
        """快捷记忆方法：记住重要信息（默认重要性=3）"""
        return self.add_memory(
            content=content,
            category="learned",
            importance=importance,
            tags=tags or [],
        )

    def end_session(self, summary: str):
        """结束会话时调用，保存摘要"""
        self.session.save_summary(summary)

    def log_evolution(self, event_type: str, description: str, metadata: dict = None):
        """记录进化事件"""
        self.session.log_evolution(event_type, description, metadata)

    def get_evolution_log(self, limit: int = 20) -> list[dict]:
        """获取进化日志"""
        return self.session.get_evolution_log(limit)
