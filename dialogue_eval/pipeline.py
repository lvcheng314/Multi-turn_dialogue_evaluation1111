from __future__ import annotations

from pathlib import Path
from statistics import mean
from uuid import uuid4
from collections.abc import Callable

from dialogue_eval.config import Settings, get_settings
from dialogue_eval.models import MockAgent, OpenAICompatibleAgent
from dialogue_eval.parser import load_task
from dialogue_eval.report import render_html_report, render_markdown_report
from dialogue_eval.runner import DialogueRunner
from dialogue_eval.runner.deepseek_dialogue_generator import DeepSeekDialogueGenerator
from dialogue_eval.scenarios import generate_scenarios
from dialogue_eval.schemas import EvalResult, RunSummary, ScoringConfig
from dialogue_eval.scorer import ScorerSkill
from dialogue_eval.storage.archive import archive_run
from dialogue_eval.storage import RunStore


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
    agent = _build_agent(settings, model)
    runner = _build_runner(settings, model, agent)
    scorer = ScorerSkill()
    scoring_config = ScoringConfig(
        enable_llm_judge=settings.enable_llm_judge,
        max_turns=settings.max_turns,
    )

    results: list[EvalResult] = []
    traces = []
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

    store.write_json(run_id, "results.json", results)
    if progress:
        progress("report_generation_started", {"run_id": run_id})
    markdown = render_markdown_report(task, scenarios, results, run_id, traces)
    html = render_html_report(markdown)
    report_markdown_path = store.write_text(run_id, "report.md", markdown)
    report_html_path = store.write_text(run_id, "report.html", html)

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
    archive_run(settings.archive_db_path, task, _archive_model_name(settings, model), summary)
    if progress:
        progress("completed", summary.model_dump(mode="json"))
    return summary


def _build_agent(settings: Settings, model: str | None) -> object:
    selected = (model or settings.model_provider).lower()
    if selected in {"mock", "mock-agent"}:
        return MockAgent()
    return OpenAICompatibleAgent(settings)


def _build_runner(settings: Settings, model: str | None, agent: object) -> object:
    selected = (model or settings.model_provider).lower()
    if selected in {"mock", "mock-agent"}:
        return DialogueRunner(agent=agent)
    return DeepSeekDialogueGenerator(settings)


def _archive_model_name(settings: Settings, model: str | None) -> str:
    selected = (model or settings.model_provider).lower()
    if selected in {"mock", "mock-agent"}:
        return "mock-agent"
    return settings.model_name
