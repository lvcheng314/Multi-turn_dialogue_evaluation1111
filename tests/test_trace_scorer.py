from dialogue_eval.parser import load_task
from dialogue_eval.runner import DialogueRunner
from dialogue_eval.scenarios import generate_scenarios
from dialogue_eval.scorer.trace import TraceScorer
from dialogue_eval.schemas import ChatMessage, DialogueTrace


def test_trace_scorer_passes_human_transfer() -> None:
    task = load_task("tasks/fengmaotui_delivery_task.json")
    scenario = generate_scenarios(task, 15)[4]
    trace = DialogueRunner().run("run_test", "dialogue_001", task, scenario)
    score, checks, evidence = TraceScorer().score(scenario, trace)
    assert score == 30
    assert checks[0].passed is True
    assert any(check.check == "human_transfer:retain_before_tool" and check.passed for check in checks)
    assert evidence


def test_trace_scorer_fails_when_expected_tool_is_missing() -> None:
    task = load_task("tasks/fengmaotui_delivery_task.json")
    scenario = next(item for item in generate_scenarios(task, 15) if item.expected_tool_calls and item.expected_tool_calls[0].tool_name == "schedule_callback")
    trace = DialogueTrace(
        run_id="run_import",
        dialogue_id="dialogue_import_001",
        task_id=task.task_id,
        scenario_id=scenario.scenario_id,
        transcript=[
            ChatMessage(turn=1, role="user", content="我现在不方便，晚点联系。"),
            ChatMessage(turn=2, role="agent", content="好的，我稍后再联系您。"),
        ],
        tool_calls=[],
        state_trace=[{"turn": 1, "task_status": "opened"}, {"turn": 2, "task_status": "callback_scheduled"}],
    )
    score, checks, evidence = TraceScorer().score(scenario, trace)
    assert score == 0
    assert checks[0].passed is False
    assert "要求调用" in checks[0].reason
    assert evidence
