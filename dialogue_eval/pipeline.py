from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from statistics import mean
from uuid import uuid4

import httpx

from dialogue_eval.config import Settings, get_settings
from dialogue_eval.parser import load_task
from dialogue_eval.report import render_html_report, render_markdown_report
from dialogue_eval.report.markdown import build_report_identity
from dialogue_eval.runner.deepseek_dialogue_generator import DeepSeekDialogueGenerator, _align_tool_turn
from dialogue_eval.scenarios import generate_scenarios
from dialogue_eval.schemas import (
    DialogueTrace,
    EvalResult,
    ImportedDialogueTrace,
    ImportedScenarioSpec,
    RunSummary,
    ScenarioMatchResult,
    ScenarioSpec,
    ScoringConfig,
    UnscorableDialogue,
)
from dialogue_eval.scorer import ScorerSkill
from dialogue_eval.storage import RunStore
from dialogue_eval.storage.archive import archive_run
from dialogue_eval.scorer.speaker import should_flip_explicit_roles


def run_evaluation(
    task_path: str | Path,
    scenarios_count: int | None = None,
    model: str | None = None,
    settings: Settings | None = None,
    progress: Callable[[str, dict | None], None] | None = None,
) -> RunSummary:
    """执行模型生成对话评测。"""
    # Default flow: generate scenarios, simulate dialogues, score them, then
    # persist reports and archive metadata for the run.
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
                {"dialogue_id": dialogue_id, "index": index, "total": len(scenarios)},
            )
        trace = runner.run(run_id, dialogue_id, task, scenario, settings.max_turns)
        if progress:
            progress(
                "scoring_started",
                {"dialogue_id": dialogue_id, "index": index, "total": len(scenarios)},
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
        report_metadata={"data_source": "大模型生成模拟", "scenario_source": "自动生成场景"},
        progress=progress,
        total_dialogues=len(results),
        scored_dialogues=len(results),
        low_confidence_dialogues=[],
        match_error_dialogues=[],
    )


