from pathlib import Path

import pytest
from fastapi import HTTPException

from dialogue_eval.api.routes import _validate_imported_trace_payload
from dialogue_eval.config import Settings
from dialogue_eval.models.openai_compatible import OpenAICompatibleAgent
from dialogue_eval.pipeline import ScenarioMatchResult, run_evaluation, run_imported_evaluation
from dialogue_eval.schemas import ChatMessage, ImportedDialogueTrace


def test_e2e_demo_smoke(tmp_path: Path) -> None:
    """验证生成分支端到端流程。"""

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
    summary = run_evaluation("database/tasks/飞毛腿任务.json", model="deepseek", settings=settings)
    run_dir = tmp_path / summary.run_id
    assert summary.completed_dialogues == 15
    assert summary.scored_dialogues == 15
    assert (run_dir / "trace.jsonl").exists()
    assert (run_dir / "report.md").exists()
    assert summary.report_markdown_path.endswith("-0001.md")
    assert summary.report_html_path.endswith("-0001.html")
    assert (tmp_path / "eval_archive.sqlite3").exists()
    report_text = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "dialogue_001" in report_text
    assert "## 评测摘要" in report_text


def test_imported_trace_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """验证导入分支高置信度场景可正常评分。"""
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

    def fake_match(trace, task, scenarios, settings):  # noqa: ANN001
        del task, settings
        return ScenarioMatchResult(
            dialogue_id=trace.dialogue_id,
            scenario_id=scenarios[0].scenario_id,
            confidence=0.92,
            reason="明显是正常推进场景",
            status="matched",
        )

    monkeypatch.setattr("dialogue_eval.pipeline.match_scenario_with_llm", fake_match)
    trace = ImportedDialogueTrace(
        dialogue_id="dialogue_import_001",
        transcript=[
            ChatMessage(turn=1, role="agent", content="您好，今天合同已生效。"),
            ChatMessage(turn=2, role="user", content="好的，我知道了。"),
            ChatMessage(turn=3, role="agent", content="请按要求完成配送任务。"),
        ],
    )
    summary = run_imported_evaluation("database/tasks/飞毛腿任务.json", trace, settings=settings)
    run_dir = tmp_path / summary.run_id
    assert summary.completed_dialogues == 1
    assert summary.scored_dialogues == 1
    assert summary.low_confidence_dialogues == 0
    assert summary.match_error_dialogues == 0
    assert (run_dir / "trace.jsonl").exists()
    report_text = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "dialogue_import_001" in report_text
    assert "复杂场景 / 低置信度对话" in report_text


def test_imported_trace_low_confidence_not_scored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """验证低置信度样本不进入评分。"""
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

    def fake_match(trace, task, scenarios, settings):  # noqa: ANN001
        del task, settings
        return ScenarioMatchResult(
            dialogue_id=trace.dialogue_id,
            scenario_id=scenarios[-1].scenario_id,
            confidence=0.52,
            reason="意图混合，置信度不足",
            status="low_confidence",
        )

    monkeypatch.setattr("dialogue_eval.pipeline.match_scenario_with_llm", fake_match)
    trace = ImportedDialogueTrace(
        dialogue_id="dialogue_low_001",
        transcript=[
            ChatMessage(turn=1, role="user", content="你先别说，我有好几个问题。"),
            ChatMessage(turn=2, role="agent", content="您可以先说最关心的问题。"),
        ],
    )
    summary = run_imported_evaluation("database/tasks/飞毛腿任务.json", trace, settings=settings)
    run_dir = tmp_path / summary.run_id
    report_text = (run_dir / "report.md").read_text(encoding="utf-8")
    assert summary.completed_dialogues == 0
    assert summary.scored_dialogues == 0
    assert summary.low_confidence_dialogues == 1
    assert summary.match_error_dialogues == 0
    assert "dialogue_low_001" in report_text
    assert "未纳入量化评分，建议人工复核" in report_text


def test_imported_trace_match_error_not_scored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """验证场景识别异常单列展示。"""
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

    def fake_match(trace, task, scenarios, settings):  # noqa: ANN001
        del task, scenarios, settings
        return ScenarioMatchResult(
            dialogue_id=trace.dialogue_id,
            status="match_error",
            reason="场景识别模型返回了非法 JSON",
            error_type="non_json_response",
        )

    monkeypatch.setattr("dialogue_eval.pipeline.match_scenario_with_llm", fake_match)
    trace = ImportedDialogueTrace(
        dialogue_id="dialogue_error_001",
        transcript=[
            ChatMessage(turn=1, role="user", content="我想问几个问题。"),
            ChatMessage(turn=2, role="agent", content="您可以先说第一个问题。"),
        ],
    )
    summary = run_imported_evaluation("database/tasks/飞毛腿任务.json", trace, settings=settings)
    run_dir = tmp_path / summary.run_id
    report_text = (run_dir / "report.md").read_text(encoding="utf-8")
    assert summary.completed_dialogues == 0
    assert summary.scored_dialogues == 0
    assert summary.low_confidence_dialogues == 0
    assert summary.match_error_dialogues == 1
    assert "场景识别异常" in report_text
    assert "non_json_response" in report_text


def test_imported_trace_batch_limit() -> None:
    """验证导入批量上限。"""
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
