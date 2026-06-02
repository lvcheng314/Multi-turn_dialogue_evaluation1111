from __future__ import annotations

from dialogue_eval.schemas import DialogueTrace, Evidence, ScenarioSpec, TaskSpec


class OutcomeScorer:
    def score(
        self,
        task: TaskSpec,
        scenario: ScenarioSpec,
        trace: DialogueTrace,
    ) -> tuple[float, list[Evidence]]:
        expected = scenario.expected_final_state.get("task_status")
        actual = trace.state_trace[-1].get("task_status") if trace.state_trace else None
        required_steps = [step for step in task.flow_steps if step.required]
        agent_text = "\n".join(message.content for message in trace.transcript if message.role == "agent")
        covered = sum(1 for step in required_steps if _step_is_covered(step.description, agent_text))
        coverage_ratio = covered / len(required_steps) if required_steps else 1.0
        coverage_score = min(18.0, 18.0 * coverage_ratio)
        completion_score = 12.0 if expected and actual == expected else 6.0 if trace.transcript else 0.0
        score = completion_score + coverage_score
        evidence = [
            Evidence(
                type="state",
                turn=None,
                comment=f"最终状态: {actual}; 预期状态: {expected}; 必需流程覆盖 {covered}/{len(required_steps)}。",
                rule_id="outcome.final_state_and_flow_coverage",
                score_delta=0 if expected and actual == expected else -6,
            )
        ]
        if len([message for message in trace.transcript if message.role == "agent"]) <= 3:
            score -= 5.0
            evidence.append(
                Evidence(
                    type="turn",
                    comment="数字人回复轮次偏少，任务说明可能不充分。",
                    rule_id="outcome.agent_turn_depth",
                    score_delta=-5,
                )
            )
        return max(0.0, round(score, 2)), evidence


def _step_is_covered(description: str, text: str) -> bool:
    keywords = [
        token.strip("，。；、： ")
        for token in description.replace("，", " ").replace("。", " ").replace("；", " ").replace("、", " ").split()
        if len(token.strip("，。；、： ")) >= 2
    ]
    if not keywords:
        return False
    return any(keyword in text for keyword in keywords[:6])
