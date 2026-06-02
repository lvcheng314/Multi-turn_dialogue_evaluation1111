from __future__ import annotations

from pathlib import Path


TASK_SOURCES: dict[str, dict[str, str]] = {
    "fengmaotui_delivery_task": {
        "name": "示例1：飞毛腿骑手外呼",
        "path": "examples/tasks/fengmaotui_delivery_task.json",
    },
    "course_live_task": {
        "name": "示例2：课程直播选项通知",
        "path": "examples/tasks/course_live_task.json",
    },
}


def resolve_task_path(task_source_id: str) -> Path:
    try:
        return Path(TASK_SOURCES[task_source_id]["path"])
    except KeyError as exc:
        raise KeyError(f"Unknown task source: {task_source_id}") from exc
