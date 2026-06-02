import typer
from pathlib import Path

from dialogue_eval.config import get_settings
from dialogue_eval.parser import load_task
from dialogue_eval.pipeline import run_evaluation
from dialogue_eval.scenarios import generate_scenarios
from dialogue_eval.schemas import DialogueTrace, ScoringConfig
from dialogue_eval.scorer import ScorerSkill
from dialogue_eval.task_sources import resolve_task_path

app = typer.Typer(help="Multi-turn dialogue evaluation CLI.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Multi-turn dialogue evaluation commands."""


@app.command("demo")
def demo() -> None:
    """Run the built-in demo task through the full evaluation pipeline."""
    summary = run_evaluation(resolve_task_path("fengmaotui_delivery_task"))
    typer.echo(f"Run completed: {summary.run_id}")
    typer.echo(f"Dialogues: {summary.completed_dialogues}/{summary.scenario_count}")
    typer.echo(f"Average score: {summary.total_score}")
    typer.echo(f"Markdown report: {summary.report_markdown_path}")
    typer.echo(f"HTML report: {summary.report_html_path}")


@app.command("run")
def run(
    task: Path | None = typer.Option(None, "--task", exists=True, readable=True),
    task_source: str = typer.Option("fengmaotui_delivery_task", "--task-source"),
    model: str = typer.Option("deepseek", "--model"),
    scenarios: int = typer.Option(15, "--scenarios", min=1),
) -> None:
    """Run an evaluation for a task JSON or Excel file."""
    task_path = task or resolve_task_path(task_source)
    summary = run_evaluation(task_path, scenarios_count=scenarios, model=model)
    typer.echo(f"Run completed: {summary.run_id}")
    typer.echo(f"Average score: {summary.total_score}")
    typer.echo(f"Report: {summary.report_markdown_path}")


@app.command("score")
def score(trace: Path = typer.Option(..., "--trace", exists=True, readable=True)) -> None:
    """Score a single DialogueTrace JSON file with the demo task/scenario context."""
    task = load_task(resolve_task_path("fengmaotui_delivery_task"))
    scenarios = generate_scenarios(task, 15)
    trace_obj = DialogueTrace.model_validate_json(trace.read_text(encoding="utf-8"))
    scenario = next(item for item in scenarios if item.scenario_id == trace_obj.scenario_id)
    settings = get_settings()
    result = ScorerSkill().score(
        task,
        scenario,
        trace_obj,
        ScoringConfig(enable_llm_judge=settings.enable_llm_judge, max_turns=settings.max_turns),
    )
    typer.echo(result.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
