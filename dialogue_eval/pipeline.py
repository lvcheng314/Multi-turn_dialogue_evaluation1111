from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from statistics import mean
from uuid import uuid4

from dialogue_eval.config import Settings, get_settings
from dialogue_eval.parser import load_task
from dialogue_eval.report import render_html_report, render_markdown_report
from dialogue_eval.report.markdown import build_report_identity
from dialogue_eval.runner.deepseek_dialogue_generator import DeepSeekDialogueGenerator
from dialogue_eval.scenarios import generate_scenarios
from dialogue_eval.schemas import DialogueTrace, EvalResult, ImportedDialogueTrace, RunSummary, ScoringConfig, ScenarioSpec
from dialogue_eval.scorer import ScorerSkill
from dialogue_eval.storage import RunStore
from dialogue_eval.storage.archive import archive_run


def run_evaluation(
    task_path: str | Path,
    scenarios_count: int | None = None,
    model: str | None = None,
    settings: Settings | None = None,
    progress: Callable[[str, dict | None], None] | None = None,
) -> RunSummary:
    settings = settings or get_settings()
    task = load_task(task_path)
    scenario_count = scenarios_count or settings.scenario_count
    if progress:
        progress("scenario_generation_started", {"scenario_count": scenario_count})
    scenarios = generate_scenarios(task, scenario_count)
    if progress:
        progress("scenario_generation_completed", {"scenario_count": len(scenarios)})
    run_id = f"run_{uuid4().hex[:12]}"

    store = RunStore(settings.runs_dir)
    runner = _build_runner(settings, model)
    scorer = ScorerSkill()
    scoring_config = ScoringConfig(
        enable_llm_judge=settings.enable_llm_judge,
        max_turns=settings.max_turns,
    )

    results: list[EvalResult] = []
    traces: list[DialogueTrace] = []
    store.write_json(run_id, "task.json", task)
    store.write_json(run_id, "scenarios.json", scenarios)

    for index, scenario in enumerate(scenarios, start=1):
        dialogue_id = f"dialogue_{index:03d}"
        if progress:
            progress(
                "model_generation_started",
                {
                    "dialogue_id": dialogue_id,
                    "index": index,
                    "total": len(scenarios),
                },
            )
        trace = runner.run(run_id, dialogue_id, task, scenario, settings.max_turns)
        if progress:
            progress(
                "scoring_started",
                {
                    "dialogue_id": dialogue_id,
                    "index": index,
                    "total": len(scenarios),
                },
            )
        result = scorer.score(task, scenario, trace, scoring_config)
        store.append_trace(run_id, trace)
        store.write_json(run_id, f"{dialogue_id}_trace.json", trace)
        store.write_json(run_id, f"{dialogue_id}_result.json", result)
        traces.append(trace)
        results.append(result)
        if progress:
            progress(
                "dialogue_completed",
                {
                    "dialogue_id": dialogue_id,
                    "index": index,
                    "total": len(scenarios),
                    "score": result.total_score,
                },
            )

    return _finalize_run(
        run_id=run_id,
        task=task,
        scenarios=scenarios,
        traces=traces,
        results=results,
        settings=settings,
        model_name=_archive_model_name(settings, model),
        store=store,
        report_metadata={"data_source": "澶фā鍨嬬敓鎴愭ā鎷?", "scenario_source": "鍦烘櫙鐢熸垚"},
        progress=progress,
    )


def run_imported_evaluation(
    task_path: str | Path,
    trace_input: ImportedDialogueTrace | list[ImportedDialogueTrace],
    settings: Settings | None = None,
    model_name: str | None = None,
    progress: Callable[[str, dict | None], None] | None = None,
) -> RunSummary:
    settings = settings or get_settings()
    task = load_task(task_path)
    scenarios = generate_scenarios(task, settings.scenario_count)
    run_id = f"run_{uuid4().hex[:12]}"
    store = RunStore(settings.runs_dir)
    scorer = ScorerSkill()
    scoring_config = ScoringConfig(
        enable_llm_judge=settings.enable_llm_judge,
        max_turns=settings.max_turns,
    )
    traces_input = trace_input if isinstance(trace_input, list) else [trace_input]
    traces: list[DialogueTrace] = []
    results: list[EvalResult] = []
    fallback_count = 0
    matched_scenarios: list[str] = []

    if progress:
        progress("scenario_generation_started", {"scenario_count": len(scenarios)})
        progress("scenario_generation_completed", {"scenario_count": len(scenarios)})

    store.write_json(run_id, "task.json", task)
    store.write_json(run_id, "scenarios.json", scenarios)

    for index, imported_trace in enumerate(traces_input, start=1):
        matched_scenario, matched_score, fallback_used = _match_scenario(imported_trace, scenarios)
        trace = _normalize_imported_trace(run_id, task.task_id, imported_trace, matched_scenario.scenario_id)
        if fallback_used:
            fallback_count += 1
        matched_scenarios.append(matched_scenario.scenario_id)

        if progress:
            progress(
                "scoring_started",
                {
                    "dialogue_id": trace.dialogue_id,
                    "index": index,
                    "total": len(traces_input),
                    "scenario_id": matched_scenario.scenario_id,
                    "matched_score": round(matched_score, 2),
                },
            )

        result = scorer.score(task, matched_scenario, trace, scoring_config)
        store.append_trace(run_id, trace)
        store.write_json(run_id, f"{trace.dialogue_id}_trace.json", trace)
        store.write_json(run_id, f"{trace.dialogue_id}_result.json", result)
        traces.append(trace)
        results.append(result)

    return _finalize_run(
        run_id=run_id,
        task=task,
        scenarios=scenarios,
        traces=traces,
        results=results,
        settings=settings,
        model_name=model_name or "imported-trace",
        store=store,
        report_metadata={
            "data_source": "涓婁紶瀵硅瘽鏁版嵁",
            "scenario_source": "鑷姩鍖归厤锛堥儴鍒嗗洖閫€鍒伴涓満鏅級" if fallback_count else "鑷姩鍖归厤",
            "matched_scenario_id": ", ".join(matched_scenarios[:5]) + (" ..." if len(matched_scenarios) > 5 else ""),
            "matched_scenario_score": f"fallback {fallback_count}/{len(traces_input)}",
        },
        progress=progress,
    )


