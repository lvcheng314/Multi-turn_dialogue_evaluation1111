from __future__ import annotations

import re
from dataclasses import dataclass

from dialogue_eval.schemas import DialogueTrace, Evidence, FlowStep, ScenarioSpec, TaskSpec
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
        expected = _normalize_status_alias(scenario.expected_final_state.get("task_status"))
        resolution = _resolve_final_state(trace, scenario)
        actual = _normalize_status_alias(resolution.status)

        required_steps = _required_steps_for_scenario(task, scenario, trace, expected)
        agent_messages = [message.content for message in speaker_messages(trace, "agent")]
        covered_steps = [step for step in required_steps if _step_is_covered(step, scenario, trace, actual)]
        coverage_ratio = len(covered_steps) / len(required_steps) if required_steps else 1.0

        completion_score = _COMPLETION_MAX_SCORE if expected and actual == expected else 6.0 if trace.transcript else 0.0
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

        short_circuit_statuses = {"transferred", "callback_scheduled", "identity_mismatch", "rejected"}
        if len(agent_messages) <= 2 and actual not in short_circuit_statuses and required_steps:
            score -= 5.0
            evidence.append(
                Evidence(
                    type="turn",
                    comment="数字人回复轮次偏少，任务说明可能不够充分。",
                    rule_id="outcome.agent_turn_depth",
                    score_delta=-5.0,
                )
            )

        return max(0.0, min(_OUTCOME_MAX_SCORE, round(score, 2))), evidence


def _resolve_final_state(trace: DialogueTrace, scenario: ScenarioSpec) -> FinalStateResolution:
    expected = _normalize_status_alias(scenario.expected_final_state.get("task_status"))

    if expected:
        for tool_call in reversed(trace.tool_calls):
            mapped = _map_tool_to_status(tool_call.tool_name, tool_call.result, expected)
            if mapped and mapped.status == expected:
                return mapped

    for tool_call in reversed(trace.tool_calls):
        if tool_call.tool_name == "update_task_status":
            status = tool_call.arguments.get("status")
            if status:
                return FinalStateResolution(_normalize_status_alias(str(status)), "tool:update_task_status.arguments.status", 1.0)

            result_status = _coerce_status(tool_call.result)
            if result_status and result_status not in {"updated", "success", "recorded", "created"}:
                return FinalStateResolution(
                    _normalize_status_alias(result_status),
                    "tool:update_task_status.result.status",
                    0.9,
                )

        mapped = _map_tool_to_status(tool_call.tool_name, tool_call.result, expected)
        if mapped:
            return mapped

    if trace.state_trace:
        final_status = trace.state_trace[-1].get("task_status")
        if final_status and str(final_status) != "in_progress":
            return FinalStateResolution(_normalize_status_alias(str(final_status)), "state_trace.final.task_status", 0.8)

    inferred = _infer_status_from_transcript(trace, scenario)
    if inferred:
        return inferred

    if trace.state_trace:
        final_status = trace.state_trace[-1].get("task_status")
        if final_status:
            return FinalStateResolution(_normalize_status_alias(str(final_status)), "state_trace.fallback", 0.4)

    return FinalStateResolution(None, "unresolved", 0.0)


def _map_tool_to_status(tool_name: str, result: dict, expected: str | None) -> FinalStateResolution | None:
    result_status = _normalize_status_alias(_coerce_status(result))

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


def _normalize_status_alias(status: str | None) -> str | None:
    if not status:
        return status
    alias_map = {
        "delivered": "notified",
        "cannot_guarantee_income": "promise_avoided",
        "ok": "ticket_created",
        "understood": "completed",
    }
    return alias_map.get(status, status)


def _infer_status_from_transcript(trace: DialogueTrace, scenario: ScenarioSpec) -> FinalStateResolution | None:
    normalized_agent = _normalize_text("\n".join(message.content for message in speaker_messages(trace, "agent")))
    normalized_user = _normalize_text("\n".join(message.content for message in speaker_messages(trace, "user")))
    expected = _normalize_status_alias(scenario.expected_final_state.get("task_status"))

    if expected == "callback_scheduled":
        if any(token in normalized_agent for token in {"回访", "回呼", "稍后联系", "晚点联系", "已登记", "已安排"}):
            return FinalStateResolution("callback_scheduled", "transcript:callback_semantics", 0.75)
    if expected == "transferred":
        if any(token in normalized_agent for token in {"转人工", "转接", "人工客服"}):
            return FinalStateResolution("transferred", "transcript:transfer_semantics", 0.75)
    if expected == "accepted":
        if any(token in normalized_user for token in {"可以", "知道了", "明白了", "我去处理", "我会去做", "能正常配送", "正常跑"}):
            return FinalStateResolution("accepted", "transcript:acceptance_semantics", 0.7)
    if expected == "rejected":
        if any(token in normalized_user for token in {"不做", "拒绝", "不用了", "不接了", "没法配送", "无法配送"}):
            return FinalStateResolution("rejected", "transcript:rejection_semantics", 0.7)
    if expected == "faq_answered":
        if "query_faq" in {call.tool_name for call in trace.tool_calls} or any(token in normalized_agent for token in {"规则", "查看", "可以在"}):
            return FinalStateResolution("faq_answered", "transcript:faq_semantics", 0.65)
    return None


