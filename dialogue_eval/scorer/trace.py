from __future__ import annotations

from dialogue_eval.schemas import DialogueTrace, Evidence, ScenarioSpec, ToolTraceCheck


TRACE_MAX_SCORE = 30.0


class TraceScorer:
    """Scores objective tool-call process evidence from DialogueTrace."""

    def score(
        self,
        scenario: ScenarioSpec,
        trace: DialogueTrace,
    ) -> tuple[float, list[ToolTraceCheck], list[Evidence]]:
        checks: list[ToolTraceCheck] = []
        evidence: list[Evidence] = []

        if not scenario.expected_tool_calls:
            return TRACE_MAX_SCORE, checks, [
                Evidence(
                    type="tool_call",
                    comment="该场景未要求工具调用，工具流程默认通过。",
                    rule_id="trace.no_required_tool",
                )
            ]

        for expected in scenario.expected_tool_calls:
            matched = [
                call
                for call in trace.tool_calls
                if call.tool_name == expected.tool_name
            ]
            first_call = matched[0] if matched else None

            called = first_call is not None
            checks.append(
                _check(
                    f"expected_tool:{expected.tool_name}:called",
                    called,
                    first_call.turn if first_call else None,
                    f"必须调用 {expected.tool_name}",
                )
            )
            evidence.append(
                Evidence(
                    type="tool_call",
                    turn=first_call.turn if first_call else None,
                    comment=(
                        f"已调用预期工具 {expected.tool_name}。"
                        if called
                        else f"缺少预期工具调用 {expected.tool_name}。"
                    ),
                    rule_id=f"trace.{expected.tool_name}.called",
                    score_delta=0 if called else -10,
                )
            )

            if first_call is None:
                checks.append(_check(f"expected_tool:{expected.tool_name}:arguments", False, None, "缺少工具调用，无法校验参数"))
                checks.append(_check(f"expected_tool:{expected.tool_name}:success", False, None, "缺少工具调用，无法校验返回结果"))
                continue

            argument_passed = all(
                first_call.arguments.get(key) == value
                for key, value in expected.arguments.items()
            )
            checks.append(
                _check(
                    f"expected_tool:{expected.tool_name}:arguments",
                    argument_passed,
                    first_call.turn,
                    f"参数必须包含并匹配 {expected.arguments}",
                )
            )
            evidence.append(
                Evidence(
                    type="tool_call",
                    turn=first_call.turn,
                    comment=(
                        f"工具参数匹配预期: {expected.arguments}。"
                        if argument_passed
                        else f"工具参数不匹配，预期 {expected.arguments}，实际 {first_call.arguments}。"
                    ),
                    rule_id=f"trace.{expected.tool_name}.arguments",
                    score_delta=0 if argument_passed else -8,
                )
            )

            success_passed = first_call.error_code is None and first_call.result.get("status") not in {"failed", "error"}
            checks.append(
                _check(
                    f"expected_tool:{expected.tool_name}:success",
                    success_passed,
                    first_call.turn,
                    "工具调用必须无 error_code，且返回状态不能是 failed/error",
                )
            )
            evidence.append(
                Evidence(
                    type="tool_call",
                    turn=first_call.turn,
                    comment=(
                        f"工具返回成功: {first_call.result}。"
                        if success_passed
                        else f"工具返回失败: error_code={first_call.error_code}, result={first_call.result}。"
                    ),
                    rule_id=f"trace.{expected.tool_name}.success",
                    score_delta=0 if success_passed else -8,
                )
            )

            if expected.tool_name == "transfer_to_human":
                passed, turn, comment = _check_human_transfer_sequence(trace, first_call.turn)
                checks.append(
                    _check(
                        "human_transfer:retain_before_tool",
                        passed,
                        turn,
                        "用户要求转人工时，数字人必须先安抚/挽留一句，再调用 transfer_to_human",
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

        score = TRACE_MAX_SCORE * sum(check.score for check in checks) / (len(checks) * 100)
        return round(score, 2), checks, evidence


def _check(name: str, passed: bool, turn: int | None, reason: str) -> ToolTraceCheck:
    return ToolTraceCheck(
        check=name,
        passed=passed,
        score=100.0 if passed else 0.0,
        turn=turn,
        reason=reason,
    )


def _check_human_transfer_sequence(trace: DialogueTrace, tool_turn: int) -> tuple[bool, int | None, str]:
    agent_messages = [
        message
        for message in trace.transcript
        if message.role == "agent" and message.turn <= tool_turn
    ]
    if not agent_messages:
        return False, None, "转人工前缺少数字人回复，未做到先安抚/挽留再转接。"

    message = agent_messages[-1]
    content = message.content
    has_ack = any(keyword in content for keyword in ["理解", "好的", "抱歉", "稍等", "马上"])
    has_transfer = any(keyword in content for keyword in ["转人工", "人工", "客服"])
    has_bridge = any(keyword in content for keyword in ["先", "帮您", "为您", "确认", "处理"])
    passed = has_ack and has_transfer and has_bridge
    if passed:
        return True, message.turn, "转人工前已先安抚/挽留一句，并在同轮或随后调用 transfer_to_human。"
    return False, message.turn, "转人工流程不完整：需要先安抚/挽留一句，再调用 transfer_to_human。"
