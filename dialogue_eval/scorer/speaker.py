from __future__ import annotations

from dialogue_eval.schemas import DialogueTrace


def likely_agent_role(trace: DialogueTrace) -> str:
    user_score = _role_score(trace, "user")
    agent_score = _role_score(trace, "agent")
    return "user" if user_score > agent_score else "agent"


def speaker_messages(trace: DialogueTrace, role: str):
    target = likely_agent_role(trace) if role == "agent" else _other_role(likely_agent_role(trace))
    return [message for message in trace.transcript if message.role == target]


def _other_role(role: str) -> str:
    return "user" if role == "agent" else "agent"


def _role_score(trace: DialogueTrace, role: str) -> int:
    messages = [message.content for message in trace.transcript if message.role == role]
    text = "\n".join(messages)
    score = 0

    outbound_markers = [
        "通知您",
        "新版",
        "入口已经上线",
        "帮助中心",
        "回访",
        "回呼",
        "感谢接听",
        "不打扰您",
        "祝您",
        "转接人工",
        "马上为您",
        "请稍候",
    ]
    recipient_markers = [
        "方便",
        "请说",
        "我有问题怎么办",
        "谢谢通知",
        "转人工",
        "晚上再联系",
        "我现在很忙",
        "我不是本人",
    ]

    score += sum(2 for token in outbound_markers if token in text)
    score -= sum(2 for token in recipient_markers if token in text)
    return score
