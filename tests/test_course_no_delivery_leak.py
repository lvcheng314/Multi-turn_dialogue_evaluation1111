from __future__ import annotations

from dataclasses import dataclass, field

from dialogue_eval.parser import load_task
from dialogue_eval.runner import DialogueRunner
from dialogue_eval.scenarios import generate_scenarios


@dataclass
class AgentResponse:
    content: str
    tool_name: str | None = None
    tool_arguments: dict = field(default_factory=dict)


class CourseAwareAgent:
    def opening(self, task):
        return AgentResponse(task.opening_line)

    def respond(self, task, scenario, user_input):
        return AgentResponse('标准直播延迟约 5 到 10 秒，低延迟约 1 到 2 秒。')

    def closing(self, task, scenario, final_status):
        return AgentResponse('后续企业微信也会同步，感谢接听。')


def test_course_task_trace_does_not_use_delivery_script() -> None:
    task = load_task('tasks/course_live_task.json')
    scenario = generate_scenarios(task, 1)[0]
    trace = DialogueRunner(agent=CourseAwareAgent()).run('run_test', 'dialogue_001', task, scenario)
    text = ''.join(message.content for message in trace.transcript if message.role == 'agent')
    assert '配送' not in text
    assert '合同已生' not in text
    assert '低延迟' in text
