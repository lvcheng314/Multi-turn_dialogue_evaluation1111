from __future__ import annotations

from dialogue_eval.schemas import ChatMessage, DialogueTrace, ExpectedToolCall, FlowStep, ScenarioSpec, TaskSpec, ToolCallTrace
from dialogue_eval.scorer.outcome import OutcomeScorer


def test_outcome_resolves_callback_from_tool_even_when_state_trace_is_stale() -> None:
    task = TaskSpec(
        task_id="sample_upload_task",
        role="agent",
        task="通知商家新版发票开具入口已上线，并指导其后续如有问题可查看帮助中心或预约回访。",
        opening_line="您好，请问现在方便接听吗？",
        flow_steps=[
            FlowStep(step_id="confirm_availability", description="确认客户当前是否方便沟通。"),
            FlowStep(step_id="announce_update", description="说明新版发票开具入口已经上线。"),
            FlowStep(step_id="explain_benefit", description="解释新入口更容易查找且支持历史记录查看。"),
            FlowStep(step_id="offer_help", description="如客户有疑问，提供帮助中心或回访支持。"),
            FlowStep(step_id="polite_close", description="礼貌结束通话。"),
        ],
    )
    scenario = ScenarioSpec(
        scenario_id="s04_busy_short",
        task_id="sample_upload_task",
        persona="当前忙碌",
        initial_user_input="我现在很忙，你快点说。",
        expected_behaviors=["一句话说明", "必要时安排回呼"],
        expected_tool_calls=[
            ExpectedToolCall(
                tool_name="schedule_callback",
                arguments={"task_id": "sample_upload_task", "preferred_time": "later_today"},
            )
        ],
        expected_final_state={"task_status": "callback_scheduled"},
    )
    trace = DialogueTrace(
        run_id="run_001",
        dialogue_id="dialogue_004",
        task_id="sample_upload_task",
        scenario_id="s04_busy_short",
        transcript=[
            ChatMessage(turn=1, role="user", content="喂，谁啊？我正忙着呢，长话短说。"),
            ChatMessage(turn=2, role="agent", content="您好，我是平台客服，通知您新版发票入口已上线，更方便查找。"),
            ChatMessage(turn=3, role="user", content="行，知道了，还有事吗？"),
            ChatMessage(turn=4, role="agent", content="如果您后续有问题，可以看帮助中心，或者我安排稍后回访。"),
            ChatMessage(turn=5, role="user", content="不用了，就这样吧。"),
            ChatMessage(turn=6, role="agent", content="好的，那先不打扰您了，再见。"),
        ],
        tool_calls=[
            ToolCallTrace(
                turn=4,
                tool_name="schedule_callback",
                arguments={"task_id": "sample_upload_task", "preferred_time": "later_today"},
                result={},
            )
        ],
        state_trace=[
            {"turn": 1, "task_status": "in_progress", "identity_confirmed": False},
            {"turn": 2, "task_status": "in_progress", "identity_confirmed": True},
            {"turn": 3, "task_status": "in_progress", "identity_confirmed": True},
            {"turn": 4, "task_status": "in_progress", "identity_confirmed": True},
            {"turn": 5, "task_status": "in_progress", "identity_confirmed": True},
            {"turn": 6, "task_status": "in_progress", "identity_confirmed": True},
        ],
    )

    score, evidence = OutcomeScorer().score(task, scenario, trace)

    assert score >= 24.0
    assert "最终状态: callback_scheduled" in evidence[0].comment
    assert "状态来源: tool:schedule_callback" in evidence[0].comment
    assert "必需流程覆盖 5/5" in evidence[0].comment


