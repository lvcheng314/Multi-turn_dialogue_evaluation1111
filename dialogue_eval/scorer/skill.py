from __future__ import annotations

from dialogue_eval.schemas import DialogueTrace, EvalResult, ScenarioSpec, ScoringConfig, TaskSpec
from dialogue_eval.scorer.aggregate import final_decision
from dialogue_eval.scorer.outcome import OutcomeScorer
from dialogue_eval.scorer.safety import SafetyScorer
from dialogue_eval.scorer.text_judge import TextJudgeScorer
from dialogue_eval.scorer.trace import TraceScorer


class ScorerSkill:
    def __init__(self) -> None:
        self.outcome = OutcomeScorer()
        self.trace = TraceScorer()
        self.safety = SafetyScorer()
        self.text = TextJudgeScorer()

    def score(
        self,
        task: TaskSpec,
        scenario: ScenarioSpec,
        trace: DialogueTrace,
        config: ScoringConfig | None = None,
    ) -> EvalResult:
        outcome_score, outcome_evidence = self.outcome.score(task, scenario, trace)
        trace_score, tool_checks, trace_evidence = self.trace.score(scenario, trace)
        safety_score, risk_flags, safety_evidence = self.safety.score(task, trace)
        text_score, text_evidence = self.text.score(task, trace, config)
        outcome_evidence = _tag_evidence(outcome_evidence, "outcome")
        trace_evidence = _tag_evidence(trace_evidence, "trace")
        safety_evidence = _tag_evidence(safety_evidence, "safety")
        text_evidence = _tag_evidence(text_evidence, "text")

        dimension_scores = {
            "outcome": round(outcome_score, 2),
            "trace": round(trace_score, 2),
            "safety": round(safety_score, 2),
            "text": round(text_score, 2),
        }
        total_score = round(sum(dimension_scores.values()), 2)
        return EvalResult(
            run_id=trace.run_id,
            dialogue_id=trace.dialogue_id,
            total_score=total_score,
            dimension_scores=dimension_scores,
            tool_trace_checks=tool_checks,
            risk_flags=risk_flags,
            evidence=outcome_evidence + trace_evidence + safety_evidence + text_evidence,
            final_decision=final_decision(total_score, risk_flags),
        )


def _tag_evidence(evidence, dimension: str):
    for item in evidence:
        item.dimension = dimension
    return evidence
