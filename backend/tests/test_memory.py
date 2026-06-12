"""测试持久记忆系统"""

import os
import sys
import json
import tempfile
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


class TestMemoryStore:
    """MemoryStore 单元测试"""

    def test_init_creates_directory(self, monkeypatch):
        """初始化自动创建存储目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("agent.memory.MEMORY_DIR", tmpdir)
            from agent.memory import MemoryStore
            store = MemoryStore(store_name="test_init")
            assert os.path.isdir(tmpdir)

    def test_add_entry(self, monkeypatch):
        """添加记忆条目"""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("agent.memory.MEMORY_DIR", tmpdir)
            from agent.memory import MemoryStore, MemoryEntry
            store = MemoryStore(store_name="test_add")
            entry = MemoryEntry(
                content="测试记忆",
                category="test",
                importance=4,
                tags=["unit_test"],
            )
            store.add(entry)
            assert len(store.entries) == 1
            assert store.entries[0].content == "测试记忆"

    def test_search_by_query(self, monkeypatch):
        """按关键词搜索"""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("agent.memory.MEMORY_DIR", tmpdir)
            from agent.memory import MemoryStore, MemoryEntry
            store = MemoryStore(store_name="test_query")
            store.add(MemoryEntry(content="飞书机器人配置", category="config", importance=5, tags=["飞书"]))
            store.add(MemoryEntry(content="用户喜欢深色主题", category="user_preference", importance=4, tags=["偏好"]))
            results = store.search(query="飞书")
            assert len(results) == 1
            assert "飞书机器人" in results[0].content

    def test_search_by_category(self, monkeypatch):
        """按类别过滤"""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("agent.memory.MEMORY_DIR", tmpdir)
            from agent.memory import MemoryStore, MemoryEntry
            store = MemoryStore(store_name="test_cat")
            store.add(MemoryEntry(content="记忆A", category="learned", importance=3))
            store.add(MemoryEntry(content="记忆B", category="user_preference", importance=3))
            results = store.search(category="learned")
            assert len(results) == 1
            assert results[0].content == "记忆A"

    def test_search_by_tags(self, monkeypatch):
        """按标签过滤"""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("agent.memory.MEMORY_DIR", tmpdir)
            from agent.memory import MemoryStore, MemoryEntry
            store = MemoryStore(store_name="test_tags")
            store.add(MemoryEntry(content="项目进展", tags=["Phase1", "urgent"], importance=5))
            store.add(MemoryEntry(content="用户偏好", tags=["preference"], importance=3))
            results = store.search(tags=["Phase1"])
            assert len(results) == 1
            assert results[0].content == "项目进展"

    def test_limit_results(self, monkeypatch):
        """限制返回数量"""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("agent.memory.MEMORY_DIR", tmpdir)
            from agent.memory import MemoryStore, MemoryEntry
            store = MemoryStore(store_name="test_limit")
            for i in range(20):
                store.add(MemoryEntry(content=f"记忆{i}", importance=3))
            results = store.search(limit=5)
            assert len(results) <= 5

    def test_get_all_categories(self, monkeypatch):
        """获取所有类别"""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("agent.memory.MEMORY_DIR", tmpdir)
            from agent.memory import MemoryStore, MemoryEntry
            store = MemoryStore(store_name="test_cats")
            store.add(MemoryEntry(content="A", category="learned"))
            store.add(MemoryEntry(content="B", category="user_preference"))
            cats = store.get_all_categories()
            assert "learned" in cats
            assert "user_preference" in cats

    def test_get_all_tags(self, monkeypatch):
        """获取所有标签"""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("agent.memory.MEMORY_DIR", tmpdir)
            from agent.memory import MemoryStore, MemoryEntry
            store = MemoryStore(store_name="test_taglist")
            store.add(MemoryEntry(content="A", tags=["tag1", "tag2"]))
            store.add(MemoryEntry(content="B", tags=["tag2", "tag3"]))
            tags = store.get_all_tags()
            assert "tag1" in tags
            assert "tag2" in tags
            assert "tag3" in tags

    def test_importance_sorting(self, monkeypatch):
        """重要性排序（高优先在前）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("agent.memory.MEMORY_DIR", tmpdir)
            from agent.memory import MemoryStore, MemoryEntry
            store = MemoryStore(store_name="test_imp")
            store.add(MemoryEntry(content="重要", importance=5))
            store.add(MemoryEntry(content="普通", importance=2))
            results = store.search()
            assert len(results) == 2
            # 重要性高的排前面
            assert results[0].importance >= results[1].importance

    def test_persistence(self, monkeypatch):
        """记忆持久化到磁盘后重新加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("agent.memory.MEMORY_DIR", tmpdir)
            from agent.memory import MemoryStore, MemoryEntry
            store1 = MemoryStore(store_name="test_persist")
            store1.add(MemoryEntry(content="持久化测试", category="test", importance=5))

            store2 = MemoryStore(store_name="test_persist")
            assert len(store2.entries) == 1
            assert store2.entries[0].content == "持久化测试"


class TestPersistentMemoryManager:
    """PersistentMemoryManager 集成测试"""

    def test_remember_and_search(self):
        """remember → search 闭环"""
        from agent.memory import PersistentMemoryManager
        mgr = PersistentMemoryManager()
        before = len(mgr.store.entries)
        mgr.remember(content="[TEST] 集成测试记忆", importance=4, tags=["integration"])
        results = mgr.search_memory(query="集成测试")
        assert len(results) >= 1
        assert any("集成测试" in r.content for r in results)

    def test_log_evolution(self):
        """记录进化事件"""
        from agent.memory import PersistentMemoryManager
        mgr = PersistentMemoryManager()
        mgr.log_evolution("test_event", "[TEST] 测试事件")
        events = mgr.get_evolution_log(limit=20)
        assert len(events) >= 1
        assert any(e["type"] == "test_event" for e in events)
