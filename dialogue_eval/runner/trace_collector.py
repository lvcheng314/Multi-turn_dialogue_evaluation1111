from __future__ import annotations

from dialogue_eval.schemas import ChatMessage, DialogueTrace, ToolCallTrace


class TraceCollector:
    def __init__(self, run_id: str, dialogue_id: str, task_id: str, scenario_id: str) -> None:
        self.trace = DialogueTrace(
            run_id=run_id,
            dialogue_id=dialogue_id,
            task_id=task_id,
            scenario_id=scenario_id,
        )

    def add_message(self, turn: int, role: str, content: str) -> None:
        self.trace.transcript.append(ChatMessage(turn=turn, role=role, content=content))

    def add_tool_call(self, call: ToolCallTrace) -> None:
        self.trace.tool_calls.append(call)

    def add_state(self, turn: int, **state: object) -> None:
        self.trace.state_trace.append({"turn": turn, **state})
