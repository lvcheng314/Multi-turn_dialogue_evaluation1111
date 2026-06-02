from __future__ import annotations

from uuid import uuid4


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


TOOLS = {
    "transfer_to_human": transfer_to_human,
    "query_faq": query_faq,
    "record_rejection": record_rejection,
    "schedule_callback": schedule_callback,
    "create_ticket": create_ticket,
    "update_task_status": update_task_status,
}
