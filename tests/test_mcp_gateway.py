from dialogue_eval.mcp_gateway import MCPToolGateway


def test_transfer_to_human_trace_success() -> None:
    trace = MCPToolGateway().call_tool(
        "transfer_to_human",
        {"user_id": "user_001", "task_id": "delivery_task", "reason": "user_requested_human"},
        turn=3,
    )
    assert trace.error_code is None
    assert trace.tool_name == "transfer_to_human"
    assert trace.result["status"] == "queued"


def test_gateway_validates_required_arguments() -> None:
    trace = MCPToolGateway().call_tool("transfer_to_human", {"task_id": "delivery_task"}, turn=3)
    assert trace.error_code == "MISSING_ARGUMENT"
