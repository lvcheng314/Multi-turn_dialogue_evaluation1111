from pathlib import Path

import pytest
from fastapi import HTTPException

from dialogue_eval.api.routes import _validate_imported_trace_payload
from dialogue_eval.config import Settings
from dialogue_eval.models.openai_compatible import OpenAICompatibleAgent
from dialogue_eval.pipeline import run_evaluation, run_imported_evaluation
from dialogue_eval.schemas import ChatMessage, ImportedDialogueTrace


def test_e2e_demo_smoke(tmp_path: Path) -> None:
    def fake_chat_with_options(
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict],
        response_format: dict | None = None,
        temperature: float = 0.2,
        max_tokens: int = 200,
    ) -> str:
        del base_url, api_key, model, messages, response_format, temperature, max_tokens
        return """
        {
          "final_status": "completed",
          "transcript": [
            {"role": "agent", "content": "您好，这边和您确认一下任务安排。"},
            {"role": "user", "content": "好的，你说。"},
            {"role": "agent", "content": "已经说明完成，稍后您按流程处理即可。"}
          ],
          "tool_calls": [],
          "state_trace": [
            {"turn": 1, "task_status": "opened", "identity_confirmed": false},
            {"turn": 2, "task_status": "in_progress", "identity_confirmed": true},
            {"turn": 3, "task_status": "completed", "identity_confirmed": true}
          ]
        }
        """.strip()

    OpenAICompatibleAgent._chat_with_options = staticmethod(fake_chat_with_options)
    settings = Settings(
        runs_dir=str(tmp_path),
        archive_db_path=str(tmp_path / "eval_archive.sqlite3"),
        enable_llm_judge=False,
        model_provider="deepseek",
        model_api_key="test-key",
        model_name="deepseek-chat",
        scenario_count=15,
        max_turns=12,
    )
    summary = run_evaluation("tasks/fengmaotui_delivery_task.json", model="deepseek", settings=settings)
    run_dir = tmp_path / summary.run_id
    assert summary.completed_dialogues == 15
    assert (run_dir / "trace.jsonl").exists()
    assert (run_dir / "report.md").exists()
    assert summary.report_markdown_path.endswith("-0001.md")
    assert summary.report_html_path.endswith("-0001.html")
    assert (tmp_path / "eval_archive.sqlite3").exists()
    report_text = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "dialogue_001" in report_text
    assert "## " in report_text


def test_imported_trace_smoke(tmp_path: Path) -> None:
    settings = Settings(
        runs_dir=str(tmp_path),
        archive_db_path=str(tmp_path / "eval_archive.sqlite3"),
        enable_llm_judge=False,
        model_provider="deepseek",
        model_api_key="test-key",
        model_name="deepseek-chat",
        scenario_count=15,
        max_turns=12,
    )
    trace = ImportedDialogueTrace(
        dialogue_id="dialogue_import_001",
        transcript=[
            ChatMessage(turn=1, role="agent", content="您好，今天合同已生效。"),
            ChatMessage(turn=2, role="user", content="好的，我知道了。"),
            ChatMessage(turn=3, role="agent", content="请按要求完成配送任务。"),
        ],
    )
    summary = run_imported_evaluation("tasks/fengmaotui_delivery_task.json", trace, settings=settings)
    run_dir = tmp_path / summary.run_id
    assert summary.completed_dialogues == 1
    assert (run_dir / "trace.jsonl").exists()
    report_text = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "dialogue_import_001" in report_text
    assert "matched_scenario_score" not in report_text


def test_imported_trace_batch_smoke(tmp_path: Path) -> None:
    settings = Settings(
        runs_dir=str(tmp_path),
        archive_db_path=str(tmp_path / "eval_archive.sqlite3"),
        enable_llm_judge=False,
        model_provider="deepseek",
        model_api_key="test-key",
        model_name="deepseek-chat",
        scenario_count=15,
        max_turns=12,
    )
    traces = [
        ImportedDialogueTrace(
            dialogue_id="dialogue_import_001",
            transcript=[
                ChatMessage(turn=1, role="agent", content="您好，今天合同已生效。"),
                ChatMessage(turn=2, role="user", content="好的，我知道了。"),
                ChatMessage(turn=3, role="agent", content="请按要求完成配送任务。"),
            ],
        ),
        ImportedDialogueTrace(
            dialogue_id="dialogue_import_002",
            transcript=[
                ChatMessage(turn=1, role="agent", content="您好，请问现在方便接听吗？"),
                ChatMessage(turn=2, role="user", content="我现在在开车，晚点联系。"),
                ChatMessage(turn=3, role="agent", content="好的，我给您安排稍后回访。"),
            ],
        ),
    ]
    summary = run_imported_evaluation("tasks/fengmaotui_delivery_task.json", traces, settings=settings)
    run_dir = tmp_path / summary.run_id
    assert summary.completed_dialogues == 2
    assert (run_dir / "dialogue_import_001_trace.json").exists()
    assert (run_dir / "dialogue_import_002_trace.json").exists()
    report_text = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "dialogue_import_001" in report_text
    assert "dialogue_import_002" in report_text


def test_imported_trace_batch_limit() -> None:
    payload = [
        {
            "dialogue_id": f"dialogue_{index:03d}",
            "transcript": [
                {"turn": 1, "role": "agent", "content": "您好"},
                {"turn": 2, "role": "user", "content": "好的"},
            ],
        }
        for index in range(101)
    ]
    with pytest.raises(HTTPException) as exc:
        _validate_imported_trace_payload(payload)
    assert exc.value.status_code == 400
    assert "up to 100 dialogues" in str(exc.value.detail)
