from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from dialogue_eval.schemas import FAQItem, FlowStep, TaskConstraints, TaskSpec


def load_task(path: str | Path) -> TaskSpec:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Task file not found: {source}")

    suffix = source.suffix.lower()
    if suffix == ".json":
        return TaskSpec.model_validate(json.loads(source.read_text(encoding="utf-8")))
    if suffix in {".xlsx", ".xls"}:
        return _load_excel(source)
    raise ValueError(f"Unsupported task file type: {suffix}")


def _load_excel(path: Path) -> TaskSpec:
    frame = pd.read_excel(path).fillna("")
    rows = _rows_to_mapping(frame)

    task_id = str(rows.get("task_id") or rows.get("Task ID") or path.stem)
    flow_text = str(rows.get("Call Flow") or rows.get("flow_steps") or "")
    faq_text = str(rows.get("Knowledge Points (FAQ)") or rows.get("FAQ") or "")
    constraints_text = str(rows.get("Constraints") or "")

    return TaskSpec(
        task_id=task_id,
        role=str(rows.get("Role") or "履约数字人"),
        task=str(rows.get("Task") or ""),
        opening_line=str(rows.get("Opening Line") or ""),
        flow_steps=_parse_flow_steps(flow_text),
        faq=_parse_faq(faq_text),
        constraints=_parse_constraints(constraints_text),
        tools=[
            "transfer_to_human",
            "query_faq",
            "record_rejection",
            "schedule_callback",
            "create_ticket",
            "update_task_status",
        ],
    )


def _rows_to_mapping(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.shape[1] >= 2 and set(frame.columns[:2]) != {"Role", "Task"}:
        return {
            str(row.iloc[0]).strip(): row.iloc[1]
            for _, row in frame.iterrows()
            if str(row.iloc[0]).strip()
        }
    return frame.iloc[0].to_dict() if not frame.empty else {}


def _parse_flow_steps(text: str) -> list[FlowStep]:
    parts = [part.strip(" -\t") for part in text.replace("\r", "\n").split("\n")]
    steps = [part for part in parts if part]
    if not steps:
        steps = ["确认用户身份", "说明任务信息", "确认用户意向"]
    return [
        FlowStep(step_id=f"step_{index:02d}", description=step)
        for index, step in enumerate(steps, start=1)
    ]


def _parse_faq(text: str) -> list[FAQItem]:
    items: list[FAQItem] = []
    for raw in text.replace("\r", "\n").split("\n"):
        line = raw.strip(" -\t")
        if not line:
            continue
        if "：" in line:
            question, answer = line.split("：", 1)
        elif ":" in line:
            question, answer = line.split(":", 1)
        else:
            question, answer = line, "请基于任务知识库回答。"
        items.append(FAQItem(question=question.strip(), answer=answer.strip()))
    return items


def _parse_constraints(text: str) -> TaskConstraints:
    forbidden_terms = []
    privacy_fields = ["身份证号", "手机号", "地址"]
    for token in ["保证收益", "一定返钱", "稳赚", "内部政策"]:
        if token in text:
            forbidden_terms.append(token)
    return TaskConstraints(
        max_reply_chars=40 if "40" in text or "简短" in text else 60,
        tone="电话口语、礼貌、简短",
        forbidden_terms=forbidden_terms or ["保证收益", "一定返钱"],
        privacy_fields=privacy_fields,
    )
