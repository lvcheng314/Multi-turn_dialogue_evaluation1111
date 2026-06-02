import json
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from dialogue_eval.config import get_settings
from dialogue_eval.models.openai_compatible import OpenAICompatibleAgent
from dialogue_eval.parser import load_task
from dialogue_eval.pipeline import run_evaluation
from dialogue_eval.report import render_html_report, render_markdown_report
from dialogue_eval.report.analysis import analyze_run, stream_analyze_run
from dialogue_eval.scenarios import generate_scenarios
from dialogue_eval.schemas import DialogueTrace, EvalResult, ScenarioSpec, TaskSpec
from dialogue_eval.storage.archive import list_groups, list_runs
from dialogue_eval.task_sources import TASK_SOURCES, resolve_task_path

router = APIRouter()


def _sse(event: str, data: dict | str) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app_env": get_settings().app_env}


@router.get("/task-sources")
def task_sources() -> dict:
    return {
        "task_sources": [
            {"id": key, "name": value["name"], "path": value["path"]}
            for key, value in TASK_SOURCES.items()
        ]
    }


@router.post("/tasks")
def create_task(payload: dict) -> dict:
    source_type = payload.get("source_type", "json")
    if source_type != "json":
        raise HTTPException(status_code=400, detail="MVP API only supports source_type=json")
    task = TaskSpec.model_validate(payload.get("task_spec", {}))
    scenarios = generate_scenarios(task, get_settings().scenario_count)
    return {"task_id": task.task_id, "scenario_count": len(scenarios)}


