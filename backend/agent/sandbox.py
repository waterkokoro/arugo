"""
沙盒快照系统 - Phase 3 核心模块

实现多文件原子快照 + 一键回滚：
- SnapshotManager: 快照的创建、列表、恢复、删除
- 覆盖所有 Agent 源码 + 配置文件 + 数据存储
- 与质量门禁集成：关键操作前自动快照

快照范围：
- 源码: tools.py, context.py, memory.py, goal_manager.py, quality_gate.py,
        agent_factory.py, tool_registry.py, __init__.py, llm_client.py, web_search.py
- 配置: system_prompt.txt
- 数据: memory_store/, goal_store/

存储位置：backend/agent/backups/snapshots/
"""

import os
import json
import shutil
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

# ============================================================
# 配置
# ============================================================

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(AGENT_DIR, "backups", "snapshots")

# 快照覆盖的文件（相对于 agent/ 目录）
SNAPSHOT_SOURCE_FILES = [
    "tools.py",
    "context.py",
    "memory.py",
    "goal_manager.py",
    "quality_gate.py",
    "agent_factory.py",
    "tool_registry.py",
    "__init__.py",
    "llm_client.py",
    "web_search.py",
    "system_prompt.txt",
]

# 快照覆盖的数据目录（相对于 agent/ 目录）
SNAPSHOT_DATA_DIRS = [
    "memory_store",
    "goal_store",
]

# 最大快照数量（超过后自动清理最旧的）
MAX_SNAPSHOTS = 20


def _ensure_snapshot_dir():
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)


# ============================================================
# 快照条目
# ============================================================

class SnapshotEntry:
    """快照元数据"""

    def __init__(
        self,
        id: str,
        name: str = "",
        description: str = "",
        created_at: str = None,
        file_count: int = 0,
        total_size: int = 0,
        trigger: str = "manual",  # manual | pre_flight | auto
    ):
        self.id = id
        self.name = name
        self.description = description
        self.created_at = created_at or datetime.now().isoformat()
        self.file_count = file_count
        self.total_size = total_size
        self.trigger = trigger

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "file_count": self.file_count,
            "total_size": self.total_size,
            "trigger": self.trigger,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SnapshotEntry":
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            description=data.get("description", ""),
            created_at=data.get("created_at", ""),
            file_count=data.get("file_count", 0),
            total_size=data.get("total_size", 0),
            trigger=data.get("trigger", "manual"),
        )


# ============================================================
# 快照管理器
# ============================================================

