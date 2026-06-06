from __future__ import annotations

import re
from dataclasses import dataclass

from dialogue_eval.schemas import DialogueTrace, Evidence, ScenarioSpec, TaskSpec
from dialogue_eval.scorer.speaker import speaker_messages

_OUTCOME_MAX_SCORE = 30.0
_COMPLETION_MAX_SCORE = 12.0
_COVERAGE_MAX_SCORE = 18.0


@dataclass
class FinalStateResolution:
    status: str | None
    source: str
    confidence: float


class OutcomeScorer:
    def score(
        self,
        task: TaskSpec,
        scenario: ScenarioSpec,
        trace: DialogueTrace,
    ) -> tuple[float, list[Evidence]]:
        expected = scenario.expected_final_state.get("task_status")
        resolution = _resolve_final_state(trace, scenario)
        actual = resolution.status

        required_steps = _required_steps_for_scenario(task, scenario)
        agent_messages = [message.content for message in speaker_messages(trace, "agent")]
        covered_steps = [step for step in required_steps if _step_is_covered(step.step_id, step.description, scenario, trace)]
        coverage_ratio = len(covered_steps) / len(required_steps) if required_steps else 1.0

        completion_score = (
            _COMPLETION_MAX_SCORE
            if expected and actual == expected
            else 6.0
            if trace.transcript
            else 0.0
        )
        coverage_score = min(_COVERAGE_MAX_SCORE, _COVERAGE_MAX_SCORE * coverage_ratio)
        score = completion_score + coverage_score

        missing_steps = [step.description for step in required_steps if step not in covered_steps]
        coverage_comment = (
            f"最终状态: {actual}; 预期状态: {expected}; 状态来源: {resolution.source}; "
            f"必需流程覆盖 {len(covered_steps)}/{len(required_steps)}。"
        )
        if missing_steps:
            coverage_comment += f" 未覆盖步骤: {'、'.join(missing_steps)}。"

        evidence = [
            Evidence(
                type="state",
                turn=None,
                comment=coverage_comment,
                rule_id="outcome.final_state_and_flow_coverage",
                score_delta=0.0 if expected and actual == expected else -6.0,
            )
        ]

        if len(agent_messages) <= 2:
            score -= 5.0
            evidence.append(
                Evidence(
                    type="turn",
                    comment="数字人回复轮次偏少，任务说明可能不充分。",
                    rule_id="outcome.agent_turn_depth",
                    score_delta=-5.0,
                )
            )

        return max(0.0, min(_OUTCOME_MAX_SCORE, round(score, 2))), evidence


def _resolve_final_state(trace: DialogueTrace, scenario: ScenarioSpec) -> FinalStateResolution:
    expected = scenario.expected_final_state.get("task_status")

    if expected:
        for tool_call in reversed(trace.tool_calls):
            mapped = _map_tool_to_status(tool_call.tool_name, tool_call.result, expected)
            if mapped and mapped.status == expected:
                return mapped

    for tool_call in reversed(trace.tool_calls):
        if tool_call.tool_name == "update_task_status":
            status = tool_call.arguments.get("status")
            if status:
                return FinalStateResolution(str(status), "tool:update_task_status.arguments.status", 1.0)

            result_status = _coerce_status(tool_call.result)
            if result_status and result_status not in {"updated", "success", "recorded", "created"}:
                return FinalStateResolution(result_status, "tool:update_task_status.result.status", 0.9)

        mapped = _map_tool_to_status(tool_call.tool_name, tool_call.result, expected)
        if mapped:
            return mapped

    if trace.state_trace:
        final_status = trace.state_trace[-1].get("task_status")
        if final_status and str(final_status) != "in_progress":
            return FinalStateResolution(str(final_status), "state_trace.final.task_status", 0.8)

    inferred = _infer_status_from_transcript(trace, scenario)
    if inferred:
        return inferred

    if trace.state_trace:
        final_status = trace.state_trace[-1].get("task_status")
        if final_status:
            return FinalStateResolution(str(final_status), "state_trace.fallback", 0.4)

    return FinalStateResolution(None, "unresolved", 0.0)


def _map_tool_to_status(tool_name: str, result: dict, expected: str | None) -> FinalStateResolution | None:
    result_status = _coerce_status(result)

    if tool_name == "schedule_callback":
        if result_status in {None, "", "scheduled", "success"} or expected == "callback_scheduled":
            return FinalStateResolution("callback_scheduled", "tool:schedule_callback", 0.95)

    if tool_name == "transfer_to_human":
        if result_status in {None, "", "queued", "success"} or expected == "transferred":
            return FinalStateResolution("transferred", "tool:transfer_to_human", 0.95)

    if tool_name == "query_faq":
        if result.get("matched") or result_status in {"answered", "success"} or "answer" in result or expected == "faq_answered":
            return FinalStateResolution("faq_answered", "tool:query_faq", 0.9)

    return None


def _coerce_status(result: dict) -> str | None:
    raw = result.get("task_status") or result.get("status")
    return str(raw) if raw else None