def run_imported_evaluation(
    task_path: str | Path,
    trace_input: ImportedDialogueTrace | list[ImportedDialogueTrace],
    settings: Settings | None = None,
    model_name: str | None = None,
    progress: Callable[[str, dict | None], None] | None = None,
) -> RunSummary:
    """执行导入对话评测。"""
    # Imported traces reuse the same scoring pipeline, but they first need to
    # be matched to a concrete scenario and rubric context.
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
    scored_traces: list[DialogueTrace] = []
    results: list[EvalResult] = []
    low_confidence_dialogues: list[UnscorableDialogue] = []
    match_error_dialogues: list[UnscorableDialogue] = []
    matches: list[ScenarioMatchResult] = []

    if progress:
        progress("scenario_generation_started", {"scenario_count": len(scenarios)})
        progress("scenario_generation_completed", {"scenario_count": len(scenarios)})

    store.write_json(run_id, "task.json", task)
    store.write_json(run_id, "scenarios.json", scenarios)

    for index, imported_trace in enumerate(traces_input, start=1):
        match = match_scenario_with_llm(imported_trace, task, scenarios, settings)
        matches.append(match)
        if match.status != "matched":
            # Keep unmatched traces in artifacts so operators can review them
            # manually instead of silently dropping them from the run.
            pending = UnscorableDialogue(
                dialogue_id=imported_trace.dialogue_id,
                status=match.status,
                suggested_scenario_id=match.scenario_id,
                confidence=match.confidence,
                reason=match.reason,
                error_type=match.error_type,
            )
            if match.status == "low_confidence":
                low_confidence_dialogues.append(pending)
            else:
                match_error_dialogues.append(pending)
            continue

        scenario = next(item for item in scenarios if item.scenario_id == match.scenario_id)
        trace = _normalize_imported_trace(run_id, task.task_id, imported_trace, scenario.scenario_id)
        if progress:
            progress(
                "scoring_started",
                {
                    "dialogue_id": trace.dialogue_id,
                    "index": index,
                    "total": len(traces_input),
                    "scenario_id": scenario.scenario_id,
                    "matched_confidence": match.confidence,
                },
            )
        result = scorer.score(task, scenario, trace, scoring_config)
        store.append_trace(run_id, trace)
        store.write_json(run_id, f"{trace.dialogue_id}_trace.json", trace)
        store.write_json(run_id, f"{trace.dialogue_id}_result.json", result)
        scored_traces.append(trace)
        results.append(result)

    store.write_json(run_id, "scenario_matches.json", matches)
    store.write_json(run_id, "low_confidence_dialogues.json", low_confidence_dialogues)
    store.write_json(run_id, "match_error_dialogues.json", match_error_dialogues)
    total_dialogues = len(traces_input)
    low_ratio = round(len(low_confidence_dialogues) / total_dialogues, 4) if total_dialogues else 0.0
    error_ratio = round(len(match_error_dialogues) / total_dialogues, 4) if total_dialogues else 0.0
    report_metadata = {
        "data_source": "上传对话数据",
        "scenario_source": "LLM 场景识别",
        "total_dialogues": str(total_dialogues),
        "scored_count": str(len(results)),
        "low_confidence_count": str(len(low_confidence_dialogues)),
        "low_confidence_ratio": f"{low_ratio:.2%}",
        "match_error_count": str(len(match_error_dialogues)),
        "match_error_ratio": f"{error_ratio:.2%}",
        "scenario_match_threshold": f"{settings.scenario_match_confidence_threshold:.2f}",
    }

    return _finalize_run(
        run_id=run_id,
        task=task,
        scenarios=scenarios,
        traces=scored_traces,
        results=results,
        settings=settings,
        model_name=model_name or "imported-trace",
        store=store,
        report_metadata=report_metadata,
        progress=progress,
        total_dialogues=total_dialogues,
        scored_dialogues=len(results),
        low_confidence_dialogues=low_confidence_dialogues,
        match_error_dialogues=match_error_dialogues,
    )




