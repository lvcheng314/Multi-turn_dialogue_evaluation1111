from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from dialogue_eval.config import Settings, get_settings
from dialogue_eval.models.openai_compatible import OpenAICompatibleAgent
from dialogue_eval.schemas import EvalResult
from dialogue_eval.storage.archive import group_history, list_runs


def analyze_run(run_dir: Path, question: str, archive_db_path: str | Path) -> str:
    results_path = run_dir / "results.json"
    task_path = run_dir / "task.json"
    if not results_path.exists() or not task_path.exists():
        raise FileNotFoundError("run artifacts are incomplete")

    task = json.loads(task_path.read_text(encoding="utf-8"))
    results = [
        EvalResult.model_validate(item)
        for item in json.loads(results_path.read_text(encoding="utf-8"))
    ]
    if "风险" in question:
        return _risk_analysis(results)
    if "建议" in question or "优化" in question:
        return _suggestions(results)
    if "对比" in question or "历史" in question:
        history = _history_for_task(archive_db_path, task["task_id"])
        return _history_analysis(history)
    return _score_analysis(results)


def stream_analyze_run(
    run_dir: Path,
    question: str,
    archive_db_path: str | Path,
    settings: Settings | None = None,
) -> Iterator[str]:
    settings = settings or get_settings()
    prompt = _analysis_prompt(run_dir, question, archive_db_path, settings)
    yield from OpenAICompatibleAgent.stream_chat_with_options(
        base_url=settings.model_base_url,
        api_key=settings.effective_model_api_key,
        model=settings.model_name,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是多轮外呼对话评测报告分析助手。必须基于给定报告和评分证据回答，"
                    "不能编造不存在的对话。用中文输出，结论清晰，优先给可执行建议。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=1200,
    )


def _analysis_prompt(
    run_dir: Path,
    question: str,
    archive_db_path: str | Path,
    settings: Settings,
) -> str:
    report_path = run_dir / "report.md"
    results_path = run_dir / "results.json"
    task_path = run_dir / "task.json"
    if not report_path.exists() or not results_path.exists() or not task_path.exists():
        raise FileNotFoundError("run artifacts are incomplete")
    task = json.loads(task_path.read_text(encoding="utf-8"))
    results = json.loads(results_path.read_text(encoding="utf-8"))
    history = group_history(archive_db_path, task["task_id"], settings.model_name)[:8]
    report = report_path.read_text(encoding="utf-8")
    compact_results = [
        {
            "dialogue_id": item.get("dialogue_id"),
            "total_score": item.get("total_score"),
            "dimension_scores": item.get("dimension_scores"),
            "risk_flags": item.get("risk_flags"),
            "tool_trace_checks": item.get("tool_trace_checks", [])[:8],
            "evidence": item.get("evidence", [])[:8],
        }
        for item in results
    ]
    return (
        f"用户问题: {question}\n\n"
        f"任务ID: {task.get('task_id')}\n"
        f"任务要求: {task.get('task')}\n\n"
        f"归档历史摘要: {json.dumps(history, ensure_ascii=False)[:3000]}\n\n"
        f"评分结果摘要: {json.dumps(compact_results, ensure_ascii=False)[:10000]}\n\n"
        f"完整 Markdown 报告:\n{report[:14000]}\n\n"
        "请直接回答用户问题。需要引用证据时，指出 dialogue_id、维度、分数、规则和轮次。"
    )


def _score_analysis(results: list[EvalResult]) -> str:
    if not results:
        return "没有可分析的评分结果。"
    sorted_results = sorted(results, key=lambda item: item.total_score)
    low = sorted_results[:3]
    lines = ["低分原因概览:"]
    for result in low:
        weakest = min(result.dimension_scores.items(), key=lambda item: item[1])
        lines.append(
            f"- {result.dialogue_id}: 总分 {result.total_score:.2f}，最低维度是 {weakest[0]}={weakest[1]:.2f}。"
        )
        evidence = [
            item
            for item in result.evidence
            if item.score_delta is not None and item.score_delta < 0
        ] or result.evidence
        for item in evidence[:4]:
            turn = f"第 {item.turn} 轮" if item.turn else "状态级证据"
            rule = f"规则 {item.rule_id}: " if item.rule_id else ""
            lines.append(f"  - {turn}: {rule}{item.comment}")
    return "\n".join(lines)


def _risk_analysis(results: list[EvalResult]) -> str:
    flagged = [result for result in results if result.risk_flags]
    if not flagged:
        return "本次报告未发现显式风险标记。仍建议重点复核低分场景中的任务覆盖和工具调用。"
    lines = ["风险点:"]
    for result in flagged:
        lines.append(f"- {result.dialogue_id}: {', '.join(result.risk_flags)}")
        for evidence in result.evidence:
            if evidence.dimension == "safety":
                turn = f"第 {evidence.turn} 轮" if evidence.turn else "状态级证据"
                lines.append(f"  - {turn}: {evidence.comment}")
    return "\n".join(lines)


def _suggestions(results: list[EvalResult]) -> str:
    averages: dict[str, float] = {}
    for dimension in ["outcome", "trace", "safety", "text"]:
        values = [result.dimension_scores.get(dimension, 0) for result in results]
        averages[dimension] = sum(values) / len(values) if values else 0
    weakest = sorted(averages.items(), key=lambda item: item[1])[:2]
    lines = ["优化建议:"]
    for dimension, score in weakest:
        if dimension == "outcome":
            lines.append(f"- Outcome 平均 {score:.2f}: 强化任务流程覆盖，要求数字人逐步确认身份、说明任务、处理异议、确认结果和礼貌收尾。")
        elif dimension == "trace":
            lines.append(f"- Trace 平均 {score:.2f}: 明确每个工具触发条件、参数和顺序，尤其是转人工必须先安抚/挽留再调用 tool。")
        elif dimension == "safety":
            lines.append(f"- Safety 平均 {score:.2f}: 收紧禁止承诺、隐私字段和越权回答规则。")
        elif dimension == "text":
            lines.append(f"- Text 平均 {score:.2f}: 增加自然追问和确认，避免过短、机械重复或只给结论。")
    return "\n".join(lines)


def _history_analysis(history: list[dict]) -> str:
    if not history:
        return "还没有同任务的历史归档。"
    latest = history[0]
    best = max(history, key=lambda item: item["total_score"])
    avg = sum(item["total_score"] for item in history) / len(history)
    return (
        "历史对比:\n"
        f"- 同任务共有 {len(history)} 次评测。\n"
        f"- 最新 run: {latest['run_id']}，总分 {latest['total_score']:.2f}。\n"
        f"- 最高分 run: {best['run_id']}，总分 {best['total_score']:.2f}。\n"
        f"- 平均分: {avg:.2f}。"
    )


def _history_for_task(archive_db_path: str | Path, task_id: str) -> list[dict]:
    return [row for row in list_runs(archive_db_path, limit=500) if row["task_id"] == task_id]