def _step_is_covered(step: FlowStep, scenario: ScenarioSpec, trace: DialogueTrace, final_status: str | None) -> bool:
    agent_text = _normalize_text("\n".join(message.content for message in speaker_messages(trace, "agent")))
    user_text = _normalize_text("\n".join(message.content for message in speaker_messages(trace, "user")))
    tool_names = {tool_call.tool_name for tool_call in trace.tool_calls}

    step_key = _classify_step(step.step_id, step.description)

    if step_key == "notify_contract":
        mentions_contract = any(token in agent_text for token in {"合同已生效", "今天合同已生效", "飞毛腿", "午晚高峰", "上线配送"})
        asks_availability = any(token in agent_text for token in {"可以正常配送", "可以开始配送", "能正常配送", "能上线配送", "是否可以配送"})
        if mentions_contract and asks_availability:
            return True
        return mentions_contract and _notification_only_satisfies_contract_step(user_text, final_status)
    if step_key == "notify_contract_partial":
        return any(token in agent_text for token in {"合同已生效", "今天合同已生效", "午晚高峰", "上线配送", "飞毛腿"})
    if step_key == "explain_delivery_requirement":
        return any(
            token in agent_text
            for token in {"需要上线配送", "按要求完成配送", "完成配送任务", "不完成", "合同和派单可能受影响", "派单可能受影响"}
        )
    if step_key == "handle_delivery_objection":
        return any(token in agent_text for token in {"注意安全", "尽量", "还是建议", "理解你的情况", "感谢配合", "辛苦"})
    if step_key == "explain_quota_rule":
        has_rank = any(token in agent_text for token in {"名额按排名分配", "报名名额", "按排名分配"})
        has_operation_rule = any(token in agent_text for token in {"减少拒单", "减少取消", "超时", "拒单越少", "完成率越高"})
        return has_rank and has_operation_rule
    if step_key == "ticket_create_or_record":
        return "update_task_status" in tool_names or any(token in agent_text for token in {"记录一下", "创建工单", "帮您记录", "后续跟进", "登记"})
    if step_key == "avoid_promise":
        return final_status == "promise_avoided" or any(
            token in agent_text for token in {"不便承诺", "不能保证", "以平台页面展示为准", "无法保证收益"}
        )
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
        return "query_faq" in tool_names or final_status == "faq_answered"
    if step_key == "accept":
        return final_status == "accepted" or any(token in user_text for token in {"可以", "知道了", "明白了", "我去处理", "正常跑"})
    if step_key == "reject":
        return final_status == "rejected" or any(token in user_text for token in {"不做", "不用了", "拒绝", "没法配送", "无法配送"})
    if step_key == "privacy":
        return any(token in agent_text for token in {"无法提供", "不能提供", "隐私", "官方渠道"})
    if step_key == "polite_close":
        return any(token in agent_text for token in {"感谢", "再见", "不打扰", "先这样", "祝您", "那先这样"})
    if step_key == "polite_close_reject_only":
        return final_status == "rejected" and any(
            token in agent_text for token in {"理解你的情况", "记录一下", "先这样", "不打扰你了"}
        )

    fragments = _extract_text_fragments(step.description)
    return any(fragment in agent_text for fragment in fragments)


