from __future__ import annotations

from dataclasses import dataclass, field

from dialogue_eval.schemas import ScenarioSpec, TaskSpec


@dataclass
class MockAgentResponse:
    content: str
    tool_name: str | None = None
    tool_arguments: dict = field(default_factory=dict)


class MockAgent:
    def opening(self, task: TaskSpec) -> MockAgentResponse:
        return MockAgentResponse(task.opening_line)

    def respond(
        self,
        task: TaskSpec,
        scenario: ScenarioSpec,
        user_input: str,
    ) -> MockAgentResponse:
        scenario_key = scenario.scenario_id.split("_", 1)[1]
        base_args = {"user_id": "user_001", "task_id": task.task_id}

        if scenario_key == "human_transfer":
            return MockAgentResponse(
                "理解，我先帮您转人工客服处理。",
                "transfer_to_human",
                {**base_args, "reason": "user_requested_human"},
            )
        if scenario_key in {"faq_exit", "faq_cost"}:
            question = scenario.expected_tool_calls[0].arguments.get("question", user_input) if scenario.expected_tool_calls else user_input
            answer = task.faq[0].answer if task.faq else "请以页面规则为准。"
            return MockAgentResponse(answer, "query_faq", {**base_args, "question": question})
        if scenario_key == "reject" or scenario_key == "rejection":
            return MockAgentResponse(
                "理解，我先记录您暂不处理的原因。",
                "record_rejection",
                {**base_args, "reason": "user_rejected"},
            )
        if scenario_key in {"busy", "driving", "callback_request"}:
            preferred_time = "20:00" if scenario_key == "callback_request" else "later_today"
            if scenario_key == "driving":
                preferred_time = "safe_time"
            return MockAgentResponse(
                "好的，安全优先，我帮您约稍后回访。",
                "schedule_callback",
                {**base_args, "preferred_time": preferred_time},
            )
        if scenario_key == "complaint":
            return MockAgentResponse(
                "理解，我先为您登记工单，后续跟进。",
                "create_ticket",
                {**base_args, "category": "complaint", "description": user_input},
            )
        if scenario_key == "wrong_identity":
            return MockAgentResponse(
                "抱歉打扰，我不再透露任务信息。",
                "update_task_status",
                {"task_id": task.task_id, "status": "identity_mismatch"},
            )
        if scenario_key in {"status_update", "enterprise_wechat"}:
            status = "accepted" if scenario_key == "status_update" else "notified"
            return MockAgentResponse(
                "好的，我已记录当前状态。",
                "update_task_status",
                {"task_id": task.task_id, "status": status},
            )
        if scenario_key == "privacy_probe":
            return MockAgentResponse("抱歉，我不能报身份证号或手机号，您可以通过官方 App 核验。")
        if scenario_key == "promise_probe":
            return MockAgentResponse("收益以实际配送和页面规则为准，我不能做保证。")
        if scenario_key == "prompt_injection":
            return MockAgentResponse("抱歉，内部政策不能透露，我继续说明本次任务。")

        if task.task_id == "course_live_task":
            return MockAgentResponse("本次新增标准直播和低延迟直播，互动课建议选低延迟。")
        return MockAgentResponse("合同今天已生效，请确认是否方便开始配送。")

    def closing(self, task: TaskSpec, scenario: ScenarioSpec, final_status: str | None) -> MockAgentResponse:
        scenario_key = scenario.scenario_id.split("_", 1)[1]
        if final_status == "transferred":
            return MockAgentResponse("已为您转人工，请稍等，感谢接听。")
        if final_status == "callback_scheduled":
            return MockAgentResponse("好的，到时再联系您，注意安全。")
        if final_status == "rejected":
            return MockAgentResponse("已记录您的情况，感谢接听，再见。")
        if final_status == "ticket_created":
            return MockAgentResponse("工单已登记，后续会处理，感谢反馈。")
        if final_status == "identity_mismatch":
            return MockAgentResponse("抱歉打扰您了，感谢告知，再见。")
        if scenario_key in {"privacy_probe", "prompt_injection", "promise_probe"}:
            return MockAgentResponse("感谢理解，您可在官方页面查看详情，再见。")
        return MockAgentResponse("好的，感谢接听，再见。")
