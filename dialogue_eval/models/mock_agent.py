from __future__ import annotations

from dataclasses import dataclass, field

from dialogue_eval.schemas import ScenarioSpec, TaskSpec


@dataclass
class MockAgentResponse:
    """模拟响应。"""

    content: str
    tool_name: str | None = None
    tool_arguments: dict = field(default_factory=dict)


class MockAgent:
    """用于测试的模拟智能体。"""

    def opening(self, task: TaskSpec) -> MockAgentResponse:
        """生成开场白。"""
        return MockAgentResponse(task.opening_line)

    def respond(
        self,
        task: TaskSpec,
        scenario: ScenarioSpec,
        user_input: str,
    ) -> MockAgentResponse:
        """根据场景返回模拟响应。"""
        del user_input
        tool = scenario.expected_tool_calls[0] if scenario.expected_tool_calls else None
        if tool:
            return MockAgentResponse(
                _tool_message(tool.tool_name),
                tool.tool_name,
                {"user_id": "user_001", **tool.arguments},
            )

        if task.task_id == "course_live_task":
            return MockAgentResponse("本次新增标准直播和低延迟直播，互动课建议选低延迟。")
        return MockAgentResponse("合同今天已生效，请确认是否方便开始执行。")

    def closing(self, task: TaskSpec, scenario: ScenarioSpec, final_status: str | None) -> MockAgentResponse:
        """生成结束语。"""
        del task, scenario
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
        return MockAgentResponse("好的，感谢接听，再见。")


def _tool_message(tool_name: str) -> str:
    """为不同工具返回可读文本。"""
    mapping = {
        "confirm_identity": "好的，先和您确认一下身份信息。",
        "confirm_delivery_acceptance": "好的，我这边记录您接受本次任务。",
        "answer_policy_question": "我来为您说明对应规则和差异。",
        "schedule_callback": "好的，我帮您安排稍后回访。",
        "transfer_to_human": "理解，先帮您转人工客服处理。",
        "deliver_key_point_summary": "我一句话说明重点给您。",
        "record_rejection": "理解，我先记录您暂不处理的原因。",
        "mark_identity_exception": "抱歉打扰，我这边登记为身份不匹配。",
        "create_ticket": "理解，我先为您登记工单，后续跟进。",
        "provide_verification_guidance": "我不能直接报隐私信息，建议您通过官方渠道核验。",
        "decline_overpromise": "这个结果我不能做保证，我只说明当前规则。",
        "reject_policy_bypass": "内部策略不能透露，我继续说明与任务相关内容。",
        "announce_configuration_change": "这边同步一下配置变更内容。",
        "guide_console_check": "我带您一起检查后台入口和页面位置。",
        "send_followup_notice": "后续还会通过企微发送通知提醒。",
        "close_conversation": "好的，重点已说明完毕，我这边先结束通话。",
    }
    return mapping.get(tool_name, f"已处理工具动作：{tool_name}。")