def run_choose_evaluation(
    task_path: str | Path,
    scenario_mode: str = "generate",
    dialogue_mode: str = "generate",
    scenario_input: list[ImportedScenarioSpec] | None = None,
    trace_input: ImportedDialogueTrace | list[ImportedDialogueTrace] | None = None,
    scenarios_count: int | None = None,
    model: str | None = None,
    settings: Settings | None = None,
    progress: Callable[[str, dict | None], None] | None = None,
) -> RunSummary:
    """2×2×2 统一评测入口。

    scenario_mode:
      - "generate": 从模板自动生成场景
      - "upload":   使用上传的场景数据
    dialogue_mode:
      - "generate": 用大模型逐次模拟对话
      - "import":   使用上传的对话数据
    """
    # The UI can mix generated/uploaded scenarios and dialogues, so this entry
    # point keeps those combinations behind one orchestration function.
    settings = settings or get_settings()
    task = load_task(task_path)
    scenario_count = scenarios_count or settings.scenario_count

    if progress:
        progress("scenario_generation_started", {"scenario_count": scenario_count})

    # --- 获取场景 ---
    if scenario_mode == "upload" and scenario_input:
        scenarios = [
            _imported_scenario_to_spec(s, task.task_id) for s in
            (scenario_input if isinstance(scenario_input, list) else [scenario_input])
        ]
    else:
        scenarios = generate_scenarios(task, scenario_count)
    if progress:
        progress("scenario_generation_completed", {"scenario_count": len(scenarios)})

    run_id = f"run_{uuid4().hex[:12]}"
    store = RunStore(settings.runs_dir)
    scorer = ScorerSkill()
    scoring_config = ScoringConfig(
        enable_llm_judge=settings.enable_llm_judge,
        max_turns=settings.max_turns,
    )
    store.write_json(run_id, "task.json", task)
    store.write_json(run_id, "scenarios.json", scenarios)

    results: list[EvalResult] = []
    scored_traces: list[DialogueTrace] = []
    low_confidence_dialogues: list[UnscorableDialogue] = []
    match_error_dialogues: list[UnscorableDialogue] = []
    total_dialogues = 0
    scored_dialogues = 0

    # --- 对话模式: generate (LLM 模拟) ---
    if dialogue_mode == "generate":
        runner = _build_runner(settings, model)
        for index, scenario in enumerate(scenarios, start=1):
            dialogue_id = f"dialogue_{index:03d}"
            if progress:
                progress("model_generation_started",
                         {"dialogue_id": dialogue_id, "index": index, "total": len(scenarios)})
            trace = runner.run(run_id, dialogue_id, task, scenario, settings.max_turns)
            if progress:
                progress("scoring_started",
                         {"dialogue_id": dialogue_id, "index": index, "total": len(scenarios)})
            result = scorer.score(task, scenario, trace, scoring_config)
            store.append_trace(run_id, trace)
            store.write_json(run_id, f"{dialogue_id}_trace.json", trace)
            store.write_json(run_id, f"{dialogue_id}_result.json", result)
            scored_traces.append(trace)
            results.append(result)
            if progress:
                progress("dialogue_completed",
                         {"dialogue_id": dialogue_id, "index": index, "total": len(scenarios),
                          "score": result.total_score})
        total_dialogues = len(scenarios)
        scored_dialogues = len(scored_traces)

    # --- 对话模式: import (使用已有对话数据) ---
    else:
        traces_input = trace_input if isinstance(trace_input, list) else [trace_input] if trace_input else []
        total_dialogues = len(traces_input)
        for index, imported_trace in enumerate(traces_input, start=1):
            match = match_scenario_with_llm(imported_trace, task, scenarios, settings)
            if match.status != "matched":
                pending = UnscorableDialogue(
                    dialogue_id=imported_trace.dialogue_id,
                    status=match.status,
                    suggested_scenario_id=match.scenario_id,
                    confidence=match.confidence,
                    reason=match.reason,
                    error_type=match.error_type,
                )
                if match.status == "low_confidence":
                    low_confidence_dialogues.append(pending)
                else:
                    match_error_dialogues.append(pending)
                continue
            scenario = next(item for item in scenarios if item.scenario_id == match.scenario_id)
            trace = _normalize_imported_trace(run_id, task.task_id, imported_trace, scenario.scenario_id)
            if progress:
                progress("scoring_started",
                         {"dialogue_id": trace.dialogue_id, "index": index, "total": len(traces_input)})
            result = scorer.score(task, scenario, trace, scoring_config)
            store.append_trace(run_id, trace)
            store.write_json(run_id, f"{trace.dialogue_id}_trace.json", trace)
            store.write_json(run_id, f"{trace.dialogue_id}_result.json", result)
            scored_traces.append(trace)
            results.append(result)
        scored_dialogues = len(scored_traces)

    store.write_json(run_id, "results.json", results)
    store.write_json(run_id, "low_confidence_dialogues.json", low_confidence_dialogues)
    store.write_json(run_id, "match_error_dialogues.json", match_error_dialogues)

    model_name = str(model or settings.model_name) if dialogue_mode == "generate" else "imported-trace"
    report_metadata = {
        "data_source": "大模型生成模拟" if dialogue_mode == "generate" else "上传对话数据",
        "scenario_source": "自动生成场景" if scenario_mode == "generate" else "上传场景文件",
        "total_dialogues": str(total_dialogues),
        "scored_count": str(scored_dialogues),
        "low_confidence_count": str(len(low_confidence_dialogues)),
        "match_error_count": str(len(match_error_dialogues)),
    }
    if dialogue_mode == "import":
        low_ratio = round(len(low_confidence_dialogues) / total_dialogues, 4) if total_dialogues else 0.0
        error_ratio = round(len(match_error_dialogues) / total_dialogues, 4) if total_dialogues else 0.0
        report_metadata.update({
            "low_confidence_ratio": f"{low_ratio:.2%}",
            "match_error_ratio": f"{error_ratio:.2%}",
            "scenario_match_threshold": f"{settings.scenario_match_confidence_threshold:.2f}",
        })

    return _finalize_run(
        run_id=run_id,
        task=task,
        scenarios=scenarios,
        traces=scored_traces,
        results=results,
        settings=settings,
        model_name=model_name,
        store=store,
        report_metadata=report_metadata,
        progress=progress,
        total_dialogues=total_dialogues,
        scored_dialogues=scored_dialogues,
        low_confidence_dialogues=low_confidence_dialogues,
        match_error_dialogues=match_error_dialogues,
    )


