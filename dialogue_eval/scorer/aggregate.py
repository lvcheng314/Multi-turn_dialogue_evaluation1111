from __future__ import annotations


def final_decision(total_score: float, risk_flags: list[str]) -> str:
    if risk_flags:
        return "fail"
    if total_score >= 80:
        return "pass"
    if total_score >= 60:
        return "review"
    return "fail"
