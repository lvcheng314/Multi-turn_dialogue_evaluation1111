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

        # MCP 工具列表（供系统调用，如转人工、查FAQ等）
        mcp_tools = "\n".join(
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

                # Build prompt
        lines = []
        lines.append("请根据下面任务和场景，生成一段完整电话对话。")
        lines.append("任务角色: " + task.role)
        lines.append("任务目标: " + task.task)
        lines.append("开场白: " + task.opening_line)
        lines.append("")
        lines.append("可用MCP工具:")
        lines.append(mcp_tools)
        expected = scenario.expected_tool_calls
        if expected:
            lines.append("[必须使用的工具] " + expected[0].tool_name)
        lines.append("场景说明: " + scenario.persona)
        lines.append("生成要求: tool_name精确匹配, agent回复大于3轮, 只返回JSON")
        return "\n".join(lines)
def _parse_json_object(content: str) -> dict:
    text = content.strip()
    if text.startswith("`"):
        text = text.strip("")
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