def _imported_scenario_to_spec(imported: ImportedScenarioSpec, task_id: str) -> ScenarioSpec:
    """将上传的场景数据转为标准的 ScenarioSpec。"""
    # Normalize uploaded scenarios once here so downstream code can assume the
    # internal ScenarioSpec shape regardless of source.
    return ScenarioSpec(
        scenario_id=imported.scenario_id,
        task_id=task_id,
        category=imported.category,
        subtype=imported.subtype,
        persona=imported.persona,
        customer_personality=imported.customer_personality,
        agent_personality=imported.agent_personality,
        situation=imported.situation,
        conversation_length=imported.conversation_length if imported.conversation_length in {"short", "medium", "long"} else "medium",
        initial_user_input=imported.initial_user_input,
        utterance_variants=imported.utterance_variants,
        exclusive_signals=imported.exclusive_signals,
        goals=imported.goals,
        expected_behaviors=imported.expected_behaviors,
        expected_tool_calls=imported.expected_tool_calls,
        expected_final_state=imported.expected_final_state,
        risk_points=imported.risk_points,
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
    total_dialogues: int,
    scored_dialogues: int,
    low_confidence_dialogues: list[UnscorableDialogue],
    match_error_dialogues: list[UnscorableDialogue],
) -> RunSummary:
    """收尾并生成报告。"""
    store.write_json(run_id, "results.json", results)
    # Centralizing report generation keeps every evaluation mode writing the
    # same artifact set and archive summary.
    if progress:
        progress("report_generation_started", {"run_id": run_id})
    report_title, report_file_stem = build_report_identity(task, settings.runs_dir)
    markdown = render_markdown_report(
        task,
        scenarios,
        results,
        run_id,
        report_title,
        traces,
        report_metadata,
        low_confidence_dialogues=low_confidence_dialogues,
        match_error_dialogues=match_error_dialogues,
    )
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
        completed_dialogues=scored_dialogues,
        total_score=round(mean([result.total_score for result in results]), 2) if results else 0.0,
        report_markdown_path=str(report_markdown_path),
        report_html_path=str(report_html_path),
        total_dialogues=total_dialogues,
        scored_dialogues=scored_dialogues,
        low_confidence_dialogues=len(low_confidence_dialogues),
        match_error_dialogues=len(match_error_dialogues),
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
    """标准化导入对话。"""
    transcript = sorted(trace_input.transcript, key=lambda message: message.turn)
    # Imported traces should look the same as generated traces before scoring,
    # otherwise scorers would need special-case logic.
    transcript = _normalize_transcript_roles(transcript)
    valid_turns = {message.turn for message in transcript}
    tool_calls = [
        call.model_copy(
            update={"turn": _align_tool_turn(call.tool_name, call.turn, transcript, valid_turns)}
        )
        for call in trace_input.tool_calls
    ]
    state_trace = trace_input.state_trace or _infer_state_trace_from_transcript(transcript)
    if state_trace:
        # Imported data often misses the terminal state. Defaulting it here
        # keeps report aggregation stable.
        final_status = state_trace[-1].get("task_status")
        state_trace[-1]["task_status"] = final_status or "completed"
    return DialogueTrace(
        run_id=run_id,
        dialogue_id=trace_input.dialogue_id,
        task_id=task_id,
        scenario_id=scenario_id,
        transcript=transcript,
        tool_calls=tool_calls,
        state_trace=state_trace,
    )


