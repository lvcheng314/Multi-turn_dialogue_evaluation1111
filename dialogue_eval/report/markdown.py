from __future__ import annotations

from collections import Counter
from statistics import mean
from pathlib import Path

from dialogue_eval.schemas import DialogueTrace, EvalResult, Evidence, ScenarioSpec, TaskSpec

DIMENSION_META = {
    "outcome": ("任务结果", "Outcome", "检查任务目标是否达成，以及关键流程是否覆盖完整。"),
    "trace": ("工具轨迹", "Trace", "检查工具调用是否正确、参数是否匹配、顺序是否合理。"),
    "safety": ("安全合规", "Safety", "检查是否存在隐私泄露、越权承诺、违规话术等风险。"),
    "text": ("话术质量", "Text", "检查表达是否自然、简洁、礼貌，并符合电话沟通场景。"),
}

REPORT_SUBJECTS = {
    "fengmaotui_delivery_task": "飞毛腿外呼",
    "course_live_task": "课程直播选项通知",
}


def render_markdown_report(
    task: TaskSpec,
    scenarios: list[ScenarioSpec],
    results: list[EvalResult],
    run_id: str,
    report_title: str,
    traces: list[DialogueTrace] | None = None,
) -> str:
    avg_score = mean([result.total_score for result in results]) if results else 0.0
    pass_count = sum(1 for result in results if result.final_decision == "pass")
    review_count = sum(1 for result in results if result.final_decision == "review")
    fail_count = sum(1 for result in results if result.final_decision == "fail")
    trace_map = {trace.dialogue_id: trace for trace in traces or []}
    scenario_map = {scenario.scenario_id: scenario for scenario in scenarios}
    low_results = sorted(results, key=lambda result: result.total_score)[:3]
    weak_dimensions = _weak_dimension_counts(results)

    lines = [
        f"# {report_title}",
        "",
        "## 评审摘要",
        "",
        f"- 报告名称: {report_title}",
        f"- 任务: {task.task}",
        f"- 角色: {task.role}",
        f"- 场景数: {len(scenarios)}",
        f"- 平均分: {avg_score:.2f}",
        f"- 结论分布: pass {pass_count} / review {review_count} / fail {fail_count}",
        f"- 最薄弱维度: {_format_counter(weak_dimensions)}",
        "",
        "## 维度说明",
        "",
    ]

    for key in ["outcome", "trace", "safety", "text"]:
        cn, en, desc = DIMENSION_META[key]
        sample = _average_dimension_score(results, key)
        lines.append(f"- {cn} {en}（平均 {sample:.2f} 分）: {desc}")

    lines.extend(
        [
            "",
        "## 主要扣分原因",
        "",
        ]
    )

    if low_results:
        for result in low_results:
            weakest = min(result.dimension_scores.items(), key=lambda item: item[1])
            weakest_label = _dimension_label(weakest[0], weakest[1])
            lines.append(
                f"- {result.dialogue_id}: 总分 {result.total_score:.2f}，最低维度 {weakest_label}。"
            )
            for evidence in _negative_or_key_evidence(result.evidence)[:3]:
                lines.append(f"  - {_evidence_line(evidence)}")
    else:
        lines.append("- 暂无评测结果。")

    lines.extend(
        [
            "",
            "## 优化建议",
            "",
            *_suggestions(weak_dimensions),
            "",
            "## 分项汇总",
            "",
            "| 对话ID | 总分 | 结论 | 任务结果 Outcome | 工具轨迹 Trace | 安全合规 Safety | 话术质量 Text |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: |",
        ]
    )

    for result in results:
        lines.append(
            "| {dialogue} | {score:.2f} | {decision} | {outcome:.2f} | {trace:.2f} | {safety:.2f} | {text:.2f} |".format(
                dialogue=result.dialogue_id,
                score=result.total_score,
                decision=_decision_label(result.final_decision),
                outcome=result.dimension_scores.get("outcome", 0),
                trace=result.dimension_scores.get("trace", 0),
                safety=result.dimension_scores.get("safety", 0),
                text=result.dimension_scores.get("text", 0),
            )
        )

    lines.extend(["", "## 可追溯证据明细", ""])
    for result in results:
        trace = trace_map.get(result.dialogue_id)
        scenario = scenario_map.get(trace.scenario_id) if trace else None
        lines.append(f"### {result.dialogue_id}")
        if scenario:
            lines.append(f"- 场景: {scenario.scenario_id} / {scenario.persona}")
            if scenario.goals:
                lines.append(f"- 场景目标: {'; '.join(scenario.goals)}")
        lines.append(f"- 总分: {result.total_score:.2f}")
        lines.append(
            "- 分项: {outcome}；{trace_score}；{safety}；{text}".format(
                outcome=_dimension_label("outcome", result.dimension_scores.get("outcome", 0)),
                trace_score=_dimension_label("trace", result.dimension_scores.get("trace", 0)),
                safety=_dimension_label("safety", result.dimension_scores.get("safety", 0)),
                text=_dimension_label("text", result.dimension_scores.get("text", 0)),
            )
        )
        lines.append(f"- 结论: {_decision_label(result.final_decision)}")

        if result.tool_trace_checks:
            lines.extend(["", "#### 工具调用客观检查", ""])
            for check in result.tool_trace_checks:
                passed = "通过" if check.passed else "失败"
                turn = f"第 {check.turn} 轮" if check.turn else "无对应轮次"
                lines.append(f"- {check.check}: {passed}, {check.score:.0f}; {turn}; {check.reason}")

        lines.extend(["", "#### 评分证据", ""])
        for dimension in ["outcome", "trace", "safety", "text"]:
            lines.append(f"- {_dimension_label(dimension, result.dimension_scores.get(dimension, 0))}")
            dimension_evidence = [
                evidence for evidence in result.evidence if evidence.dimension == dimension
            ]
            if not dimension_evidence:
                lines.append("  - 无该项证据。")
            for evidence in dimension_evidence:
                lines.append(f"  - {_evidence_line(evidence)}")

        if trace:
            lines.extend(["", "#### 对话原文", ""])
            for message in trace.transcript:
                role = {"user": "用户", "agent": "数字人", "system": "系统"}.get(message.role, message.role)
                lines.append(f"- 第 {message.turn} 轮 {role}: {message.content}")

            lines.extend(["", "#### 工具调用 trace", ""])
            if trace.tool_calls:
                for call in trace.tool_calls:
                    status = "成功" if call.error_code is None else f"失败 {call.error_code}"
                    lines.append(
                        f"- 第 {call.turn} 轮 `{call.tool_name}`: {status}; 参数 {call.arguments}; 结果 {call.result}"
                    )
            else:
                lines.append("- 无工具调用。")

            lines.extend(["", "#### 状态 trace", ""])
            for state in trace.state_trace:
                lines.append(f"- 第 {state.get('turn')} 轮: {state}")

        if result.risk_flags:
            lines.append(f"- 风险标记: {', '.join(result.risk_flags)}")
        lines.append("")

    return "\n".join(lines)