@router.post("/tasks/{task_id}/scenarios")
def create_scenarios(task_id: str, payload: dict) -> dict:
    try:
        task = load_task(resolve_task_path(task_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    scenarios = generate_scenarios(task, int(payload.get("count", get_settings().scenario_count)))
    return {"task_id": task.task_id, "scenarios": [item.model_dump(mode="json") for item in scenarios]}


@router.post("/eval-runs")
def create_eval_run(payload: dict) -> dict:
    task_path = _resolve_payload_task(payload)
    scenario_count = int(payload.get("scenarios") or get_settings().scenario_count)
    model = payload.get("model") or get_settings().model_provider
    summary = run_evaluation(task_path, scenarios_count=scenario_count, model=model)
    return summary.model_dump(mode="json")


@router.post("/eval-runs/stream")
def create_eval_run_stream(payload: dict):
    def events():
        queue: Queue[str | None] = Queue()

        def put(event: str, data: dict | str) -> None:
            queue.put(_sse(event, data))

        def worker() -> None:
            try:
                task_path = _resolve_payload_task(payload)
                scenario_count = int(payload.get("scenarios") or get_settings().scenario_count)
                model = payload.get("model") or get_settings().model_provider

                put("stage", {"stage": "scenario_generation_started", "message": "正在生成测试场景..."})

                def progress(stage: str, data: dict | None = None) -> None:
                    messages = {
                        "scenario_generation_completed": "测试场景已生成，准备执行对话...",
                        "model_generation_started": "正在生成完整对话...",
                        "scoring_started": "正在评分...",
                        "report_generation_started": "正在生成评测报告...",
                    }
                    if stage in messages:
                        put("stage", {"stage": stage, "message": messages[stage], **(data or {})})

                summary = run_evaluation(task_path, scenarios_count=scenario_count, model=model, progress=progress)
                put("complete", summary.model_dump(mode="json"))
            except Exception as exc:
                put("error", {"message": str(exc)})
            finally:
                queue.put(None)

        Thread(target=worker, daemon=True).start()
        while True:
            try:
                item = queue.get(timeout=15)
            except Empty:
                yield _sse("ping", {})
                continue
            if item is None:
                break
            yield item

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/archives/runs")
def archive_runs() -> dict:
    return {"runs": list_runs(get_settings().archive_db_path)}


@router.get("/archives/groups")
def archive_groups() -> dict:
    return {"groups": list_groups(get_settings().archive_db_path)}


@router.get("/eval-runs/{run_id}")
def get_eval_run(run_id: str) -> dict:
    run_dir = Path(get_settings().runs_dir) / run_id
    results_path = run_dir / "results.json"
    if not results_path.exists():
        raise HTTPException(status_code=404, detail="run_id not found")
    results = json.loads(results_path.read_text(encoding="utf-8"))
    return {
        "run_id": run_id,
        "status": "completed",
        "completed_dialogues": len(results),
        "total_dialogues": len(results),
    }


@router.get("/eval-runs/{run_id}/report")
def get_report(run_id: str) -> dict:
    run_dir = Path(get_settings().runs_dir) / run_id
    report_meta_path = run_dir / "report_meta.json"
    report_path = run_dir / "report.md"
    if not report_path.exists() and not (run_dir / "results.json").exists():
        raise HTTPException(status_code=404, detail="report not found")

    task_path = run_dir / "task.json"
    scenarios_path = run_dir / "scenarios.json"
    results_path = run_dir / "results.json"
    trace_path = run_dir / "trace.jsonl"
    report_meta = {}
    if report_meta_path.exists():
        report_meta = json.loads(report_meta_path.read_text(encoding="utf-8"))
    named_markdown_path = run_dir / str(report_meta.get("report_markdown_name") or "report.md")
    named_html_path = run_dir / str(report_meta.get("report_html_name") or "report.html")
    if task_path.exists() and scenarios_path.exists() and results_path.exists() and trace_path.exists():
        task = TaskSpec.model_validate(json.loads(task_path.read_text(encoding="utf-8")))
        scenarios = [
            ScenarioSpec.model_validate(item)
            for item in json.loads(scenarios_path.read_text(encoding="utf-8"))
        ]
        results = [
            EvalResult.model_validate(item)
            for item in json.loads(results_path.read_text(encoding="utf-8"))
        ]
        traces = [
            DialogueTrace.model_validate(json.loads(line))
            for line in trace_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        report_title = str(report_meta.get("report_title") or report_path.stem)
        markdown = render_markdown_report(task, scenarios, results, run_id, report_title, traces)
        html = render_html_report(markdown)
        report_path.write_text(markdown, encoding="utf-8")
        (run_dir / "report.html").write_text(html, encoding="utf-8")
        named_markdown_path.write_text(markdown, encoding="utf-8")
        named_html_path.write_text(html, encoding="utf-8")
        avg = sum(item.total_score for item in results) / len(results) if results else 0
    else:
        raw_results = json.loads(results_path.read_text(encoding="utf-8"))
        avg = sum(item["total_score"] for item in raw_results) / len(raw_results) if raw_results else 0
        markdown = named_markdown_path.read_text(encoding="utf-8") if named_markdown_path.exists() else report_path.read_text(encoding="utf-8")
        html = named_html_path.read_text(encoding="utf-8") if named_html_path.exists() else (run_dir / "report.html").read_text(encoding="utf-8")
    return {
        "run_id": run_id,
        "total_score": round(avg, 2),
        "report_markdown": markdown,
        "report_html": html,
        "report_html_path": str(named_html_path if named_html_path.exists() else (run_dir / "report.html")),
    }


@router.get("/eval-runs/{run_id}/report.html")
def get_report_html(run_id: str):
    from fastapi.responses import HTMLResponse

    report = get_report(run_id)
    return HTMLResponse(report["report_html"])


@router.post("/eval-runs/{run_id}/analyze")
def analyze_report(run_id: str, payload: dict) -> dict:
    run_dir = Path(get_settings().runs_dir) / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="run_id not found")
    question = str(payload.get("question") or "分析低分原因")
    try:
        answer = analyze_run(run_dir, question, get_settings().archive_db_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"run_id": run_id, "answer": answer}


@router.post("/eval-runs/{run_id}/analyze/stream")
def analyze_report_stream(run_id: str, payload: dict):
    def events():
        run_dir = Path(get_settings().runs_dir) / run_id
        if not run_dir.exists():
            yield _sse("error", {"message": "run_id not found"})
            return
        question = str(payload.get("question") or "分析低分原因")
        try:
            yield _sse("stage", {"stage": "analysis_started", "message": "正在分析评测报告..."})
            for chunk in stream_analyze_run(run_dir, question, get_settings().archive_db_path):
                yield _sse("delta", chunk)
            yield _sse("complete", {"run_id": run_id})
        except Exception as exc:
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/assistant/stream")
def assistant_stream(payload: dict):
    def events():
        settings = get_settings()
        try:
            messages = payload.get("messages") or []
            active_run_id = str(payload.get("active_run_id") or "").strip()
            system_prompt = _assistant_system_prompt(active_run_id)
            yield _sse("stage", {"stage": "assistant_started", "message": "正在调用报告助手..."})
            for chunk in OpenAICompatibleAgent.stream_chat_with_options(
                base_url=settings.model_base_url,
                api_key=settings.effective_model_api_key,
                model=settings.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    *_normalize_assistant_messages(messages),
                ],
                temperature=0.3,
                max_tokens=1200,
            ):
                yield _sse("delta", chunk)
            yield _sse("complete", {"status": "completed"})
        except Exception as exc:
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream")


def _resolve_payload_task(payload: dict) -> Path:
    custom_text = str(payload.get("custom_task") or "").strip()
    if custom_text:
        return _write_custom_task(custom_text)
    task_id = payload.get("task_id") or payload.get("task_source_id") or "fengmaotui_delivery_task"
    try:
        return resolve_task_path(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _normalize_assistant_messages(messages: list[dict]) -> list[dict]:
    normalized = []
    for item in messages[-12:]:
        role = item.get("role")
        if role == "bot":
            role = "assistant"
        elif role != "user":
            continue
        content = str(item.get("content") or item.get("text") or "").strip()
        if content:
            normalized.append({"role": role, "content": content[:3000]})
    return normalized


def _assistant_system_prompt(active_run_id: str) -> str:
    task_list = "\n".join(f"- {key}: {value['name']}" for key, value in TASK_SOURCES.items())
    base = (
        "你是 Dialogue Eval Bot 的报告助手，服务对象是正在做多轮外呼任务评测的用户。\n"
        "你可以帮助用户理解任务源、评测流程、报告、低分原因和任务指令优化建议。\n"
        "前端已有任务按钮负责启动评测；如果用户想开始评测，提示他选择任务按钮或提供自定义任务。\n"
        "不要声称自己已经点击按钮、启动任务或访问不存在的数据。回答要简洁、直接、可执行。\n"
        f"当前可选任务源:\n{task_list}\n"
    )
    if not active_run_id:
        return base + "当前还没有活跃评测报告。"

    run_dir = Path(get_settings().runs_dir) / active_run_id
    report_path = run_dir / "report.md"
    if not report_path.exists():
        return base + f"当前活跃 run_id 是 {active_run_id}，但报告文件暂不可读。"
    report = report_path.read_text(encoding="utf-8")[:12000]
    return (
        base
        + f"当前活跃 run_id 是 {active_run_id}。以下是当前报告摘要，回答报告相关问题时必须基于它:\n\n{report}"
    )


def _write_custom_task(text: str) -> Path:
    task_id = f"custom_{uuid4().hex[:8]}"
    path = Path("runs") / "custom_tasks" / f"{task_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    task = {
        "task_id": task_id,
        "role": "外呼数字人",
        "task": text,
        "opening_line": "您好，这边有一项通知需要和您确认，请问现在方便吗？",
        "flow_steps": [
            {"step_id": "confirm_identity", "description": "先确认接听人身份和是否方便沟通。", "required": True},
            {"step_id": "explain_task", "description": "清晰说明本次外呼任务内容。", "required": True},
            {"step_id": "handle_questions", "description": "根据用户问题进行解释和澄清。", "required": True},
            {"step_id": "confirm_result", "description": "确认用户理解或记录后续动作。", "required": True},
            {"step_id": "polite_close", "description": "礼貌结束通话。", "required": True},
        ],
        "faq": [],
        "constraints": {
            "max_reply_chars": 45,
            "tone": "电话口语、自然、礼貌、说明清楚",
            "forbidden_terms": ["保证收益", "一定返钱", "优惠到", "折扣到", "内部政策"],
            "privacy_fields": ["身份证号", "手机号", "地址"],
        },
        "tools": [
            "transfer_to_human",
            "query_faq",
            "record_rejection",
            "schedule_callback",
            "create_ticket",
            "update_task_status",
        ],
    }
    path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
