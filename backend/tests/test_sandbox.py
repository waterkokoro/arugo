"""沙盒快照系统测试"""

import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.sandbox import SnapshotManager, SnapshotEntry, get_snapshot_manager


class TestSnapshotEntry:
    """SnapshotEntry 数据类测试"""

    def test_create_entry(self):
        entry = SnapshotEntry(
            id="test_001",
            name="Test Snapshot",
            description="A test",
            file_count=5,
            total_size=1024,
        )
        assert entry.id == "test_001"
        assert entry.name == "Test Snapshot"
        assert entry.file_count == 5
        assert entry.total_size == 1024
        assert entry.trigger == "manual"

    def test_serialization(self):
        entry = SnapshotEntry(
            id="test_001",
            name="Test",
            description="Desc",
            file_count=3,
            total_size=512,
        )
        d = entry.to_dict()
        assert d["id"] == "test_001"
        assert d["file_count"] == 3

        # 反序列化
        restored = SnapshotEntry.from_dict(d)
        assert restored.id == entry.id
        assert restored.name == entry.name
        assert restored.file_count == entry.file_count

    def test_auto_timestamp(self):
        entry = SnapshotEntry(id="test", name="T")
        assert entry.created_at  # 自动生成时间戳


class TestSnapshotManager:
    """SnapshotManager 核心功能测试"""

    def test_list_snapshots(self):
        """列表应返回结果（可能有或没有快照）"""
        mgr = get_snapshot_manager()
        snapshots = mgr.list_snapshots()
        assert isinstance(snapshots, list)

    def test_get_snapshot_report(self):
        """报告应生成字符串"""
        mgr = get_snapshot_manager()
        report = mgr.get_snapshot_report()
        assert isinstance(report, str)
        assert "沙盒快照系统" in report

    def test_create_and_delete_cycle(self):
        """创建→验证→删除 完整周期"""
        mgr = get_snapshot_manager()

        # 创建
        entry = mgr.create_snapshot(
            name="单元测试快照",
            description="pytest 自动创建",
            trigger="manual",
        )
        assert entry is not None
        assert entry.file_count > 0
        assert entry.total_size > 0

        # 验证存在于列表中
        snapshots = mgr.list_snapshots()
        ids = [s.id for s in snapshots]
        assert entry.id in ids

        # 删除
        success, msg = mgr.delete_snapshot(entry.id)
        assert success
        assert "已删除" in msg

        # 验证不再存在
        snapshots = mgr.list_snapshots()
        ids = [s.id for s in snapshots]
        assert entry.id not in ids

    def test_delete_nonexistent(self):
        """删除不存在的快照应返回失败"""
        mgr = get_snapshot_manager()
        success, msg = mgr.delete_snapshot("nonexistent_id")
        assert not success
        assert "不存在" in msg

    def test_restore_nonexistent(self):
        """恢复不存在的快照应返回失败"""
        mgr = get_snapshot_manager()
        success, msg = mgr.restore_snapshot("nonexistent_id")
        assert not success
        assert "不存在" in msg


class TestSnapshotConfig:
    """快照配置验证"""

    def test_source_files_exist(self):
        """所有声明的源文件应实际存在"""
        from agent.sandbox import SNAPSHOT_SOURCE_FILES, AGENT_DIR
        for fname in SNAPSHOT_SOURCE_FILES:
            fpath = os.path.join(AGENT_DIR, fname)
            assert os.path.isfile(fpath), f"快照源文件不存在: {fname}"

    def test_max_snapshots_defined(self):
        """最大快照数应已定义"""
        from agent.sandbox import MAX_SNAPSHOTS
        assert MAX_SNAPSHOTS > 0
        assert MAX_SNAPSHOTS <= 100
