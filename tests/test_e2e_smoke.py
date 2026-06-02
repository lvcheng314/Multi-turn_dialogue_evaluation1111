from pathlib import Path

from dialogue_eval.config import Settings
from dialogue_eval.models.openai_compatible import OpenAICompatibleAgent
from dialogue_eval.pipeline import run_evaluation


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
    summary = run_evaluation("examples/tasks/fengmaotui_delivery_task.json", model="deepseek", settings=settings)
    run_dir = tmp_path / summary.run_id
    assert summary.completed_dialogues == 15
    assert (run_dir / "trace.jsonl").exists()
    assert (run_dir / "report.md").exists()
    assert (tmp_path / "eval_archive.sqlite3").exists()
    assert "多轮对话评测报告" in (run_dir / "report.md").read_text(encoding="utf-8")
