from __future__ import annotations

import time

from dialogue_eval.mcp_gateway.mock_tools import TOOLS
from dialogue_eval.mcp_gateway.tool_specs import default_tool_specs
from dialogue_eval.schemas import MCPToolSpec, ToolCallTrace


class MCPToolGateway:
    def __init__(self, tool_specs: list[MCPToolSpec] | None = None) -> None:
        self._specs = {spec.tool_name: spec for spec in (tool_specs or default_tool_specs())}

    def list_tools(self) -> list[MCPToolSpec]:
        return list(self._specs.values())

    def call_tool(self, tool_name: str, arguments: dict, turn: int) -> ToolCallTrace:
        started = time.perf_counter()
        if tool_name not in self._specs or tool_name not in TOOLS:
            return self._trace(turn, tool_name, arguments, {}, started, "TOOL_NOT_FOUND")

        missing = [
            name for name in self._specs[tool_name].required_arguments if not arguments.get(name)
        ]
        if missing:
            return self._trace(
                turn,
                tool_name,
                arguments,
                {"missing_arguments": missing},
                started,
                "MISSING_ARGUMENT",
            )

        if tool_name == "transfer_to_human":
            allowed = self._specs[tool_name].allowed_reasons
            if arguments.get("reason") not in allowed:
                return self._trace(
                    turn,
                    tool_name,
                    arguments,
                    {"allowed_reasons": allowed},
                    started,
                    "INVALID_ARGUMENT",
                )

        try:
            result = TOOLS[tool_name](arguments)
        except Exception as exc:
            return self._trace(
                turn,
                tool_name,
                arguments,
                {"error": str(exc)},
                started,
                "TOOL_EXECUTION_FAILED",
            )
        return self._trace(turn, tool_name, arguments, result, started, None)

    @staticmethod
    def _trace(
        turn: int,
        tool_name: str,
        arguments: dict,
        result: dict,
        started: float,
        error_code: str | None,
    ) -> ToolCallTrace:
        latency_ms = max(1, int((time.perf_counter() - started) * 1000))
        return ToolCallTrace(
            turn=turn,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            latency_ms=latency_ms,
            error_code=error_code,
        )
