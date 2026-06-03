from dialogue_eval.parser import load_task
from dialogue_eval.runner import DialogueRunner
from dialogue_eval.scenarios import generate_scenarios
from dialogue_eval.schemas import ScoringConfig
from dialogue_eval.scorer import ScorerSkill


def test_scorer_skill_outputs_dimensions() -> None:
    task = load_task("tasks/fengmaotui_delivery_task.json")
    scenario = generate_scenarios(task, 15)[4]
    trace = DialogueRunner().run("run_test", "dialogue_001", task, scenario)
    result = ScorerSkill().score(task, scenario, trace, ScoringConfig(enable_llm_judge=False))
    assert result.total_score >= 70
    assert result.final_decision in {"pass", "review"}
    assert set(result.dimension_scores) == {"outcome", "trace", "safety", "text"}
    assert any(check.check == "human_transfer:retain_before_tool" for check in result.tool_trace_checks)


def test_safety_scorer_flags_privacy_leak() -> None:
    task = load_task("tasks/fengmaotui_delivery_task.json")
    scenario = generate_scenarios(task, 15)[8]
    trace = DialogueRunner().run("run_test", "dialogue_001", task, scenario)
    trace.transcript[2].content = "您的身份证号是 123456。"
    result = ScorerSkill().score(task, scenario, trace, ScoringConfig(enable_llm_judge=False))
    assert result.final_decision == "fail"
    assert any(flag.startswith("privacy_leak") for flag in result.risk_flags)
