from __future__ import annotations

import json

from dialogue_eval.config import Settings
from dialogue_eval.mcp_gateway.tool_specs import default_tool_specs
from dialogue_eval.models.openai_compatible import OpenAICompatibleAgent
from dialogue_eval.schemas import ChatMessage, DialogueTrace, ScenarioSpec, TaskSpec, ToolCallTrace


class DeepSeekDialogueGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(
        self,
        run_id: str,
        dialogue_id: str,
        task: TaskSpec,
        scenario: ScenarioSpec,
        max_turns: int = 20,
    ) -> DialogueTrace:
        prompt = self._build_prompt(task, scenario, max_turns)
        content = OpenAICompatibleAgent._chat_with_options(
            base_url=self.settings.model_base_url,
            api_key=self.settings.effective_model_api_key,
            model=self.settings.model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是多轮电话对话数据生成器。必须同时扮演用户和数字人，"
                        "生成符合真实电话沟通逻辑的完整对话。只返回 JSON。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=3000,
        )
        payload = _parse_json_object(content)
        transcript = [
            ChatMessage(turn=index, role=item["role"], content=item["content"])
            for index, item in enumerate(payload.get("transcript", []), start=1)
            if item.get("role") in {"user", "agent"} and item.get("content")
        ]
        if not transcript:
            raise RuntimeError(f"DeepSeek returned empty transcript: {content}")

        final_status = scenario.expected_final_state.get("task_status", payload.get("final_status", "completed"))
        tool_calls = _parse_tool_calls(payload.get("tool_calls", []), transcript)
        state_trace = _parse_state_trace(payload.get("state_trace", []), transcript)
        if state_trace:
            state_trace[-1]["task_status"] = final_status
        else:
            state_trace = [
                {"turn": message.turn, "task_status": "in_progress", "identity_confirmed": message.turn > 1}
                for message in transcript
            ]
            if state_trace:
                state_trace[-1]["task_status"] = final_status

        return DialogueTrace(
            run_id=run_id,
            dialogue_id=dialogue_id,
            task_id=task.task_id,
            scenario_id=scenario.scenario_id,
            transcript=transcript,
            tool_calls=tool_calls,
            state_trace=state_trace,
        )

    @staticmethod
    def _build_prompt(task: TaskSpec, scenario: ScenarioSpec, max_turns: int) -> str:
        flow = "\n".join(f"- {step.description}" for step in task.flow_steps)
        faq = "\n".join(f"- 问: {item.question}\n  答: {item.answer}" for item in task.faq)
        tools = "\n".join(
            "- {name}: {desc}; required={required}; allowed_reasons={reasons}; success_state={state}".format(
                name=tool.tool_name,
                desc=tool.description,
                required=tool.required_arguments,
                reasons=tool.allowed_reasons,
                state=tool.success_state,
            )
            for tool in default_tool_specs()
            if tool.tool_name in task.tools
        )
        expected_tools = ", ".join(call.tool_name for call in scenario.expected_tool_calls) or "无"
        length_hint = {
            "short": "6-8 个 turn，用户很快打断、忙碌、拒绝或结束。",
            "medium": "10-14 个 turn，有自然问答、追问和确认。",
            "long": "16-22 个 turn，充分解释问题、处理异议、确认理解后结束。",
        }[scenario.conversation_length]
        return f"""
请根据下面任务和场景，生成一段完整电话对话。

任务角色: {task.role}
任务目标: {task.task}
开场白: {task.opening_line}
流程要求:
{flow}

FAQ:
{faq}

可用工具:
{tools}

约束:
- 数字人语气: {task.constraints.tone}
- 数字人每次回复尽量短，但不能为了短而不说明白
- 禁止词: {", ".join(task.constraints.forbidden_terms)}
- 隐私字段: {", ".join(task.constraints.privacy_fields)}

场景:
- 场景 ID: {scenario.scenario_id}
- 场景说明: {scenario.persona}
- 客户性格: {scenario.customer_personality}
- 数字人风格: {scenario.agent_personality}
- 通话情境: {scenario.situation}
- 对话长度: {length_hint}
- 测试目标: {"；".join(scenario.goals)}
- 期望行为: {"；".join(scenario.expected_behaviors)}
- 期望工具: {expected_tools}
- 风险点: {"；".join(scenario.risk_points)}

生成要求:
1. 用户必须像真实接电话的人，第二句通常是“是的，有什么事？”、“嗯，请讲”等，不能提前知道任务细节。
2. 用户会根据数字人的说明自然追问、打断、拒绝、确认或结束。
3. 数字人要按任务逐步说明，不要串到其他任务。
4. 对话长短要符合场景，最多 {max_turns} 个 turn。
5. 如果场景需要转人工、回访、记录拒绝、查询 FAQ 或更新状态，数字人口头上要自然体现，并在 tool_calls 中虚拟返回一次调用。
6. 每个 turn 都要在 state_trace 中返回状态快照；状态必须跟对话进展一致。
7. 只返回 JSON，不要 Markdown。

JSON 格式:
{{
  "final_status": "completed",
  "transcript": [
    {{"role": "agent", "content": "数字人第一句"}},
    {{"role": "user", "content": "用户回复"}}
  ],
  "tool_calls": [
    {{
      "turn": 6,
      "tool_name": "schedule_callback",
      "arguments": {{"user_id": "user_001", "task_id": "{task.task_id}", "preferred_time": "later_today"}},
      "result": {{"status": "scheduled", "callback_id": "virtual_callback_001"}},
      "latency_ms": 80,
      "error_code": null
    }}
  ],
  "state_trace": [
    {{"turn": 1, "task_status": "opened", "identity_confirmed": false}},
    {{"turn": 2, "task_status": "in_progress", "identity_confirmed": true}}
  ]
}}
""".strip()


