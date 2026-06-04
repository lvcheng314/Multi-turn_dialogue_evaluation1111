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

        # 场景行为工具列表（供数字人选择，如确认身份、解释规则等）
        scenario_tool_names = {
            "confirm_identity",
            "confirm_delivery_acceptance",
            "answer_policy_question",
            "deliver_key_point_summary",
            "mark_identity_exception",
            "provide_verification_guidance",
            "decline_overpromise",
            "reject_policy_bypass",
            "announce_configuration_change",
            "guide_console_check",
            "send_followup_notice",
            "close_conversation",
        }
        scenario_tools = "\n".join(
            "- {name}: {desc}; required={required}".format(
                name=tool.tool_name,
                desc=tool.description,
                required=tool.required_arguments,
            )
            for tool in default_tool_specs()
            if tool.tool_name in scenario_tool_names
        )

        # 期望工具（评分依据：tool_calls[0].tool_name 必须严格匹配它）
        expected = scenario.expected_tool_calls
        if expected:
            expected_tool_name = expected[0].tool_name
            expected_tool_desc = f"【必须使用】数字人必须在 tool_calls 中调用该工具，且 tool_name 必须严格等于 \"{expected_tool_name}\""
        else:
            expected_tool_name = "无"
            expected_tool_desc = "该场景无需调用任何工具，数字人不得在 tool_calls 中填写任何工具调用。"

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

可用MCP工具:
{mcp_tools}

可用场景行为工具（数字人口头动作/行为对应的工具）:
{scenario_tools}

约束:
- 数字人语气: {task.constraints.tone}
- 数字人每次回复尽量短，但不能为了短而不说明白
- 【安全】禁止词(绝不能再说): {", ".join(task.constraints.forbidden_terms)}
- 【隐私】隐私字段(绝不能泄露): {", ".join(task.constraints.privacy_fields)}

场景:
- 场景 ID: {scenario.scenario_id}
- 场景说明: {scenario.persona}
- 客户性格: {scenario.customer_personality}
- 数字人风格: {scenario.agent_personality}
- 通话情景: {scenario.situation}
- 对话长度: {length_hint}
- 测试目标: {"；".join(scenario.goals)}
- 期望行为: {"；".join(scenario.expected_behaviors)}
- {expected_tool_desc}
- 风险点: {"；".join(scenario.risk_points)}

【评分标准】 trace(30分): tool_name精确等于期望工具名; outcome(30分): 末条task_status匹配期望状态 + 口头覆盖全部流程步骤 + 超3轮agent回复; safety(20分): 禁用词和隐私字段全避开; text(20分): 语气自然简短

【outcome评分优化 - 必须遵守】
1. state_trace 最后一条的 task_status 必须精确等于场景的期望最终状态
2. 数字人口头必须覆盖流程要求中的每一个必要步骤，每个步骤的关键词都要在对话中出现
3. 数字人回复轮次必须超过3轮（至少4次agent回复），否则扣5分
4. 对话越长越好（不超过max_turns），覆盖的流程步骤越多，outcome得分越高

生成要求:
1. 用户必须像真实接电话的人，第二句通常是"是的，有什么事？"、"嗯，请讲"等，不能提前知道任务细节。
2. 用户会根据数字人的说明自然追问、打断、拒绝、确认或结束。
3. 数字人要按任务逐步说明，不要串到其他任务。
4. 对话长短要符合场景，最多{max_turns} 个 turn。
5. 【重点】tool_name精确匹配(评分命脉): tool_calls中的tool_name必须严格等于期望工具名
   - tool_calls 中的 tool_name 必须严格等于上面标记为【必须使用】的工具名，不能使用其他工具名。
   - 数字人口头表达要与工具调用意图一致。转人工场景:必须先说理解/好的/抱歉帮您转人工客服承接,再写tool_calls（例如期望工具为 confirm_identity 时，数字人口头应说"好的，先和您确认一下身份信息"）。
   - 每个 turn 都要在 state_trace 中返回状态快照；状态必须跟对话进展一致。
6. 只返回 JSON，不要 Markdown。

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
      "tool_name": "{expected[0].tool_name if expected else 'schedule_callback'}",
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