def _required_steps_for_scenario(task: TaskSpec, scenario: ScenarioSpec, trace: DialogueTrace, expected: str | None) -> list[FlowStep]:
    required = [step for step in task.flow_steps if step.required]
    scenario_id = (scenario.scenario_id or "").lower()
    callback_busy_case = _is_busy_callback_case(scenario, expected)
    callback_busy_trace_case = _is_busy_callback_trace(trace, expected)

    if scenario_id.startswith("fm_ask_quota_rule"):
        return _filter_steps(required, {"notify_contract_partial", "explain_quota_rule"})
    if scenario_id.startswith("fm_faq_contract_diff"):
        return _filter_steps(required, {"notify_contract_partial", "explain_delivery_requirement"})
    if scenario_id.startswith("fm_one_sentence_summary"):
        return _filter_steps(required, {"notify_contract_partial"})
    if scenario_id.startswith("fm_complaint_quota"):
        return _filter_steps(required, {"ticket_create_or_record"})
    if scenario_id.startswith("fm_promise_income"):
        return _filter_steps(required, {"avoid_promise"})
    if scenario_id.startswith("fm_wrong_person"):
        return []
    if (
        scenario_id.startswith("fm_busy_delivering")
        or scenario_id.startswith("fm_driving_to_station")
        or callback_busy_case
        or callback_busy_trace_case
    ):
        return _filter_steps(required, {"notify_contract_partial", "callback", "polite_close"})
    if scenario_id.startswith("fm_human_transfer"):
        return []

    if expected == "accepted":
        return [step for step in required if _classify_step(step.step_id, step.description) != "polite_close_reject_only"]

    if expected == "rejected":
        return _filter_steps(required, {"notify_contract", "explain_delivery_requirement", "handle_delivery_objection", "polite_close_reject_only"})

    if expected == "transferred":
        return []

    if expected == "callback_scheduled":
        return _filter_steps(required, {"announce_update", "offer_help", "polite_close", "callback"})

    return required


def _is_busy_callback_case(scenario: ScenarioSpec, expected: str | None) -> bool:
    if expected != "callback_scheduled":
        return False

    combined = _normalize_text(
        " ".join(
            [
                scenario.category,
                scenario.subtype,
                scenario.persona,
                scenario.customer_personality,
                scenario.agent_personality,
                scenario.situation,
                scenario.initial_user_input,
                " ".join(scenario.utterance_variants),
                " ".join(scenario.exclusive_signals),
                " ".join(scenario.goals),
                " ".join(scenario.expected_behaviors),
            ]
        )
    )
    busy_tokens = {
        "不方便接",
        "不方便聊",
        "路上",
        "去站点",
        "在开车",
        "在骑车",
        "配送中",
        "送单",
        "跑单",
        "先忙",
        "注意安全",
        "到了再说",
    }
    return any(token in combined for token in busy_tokens)


def _is_busy_callback_trace(trace: DialogueTrace, expected: str | None) -> bool:
    if expected != "callback_scheduled":
        return False
    user_text = _normalize_text("\n".join(message.content for message in speaker_messages(trace, "user")))
    busy_tokens = {
        "不方便接",
        "不方便聊",
        "路上",
        "去站点",
        "在开车",
        "在骑车",
        "配送中",
        "送单",
        "跑单",
        "先忙",
        "到了再说",
        "没空细说",
    }
    return any(token in user_text for token in busy_tokens)


def _filter_steps(required: list[FlowStep], keep: set[str]) -> list[FlowStep]:
    filtered = [step for step in required if _classify_step(step.step_id, step.description) in keep]
    return filtered or required


def _notification_only_satisfies_contract_step(user_text: str, final_status: str | None) -> bool:
    if final_status == "callback_scheduled":
        return True
    acknowledgement_tokens = {
        "知道了",
        "明白了",
        "好的",
        "可以",
        "行",
        "没问题",
    }
    busy_tokens = {
        "不方便",
        "没空",
        "先忙",
        "跑单",
        "配送中",
        "到了再说",
    }
    return any(token in user_text for token in acknowledgement_tokens) or any(token in user_text for token in busy_tokens)


def _classify_step(step_id: str, description: str) -> str:
    normalized = _normalize_text(f"{step_id} {description}")

    if any(token in normalized for token in {"投诉", "工单", "记录情况", "跟进处理"}):
        return "ticket_create_or_record"
    if any(token in normalized for token in {"收益", "保证", "承诺", "不能承诺"}):
        return "avoid_promise"
    if "notifycontract" in normalized or any(token in normalized for token in {"合同已生效", "开始配送", "上线配送", "午晚高峰"}):
        if any(token in normalized for token in {"询问", "是否可以", "开始配送"}):
            return "notify_contract"
        return "notify_contract_partial"
    if "explaindeliveryrequirement" in normalized or any(token in normalized for token in {"按要求完成配送", "配送任务", "派单可能受影响"}):
        return "explain_delivery_requirement"
    if "handledeliveryobjection" in normalized or any(token in normalized for token in {"不想配送", "愿意配送", "注意安全"}):
        return "handle_delivery_objection"
    if "explainquotarule" in normalized or any(token in normalized for token in {"名额按排名分配", "减少拒单", "减少取消", "超时"}):
        return "explain_quota_rule"
    if "politeclose" in normalized and any(token in normalized for token in {"无法配送", "记录情况", "礼貌结束"}):
        return "polite_close_reject_only"
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
    return re.sub(r"[\s,，。；：、】【！!？?\\/\-\(\)\[\]\{\}\"'`]+", "", text).lower()