def _weak_dimension_counts(results: list[EvalResult]) -> Counter:
    counter: Counter[str] = Counter()
    for result in results:
        if result.dimension_scores:
            weakest = min(result.dimension_scores.items(), key=lambda item: item[1])[0]
            counter[weakest] += 1
    return counter


def _format_counter(counter: Counter) -> str:
    if not counter:
        return "暂无"
    return ", ".join(
        f"{DIMENSION_META.get(key, (key, key, ''))[0]} {DIMENSION_META.get(key, (key, key, ''))[1]}({value})"
        for key, value in counter.most_common(3)
    )


def _average_dimension_score(results: list[EvalResult], dimension: str) -> float:
    if not results:
        return 0.0
    values = [result.dimension_scores.get(dimension, 0.0) for result in results]
    return round(mean(values), 2) if values else 0.0


def _dimension_label(dimension: str, score: float | None = None, include_score: bool = True) -> str:
    cn, en, _ = DIMENSION_META.get(dimension, (dimension, dimension.title(), ""))
    if include_score and score is not None:
        return f"{cn} {en}（{score:.2f}分）"
    return f"{cn} {en}"


def _decision_label(decision: str) -> str:
    return {
        "pass": "通过",
        "review": "复核",
        "fail": "失败",
    }.get(decision, decision)


def build_report_identity(task: TaskSpec, runs_dir: str | Path) -> tuple[str, str]:
    from datetime import datetime

    subject = REPORT_SUBJECTS.get(task.task_id) or _fallback_subject(task)
    now = datetime.now()
    display_date = now.strftime("%Y/%m/%d")
    file_date = now.strftime("%Y-%m-%d")
    serial = _next_report_serial(subject, runs_dir, file_date)
    title = f"{subject}测评报告{display_date}/{serial}"
    filename = f"{_safe_filename(subject)}测评报告{file_date}-{serial}"
    return title, filename


def _fallback_subject(task: TaskSpec) -> str:
    text = task.task.replace("致电", "").replace("告知", "").replace("通知", "").strip("，。； ")
    if len(text) > 10:
        text = text[:10]
    return text or task.task_id


def _next_report_serial(subject: str, runs_dir: str | Path, file_date: str) -> str:
    pattern = f"{_safe_filename(subject)}测评报告{file_date}-"
    max_serial = 0
    runs_path = Path(runs_dir)
    if runs_path.exists():
        for candidate in runs_path.rglob("*.md"):
            name = candidate.stem
            if not name.startswith(pattern):
                continue
            suffix = name.removeprefix(pattern)
            if len(suffix) == 4 and suffix.isdigit():
                max_serial = max(max_serial, int(suffix))
    return f"{max_serial + 1:04d}"


def _safe_filename(text: str) -> str:
    invalid = '<>:"/\\|?*'
    return "".join("_" if ch in invalid else ch for ch in text).strip()


def _negative_or_key_evidence(evidence: list[Evidence]) -> list[Evidence]:
    negative = [item for item in evidence if item.score_delta is not None and item.score_delta < 0]
    if negative:
        return negative
    return evidence


def _evidence_line(evidence: Evidence) -> str:
    turn = f"第 {evidence.turn} 轮" if evidence.turn else "状态级证据"
    rule = f"规则 {evidence.rule_id}; " if evidence.rule_id else ""
    delta = f"; 扣分 {abs(evidence.score_delta):.0f}" if evidence.score_delta and evidence.score_delta < 0 else ""
    return f"{turn}: {rule}{evidence.comment}{delta}"


def _suggestions(weak_dimensions: Counter) -> list[str]:
    if not weak_dimensions:
        return ["- 先完成一次完整评测，生成可分析的结果。"]
    suggestions = []
    for dimension, _ in weak_dimensions.most_common(3):
        if dimension == "trace":
            suggestions.append("- 强化工具调用流程：为转人工、回访、FAQ、拒绝记录等场景明确触发条件、参数和调用顺序。")
        elif dimension == "outcome":
            suggestions.append("- 强化任务流程覆盖：要求数字人逐步覆盖身份确认、任务说明、异议处理、结果确认和礼貌收尾。")
        elif dimension == "text":
            suggestions.append("- 优化话术质量：减少机械重复，增加自然追问、确认和简短解释。")
        elif dimension == "safety":
            suggestions.append("- 收紧安全边界：避免承诺收益、泄露隐私字段或响应越权诱导。")
    return suggestions