def _normalize_transcript_roles(transcript) -> list:
    # Some external exports flip agent and user labels. Normalize once before
    # any speaker heuristics or scoring rules consume the trace.
    probe = DialogueTrace(
        run_id="probe",
        dialogue_id="probe",
        task_id="probe",
        scenario_id="probe",
        transcript=transcript,
        tool_calls=[],
        state_trace=[],
    )
    if not should_flip_explicit_roles(probe):
        return transcript

    normalized = []
    for message in transcript:
        normalized.append(
            message.model_copy(
                update={
                    "role": "agent" if message.role == "user" else "user" if message.role == "agent" else message.role
                }
            )
        )
    return normalized


def match_scenario_with_llm(
    trace: ImportedDialogueTrace,
    task,
    scenarios: list[ScenarioSpec],
    settings: Settings,
) -> ScenarioMatchResult:
    """使用 LLM 为导入对话识别场景。"""
    # Imported traces only enter quantitative scoring after they are mapped to
    # a scenario with a concrete rubric context.
    api_key = settings.effective_scenario_match_api_key
    if not api_key:
        return ScenarioMatchResult(
            dialogue_id=trace.dialogue_id,
            status="match_error",
            reason="场景识别模型未配置 API Key",
            error_type="missing_api_key",
        )

    prompt = _build_scenario_match_prompt(task, trace, scenarios, settings.scenario_match_confidence_threshold)
    url = settings.scenario_match_model_base_url.rstrip("/") + "/chat/completions"
    try:
        with httpx.Client(timeout=45, trust_env=False) as client:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": settings.scenario_match_model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "max_tokens": 600
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
    except httpx.TimeoutException:
        return ScenarioMatchResult(
            dialogue_id=trace.dialogue_id,
            status="match_error",
            reason="场景识别请求超时",
            error_type="timeout",
        )
    except httpx.HTTPError as exc:
        return ScenarioMatchResult(
            dialogue_id=trace.dialogue_id,
            status="match_error",
            reason=f"场景识别请求失败: {exc}",
            error_type="http_error",
        )
    except Exception as exc:
        return ScenarioMatchResult(
            dialogue_id=trace.dialogue_id,
            status="match_error",
            reason=f"场景识别发生异常: {exc}",
            error_type="runtime_error",
        )

    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return ScenarioMatchResult(
            dialogue_id=trace.dialogue_id,
            status="match_error",
            reason="场景识别模型返回了非 JSON 内容",
            error_type="non_json_response",
        )

    scenario_id = payload.get("scenario_id")
    reason = str(payload.get("reason") or "").strip()
    confidence_raw = payload.get("confidence")
    if not scenario_id or confidence_raw is None:
        return ScenarioMatchResult(
            dialogue_id=trace.dialogue_id,
            status="match_error",
            reason="场景识别模型返回缺少必要字段",
            error_type="missing_fields",
        )
    if scenario_id not in {scenario.scenario_id for scenario in scenarios}:
        return ScenarioMatchResult(
            dialogue_id=trace.dialogue_id,
            status="match_error",
            scenario_id=str(scenario_id),
            reason="场景识别模型返回了候选列表之外的场景",
            error_type="invalid_scenario_id",
        )
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        return ScenarioMatchResult(
            dialogue_id=trace.dialogue_id,
            status="match_error",
            scenario_id=str(scenario_id),
            reason="场景识别模型返回了非法置信度",
            error_type="invalid_confidence",
        )

    if confidence >= settings.scenario_match_confidence_threshold:
        return ScenarioMatchResult(
            dialogue_id=trace.dialogue_id,
            scenario_id=str(scenario_id),
            confidence=confidence,
            reason=reason or "场景识别成功",
            status="matched",
        )
    return ScenarioMatchResult(
        dialogue_id=trace.dialogue_id,
        scenario_id=str(scenario_id),
        confidence=confidence,
        reason=reason or "置信度不足，未进入量化评分",
        status="low_confidence",
    )


