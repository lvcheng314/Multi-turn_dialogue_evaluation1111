from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class FlowStep(BaseModel):
    step_id: str
    description: str
    required: bool = True


class FAQItem(BaseModel):
    question: str
    answer: str


class TaskConstraints(BaseModel):
    max_reply_chars: int = 40
    tone: str = "电话口语、礼貌、简短"
    forbidden_terms: list[str] = Field(default_factory=list)
    privacy_fields: list[str] = Field(default_factory=list)


class TaskSpec(BaseModel):
    task_id: str
    role: str
    task: str
    opening_line: str
    flow_steps: list[FlowStep]
    faq: list[FAQItem] = Field(default_factory=list)
    constraints: TaskConstraints = Field(default_factory=TaskConstraints)
    tools: list[str] = Field(default_factory=list)


class ExpectedToolCall(BaseModel):
    tool_name: str
    required: bool = True
    arguments: dict[str, Any] = Field(default_factory=dict)


class ScenarioSpec(BaseModel):
    scenario_id: str
    task_id: str
    persona: str
    customer_personality: str = ""
    agent_personality: str = ""
    situation: str = ""
    conversation_length: Literal["short", "medium", "long"] = "medium"
    initial_user_input: str
    goals: list[str] = Field(default_factory=list)
    expected_behaviors: list[str] = Field(default_factory=list)
    expected_tool_calls: list[ExpectedToolCall] = Field(default_factory=list)
    expected_final_state: dict[str, Any] = Field(default_factory=dict)
    risk_points: list[str] = Field(default_factory=list)


class MCPToolSpec(BaseModel):
    tool_name: str
    description: str
    required_arguments: list[str] = Field(default_factory=list)
    allowed_reasons: list[str] = Field(default_factory=list)
    success_state: dict[str, Any] = Field(default_factory=dict)
    risk_level: Literal["low", "medium", "high"] = "low"


class ChatMessage(BaseModel):
    turn: int
    role: Literal["user", "agent", "system"]
    content: str


class ToolCallTrace(BaseModel):
    turn: int
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = 0
    error_code: str | None = None


class DialogueTrace(BaseModel):
    run_id: str
    dialogue_id: str
    task_id: str
    scenario_id: str
    transcript: list[ChatMessage] = Field(default_factory=list)
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    state_trace: list[dict[str, Any]] = Field(default_factory=list)


class ImportedDialogueTrace(BaseModel):
    run_id: str | None = None
    dialogue_id: str
    task_id: str | None = None
    scenario_id: str | None = None
    transcript: list[ChatMessage] = Field(default_factory=list)
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    state_trace: list[dict[str, Any]] = Field(default_factory=list)


class ToolTraceCheck(BaseModel):
    check: str
    passed: bool
    score: float
    turn: int | None = None
    reason: str = ""


class Evidence(BaseModel):
    type: str
    turn: int | None = None
    comment: str
    dimension: str | None = None
    rule_id: str | None = None
    score_delta: float | None = None


class EvalResult(BaseModel):
    run_id: str
    dialogue_id: str
    total_score: float
    dimension_scores: dict[str, float]
    tool_trace_checks: list[ToolTraceCheck] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    final_decision: Literal["pass", "review", "fail"]


class ScoringConfig(BaseModel):
    enable_llm_judge: bool = False
    max_turns: int = 20


class RunSummary(BaseModel):
    run_id: str
    task_id: str
    status: str
    scenario_count: int
    completed_dialogues: int
    total_score: float
    report_markdown_path: str
    report_html_path: str
