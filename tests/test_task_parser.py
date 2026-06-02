from dialogue_eval.parser import load_task
from dialogue_eval.schemas import TaskSpec


def test_load_demo_task_json() -> None:
    task = load_task("examples/tasks/fengmaotui_delivery_task.json")
    assert isinstance(task, TaskSpec)
    assert task.task_id == "fengmaotui_delivery_task"
    assert task.flow_steps
    assert "飞毛腿" in task.task


def test_load_course_task_json() -> None:
    task = load_task("examples/tasks/course_live_task.json")
    assert task.task_id == "course_live_task"
    assert "低延迟直播" in task.task
    assert task.constraints.max_reply_chars == 50
