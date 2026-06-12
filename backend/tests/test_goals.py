"""测试目标与里程碑管理器"""

import os
import sys
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from agent.goal_manager import get_goal_manager, Goal, Milestone


class TestGoalCRUD:
    """目标基本 CRUD —— 使用实际存储"""

    def test_create_goal(self):
        """创建目标"""
        gm = get_goal_manager()
        g = gm.create_goal(
            title="[TEST] 测试目标",
            description="用于测试的目标",
            priority=3,
            tags=["test"],
        )
        assert g.id is not None
        assert g.title == "[TEST] 测试目标"
        assert g.status == "active"
        assert g.progress == 0
        # 清理
        gm._goals.pop(g.id, None)
        gm._save()

    def test_create_multiple_goals(self):
        """创建多个目标，ID 不同"""
        gm = get_goal_manager()
        g1 = gm.create_goal(title="[TEST] 目标A")
        g2 = gm.create_goal(title="[TEST] 目标B")
        assert g1.id != g2.id
        # 清理
        gm._goals.pop(g1.id, None)
        gm._goals.pop(g2.id, None)
        gm._save()

    def test_list_goals(self):
        """列出目标"""
        gm = get_goal_manager()
        g1 = gm.create_goal(title="[TEST] 活跃")
        g2 = gm.create_goal(title="[TEST] 已完成")
        gm.update_goal(g2.id, status="completed")

        all_goals = gm.list_goals()
        assert len(all_goals) >= 2

        active = gm.list_goals(status="active")
        assert any(g.title == "[TEST] 活跃" for g in active)

        # 清理
        gm._goals.pop(g1.id, None)
        gm._goals.pop(g2.id, None)
        gm._save()

    def test_update_goal_status(self):
        """更新目标状态"""
        gm = get_goal_manager()
        g = gm.create_goal(title="[TEST] 待完成")
        updated = gm.update_goal(g.id, status="completed")
        assert updated is not None
        assert updated.status == "completed"
        # 清理
        gm._goals.pop(g.id, None)
        gm._save()

    def test_update_goal_priority(self):
        """更新目标优先级"""
        gm = get_goal_manager()
        g = gm.create_goal(title="[TEST] 低优先级", priority=1)
        updated = gm.update_goal(g.id, priority=5)
        assert updated.priority == 5
        # 清理
        gm._goals.pop(g.id, None)
        gm._save()

    def test_get_nonexistent_goal(self):
        """获取不存在的目标返回 None"""
        gm = get_goal_manager()
        assert gm.get_goal("nonexistent_id_9999") is None

    def test_persistence(self):
        """目标持久化"""
        gm = get_goal_manager()
        g = gm.create_goal(title="[TEST] 持久化测试")
        gm._save()
        # 重新加载
        gm2 = get_goal_manager()
        loaded = gm2.get_goal(g.id)
        assert loaded is not None
        assert loaded.title == "[TEST] 持久化测试"
        # 清理
        gm2._goals.pop(g.id, None)
        gm2._save()


class TestMilestones:
    """里程碑管理"""

    def test_add_milestone(self):
        """添加里程碑"""
        gm = get_goal_manager()
        g = gm.create_goal(title="[TEST] 里程碑目标")
        m = gm.add_milestone(g.id, "第一步", "完成 A")
        assert m is not None
        assert m.id is not None
        assert m.title == "第一步"
        assert m.status == "pending"
        # 清理
        gm._goals.pop(g.id, None)
        gm._save()

    def test_add_milestone_to_nonexistent_goal(self):
        """向不存在的目标添加里程碑返回 None"""
        gm = get_goal_manager()
        m = gm.add_milestone("fake_id_nonexistent", "test")
        assert m is None

    def test_update_milestone_status(self):
        """更新里程碑状态"""
        gm = get_goal_manager()
        g = gm.create_goal(title="[TEST] 更新里程碑")
        m = gm.add_milestone(g.id, "里程碑1")
        updated = gm.update_milestone(g.id, m.id, status="in_progress")
        assert updated is not None
        assert updated.status == "in_progress"
        # 清理
        gm._goals.pop(g.id, None)
        gm._save()

    def test_milestone_completion_updates_goal_progress(self):
        """完成里程碑 → 目标进度自动更新"""
        gm = get_goal_manager()
        g = gm.create_goal(title="[TEST] 进度测试")
        gm.add_milestone(g.id, "M1")
        m2 = gm.add_milestone(g.id, "M2")
        gm.update_milestone(g.id, m2.id, status="completed")

        g_updated = gm.get_goal(g.id)
        assert g_updated.progress == 50

        # 清理
        gm._goals.pop(g.id, None)
        gm._save()

    def test_all_milestones_completed(self):
        """所有里程碑完成 → 目标进度 100%"""
        gm = get_goal_manager()
        g = gm.create_goal(title="[TEST] 全完成")
        m1 = gm.add_milestone(g.id, "M1")
        m2 = gm.add_milestone(g.id, "M2")
        m3 = gm.add_milestone(g.id, "M3")
        gm.update_milestone(g.id, m1.id, status="completed")
        gm.update_milestone(g.id, m2.id, status="completed")
        gm.update_milestone(g.id, m3.id, status="completed")

        g_updated = gm.get_goal(g.id)
        assert g_updated.progress == 100
        # 清理
        gm._goals.pop(g.id, None)
        gm._save()

    def test_update_milestone_progress(self):
        """更新里程碑进度"""
        gm = get_goal_manager()
        g = gm.create_goal(title="[TEST] 进度里程碑")
        m = gm.add_milestone(g.id, "进行中")
        updated = gm.update_milestone(g.id, m.id, progress=50)
        assert updated.progress == 50
        # 清理
        gm._goals.pop(g.id, None)
        gm._save()


class TestGoalManagerEdgeCases:
    """边界情况"""

    def test_filter_nonexistent_status(self):
        """过滤不存在的状态"""
        gm = get_goal_manager()
        goals = gm.list_goals(status="unknown_status_xyz")
        assert goals == []

    def test_deadline_format(self):
        """截止日期格式"""
        gm = get_goal_manager()
        g = gm.create_goal(title="[TEST] 有截止", deadline="2026-12-31")
        assert g.deadline == "2026-12-31"
        # 清理
        gm._goals.pop(g.id, None)
        gm._save()
