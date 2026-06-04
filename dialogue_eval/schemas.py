from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class FlowStep(BaseModel):
    """任务流程步骤定义。"""

    step_id: str
    description: str
    required: bool = True


class FAQItem(BaseModel):
    """FAQ 条目定义。"""

    question: str
    answer: str


class TaskConstraints(BaseModel):
    """任务约束定义。"""

    max_reply_chars: int = 40
    tone: str = "电话口语、礼貌、简短"
    forbidden_terms: list[str] = Field(default_factory=list)
    privacy_fields: list[str] = Field(default_factory=list)


class TaskSpec(BaseModel):
    """任务规格定义。"""

    task_id: str
    role: str
    task: str
    opening_line: str
    flow_steps: list[FlowStep]
    faq: list[FAQItem] = Field(default_factory=list)
    constraints: TaskConstraints = Field(default_factory=TaskConstraints)
    tools: list[str] = Field(default_factory=list)


class ExpectedToolCall(BaseModel):
    """预期工具调用定义。"""

    tool_name: str
    required: bool = True
    arguments: dict[str, Any] = Field(default_factory=dict)


class ScenarioSpec(BaseModel):
    """场景规格定义。"""

    scenario_id: str
    task_id: str
    category: str = ""
    subtype: str = ""
    persona: str
    customer_personality: str = ""
    agent_personality: str = ""
    situation: str = ""
    conversation_length: Literal["short", "medium", "long"] = "medium"
    initial_user_input: str
    utterance_variants: list[str] = Field(default_factory=list)
    exclusive_signals: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    expected_behaviors: list[str] = Field(default_factory=list)
    expected_tool_calls: list[ExpectedToolCall] = Field(default_factory=list)
    expected_final_state: dict[str, Any] = Field(default_factory=dict)
    risk_points: list[str] = Field(default_factory=list)


class ImportedScenarioSpec(BaseModel):
    """导入的场景规格定义（用于上传已有场景 JSON 文件，所有字段可选/可缺省）。"""

    scenario_id: str
    task_id: str | None = None
    category: str = ""
    subtype: str = ""
    persona: str = ""
    customer_personality: str = ""
    agent_personality: str = ""
    situation: str = ""
    conversation_length: str = "medium"
    initial_user_input: str = ""
    utterance_variants: list[str] = Field(default_factory=list)
    exclusive_signals: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    expected_behaviors: list[str] = Field(default_factory=list)
    expected_tool_calls: list[ExpectedToolCall] = Field(default_factory=list)
    expected_final_state: dict[str, Any] = Field(default_factory=dict)
    risk_points: list[str] = Field(default_factory=list)





class MCPToolSpec(BaseModel):
    """MCP 工具规格定义。"""

    tool_name: str
    description: str
    required_arguments: list[str] = Field(default_factory=list)
    allowed_reasons: list[str] = Field(default_factory=list)
    success_state: dict[str, Any] = Field(default_factory=dict)
    risk_level: Literal["low", "medium", "high"] = "low"


class ChatMessage(BaseModel):
    """对话消息。"""

    turn: int
    role: Literal["user", "agent", "system"]
    content: str


class ToolCallTrace(BaseModel):
    """工具调用轨迹。"""

    turn: int
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = 0
    error_code: str | None = None


class DialogueTrace(BaseModel):
    """标准化对话轨迹。"""

    run_id: str
    dialogue_id: str
    task_id: str
    scenario_id: str
    transcript: list[ChatMessage] = Field(default_factory=list)
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    state_trace: list[dict[str, Any]] = Field(default_factory=list)


class ImportedDialogueTrace(BaseModel):
    """导入的对话轨迹。"""

    run_id: str | None = None
    dialogue_id: str
    task_id: str | None = None
    scenario_id: str | None = None
    transcript: list[ChatMessage] = Field(default_factory=list)
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    state_trace: list[dict[str, Any]] = Field(default_factory=list)


class ToolTraceCheck(BaseModel):
    """工具检查结果。"""

    check: str
    passed: bool
    score: float
    turn: int | None = None
    reason: str = ""


class Evidence(BaseModel):
    """评分证据。"""

    type: str
    turn: int | None = None
    comment: str
    dimension: str | None = None
    rule_id: str | None = None
    score_delta: float | None = None


class EvalResult(BaseModel):
    """单条对话评分结果。"""

    run_id: str
    dialogue_id: str
    total_score: float
    dimension_scores: dict[str, float]
    tool_trace_checks: list[ToolTraceCheck] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    final_decision: Literal["pass", "review", "fail"]


class ScoringConfig(BaseModel):
    """评分配置。"""

    enable_llm_judge: bool = False
    max_turns: int = 20


class RunSummary(BaseModel):
    """运行摘要。"""

    run_id: str
    task_id: str
    status: str
    scenario_count: int
    completed_dialogues: int
    total_score: float
    report_markdown_path: str
    report_html_path: str
    total_dialogues: int = 0
    scored_dialogues: int = 0
    low_confidence_dialogues: int = 0
    match_error_dialogues: int = 0


class ScenarioMatchResult(BaseModel):
    """场景识别结果。"""

    dialogue_id: str
    scenario_id: str | None = None
    confidence: float | None = None
    reason: str = ""
    matched_by: Literal["llm"] = "llm"
    status: Literal["matched", "low_confidence", "match_error"]
    error_type: str | None = None


class UnscorableDialogue(BaseModel):
    """未进入量化评分的对话。"""

    dialogue_id: str
    status: Literal["low_confidence", "match_error"]
    suggested_scenario_id: str | None = None
    confidence: float | None = None
    reason: str = ""
    error_type: str | None = None
