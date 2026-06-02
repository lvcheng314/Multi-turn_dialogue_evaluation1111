from __future__ import annotations

from typing import Protocol

from dialogue_eval.schemas import ScenarioSpec, TaskSpec


class AgentResponse(Protocol):
    content: str
    tool_name: str | None
    tool_arguments: dict


class DialogueAgent(Protocol):
    def respond(self, task: TaskSpec, scenario: ScenarioSpec, user_input: str) -> AgentResponse:
        ...
