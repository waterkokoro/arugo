"""目标管理器测试"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.goal_manager import Goal, Milestone, GoalManager


class TestGoalDataClass:
    """Goal 数据类测试"""

    def test_create_goal(self):
        g = Goal(
            title="测试目标",
            description="一个测试",
            priority=3,
            tags=["test"],
        )
        assert g.title == "测试目标"
        assert g.priority == 3
        assert g.status == "active"
        assert g.progress == 0
        assert g.id  # 自动生成
        assert g.created_at  # 自动生成

    def test_goal_to_dict(self):
        g = Goal(title="T", priority=5)
        d = g.to_dict()
        assert d["title"] == "T"
        assert d["priority"] == 5
        assert "milestones" in d


class TestMilestoneDataClass:
    """Milestone 数据类测试"""

    def test_create_milestone(self):
        m = Milestone(
            title="M1",
            completion_criteria="完成XYZ",
        )
        assert m.title == "M1"
        assert m.status == "pending"
        assert m.progress == 0
        assert m.id

    def test_milestone_to_dict(self):
        m = Milestone(title="M1", completion_criteria="Finish it")
        d = m.to_dict()
        assert d["title"] == "M1"
        assert d["completion_criteria"] == "Finish it"


class TestGoalManager:
    """GoalManager 核心功能测试"""

    def test_create_and_get_goal(self):
        gm = GoalManager()
        g = gm.create_goal(
            title="测试目标A",
            description="用于测试",
            priority=4,
            tags=["test"],
        )
        assert g is not None
        assert g.title == "测试目标A"

        # 获取
        retrieved = gm.get_goal(g.id)
        assert retrieved is not None
        assert retrieved.title == g.title

        # 清理
        gm.delete_goal(g.id)

    def test_list_goals(self):
        gm = GoalManager()
        g1 = gm.create_goal(title="G1", priority=1)
        g2 = gm.create_goal(title="G2", priority=5)

        goals = gm.list_goals()
        ids = [g.id for g in goals]
        assert g1.id in ids
        assert g2.id in ids

        # 按状态过滤
        active = gm.list_goals(status="active")
        assert all(g.status == "active" for g in active)

        # 清理
        gm.delete_goal(g1.id)
        gm.delete_goal(g2.id)

    def test_update_goal(self):
        gm = GoalManager()
        g = gm.create_goal(title="Old Title", priority=2)

        updated = gm.update_goal(g.id, title="New Title", status="completed")
        assert updated is not None
        assert updated.title == "New Title"
        assert updated.status == "completed"

        gm.delete_goal(g.id)

    def test_add_milestone(self):
        gm = GoalManager()
        g = gm.create_goal(title="Parent Goal")

        m = gm.add_milestone(g.id, "Step 1", "Complete step 1")
        assert m is not None
        assert m.title == "Step 1"

        # 验证关联
        g2 = gm.get_goal(g.id)
        assert len(g2.milestones) == 1

        gm.delete_goal(g.id)

    def test_update_milestone_completes_goal(self):
        """里程碑全部完成时目标进度应为 100%"""
        gm = GoalManager()
        g = gm.create_goal(title="Completion Test")
        m = gm.add_milestone(g.id, "Only Step")

        updated = gm.update_milestone(g.id, m.id, status="completed", progress=100)
        assert updated.status == "completed"

        g2 = gm.get_goal(g.id)
        assert g2.progress == 100

        gm.delete_goal(g.id)

    def test_delete_nonexistent(self):
        gm = GoalManager()
        result = gm.delete_goal("nonexistent")
        assert result is False

    def test_update_nonexistent(self):
        gm = GoalManager()
        result = gm.update_goal("nonexistent", title="X")
        assert result is None
