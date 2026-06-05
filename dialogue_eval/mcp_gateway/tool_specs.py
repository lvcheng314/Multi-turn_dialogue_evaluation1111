from dialogue_eval.schemas import MCPToolSpec


def default_tool_specs() -> list[MCPToolSpec]:
    return [
        # --- MCP 工具 ---
        MCPToolSpec(
            tool_name="transfer_to_human",
            description="将当前用户请求转接到人工客服队列。",
            required_arguments=["user_id", "task_id", "reason"],
            allowed_reasons=["user_requested_human", "complaint", "business_boundary"],
            success_state={"task_status": "transferred"},
            risk_level="medium",
        ),
        MCPToolSpec(
            tool_name="query_faq",
            description="查询任务 FAQ。",
            required_arguments=["task_id", "question"],
            success_state={"task_status": "faq_answered"},
        ),
        MCPToolSpec(
            tool_name="schedule_callback",
            description="预约回访。",
            required_arguments=["user_id", "task_id", "preferred_time"],
            success_state={"task_status": "callback_scheduled"},
        ),
        MCPToolSpec(
            tool_name="update_task_status",
            description="更新任务状态。",
            required_arguments=["task_id", "status"],
            success_state={},
        )
]
