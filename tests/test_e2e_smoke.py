from pathlib import Path

from dialogue_eval.config import Settings
from dialogue_eval.pipeline import run_evaluation


def test_e2e_demo_smoke(tmp_path: Path) -> None:
    settings = Settings(
        runs_dir=str(tmp_path),
        archive_db_path=str(tmp_path / "eval_archive.sqlite3"),
        enable_llm_judge=False,
        model_provider="mock",
        scenario_count=15,
        max_turns=12,
    )
    summary = run_evaluation("examples/tasks/fengmaotui_delivery_task.json", model="mock", settings=settings)
    run_dir = tmp_path / summary.run_id
    assert summary.completed_dialogues == 15
    assert (run_dir / "trace.jsonl").exists()
    assert (run_dir / "report.md").exists()
    assert (tmp_path / "eval_archive.sqlite3").exists()
    assert "多轮对话评测报告" in (run_dir / "report.md").read_text(encoding="utf-8")
