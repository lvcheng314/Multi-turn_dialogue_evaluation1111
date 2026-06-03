from __future__ import annotations

from dialogue_eval.schemas import DialogueTrace, Evidence, ScenarioSpec, ToolTraceCheck


TRACE_MAX_SCORE = 30.0


class TraceScorer:
    """对工具调用正确性进行评分。"""

    def score(
        self,
        scenario: ScenarioSpec,
        trace: DialogueTrace,
    ) -> tuple[float, list[ToolTraceCheck], list[Evidence]]:
        """按“该调才调、调对才得分”的规则评分。"""
        expected_tools = [call.tool_name for call in scenario.expected_tool_calls]
        actual_tools = [call.tool_name for call in trace.tool_calls]

        if not expected_tools and not actual_tools:
            return TRACE_MAX_SCORE, [
                _check("tool_trace:no_call_needed", True, None, "该场景无需调用工具，且实际未调用。")
            ], [
                Evidence(
                    type="tool_call",
                    comment="该场景无需调用工具，实际也未调用，工具轨迹满分。",
                    rule_id="trace.no_call_needed",
                )
            ]

        if not expected_tools and actual_tools:
            checks = [
                _check(
                    "tool_trace:unexpected_call",
                    False,
                    trace.tool_calls[0].turn if trace.tool_calls else None,
                    f"该场景无需调用工具，但实际调用了 {', '.join(actual_tools)}。",
                )
            ]
            evidence = [
                Evidence(
                    type="tool_call",
                    turn=trace.tool_calls[0].turn if trace.tool_calls else None,
                    comment=f"该场景无需调用工具，但实际调用了 {', '.join(actual_tools)}。",
                    rule_id="trace.unexpected_call",
                    score_delta=-30,
                )
            ]
            return 0.0, checks, evidence

        if not actual_tools:
            checks = [
                _check(
                    "tool_trace:missing_expected_call",
                    False,
                    None,
                    f"该场景要求调用 {', '.join(expected_tools)}，但未调用。",
                )
            ]
            evidence = [
                Evidence(
                    type="tool_call",
                    comment=f"该场景要求调用 {', '.join(expected_tools)}，但未调用。",
                    rule_id="trace.missing_expected_call",
                    score_delta=-30,
                )
            ]
            return 0.0, checks, evidence

        expected_primary = expected_tools[0]
        actual_primary = actual_tools[0]
        matched = actual_primary == expected_primary and len(actual_tools) == len(expected_tools)
        checks = [
            _check(
                "tool_trace:expected_primary_tool",
                matched,
                trace.tool_calls[0].turn if trace.tool_calls else None,
                (
                    f"应调用 {expected_primary}，实际调用 {actual_primary}。"
                    if actual_tools
                    else f"应调用 {expected_primary}，但未调用。"
                ),
            )
        ]

        evidence = [
            Evidence(
                type="tool_call",
                turn=trace.tool_calls[0].turn if trace.tool_calls else None,
                comment=(
                    f"工具调用正确：应调用 {expected_primary}，实际调用 {actual_primary}。"
                    if matched
                    else f"工具调用错误：应调用 {expected_primary}，实际调用 {', '.join(actual_tools)}。"
                ),
                rule_id="trace.expected_primary_tool",
                score_delta=0 if matched else -30,
            )
        ]

        if matched and expected_primary == "transfer_to_human":
            passed, turn, comment = _check_human_transfer_sequence(trace, trace.tool_calls[0].turn)
            checks.append(
                _check(
                    "human_transfer:retain_before_tool",
                    passed,
                    turn,
                    "转人工前应先安抚或承接一句。",
                )
            )
            evidence.append(
                Evidence(
                    type="turn",
                    turn=turn,
                    comment=comment,
                    rule_id="trace.transfer_to_human.retain_before_tool",
                    score_delta=0 if passed else -10,
                )
            )
            if not passed:
                return 0.0, checks, evidence

        return (TRACE_MAX_SCORE if matched else 0.0), checks, evidence


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
    agent_messages = [message for message in trace.transcript if message.role == "agent" and message.turn <= tool_turn]
    if not agent_messages:
        return False, None, "转人工前缺少数字人回复，未做到先安抚/承接再转接。"

    message = agent_messages[-1]
    content = message.content
    has_ack = any(keyword in content for keyword in ["理解", "好的", "抱歉", "稍等", "马上"])
    has_transfer = any(keyword in content for keyword in ["转人工", "人工", "客服"])
    has_bridge = any(keyword in content for keyword in ["帮您", "为您", "处理", "转接", "安排"])
    passed = has_ack and has_transfer and has_bridge
    if passed:
        return True, message.turn, "转人工前已先安抚/承接，再调用工具。"
    return False, message.turn, "转人工前未体现完整承接动作。"
