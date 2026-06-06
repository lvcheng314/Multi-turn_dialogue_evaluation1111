from __future__ import annotations

from dialogue_eval.schemas import DialogueTrace, Evidence, ScenarioSpec, ToolTraceCheck
from dialogue_eval.scorer.speaker import speaker_messages


TRACE_MAX_SCORE = 30.0



TRACE_MAX_SCORE = 30.0

class TraceScorer:
    """对工具调用正确性进行评分（命中率模式）。"""

    def score(
        self,
        scenario: ScenarioSpec,
        trace: DialogueTrace,
    ) -> tuple[float, list[ToolTraceCheck], list[Evidence]]:
        """按工具命中率评分：trace = 30 * (匹配工具数 / 期望工具数)。"""
        expected_tools = [call.tool_name for call in scenario.expected_tool_calls]
        actual_tools = [call.tool_name for call in trace.tool_calls]

        expected_set = set(expected_tools)
        actual_set = set(actual_tools)
        hits = expected_set & actual_set
        extras = actual_set - expected_set

        checks: list[ToolTraceCheck] = []
        evidence: list[Evidence] = []

        # Case 1: no expected, no actual -> perfect
        if not expected_tools and not actual_tools:
            return TRACE_MAX_SCORE, [
                _check("tool_trace:no_call_needed", True, None, "该场景无需调用工具，且实际未调用。")
            ], [
                Evidence(type="tool_call", comment="该场景无需调用工具，实际也未调用，工具轨迹满分。",
                         rule_id="trace.no_call_needed")
            ]

        # Case 2: has expected, no actual -> 0
        if expected_tools and not actual_tools:
            return 0.0, [
                _check("tool_trace:missing_expected_call", False, None,
                       f"该场景要求调用 {', '.join(expected_tools)}，但未调用。")
            ], [
                Evidence(type="tool_call", comment=f"该场景要求调用 {', '.join(expected_tools)}，但未调用。",
                         rule_id="trace.missing_expected_call", score_delta=-30)
            ]

        # Case 3: calculate hit rate
        total_exp = max(len(expected_set), 1)
        hit_count = len(hits)
        miss_count = len(expected_set - actual_set)
        extra_count = len(extras)

        score = TRACE_MAX_SCORE * hit_count / total_exp
        # Penalty for unexpected tool calls
        score -= 5.0 * extra_count
        score = max(0.0, min(TRACE_MAX_SCORE, round(score, 2)))

        # Build evidence
        if miss_count > 0:
            evidence.append(Evidence(
                type="tool_call",
                comment=f"期望工具 {', '.join(expected_set - actual_set)} 未被调用。",
                rule_id="trace.missed_expected_tools",
                score_delta=-round(30.0 * miss_count / total_exp, 1)
            ))
        if extra_count > 0:
            evidence.append(Evidence(
                type="tool_call",
                turn=trace.tool_calls[0].turn if trace.tool_calls else None,
                comment=f"调用了非期望工具: {', '.join(extras)}。",
                rule_id="trace.extra_unexpected_tools",
                score_delta=-5.0 * extra_count
            ))

        if hit_count > 0:
            evidence.append(Evidence(
                type="tool_call",
                turn=trace.tool_calls[0].turn if trace.tool_calls else None,
                comment=f"命中期望工具: {', '.join(hits)}（{hit_count}/{total_exp}）。" if hit_count < total_exp
                       else f"工具调用全部正确: {', '.join(hits)}。",
                rule_id="trace.hit_expected_tools",
                score_delta=0
            ))

        checks.append(_check(
            "tool_trace:hit_rate",
            hit_count == total_exp,
            trace.tool_calls[0].turn if trace.tool_calls else None,
            f"期望工具: {', '.join(expected_tools)}；实际调用: {', '.join(actual_tools)}；命中率: {hit_count}/{total_exp}。"
        ))

        # Human transfer ack check (only if transfer_to_human was called)
        if "transfer_to_human" in actual_set:
            passed, turn, comment = _check_human_transfer_sequence(trace, trace.tool_calls[0].turn)
            checks.append(_check(
                "human_transfer:retain_before_tool", passed, turn,
                "转人工前应先安抚或承接一句。"
            ))
            evidence.append(Evidence(
                type="turn", turn=turn, comment=comment,
                rule_id="trace.transfer_to_human.retain_before_tool",
                score_delta=0 if passed else -10
            ))
            if not passed:
                score = max(0.0, score - 10.0)

        return score, checks, evidence
def _check(name: str, passed: bool, turn: int | None, reason: str) -> ToolTraceCheck:
    """构造检查结果。"""
    return ToolTraceCheck(
        check=name,
        passed=passed,
        score=100.0 if passed else 0.0,
        turn=turn,
        reason=reason,
    )


def _check_human_transfer_sequence(trace: DialogueTrace, tool_turn: int) -> tuple[bool, int | None, str]:
    """检查转人工前是否有承接。"""
    agent_messages = [message for message in speaker_messages(trace, "agent") if message.turn <= tool_turn]
    if not agent_messages:
        return False, None, "转人工前缺少数字人回复，未做到先安抚/承接再转接。"

    message = agent_messages[-1]
    content = message.content
    has_ack = any(keyword in content for keyword in ["理解", "好的", "抱歉", "收到", "明白", "马上", "稍等"])
    has_transfer = any(keyword in content for keyword in ["转人工", "人工", "客服", "转接"])
    has_bridge = any(keyword in content for keyword in ["帮您", "为您", "处理", "转接", "安排", "联系"])
    user_messages = [message for message in speaker_messages(trace, "user") if message.turn <= tool_turn]
    immediate_transfer_requested = any(
        any(keyword in message.content for keyword in ["转人工", "人工客服", "别跟我说了", "不要机器人"])
        for message in user_messages[-2:]
    )
    if immediate_transfer_requested:
        passed = has_transfer and (has_ack or has_bridge)
    else:
        passed = has_ack and has_transfer and has_bridge
    if passed:
        return True, message.turn, "转人工前已完成必要承接并明确转接。"
    return False, message.turn, "转人工前未体现必要承接或未明确说明转接。"