class SnapshotManager:
    """多文件原子快照管理器"""

    def __init__(self):
        _ensure_snapshot_dir()
        self._index_path = os.path.join(SNAPSHOT_DIR, "_index.json")
        self._snapshots: dict[str, SnapshotEntry] = {}
        self._load_index()

    # ========== 索引管理 ==========

    def _load_index(self):
        """加载快照索引"""
        if os.path.exists(self._index_path):
            try:
                with open(self._index_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for sd in data.get("snapshots", []):
                        entry = SnapshotEntry.from_dict(sd)
                        self._snapshots[entry.id] = entry
            except (json.JSONDecodeError, KeyError):
                self._snapshots = {}

    def _save_index(self):
        """保存快照索引"""
        data = {
            "snapshots": [s.to_dict() for s in self._snapshots.values()],
            "updated_at": datetime.now().isoformat(),
        }
        with open(self._index_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _gen_snapshot_id(self) -> str:
        """生成快照 ID（时间戳 + 随机）"""
        raw = f"{datetime.now().isoformat()}-{os.urandom(4).hex()}"
        return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + hashlib.md5(raw.encode()).hexdigest()[:6]

    # ========== 快照操作 ==========

    def create_snapshot(
        self,
        name: str = "",
        description: str = "",
        trigger: str = "manual",
    ) -> SnapshotEntry:
        """创建全状态快照

        Args:
            name: 快照名称（可选，如 "Phase3 改造前"）
            description: 快照描述
            trigger: 触发方式 (manual, pre_flight, auto)

        Returns:
            SnapshotEntry: 快照元数据
        """
        snapshot_id = self._gen_snapshot_id()
        snapshot_path = os.path.join(SNAPSHOT_DIR, snapshot_id)
        os.makedirs(snapshot_path, exist_ok=True)

        file_count = 0
        total_size = 0

        # 1. 复制源码文件
        src_dir = os.path.join(snapshot_path, "src")
        os.makedirs(src_dir, exist_ok=True)

        for filename in SNAPSHOT_SOURCE_FILES:
            filepath = os.path.join(AGENT_DIR, filename)
            if os.path.isfile(filepath):
                dest = os.path.join(src_dir, filename)
                shutil.copy2(filepath, dest)
                file_count += 1
                total_size += os.path.getsize(filepath)

        # 2. 复制数据目录
        data_dir = os.path.join(snapshot_path, "data")
        os.makedirs(data_dir, exist_ok=True)

        for dirname in SNAPSHOT_DATA_DIRS:
            dirpath = os.path.join(AGENT_DIR, dirname)
            if os.path.isdir(dirpath):
                dest = os.path.join(data_dir, dirname)
                shutil.copytree(dirpath, dest)
                for root, _, files in os.walk(dest):
                    for f in files:
                        fp = os.path.join(root, f)
                        file_count += 1
                        total_size += os.path.getsize(fp)

        # 3. 记录快照元数据
        if not name:
            name = f"Snapshot {snapshot_id}"

        entry = SnapshotEntry(
            id=snapshot_id,
            name=name,
            description=description,
            file_count=file_count,
            total_size=total_size,
            trigger=trigger,
        )
        self._snapshots[snapshot_id] = entry
        self._save_index()

        # 4. 清理超出限制的旧快照
        self._cleanup_old_snapshots()

        return entry

    def list_snapshots(self, limit: int = 20) -> list[SnapshotEntry]:
        """列出所有快照，按时间倒序"""
        snapshots = list(self._snapshots.values())
        snapshots.sort(key=lambda s: s.created_at, reverse=True)
        return snapshots[:limit]

    def get_snapshot(self, snapshot_id: str) -> Optional[SnapshotEntry]:
        """获取单个快照信息"""
        return self._snapshots.get(snapshot_id)

    def restore_snapshot(self, snapshot_id: str) -> tuple[bool, str]:
        """从快照恢复所有文件

        Args:
            snapshot_id: 快照 ID

        Returns:
            (success, message)
        """
        entry = self._snapshots.get(snapshot_id)
        if not entry:
            return False, f"快照不存在: {snapshot_id}"

        snapshot_path = os.path.join(SNAPSHOT_DIR, snapshot_id)
        if not os.path.isdir(snapshot_path):
            return False, f"快照数据目录不存在: {snapshot_path}"

        # 恢复前先创建一个安全快照（防止恢复操作本身出错）
        try:
            safety_entry = self.create_snapshot(
                name=f"恢复前自动备份 ({snapshot_id})",
                description=f"在从快照 {snapshot_id} 恢复前自动创建",
                trigger="pre_flight",
            )
        except Exception:
            safety_entry = None  # 即使安全快照失败也继续

        restored_files = []
        failed_files = []

        # 1. 恢复源码文件
        src_dir = os.path.join(snapshot_path, "src")
        if os.path.isdir(src_dir):
            for filename in SNAPSHOT_SOURCE_FILES:
                src_file = os.path.join(src_dir, filename)
                if os.path.isfile(src_file):
                    dest_file = os.path.join(AGENT_DIR, filename)
                    try:
                        shutil.copy2(src_file, dest_file)
                        restored_files.append(filename)
                    except Exception as e:
                        failed_files.append(f"{filename}: {e}")

        # 2. 恢复数据目录
        data_dir = os.path.join(snapshot_path, "data")
        if os.path.isdir(data_dir):
            for dirname in SNAPSHOT_DATA_DIRS:
                src_data = os.path.join(data_dir, dirname)
                if os.path.isdir(src_data):
                    dest_data = os.path.join(AGENT_DIR, dirname)
                    try:
                        if os.path.isdir(dest_data):
                            shutil.rmtree(dest_data)
                        shutil.copytree(src_data, dest_data)
                        restored_files.append(f"{dirname}/ (数据目录)")
                    except Exception as e:
                        failed_files.append(f"{dirname}: {e}")

        safety_msg = f"\n安全快照: {safety_entry.id}" if safety_entry else ""
        msg = (
            f"从快照 '{entry.name}' ({snapshot_id}) 恢复完成。\n"
            f"✅ 已恢复: {', '.join(restored_files) if restored_files else '无'}"
            f"{safety_msg}\n"
            f"⚠️ 请重启服务: ./manage.sh restart\n"
            f"创建时间: {entry.created_at}"
        )
        if failed_files:
            msg += f"\n❌ 失败: {', '.join(failed_files)}"

        return True, msg

    def delete_snapshot(self, snapshot_id: str) -> tuple[bool, str]:
        """删除指定快照

        Args:
            snapshot_id: 快照 ID

        Returns:
            (success, message)
        """
        entry = self._snapshots.get(snapshot_id)
        if not entry:
            return False, f"快照不存在: {snapshot_id}"

        snapshot_path = os.path.join(SNAPSHOT_DIR, snapshot_id)
        if os.path.isdir(snapshot_path):
            try:
                shutil.rmtree(snapshot_path)
            except Exception as e:
                return False, f"删除快照文件失败: {e}"

        del self._snapshots[snapshot_id]
        self._save_index()

        return True, f"快照 '{entry.name}' ({snapshot_id}) 已删除"

    def _cleanup_old_snapshots(self):
        """清理超出数量限制的旧快照"""
        if len(self._snapshots) <= MAX_SNAPSHOTS:
            return

        snapshots = sorted(
            self._snapshots.values(),
            key=lambda s: s.created_at,
        )
        to_delete = snapshots[: len(snapshots) - MAX_SNAPSHOTS]

        for entry in to_delete:
            snapshot_path = os.path.join(SNAPSHOT_DIR, entry.id)
            if os.path.isdir(snapshot_path):
                shutil.rmtree(snapshot_path)
            del self._snapshots[entry.id]

        self._save_index()

    def pre_flight_snapshot(self, operation: str, target: str) -> Optional[SnapshotEntry]:
        """关键操作前自动创建轻量快照

        Args:
            operation: 操作类型（如 "add_tool_to_self", "write_file"）
            target: 操作目标（如工具名、文件路径）

        Returns:
            快照条目，失败返回 None
        """
        try:
            return self.create_snapshot(
                name=f"Pre-flight: {operation} → {target}",
                description=f"操作 '{operation}' 在 '{target}' 前的自动快照",
                trigger="pre_flight",
            )
        except Exception as e:
            print(f"[Sandbox] Pre-flight snapshot failed: {e}")
            return None

    def get_snapshot_report(self) -> str:
        """生成快照系统状态报告"""
        snapshots = self.list_snapshots()
        total_size = sum(s.total_size for s in snapshots)
        pre_flight_count = sum(1 for s in snapshots if s.trigger == "pre_flight")
        manual_count = sum(1 for s in snapshots if s.trigger == "manual")

        lines = [
            f"[沙盒快照系统]",
            f"快照总数: {len(snapshots)} (最多 {MAX_SNAPSHOTS})",
            f"  - 手动快照: {manual_count}",
            f"  - 操作前自动快照: {pre_flight_count}",
            f"总占用空间: {total_size / 1024:.1f} KB",
            f"存储位置: {SNAPSHOT_DIR}",
        ]

        if snapshots:
            lines.append(f"\n最近快照:")
            for s in snapshots[:5]:
                kb = s.total_size / 1024
                trigger_icon = {"manual": "📸", "pre_flight": "🛡️", "auto": "🤖"}.get(s.trigger, "❓")
                lines.append(
                    f"  {trigger_icon} {s.id}: {s.name} "
                    f"({s.file_count}文件, {kb:.1f}KB, {s.created_at[:19]})"
                )

        return "\n".join(lines)

    def integrate_with_quality_gate(self, operation: str, target: str) -> Optional[str]:
        """与质量门禁集成：关键操作前自动快照并返回快照ID

        Args:
            operation: 操作类型
            target: 操作目标

        Returns:
            快照ID（用于回滚），None 表示快照失败
        """
        entry = self.pre_flight_snapshot(operation, target)
        return entry.id if entry else None


# ============================================================
# 单例
# ============================================================

_snapshot_manager: Optional[SnapshotManager] = None


def get_snapshot_manager() -> SnapshotManager:
    """获取全局 SnapshotManager 单例"""
    global _snapshot_manager
    if _snapshot_manager is None:
        _snapshot_manager = SnapshotManager()
    return _snapshot_manager
