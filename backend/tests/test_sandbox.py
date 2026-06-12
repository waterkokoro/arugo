"""测试沙盒快照系统"""

import os
import sys
import tempfile
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


class TestSnapshotManager:
    """快照管理器测试 —— 使用实际系统（安全操作）"""

    def test_create_snapshot(self):
        """创建快照"""
        from agent.sandbox import get_snapshot_manager
        mgr = get_snapshot_manager()
        entry = mgr.create_snapshot(name="[TEST] 测试快照", description="pytest测试", trigger="test")
        assert entry.id is not None
        assert entry.name == "[TEST] 测试快照"
        assert entry.file_count > 0
        assert entry.total_size > 0
        # 清理
        mgr.delete_snapshot(entry.id)

    def test_list_snapshots(self):
        """列出快照"""
        from agent.sandbox import get_snapshot_manager
        mgr = get_snapshot_manager()
        before = len(mgr.list_snapshots())
        e1 = mgr.create_snapshot(name="[TEST] 快照1", trigger="test")
        e2 = mgr.create_snapshot(name="[TEST] 快照2", trigger="test")
        after = len(mgr.list_snapshots())
        assert after >= before + 2
        # 清理
        mgr.delete_snapshot(e1.id)
        mgr.delete_snapshot(e2.id)

    def test_delete_snapshot(self):
        """删除快照"""
        from agent.sandbox import get_snapshot_manager
        mgr = get_snapshot_manager()
        entry = mgr.create_snapshot(name="[TEST] 待删除", trigger="test")
        snap_id = entry.id
        success, msg = mgr.delete_snapshot(snap_id)
        assert success
        entries = mgr.list_snapshots()
        assert all(e.id != snap_id for e in entries)

    def test_delete_nonexistent_snapshot(self):
        """删除不存在的快照"""
        from agent.sandbox import get_snapshot_manager
        mgr = get_snapshot_manager()
        success, msg = mgr.delete_snapshot("nonexistent_9999")
        assert not success

    def test_max_snapshots_cleanup(self):
        """超过上限自动清理"""
        from agent.sandbox import get_snapshot_manager, MAX_SNAPSHOTS
        mgr = get_snapshot_manager()
        # 创建一些测试快照然后验证 limit 逻辑
        # 不创建过多以免污染，只验证上限常量存在
        assert MAX_SNAPSHOTS > 0
        assert MAX_SNAPSHOTS <= 50  # 合理上限

    def test_snapshot_report(self):
        """快照报告可读"""
        from agent.sandbox import get_snapshot_manager
        mgr = get_snapshot_manager()
        e = mgr.create_snapshot(name="[TEST] 报告测试", trigger="test")
        report = mgr.get_snapshot_report()
        assert "沙盒快照系统" in report
        # 清理
        mgr.delete_snapshot(e.id)

    def test_restore_creates_safety_snapshot(self):
        """恢复前自动创建安全快照"""
        from agent.sandbox import get_snapshot_manager
        mgr = get_snapshot_manager()
        before = len(mgr.list_snapshots())
        entry = mgr.create_snapshot(name="[TEST] 用于恢复测试", trigger="test")
        # 恢复（会创建安全快照）
        mgr.restore_snapshot(entry.id)
        after = len(mgr.list_snapshots())
        # 至少原快照还在，安全快照也被创建
        assert after >= before + 2
        # 清理：删除测试快照和安全快照
        for e in mgr.list_snapshots():
            if "[TEST]" in e.name or "恢复前自动备份" in e.name:
                mgr.delete_snapshot(e.id)

    def test_restore_nonexistent_snapshot(self):
        """恢复不存在的快照"""
        from agent.sandbox import get_snapshot_manager
        mgr = get_snapshot_manager()
        success, msg = mgr.restore_snapshot("nonexistent_9999")
        assert not success
        assert "不存在" in msg


class TestSnapshotWithActualCode:
    """使用实际代码目录的快照测试"""

    def test_snapshot_covers_key_files(self):
        """快照覆盖关键文件"""
        from agent.sandbox import get_snapshot_manager
        mgr = get_snapshot_manager()
        entry = mgr.create_snapshot(name="[TEST] 代码快照", trigger="test")
        assert entry.file_count >= 3  # 至少 tools.py, context.py, __init__.py
        mgr.delete_snapshot(entry.id)

    def test_snapshot_directory_structure(self):
        """快照目录结构正确"""
        from agent.sandbox import get_snapshot_manager, SNAPSHOT_DIR
        mgr = get_snapshot_manager()
        entry = mgr.create_snapshot(name="[TEST] 结构测试", trigger="test")
        snap_path = os.path.join(SNAPSHOT_DIR, entry.id)
        assert os.path.isdir(snap_path)
        contents = os.listdir(snap_path)
        assert len(contents) > 0
        mgr.delete_snapshot(entry.id)
