"""飞书执行追踪 — 循环文件存储

设计：
    logs/feishu_executions/
    ├── _index.txt          ← 下一个写入的文件编号 (1-20)
    ├── exec_01.json        ← 最早
    ├── exec_02.json
    ├── ...
    └── exec_20.json        ← 最新（循环覆盖 exec_01）

每条记录包含完整执行追踪：消息、Agent 事件流、时间戳。
"""

import json
import os
import time
from datetime import datetime

# 配置
_MAX_FILES = 20
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "feishu_executions")
_INDEX_FILE = os.path.join(_LOG_DIR, "_index.txt")


def _ensure_dir():
    os.makedirs(_LOG_DIR, exist_ok=True)


def _get_next_index() -> int:
    """读取当前写入编号，返回 1-20"""
    _ensure_dir()
    try:
        with open(_INDEX_FILE) as f:
            idx = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        idx = 1
    return idx


def _set_next_index(idx: int):
    """写入下一个编号"""
    _ensure_dir()
    next_idx = (idx % _MAX_FILES) + 1
    with open(_INDEX_FILE, "w") as f:
        f.write(str(next_idx))


def save_execution(trace: dict):
    """保存执行追踪到下一个循环文件

    Args:
        trace: {
            "message_id": str,
            "sender_id": str,
            "chat_id": str,
            "text": str,           # 用户消息（截断到500字）
            "reply": str,          # 最终回复（截断到2000字）
            "tool_count": int,
            "events": [dict, ...], # AgentEvent.to_dict() 列表
        }
    """
    idx = _get_next_index()
    filepath = os.path.join(_LOG_DIR, f"exec_{idx:02d}.json")

    record = {
        "id": idx,
        "timestamp": datetime.now().isoformat(),
        "unix_time": time.time(),
        **trace,
    }

    try:
        _ensure_dir()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        _set_next_index(idx)
    except Exception as e:
        print(f"[ExecLog] 写入失败: {e}")


def list_executions(limit: int = 10) -> list[dict]:
    """列出最近的执行记录（按时间倒序）"""
    _ensure_dir()
    records = []
    for i in range(1, _MAX_FILES + 1):
        filepath = os.path.join(_LOG_DIR, f"exec_{i:02d}.json")
        if os.path.exists(filepath):
            try:
                with open(filepath, encoding="utf-8") as f:
                    record = json.load(f)
                    records.append(record)
            except Exception:
                pass

    # 按时间倒序
    records.sort(key=lambda r: r.get("unix_time", 0), reverse=True)
    return records[:limit]


def get_execution(file_id: int) -> dict | None:
    """读取指定编号的执行记录"""
    filepath = os.path.join(_LOG_DIR, f"exec_{file_id:02d}.json")
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_stats() -> dict:
    """存储统计"""
    _ensure_dir()
    files = [f for f in os.listdir(_LOG_DIR) if f.startswith("exec_") and f.endswith(".json")]
    total_size = sum(
        os.path.getsize(os.path.join(_LOG_DIR, f)) for f in files
    )
    return {
        "file_count": len(files),
        "max_files": _MAX_FILES,
        "total_size_kb": round(total_size / 1024, 1),
        "dir": _LOG_DIR,
    }
