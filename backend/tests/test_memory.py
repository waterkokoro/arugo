"""持久记忆系统测试"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.memory import PersistentMemoryManager, MemoryEntry, MemoryStore


class TestMemoryEntry:
    """MemoryEntry 数据类测试"""

    def test_create_entry(self):
        entry = MemoryEntry(
            content="Test memory",
            importance=4,
            tags=["test", "unit"],
            category="learned",
        )
        assert entry.content == "Test memory"
        assert entry.importance == 4
        assert "test" in entry.tags
        assert entry.category == "learned"
        assert entry.id  # 自动生成
        assert entry.timestamp  # 自动生成

    def test_to_dict_roundtrip(self):
        entry = MemoryEntry(
            content="Test content",
            importance=3,
            tags=["a", "b"],
            category="user_preference",
        )
        d = entry.to_dict()
        restored = MemoryEntry.from_dict(d)
        assert restored.content == entry.content
        assert restored.importance == entry.importance
        assert restored.tags == entry.tags
        assert restored.category == entry.category


class TestMemoryStore:
    """MemoryStore 存储层测试"""

    def test_add_and_search(self):
        store = MemoryStore()
        entry = MemoryEntry(
            content="用户喜欢深色主题",
            importance=5,
            tags=["偏好", "UI"],
            category="user_preference",
        )
        store.add(entry)

        # 搜索
        results = store.search(query="深色")
        assert len(results) >= 1
        assert "深色主题" in results[0].content

    def test_search_by_category(self):
        store = MemoryStore()
        store.add(MemoryEntry(content="A decision", category="decision"))
        store.add(MemoryEntry(content="A preference", category="user_preference"))

        results = store.search(category="decision")
        assert all(r.category == "decision" for r in results)

    def test_search_by_tags(self):
        store = MemoryStore()
        store.add(MemoryEntry(content="Tagged A", tags=["alpha"]))
        store.add(MemoryEntry(content="Tagged B", tags=["beta"]))

        results = store.search(tags=["alpha"])
        assert all("alpha" in r.tags for r in results)

    def test_get_all_categories(self):
        store = MemoryStore()
        store.add(MemoryEntry(content="A", category="cat1"))
        store.add(MemoryEntry(content="B", category="cat2"))

        cats = store.get_all_categories()
        assert "cat1" in cats
        assert "cat2" in cats

    def test_get_all_tags(self):
        store = MemoryStore()
        store.add(MemoryEntry(content="A", tags=["t1", "t2"]))
        store.add(MemoryEntry(content="B", tags=["t2", "t3"]))

        tags = store.get_all_tags()
        assert "t1" in tags
        assert "t2" in tags
        assert "t3" in tags

    def test_importance_sorting(self):
        """高重要性应排在前面"""
        store = MemoryStore()
        store.add(MemoryEntry(content="Low", importance=1))
        store.add(MemoryEntry(content="High", importance=5))

        results = store.search(query="")  # 获取全部
        # 第一个应该是重要性最高的
        assert results[0].importance >= results[-1].importance

    def test_limit(self):
        store = MemoryStore()
        for i in range(10):
            store.add(MemoryEntry(content=f"Memory {i}", importance=1))

        results = store.search(query="", limit=5)
        assert len(results) <= 5