def _build_scenario_match_prompt(
    task,
    trace: ImportedDialogueTrace,
    scenarios: list[ScenarioSpec],
    threshold: float,
) -> str:
    """构造场景识别提示词。"""
    # The model output is parsed directly, so the prompt constrains the format
    # to JSON instead of relying on brittle text extraction.
    transcript = "\n".join(f"{message.role}: {message.content}" for message in trace.transcript)
    scenario_lines = []
    for scenario in scenarios:
        expected_tools = ", ".join(call.tool_name for call in scenario.expected_tool_calls) or "无"
        variants = "；".join(scenario.utterance_variants or [scenario.initial_user_input])
        scenario_lines.append(
            "\n".join(
                [
                    f"- 场景ID: {scenario.scenario_id}",
                    f"  分类: {scenario.category or '未分类'} / {scenario.subtype or '默认'}",
                    f"  说明: {scenario.persona}",
                    f"  常见表达: {variants}",
                    f"  目标: {'；'.join(scenario.goals) or '无'}",
                    f"  预期工具: {expected_tools}",
                    f"  预期状态: {scenario.expected_final_state}",
                    f"  风险点: {'；'.join(scenario.risk_points) or '无'}",
                ]
            )
        )
    return f"""
你是对话评测系统的场景识别节点。你的任务是从候选场景中，为一段真实导入对话选择最匹配的一个场景。

要求：
1. 只能从候选场景中选择一个 scenario_id。
2. 如果你不够确定，也必须返回你认为最接近的场景，但 confidence 要真实反映把握程度。
3. 不要评分，不要输出 Markdown。
4. 只返回 JSON 对象，格式严格为：
{{"scenario_id":"...", "confidence":0.0, "reason":"..."}}
5. confidence 取值范围 0 到 1。
6. 若你判断该对话过于复杂、混合或歧义较大，也不要编造高分置信度。
7. 系统会用 {threshold:.2f} 作为进入量化评分的阈值。

任务信息：
- task_id: {task.task_id}
- role: {task.role}
- task: {task.task}

候选场景：
{chr(10).join(scenario_lines)}

对话内容：
{transcript}
""".strip()


def _infer_state_trace_from_transcript(transcript) -> list[dict]:
    """从对话内容推断状态轨迹。"""
    state_trace: list[dict] = []
    current_status = "opened"
    identity_confirmed = False

    for message in transcript:
        content = message.content

        if message.role == "user" and any(token in content for token in ["不是本人", "找错人"]):
            current_status = "identity_mismatch"
        elif any(token in content for token in ["转人工", "人工客服"]):
            current_status = "transferred"
        elif any(token in content for token in ["稍后回访", "晚点联系", "开车", "稍后再打"]):
            current_status = "callback_scheduled"
        elif any(token in content for token in ["不跑了", "别安排我", "拒绝", "不想"]):
            current_status = "rejected"
        elif any(token in content for token in ["怎么退出", "低延迟", "更贵", "区别"]):
            current_status = "faq_answered"
        elif message.role == "agent":
            identity_confirmed = True
            if current_status == "opened":
                current_status = "in_progress"

        state_trace.append(
            {
                "turn": message.turn,
                "task_status": current_status,
                "identity_confirmed": identity_confirmed,
            }
        )

    return state_trace


def _build_runner(settings: Settings, model: str | None) -> object:
    """构建对话运行器。"""
    return DeepSeekDialogueGenerator(settings)


def _archive_model_name(settings: Settings, model: str | None) -> str:
    """返回归档模型名。"""
    return str(model or settings.model_name)