def _finalize_run(
    *,
    run_id: str,
    task,
    scenarios: list[ScenarioSpec],
    traces: list[DialogueTrace],
    results: list[EvalResult],
    settings: Settings,
    model_name: str,
    store: RunStore,
    report_metadata: dict[str, str],
    progress: Callable[[str, dict | None], None] | None = None,
) -> RunSummary:
    store.write_json(run_id, "results.json", results)
    if progress:
        progress("report_generation_started", {"run_id": run_id})
    report_title, report_file_stem = build_report_identity(task, settings.runs_dir)
    markdown = render_markdown_report(task, scenarios, results, run_id, report_title, traces, report_metadata)
    html = render_html_report(markdown)
    report_markdown_path = store.write_text(run_id, f"{report_file_stem}.md", markdown)
    report_html_path = store.write_text(run_id, f"{report_file_stem}.html", html)
    store.write_text(run_id, "report.md", markdown)
    store.write_text(run_id, "report.html", html)
    store.write_json(
        run_id,
        "report_meta.json",
        {
            "report_title": report_title,
            "report_markdown_name": report_markdown_path.name,
            "report_html_name": report_html_path.name,
            **report_metadata,
        },
    )

    summary = RunSummary(
        run_id=run_id,
        task_id=task.task_id,
        status="completed",
        scenario_count=len(scenarios),
        completed_dialogues=len(results),
        total_score=round(mean([result.total_score for result in results]), 2) if results else 0.0,
        report_markdown_path=str(report_markdown_path),
        report_html_path=str(report_html_path),
    )
    archive_run(settings.archive_db_path, task, model_name, summary)
    if progress:
        progress("completed", summary.model_dump(mode="json"))
    return summary


def _normalize_imported_trace(
    run_id: str,
    task_id: str,
    trace_input: ImportedDialogueTrace,
    scenario_id: str,
) -> DialogueTrace:
    transcript = sorted(trace_input.transcript, key=lambda message: message.turn)
    state_trace = trace_input.state_trace or [
        {
            "turn": message.turn,
            "task_status": "in_progress" if message.turn > 1 else "opened",
            "identity_confirmed": message.turn > 1,
        }
        for message in transcript
    ]
    if state_trace:
        state_trace[-1]["task_status"] = state_trace[-1].get("task_status", "completed") or "completed"
    return DialogueTrace(
        run_id=run_id,
        dialogue_id=trace_input.dialogue_id,
        task_id=task_id,
        scenario_id=scenario_id,
        transcript=transcript,
        tool_calls=trace_input.tool_calls,
        state_trace=state_trace,
    )


def _match_scenario(trace: DialogueTrace, scenarios: list[ScenarioSpec]) -> tuple[ScenarioSpec, float, bool]:
    transcript_text = " ".join(message.content for message in trace.transcript).lower()
    best = scenarios[0]
    best_score = -1.0
    for scenario in scenarios:
        parts = [
            scenario.persona,
            scenario.initial_user_input,
            *scenario.goals,
            *scenario.expected_behaviors,
            *scenario.risk_points,
        ]
        score = 0.0
        for token in _tokens(" ".join(parts)):
            if token and token in transcript_text:
                score += 1.0
        if score > best_score:
            best = scenario
            best_score = score
    return best, best_score, best_score <= 0


def _tokens(text: str) -> list[str]:
    normalized = text.replace("锛?", " ").replace("銆?", " ").replace("銆?", " ").replace("锛?", " ").lower()
    return [token for token in normalized.split() if len(token) >= 2]


def _build_runner(settings: Settings, model: str | None) -> object:
    return DeepSeekDialogueGenerator(settings)


def _archive_model_name(settings: Settings, model: str | None) -> str:
    return str(model or settings.model_name)
