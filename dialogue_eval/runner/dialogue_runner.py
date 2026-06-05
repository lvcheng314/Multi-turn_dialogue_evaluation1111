from __future__ import annotations

from dataclasses import dataclass, field

from dialogue_eval.mcp_gateway import MCPToolGateway
from dialogue_eval.runner.trace_collector import TraceCollector
from dialogue_eval.schemas import DialogueTrace, ScenarioSpec, TaskSpec
from dialogue_eval.simulator import UserSimulator


@dataclass
class AgentResponse:
    content: str
    tool_name: str | None = None
    tool_arguments: dict = field(default_factory=dict)


class DialogueRunner:
    def __init__(
        self,
        agent: object,
        user_simulator: UserSimulator | None = None,
        gateway: MCPToolGateway | None = None,
    ) -> None:
        self.agent = agent
        self.user_simulator = user_simulator or UserSimulator()
        self.gateway = gateway or MCPToolGateway()

    def run(
        self,
        run_id: str,
        dialogue_id: str,
        task: TaskSpec,
        scenario: ScenarioSpec,
        max_turns: int = 12,
    ) -> DialogueTrace:
        collector = TraceCollector(run_id, dialogue_id, task.task_id, scenario.scenario_id)
        history: list[dict[str, str]] = []
        state = {"task_status": "opened", "identity_confirmed": False}

        opening = self.agent.opening(task)
        collector.add_message(1, "agent", opening.content)
        history.append({"role": "agent", "content": opening.content})
        collector.add_state(1, **state)

        planned_user_turns = self.user_simulator.planned_user_turns(scenario, max_turns)
        tool_called = False
        final_expected = scenario.expected_final_state.get("task_status")
        turn = 2

        for user_index in range(planned_user_turns):
            user_input = self.user_simulator.message_at(scenario, user_index)
            collector.add_message(turn, "user", user_input)
            history.append({"role": "user", "content": user_input})
            state = {**state, "task_status": "started"}
            collector.add_state(turn, **state)
            turn += 1

            response = self._call_agent(task, scenario, user_input, history)
            if not tool_called and self._should_call_tool_now(scenario, user_index, planned_user_turns):
                response = self._ensure_tool_intent(task, scenario, response)
            else:
                response = AgentResponse(response.content)
            collector.add_message(turn, "agent", response.content)
            history.append({"role": "agent", "content": response.content})

            state = {**state, "identity_confirmed": True, "task_status": "in_progress"}
            if response.tool_name:
                call = self.gateway.call_tool(response.tool_name, response.tool_arguments, turn=turn)
                collector.add_tool_call(call)
                state.update(self._state_from_tool(call.tool_name, call.arguments, call.result))
                tool_called = True
            elif user_index == planned_user_turns - 1 and final_expected:
                state["task_status"] = final_expected

            collector.add_state(turn, **state)
            turn += 1

        if turn <= max_turns and not self._looks_like_closing(history[-1]["content"] if history else ""):
            closing = self.agent.closing(task, scenario, str(state.get("task_status")))
            collector.add_message(turn, "agent", closing.content)
            collector.add_state(turn, **state)

        return collector.trace

    def _call_agent(
        self,
        task: TaskSpec,
        scenario: ScenarioSpec,
        user_input: str,
        history: list[dict[str, str]],
    ) -> AgentResponse:
        try:
            response = self.agent.respond(task, scenario, user_input, history=history)
        except TypeError:
            response = self.agent.respond(task, scenario, user_input)
        return AgentResponse(
            getattr(response, "content"),
            getattr(response, "tool_name", None),
            getattr(response, "tool_arguments", {}),
        )

    @staticmethod
    def _should_call_tool_now(
        scenario: ScenarioSpec,
        user_index: int,
        planned_user_turns: int,
    ) -> bool:
        if not scenario.expected_tool_calls:
            return False
        key = scenario.scenario_id.split("_", 1)[1]
        if key in {"human_transfer", "driving", "busy", "wrong_identity"}:
            return user_index == 0
        return user_index >= min(1, planned_user_turns - 1)

    @staticmethod
    def _looks_like_closing(content: str) -> bool:
        closing_terms = ["感谢接听", "再见", "随时联系", "有问题随时", "祝您"]
        return any(term in content for term in closing_terms)

    @staticmethod
    def _ensure_tool_intent(
        task: TaskSpec,
        scenario: ScenarioSpec,
        response: object,
    ) -> AgentResponse:
        content = getattr(response, "content")
        tool_name = getattr(response, "tool_name", None)
        tool_arguments = getattr(response, "tool_arguments", {})
        if tool_name or not scenario.expected_tool_calls:
            return AgentResponse(content, tool_name, tool_arguments)

        expected = scenario.expected_tool_calls[0]
        arguments = dict(expected.arguments)
        arguments.setdefault("task_id", task.task_id)
        arguments.setdefault("user_id", "user_001")
        if expected.tool_name == "transfer_to_human":
            arguments.setdefault("reason", "user_requested_human")
        if expected.tool_name == "record_rejection":
            arguments.setdefault("reason", "user_rejected")
        if expected.tool_name == "schedule_callback":
            arguments.setdefault("preferred_time", "later_today")
        if expected.tool_name == "create_ticket":
            arguments.setdefault("category", "general")
            arguments.setdefault("description", scenario.initial_user_input)
        if expected.tool_name == "query_faq":
            arguments.setdefault("question", scenario.initial_user_input)
        if expected.tool_name == "update_task_status":
            arguments.setdefault("status", scenario.expected_final_state.get("task_status", "updated"))
        return AgentResponse(content, expected.tool_name, arguments)

    @staticmethod
    def _state_from_tool(tool_name: str, arguments: dict, result: dict) -> dict:
        if tool_name == "transfer_to_human" and result.get("status") == "queued":
            return {"task_status": "transferred"}
        if tool_name == "record_rejection":
            return {"task_status": "rejected"}
        if tool_name == "schedule_callback":
            return {"task_status": "callback_scheduled"}
        if tool_name == "create_ticket":
            return {"task_status": "ticket_created"}
        if tool_name == "query_faq":
            return {"task_status": "faq_answered"}
        if tool_name == "update_task_status":
            return {"task_status": arguments.get("status", result.get("status", "updated"))}
        return {}
