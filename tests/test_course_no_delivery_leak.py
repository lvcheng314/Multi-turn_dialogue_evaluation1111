from dialogue_eval.models.mock_agent import MockAgentResponse
from dialogue_eval.parser import load_task
from dialogue_eval.runner import DialogueRunner
from dialogue_eval.scenarios import generate_scenarios


class CourseAwareAgent:
    def opening(self, task):
        return MockAgentResponse(task.opening_line)

    def respond(self, task, scenario, user_input):
        return MockAgentResponse("标准直播延迟约 5 到 10 秒，低延迟约 1 到 2 秒。")

    def closing(self, task, scenario, final_status):
        return MockAgentResponse("后续企业微信也会同步，感谢接听。")


def test_course_task_trace_does_not_use_delivery_script() -> None:
    task = load_task("examples/tasks/course_live_task.json")
    scenario = generate_scenarios(task, 1)[0]
    trace = DialogueRunner(agent=CourseAwareAgent()).run("run_test", "dialogue_001", task, scenario)
    text = "\n".join(message.content for message in trace.transcript if message.role == "agent")
    assert "配送" not in text
    assert "合同已生效" not in text
    assert "低延迟" in text