def _infer_status_from_transcript(trace: DialogueTrace, scenario: ScenarioSpec) -> FinalStateResolution | None:
    normalized_agent = _normalize_text("\n".join(message.content for message in speaker_messages(trace, "agent")))
    normalized_user = _normalize_text("\n".join(message.content for message in speaker_messages(trace, "user")))
    expected = scenario.expected_final_state.get("task_status")

    if expected == "callback_scheduled":
        if any(token in normalized_agent for token in {"回访", "回呼", "稍后联系", "晚点联系", "已登记", "已安排"}):
            return FinalStateResolution("callback_scheduled", "transcript:callback_semantics", 0.75)
    if expected == "transferred":
        if any(token in normalized_agent for token in {"转人工", "转接", "人工客服"}):
            return FinalStateResolution("transferred", "transcript:transfer_semantics", 0.75)
    if expected == "accepted":
        if any(token in normalized_user for token in {"可以", "知道了", "明白了", "我去处理", "我会去做"}):
            return FinalStateResolution("accepted", "transcript:acceptance_semantics", 0.7)
    if expected == "rejected":
        if any(token in normalized_user for token in {"不做", "拒绝", "不用了", "不接受"}):
            return FinalStateResolution("rejected", "transcript:rejection_semantics", 0.7)
    if expected == "faq_answered":
        if any(token in normalized_agent for token in {"帮助中心", "规则", "查看", "可以在"}):
            return FinalStateResolution("faq_answered", "transcript:faq_semantics", 0.65)
    return None


def _step_is_covered(step_id: str, description: str, scenario: ScenarioSpec, trace: DialogueTrace) -> bool:
    agent_text = _normalize_text("\n".join(message.content for message in speaker_messages(trace, "agent")))
    user_text = _normalize_text("\n".join(message.content for message in speaker_messages(trace, "user")))
    tool_names = {tool_call.tool_name for tool_call in trace.tool_calls}
    final_status = _resolve_final_state(trace, scenario).status

    step_key = _classify_step(step_id, description)
    if step_key == "confirm_availability":
        return any(token in agent_text for token in {"方便接听", "方便沟通", "现在方便", "打扰"})
    if step_key == "identity_confirm":
        return any(token in agent_text for token in {"本人", "身份", "核实", "确认"})
    if step_key == "announce_update":
        return any(token in agent_text for token in {"发票", "新版", "上线", "入口"})
    if step_key == "explain_benefit":
        return any(token in agent_text for token in {"更方便", "更容易", "历史记录", "查找", "查看"})
    if step_key == "offer_help":
        return any(token in agent_text for token in {"帮助中心", "回访", "回呼", "问题", "支持"})
    if step_key == "callback":
        return "schedule_callback" in tool_names or final_status == "callback_scheduled" or any(
            token in agent_text or token in user_text for token in {"回访", "回呼", "稍后联系", "晚点联系"}
        )
    if step_key == "transfer":
        return "transfer_to_human" in tool_names or final_status == "transferred" or any(
            token in agent_text or token in user_text for token in {"转人工", "人工客服", "转接"}
        )
    if step_key == "faq":
        return "query_faq" in tool_names or final_status == "faq_answered" or "帮助中心" in agent_text
    if step_key == "accept":
        return final_status == "accepted" or any(token in user_text for token in {"可以", "知道了", "明白了", "我去处理"})
    if step_key == "reject":
        return final_status == "rejected" or any(token in user_text for token in {"不做", "不用了", "拒绝"})
    if step_key == "privacy":
        return any(token in agent_text for token in {"无法提供", "不能提供", "隐私", "官方渠道"})
    if step_key == "polite_close":
        return any(token in agent_text for token in {"感谢", "再见", "不打扰", "先这样", "祝您"})

    fragments = _extract_text_fragments(description)
    return any(fragment in agent_text for fragment in fragments)


def _required_steps_for_scenario(task: TaskSpec, scenario: ScenarioSpec) -> list:
    expected = scenario.expected_final_state.get("task_status")
    required = [step for step in task.flow_steps if step.required]

    if expected == "transferred":
        keep = {"confirm_availability", "transfer"}
        return [step for step in required if _classify_step(step.step_id, step.description) in keep]

    if expected == "callback_scheduled":
        keep = {"confirm_availability", "announce_update", "offer_help", "polite_close", "callback"}
        return [step for step in required if _classify_step(step.step_id, step.description) in keep]

    return required


def _classify_step(step_id: str, description: str) -> str:
    normalized = _normalize_text(f"{step_id} {description}")

    if "confirmavailability" in normalized or any(token in normalized for token in {"方便接听", "方便沟通", "是否方便"}):
        return "confirm_availability"
    if any(token in normalized for token in {"身份", "本人", "核实"}):
        return "identity_confirm"
    if "announceupdate" in normalized or any(token in normalized for token in {"上线", "通知", "入口"}):
        return "announce_update"
    if "explainbenefit" in normalized or any(token in normalized for token in {"历史记录", "更方便", "更容易", "查找"}):
        return "explain_benefit"
    if "offerhelp" in normalized or any(token in normalized for token in {"帮助中心", "回访", "回呼", "支持"}):
        return "offer_help"
    if any(token in normalized for token in {"回访", "回呼", "预约"}):
        return "callback"
    if any(token in normalized for token in {"人工", "转接", "投诉"}):
        return "transfer"
    if any(token in normalized for token in {"faq", "规则", "解答", "解释"}):
        return "faq"
    if any(token in normalized for token in {"接受", "意向", "开始执行"}):
        return "accept"
    if any(token in normalized for token in {"拒绝", "取消"}):
        return "reject"
    if any(token in normalized for token in {"隐私", "泄露", "官方渠道"}):
        return "privacy"
    if any(token in normalized for token in {"结束通话", "礼貌结束", "收尾", "再见"}):
        return "polite_close"
    return "generic"


def _extract_text_fragments(text: str) -> list[str]:
    normalized = _normalize_text(text)
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
    return list(dict.fromkeys(tokens[:6]))


def _normalize_text(text: str) -> str:
    text = text or ""
    return re.sub(r"[\s,，。；：、！？\-\(\)\[\]\{\}\"'`]+", "", text).lower()