def test_outcome_resolves_accepted_from_update_task_status_arguments() -> None:
    task = TaskSpec(
        task_id="task_accepted",
        role="agent",
        task="通知任务",
        opening_line="您好",
        flow_steps=[
            FlowStep(step_id="identity_confirm", description="确认用户身份"),
            FlowStep(step_id="announce_update", description="说明任务内容"),
            FlowStep(step_id="accept_status", description="确认用户接受"),
            FlowStep(step_id="polite_close", description="礼貌结束通话"),
        ],
    )
    scenario = ScenarioSpec(
        scenario_id="scenario_accepted",
        task_id="task_accepted",
        persona="正常沟通",
        initial_user_input="可以，你说吧",
        expected_tool_calls=[
            ExpectedToolCall(
                tool_name="update_task_status",
                arguments={"task_id": "task_accepted", "status": "accepted"},
            )
        ],
        expected_final_state={"task_status": "accepted"},
    )
    trace = DialogueTrace(
        run_id="run_accepted",
        dialogue_id="dialogue_accepted",
        task_id="task_accepted",
        scenario_id="scenario_accepted",
        transcript=[
            ChatMessage(turn=1, role="agent", content="您好，请问是本人吗？"),
            ChatMessage(turn=2, role="user", content="是本人，你说吧。"),
            ChatMessage(turn=3, role="agent", content="新版入口已经上线了，现在更容易查找。"),
            ChatMessage(turn=4, role="user", content="好的，我知道了。"),
            ChatMessage(turn=5, role="agent", content="好的，感谢接听，再见。"),
        ],
        tool_calls=[
            ToolCallTrace(
                turn=5,
                tool_name="update_task_status",
                arguments={"task_id": "task_accepted", "status": "accepted"},
                result={"status": "updated"},
            )
        ],
        state_trace=[
            {"turn": 1, "task_status": "opened", "identity_confirmed": False},
            {"turn": 5, "task_status": "in_progress", "identity_confirmed": True},
        ],
    )

    score, evidence = OutcomeScorer().score(task, scenario, trace)

    assert score >= 25.0
    assert "最终状态: accepted" in evidence[0].comment
    assert "状态来源: tool:update_task_status.arguments.status" in evidence[0].comment


def test_outcome_keeps_low_score_when_callback_is_not_actually_arranged() -> None:
    task = TaskSpec(
        task_id="sample_upload_task",
        role="agent",
        task="通知商家新版发票开具入口已上线，并指导其后续如有问题可查看帮助中心或预约回访。",
        opening_line="您好，请问现在方便接听吗？",
        flow_steps=[
            FlowStep(step_id="confirm_availability", description="确认客户当前是否方便沟通。"),
            FlowStep(step_id="announce_update", description="说明新版发票开具入口已经上线。"),
            FlowStep(step_id="offer_help", description="如客户有疑问，提供帮助中心或回访支持。"),
            FlowStep(step_id="polite_close", description="礼貌结束通话。"),
        ],
    )
    scenario = ScenarioSpec(
        scenario_id="s04_busy_short",
        task_id="sample_upload_task",
        persona="当前忙碌",
        initial_user_input="我现在很忙",
        expected_tool_calls=[
            ExpectedToolCall(
                tool_name="schedule_callback",
                arguments={"task_id": "sample_upload_task", "preferred_time": "later_today"},
            )
        ],
        expected_final_state={"task_status": "callback_scheduled"},
    )
    trace = DialogueTrace(
        run_id="run_bad",
        dialogue_id="dialogue_bad",
        task_id="sample_upload_task",
        scenario_id="s04_busy_short",
        transcript=[
            ChatMessage(turn=1, role="user", content="我现在很忙。"),
            ChatMessage(turn=2, role="agent", content="好的，新版入口已经上线了，您有空自己看一下帮助中心。"),
            ChatMessage(turn=3, role="agent", content="那先这样，再见。"),
        ],
        tool_calls=[],
        state_trace=[
            {"turn": 1, "task_status": "in_progress", "identity_confirmed": False},
            {"turn": 3, "task_status": "in_progress", "identity_confirmed": True},
        ],
    )

    score, evidence = OutcomeScorer().score(task, scenario, trace)

    assert score < 24.0
    assert "最终状态: in_progress" in evidence[0].comment
