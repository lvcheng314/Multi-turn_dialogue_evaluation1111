from __future__ import annotations

from dialogue_eval.scenarios.templates import COURSE_SCENARIO_TEMPLATES, SCENARIO_TEMPLATES
from dialogue_eval.schemas import ExpectedToolCall, ScenarioSpec, TaskSpec


def generate_scenarios(task: TaskSpec, count: int = 15) -> list[ScenarioSpec]:
    """按任务生成场景列表。"""
    if count <= 0:
        raise ValueError("count must be greater than 0")

    templates = COURSE_SCENARIO_TEMPLATES if task.task_id in {"course_live_task"} else SCENARIO_TEMPLATES
    scenarios: list[ScenarioSpec] = []
    for index, template in enumerate(templates[:count], start=1):
        tool = template.get("tool")
        expected_tool_calls = []
        if tool:
            arguments = {"task_id": task.task_id, **tool.get("arguments", {})}
            expected_tool_calls.append(
                ExpectedToolCall(
                    tool_name=tool["tool_name"],
                    required=True,
                    arguments=arguments,
                )
            )

        scenarios.append(
            ScenarioSpec(
                scenario_id=f"s{index:02d}_{template['key']}",
                task_id=task.task_id,
                category=template.get("category", ""),
                subtype=template.get("subtype", ""),
                persona=template["persona"],
                customer_personality=template.get("customer_personality", template["persona"]),
                agent_personality=template.get("agent_personality", "专业、自然、礼貌"),
                situation=template.get("situation", template["persona"]),
                conversation_length=template.get("conversation_length", "medium"),
                initial_user_input=template["initial"],
                utterance_variants=template.get("utterance_variants", [template["initial"]]),
                exclusive_signals=template.get("exclusive_signals", []),
                goals=template.get("goals", []),
                expected_behaviors=template.get("behaviors", []),
                expected_tool_calls=expected_tool_calls,
                expected_final_state=template.get("final", {}),
                risk_points=template.get("risks", []),
            )
        )
    return scenarios