def _parse_json_object(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end >= start:
        text = text[start : end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"DeepSeek returned invalid JSON: {text[:1000]}") from exc


def _parse_tool_calls(raw_calls: list, transcript: list[ChatMessage]) -> list[ToolCallTrace]:
    valid_turns = {message.turn for message in transcript}
    calls: list[ToolCallTrace] = []
    for raw in raw_calls or []:
        try:
            turn = int(raw.get("turn", 1))
            if turn not in valid_turns:
                turn = _nearest_agent_turn(transcript)
            calls.append(
                ToolCallTrace(
                    turn=turn,
                    tool_name=str(raw.get("tool_name", "")),
                    arguments=dict(raw.get("arguments") or {}),
                    result=dict(raw.get("result") or {}),
                    latency_ms=int(raw.get("latency_ms") or 0),
                    error_code=raw.get("error_code"),
                )
            )
        except (TypeError, ValueError):
            continue
    return [call for call in calls if call.tool_name]


def _parse_state_trace(raw_states: list, transcript: list[ChatMessage]) -> list[dict]:
    valid_turns = {message.turn for message in transcript}
    states: list[dict] = []
    for raw in raw_states or []:
        if not isinstance(raw, dict):
            continue
        try:
            turn = int(raw.get("turn"))
        except (TypeError, ValueError):
            continue
        if turn in valid_turns:
            state = dict(raw)
            state["turn"] = turn
            states.append(state)
    seen = {state["turn"] for state in states}
    for message in transcript:
        if message.turn not in seen:
            states.append(
                {
                    "turn": message.turn,
                    "task_status": "in_progress",
                    "identity_confirmed": message.turn > 1,
                }
            )
    return sorted(states, key=lambda item: item["turn"])


def _nearest_agent_turn(transcript: list[ChatMessage]) -> int:
    for message in reversed(transcript):
        if message.role == "agent":
            return message.turn
    return transcript[-1].turn if transcript else 1
