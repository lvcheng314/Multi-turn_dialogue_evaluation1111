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
            tool_name="record_rejection",
            description="记录用户拒绝原因。",
            required_arguments=["user_id", "task_id", "reason"],
            success_state={"task_status": "rejected"},
        ),
        MCPToolSpec(
            tool_name="schedule_callback",
            description="预约回访。",
            required_arguments=["user_id", "task_id", "preferred_time"],
            success_state={"task_status": "callback_scheduled"},
        ),
        MCPToolSpec(
            tool_name="create_ticket",
            description="创建投诉或业务工单。",
            required_arguments=["user_id", "task_id", "category", "description"],
            success_state={"task_status": "ticket_created"},
            risk_level="medium",
        ),
        MCPToolSpec(
            tool_name="update_task_status",
            description="更新任务状态。",
            required_arguments=["task_id", "status"],
            success_state={},
        ),
        # --- 行为/场景工具 (Behavioral / Scenario Tools) ---
        MCPToolSpec(
            tool_name="confirm_identity",
            description="确认接听人身份是否为负责人。",
            required_arguments=["user_id", "task_id", "result"],
            success_state={"task_status": "identity_confirmed"},
        ),
        MCPToolSpec(
            tool_name="confirm_delivery_acceptance",
            description="确认骑手接受配送任务或商家接受任务安排。",
            required_arguments=["user_id", "task_id", "result"],
            success_state={"task_status": "accepted"},
        ),
        MCPToolSpec(
            tool_name="answer_policy_question",
            description="回答用户关于政策、规则、差异的疑问。",
            required_arguments=["task_id", "topic"],
            success_state={"task_status": "answered"},
        ),
        MCPToolSpec(
            tool_name="deliver_key_point_summary",
            description="用极短的一句话概括核心通知内容。",
            required_arguments=["user_id", "task_id", "style"],
            success_state={"task_status": "summarized"},
        ),
        MCPToolSpec(
            tool_name="mark_identity_exception",
            description="标记身份不匹配异常并终止沟通。",
            required_arguments=["user_id", "task_id", "status"],
            success_state={"task_status": "identity_mismatch"},
        ),
        MCPToolSpec(
            tool_name="provide_verification_guidance",
            description="指引用户通过官方渠道验证身份，避免泄露隐私。",
            required_arguments=["user_id", "task_id", "channel"],
            success_state={"task_status": "privacy_protected"},
        ),
        MCPToolSpec(
            tool_name="decline_overpromise",
            description="拒绝越权承诺收益或结果。",
            required_arguments=["user_id", "task_id", "reason"],
            success_state={"task_status": "promise_avoided"},
        ),
        MCPToolSpec(
            tool_name="reject_policy_bypass",
            description="拒绝绕过规则的请求，回到任务范围。",
            required_arguments=["user_id", "task_id", "reason"],
            success_state={"task_status": "injection_blocked"},
        ),
        MCPToolSpec(
            tool_name="announce_configuration_change",
            description="通知用户配置变更详情。",
            required_arguments=["task_id", "scope"],
            success_state={"task_status": "notified"},
        ),
        MCPToolSpec(
            tool_name="guide_console_check",
            description="引导用户检查后台页面或权限。",
            required_arguments=["task_id", "surface"],
            success_state={"task_status": "guided"},
        ),
        MCPToolSpec(
            tool_name="send_followup_notice",
            description="通知后续将通过企微等渠道发送提醒。",
            required_arguments=["task_id", "channel"],
            success_state={"task_status": "notified"},
        ),
        MCPToolSpec(
            tool_name="close_conversation",
            description="确认用户无其他问题，礼貌结束通话。",
            required_arguments=["task_id", "result"],
            success_state={"task_status": "completed"},
        ),
    ]
