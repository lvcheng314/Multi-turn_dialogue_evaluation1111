from dialogue_eval.parser import load_task
from dialogue_eval.scenarios import generate_scenarios


def test_generate_15_scenarios() -> None:
    task = load_task("examples/tasks/fengmaotui_delivery_task.json")
    scenarios = generate_scenarios(task, 15)
    assert len(scenarios) == 15
    assert scenarios[4].scenario_id == "s05_human_transfer"
    assert scenarios[4].expected_tool_calls[0].tool_name == "transfer_to_human"
