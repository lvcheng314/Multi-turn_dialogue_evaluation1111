from __future__ import annotations

from uuid import uuid4


# --- MCP 工具 ---
def transfer_to_human(arguments: dict) -> dict:
    return {"status": "queued", "ticket_id": f"ticket_{uuid4().hex[:8]}"}

def query_faq(arguments: dict) -> dict:
    return {"matched": True, "answer": "请以任务 FAQ 和页面规则为准。"}

def record_rejection(arguments: dict) -> dict:
    return {"status": "recorded"}

def schedule_callback(arguments: dict) -> dict:
    return {"status": "scheduled", "callback_id": f"callback_{uuid4().hex[:8]}"}

def create_ticket(arguments: dict) -> dict:
    return {"status": "created", "ticket_id": f"ticket_{uuid4().hex[:8]}"}

def update_task_status(arguments: dict) -> dict:
    return {"status": arguments.get("status", "updated")}


# --- 行为/场景工具 (Behavioral / Scenario Tools) ---
def confirm_identity(arguments: dict) -> dict:
    return {"confirmed": True, "result": arguments.get("result", "self_confirmed")}

def confirm_delivery_acceptance(arguments: dict) -> dict:
    return {"confirmed": True, "result": arguments.get("result", "accepted")}

def answer_policy_question(arguments: dict) -> dict:
    return {"answered": True, "topic": arguments.get("topic", "general")}

def deliver_key_point_summary(arguments: dict) -> dict:
    return {"delivered": True, "style": arguments.get("style", "one_sentence")}

def mark_identity_exception(arguments: dict) -> dict:
    return {"marked": True, "status": arguments.get("status", "identity_mismatch")}

def provide_verification_guidance(arguments: dict) -> dict:
    return {"guided": True, "channel": arguments.get("channel", "official_app")}

def decline_overpromise(arguments: dict) -> dict:
    return {"declined": True, "reason": arguments.get("reason", "cannot_guarantee_income")}

def reject_policy_bypass(arguments: dict) -> dict:
    return {"rejected": True, "reason": arguments.get("reason", "policy_request_denied")}

def announce_configuration_change(arguments: dict) -> dict:
    return {"announced": True, "scope": arguments.get("scope", "course_live")}

def guide_console_check(arguments: dict) -> dict:
    return {"guided": True, "surface": arguments.get("surface", "web_console")}

def send_followup_notice(arguments: dict) -> dict:
    return {"sent": True, "channel": arguments.get("channel", "enterprise_wechat")}

def close_conversation(arguments: dict) -> dict:
    return {"closed": True, "result": arguments.get("result", "understood")}


TOOLS = {
    # MCP 工具
    "transfer_to_human": transfer_to_human,
    "query_faq": query_faq,
    "record_rejection": record_rejection,
    "schedule_callback": schedule_callback,
    "create_ticket": create_ticket,
    "update_task_status": update_task_status,
    # 行为/场景工具
    "confirm_identity": confirm_identity,
    "confirm_delivery_acceptance": confirm_delivery_acceptance,
    "answer_policy_question": answer_policy_question,
    "deliver_key_point_summary": deliver_key_point_summary,
    "mark_identity_exception": mark_identity_exception,
    "provide_verification_guidance": provide_verification_guidance,
    "decline_overpromise": decline_overpromise,
    "reject_policy_bypass": reject_policy_bypass,
    "announce_configuration_change": announce_configuration_change,
    "guide_console_check": guide_console_check,
    "send_followup_notice": send_followup_notice,
    "close_conversation": close_conversation,
}
