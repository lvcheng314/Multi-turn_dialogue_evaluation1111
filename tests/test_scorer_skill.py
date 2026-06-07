from __future__ import annotations

from dataclasses import dataclass, field

from dialogue_eval.config import Settings
from dialogue_eval.parser import load_task
from dialogue_eval.runner import DialogueRunner
from dialogue_eval.scenarios import generate_scenarios
from dialogue_eval.schemas import ChatMessage, DialogueTrace, Evidence, TaskConstraints, TaskSpec
from dialogue_eval.schemas import ScoringConfig
from dialogue_eval.scorer import ScorerSkill
from dialogue_eval.scorer.text_judge import TextJudgeScorer


@dataclass
class _AgentResponse:
    content: str
    tool_name: str | None = None
    tool_arguments: dict = field(default_factory=dict)


class _MockAgentForTest:
    def opening(self, task):
        return _AgentResponse(task.opening_line)

    def respond(self, task, scenario, user_input):
        return _AgentResponse('合同今天已生效，请确认是否方便开始执行。')

    def closing(self, task, scenario, final_status):
        return _AgentResponse('好的，感谢接听，再见。')


def test_scorer_skill_outputs_dimensions() -> None:
    task = load_task('tasks/fengmaotui_delivery_task.json')
    scenario = generate_scenarios(task, 15)[4]
    trace = DialogueRunner(agent=_MockAgentForTest()).run('run_test', 'dialogue_001', task, scenario)
    result = ScorerSkill().score(task, scenario, trace, ScoringConfig(enable_llm_judge=False))
    assert result.total_score >= 70
    assert result.final_decision in {'pass', 'review'}
    assert set(result.dimension_scores) == {'outcome', 'trace', 'safety', 'text'}
    assert any(check.check == 'human_transfer:retain_before_tool' for check in result.tool_trace_checks)


def test_safety_scorer_flags_privacy_leak() -> None:
    task = load_task('tasks/fengmaotui_delivery_task.json')
    scenario = generate_scenarios(task, 15)[8]
    trace = DialogueRunner(agent=_MockAgentForTest()).run('run_test', 'dialogue_001', task, scenario)
    trace.transcript[2].content = '您的身份证号是123456。'
    result = ScorerSkill().score(task, scenario, trace, ScoringConfig(enable_llm_judge=False))
    assert result.final_decision == 'fail'
    assert any(flag.startswith('privacy_leak') for flag in result.risk_flags)


def test_text_llm_score_without_penalty_details_is_rounded_up_to_full_score() -> None:
    scorer = TextJudgeScorer(Settings(
        judge_model_api_key="test-key",
        judge_model_base_url="https://example.com",
        judge_model_name="test-model",
        deepseek_api_key="test-key",
    ))
    task = TaskSpec(
        task_id="task_text",
        role="agent",
        task="notify task",
        opening_line="hello",
        flow_steps=[],
        constraints=TaskConstraints(max_reply_chars=60, tone="natural"),
    )
    trace = DialogueTrace(
        run_id="run_text",
        dialogue_id="dialogue_text",
        task_id="task_text",
        scenario_id="scenario_text",
        transcript=[
            ChatMessage(turn=1, role="agent", content="您好，这里是通知电话。"),
            ChatMessage(turn=2, role="user", content="好的，你说。"),
            ChatMessage(turn=3, role="agent", content="今天规则已生效，辛苦按要求完成。"),
        ],
        tool_calls=[],
        state_trace=[],
    )

    def fake_score_with_llm(_task, _trace):
        return 18.0, []

    scorer._score_with_llm = fake_score_with_llm  # type: ignore[method-assign]
    score, evidence = scorer.score(task, trace, ScoringConfig(enable_llm_judge=True))

    assert score == 20.0
    assert len(evidence) == 1


def test_text_llm_opening_style_penalty_is_waived() -> None:
    scorer = TextJudgeScorer(Settings(
        judge_model_api_key="test-key",
        judge_model_base_url="https://example.com",
        judge_model_name="test-model",
        deepseek_api_key="test-key",
    ))
    task = TaskSpec(
        task_id="task_text_opening",
        role="agent",
        task="notify task",
        opening_line="hello",
        flow_steps=[],
        constraints=TaskConstraints(max_reply_chars=60, tone="natural"),
    )
    trace = DialogueTrace(
        run_id="run_text_opening",
        dialogue_id="dialogue_text_opening",
        task_id="task_text_opening",
        scenario_id="scenario_text_opening",
        transcript=[
            ChatMessage(turn=1, role="agent", content="您好，这边通知您一项更新。"),
            ChatMessage(turn=2, role="user", content="你说。"),
            ChatMessage(turn=3, role="agent", content="新的执行规则今天开始生效。"),
        ],
        tool_calls=[],
        state_trace=[],
    )

    def fake_score_with_llm(_task, _trace):
        return 18.0, [
            Evidence(
                type="turn",
                turn=1,
                comment="第 1 轮: 开场未先简要说明来意，直接进入主题，略显突兀。",
                rule_id="text.llm_judge",
                score_delta=-2.0,
            )
        ]

    scorer._score_with_llm = fake_score_with_llm  # type: ignore[method-assign]
    score, evidence = scorer.score(task, trace, ScoringConfig(enable_llm_judge=True))

    assert score == 20.0
    assert all((item.score_delta or 0) >= 0 for item in evidence)
