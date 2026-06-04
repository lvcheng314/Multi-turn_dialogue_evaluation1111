from pathlib import Path

from dialogue_eval.parser import load_task
from dialogue_eval.report.html import render_html_report
from dialogue_eval.report.markdown import build_report_identity, render_markdown_report
from dialogue_eval.schemas import DialogueTrace, EvalResult, Evidence, ScenarioSpec


def test_report_markdown_uses_chinese_title_explanations_and_table() -> None:
    """验证 Markdown 报告结构。"""
    task = load_task("tasks/fengmaotui_delivery_task.json")
    scenario = ScenarioSpec(
        scenario_id="scenario_001",
        task_id=task.task_id,
        category="正常推进",
        subtype="配合确认",
        persona="愿意配合的骑手",
        initial_user_input="好的，你说。",
        goals=["确认合同生效"],
    )
    trace = DialogueTrace(
        run_id="run_abc123ef",
        dialogue_id="dialogue_001",
        task_id=task.task_id,
        scenario_id=scenario.scenario_id,
        transcript=[],
        tool_calls=[],
        state_trace=[],
    )
    result = EvalResult(
        run_id="run_abc123ef",
        dialogue_id="dialogue_001",
        total_score=56.0,
        dimension_scores={"outcome": 14.0, "trace": 21.0, "safety": 1.0, "text": 20.0},
        evidence=[Evidence(type="rule", dimension="safety", comment="出现高风险话术", score_delta=-19)],
        final_decision="review",
    )

    report_title = "飞毛腿外呼测评报告2026/06/02/0001"
    markdown = render_markdown_report(task, [scenario], [result], "run_abc123ef", report_title, [trace])

    assert f"# {report_title}" in markdown
    assert "## 维度说明" in markdown
    assert "平均分: 56.00 / 100" in markdown
    assert "任务结果 Outcome（平均 14.00 / 30 分）" in markdown
    assert "安全合规 Safety（平均 1.00 / 20 分）" in markdown
    assert "| 对话ID | 总分 | 结论 | 任务结果 Outcome | 工具轨迹 Trace | 安全合规 Safety | 话术质量 Text |" in markdown
    assert "| dialogue_001 | 56.00 / 100 | 复核 | 14.00 / 30 | 21.00 / 30 | 1.00 / 20 | 20.00 / 20 |" in markdown
    assert "任务结果 Outcome（14.00 / 30 分）" in markdown
    assert "安全合规 Safety（1.00 / 20 分）" in markdown


def test_report_html_wraps_ordered_list_items_in_single_ol() -> None:
    """验证 HTML 有序列表渲染。"""
    html = render_html_report(
        "\n".join(
            [
                "# 标题",
                "",
                "1. 第一项",
                "2. 第二项",
                "3. 第三项",
            ]
        )
    )

    assert html.count("<ol>") == 1
    assert html.count("<li>") == 3
    assert "第一项" in html
    assert "第二项" in html
    assert "第三项" in html


def test_build_report_identity_starts_with_0001_in_empty_runs_dir(tmp_path: Path) -> None:
    """验证空目录下报告流水号从 0001 开始。"""
    task = load_task("tasks/fengmaotui_delivery_task.json")
    title, filename = build_report_identity(task, tmp_path)

    assert title.endswith("/0001")
    assert filename.endswith("-0001")
