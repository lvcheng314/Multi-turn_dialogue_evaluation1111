import json

import pytest

from dialogue_eval.parser import load_task
from dialogue_eval.schemas import TaskSpec
from dialogue_eval.task_sources import inspect_uploaded_task, list_task_sources, load_uploaded_task_content, resolve_task_path


def test_load_demo_task_json() -> None:
    task = load_task("tasks/fengmaotui_delivery_task.json")
    assert isinstance(task, TaskSpec)
    assert task.task_id == "fengmaotui_delivery_task"
    assert task.flow_steps
    assert "飞毛腿" in task.task


def test_load_course_task_json() -> None:
    task = load_task("tasks/course_live_task.json")
    assert task.task_id == "course_live_task"
    assert "低延迟直播" in task.task
    assert task.constraints.max_reply_chars == 50


def test_resolve_task_source_paths_exist() -> None:
    assert resolve_task_path("fengmaotui_delivery_task").exists()
    assert resolve_task_path("course_live_task").exists()


def test_task_library_lists_seed_tasks() -> None:
    task_ids = {item["id"] for item in list_task_sources()}
    assert "fengmaotui_delivery_task" in task_ids
    assert "course_live_task" in task_ids


def test_inspect_uploaded_task_detects_duplicate_by_content() -> None:
    content = resolve_task_path("fengmaotui_delivery_task").read_bytes()

    result = inspect_uploaded_task("copied_task.json", content)

    assert result["status"] == "duplicate"
    assert result["duplicate_of"] is not None
    assert result["duplicate_of"]["id"] == "fengmaotui_delivery_task"


def test_inspect_uploaded_task_detects_duplicate_by_semantic_json() -> None:
    task = load_task("tasks/fengmaotui_delivery_task.json")
    content = json.dumps(task.model_dump(mode="json"), ensure_ascii=False, indent=4).encode("utf-8")

    result = inspect_uploaded_task("reformatted_task.json", content)

    assert result["status"] == "duplicate"
    assert result["duplicate_of"] is not None
    assert result["duplicate_of"]["id"] == "fengmaotui_delivery_task"


def test_load_uploaded_task_content_rejects_invalid_json() -> None:
    with pytest.raises(Exception):
        load_uploaded_task_content("broken_task.json", b'{"task_id": ')
