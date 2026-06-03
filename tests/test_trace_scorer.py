from dialogue_eval.parser import load_task
from dialogue_eval.runner import DialogueRunner
from dialogue_eval.scenarios import generate_scenarios
from dialogue_eval.scorer.trace import TraceScorer


def test_trace_scorer_passes_human_transfer() -> None:
    task = load_task("tasks/fengmaotui_delivery_task.json")
    scenario = generate_scenarios(task, 15)[4]
    trace = DialogueRunner().run("run_test", "dialogue_001", task, scenario)
    score, checks, evidence = TraceScorer().score(scenario, trace)
    assert score == 30
    assert checks[0].passed is True
    assert any(check.check == "human_transfer:retain_before_tool" and check.passed for check in checks)
    assert evidence
