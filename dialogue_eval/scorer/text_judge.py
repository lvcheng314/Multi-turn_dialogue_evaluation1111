from __future__ import annotations

import json

import httpx

from dialogue_eval.config import Settings, get_settings
from dialogue_eval.schemas import DialogueTrace, Evidence, ScoringConfig, TaskSpec


class TextJudgeScorer:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def score(
        self,
        task: TaskSpec,
        trace: DialogueTrace,
        config: ScoringConfig | None = None,
    ) -> tuple[float, list[Evidence]]:
        if config and config.enable_llm_judge:
            return self._score_with_llm(task, trace)
        return self._score_with_rules(task, trace)

    def _score_with_rules(self, task: TaskSpec, trace: DialogueTrace) -> tuple[float, list[Evidence]]:
        agent_messages = [message for message in trace.transcript if message.role == "agent"]
        if not agent_messages:
            return 0.0, [
                Evidence(
                    type="turn",
                    comment="缺少数字人回复。",
                    rule_id="text.no_agent_reply",
                    score_delta=-20,
                )
            ]

        score = 20.0
        evidence: list[Evidence] = []
        max_chars = task.constraints.max_reply_chars
        user_turns = len([message for message in trace.transcript if message.role == "user"])
        last_turn = trace.transcript[-1].turn if trace.transcript else None

        if user_turns < 3:
            score -= 5.0
            evidence.append(
                Evidence(
                    type="turn",
                    turn=last_turn,
                    comment="对话轮次偏短，缺少自然追问和确认。",
                    rule_id="text.turn_depth",
                    score_delta=-5,
                )
            )
        elif user_turns < 5:
            score -= 2.0
            evidence.append(
                Evidence(
                    type="turn",
                    turn=last_turn,
                    comment="对话轮次较短，说明深度有限。",
                    rule_id="text.turn_depth",
                    score_delta=-2,
                )
            )

        for message in agent_messages:
            if len(message.content) > max_chars * 2:
                score -= 3.0
                evidence.append(
                    Evidence(
                        type="turn",
                        turn=message.turn,
                        comment=f"回复长度 {len(message.content)} 超过约束上限的 2 倍。",
                        rule_id="text.reply_length",
                        score_delta=-3,
                    )
                )

        joined = " ".join(message.content for message in agent_messages)
        polite_keywords = ["您好", "你好", "好的", "理解", "抱歉", "感谢"]
        if any(keyword in joined for keyword in polite_keywords):
            polite_turn = _first_turn_with_any(agent_messages, polite_keywords)
            evidence.append(
                Evidence(
                    type="turn",
                    turn=polite_turn,
                    comment="话术保持礼貌和电话口语。",
                    rule_id="text.politeness",
                )
            )
        else:
            score -= 3.0
            evidence.append(
                Evidence(
                    type="turn",
                    turn=agent_messages[-1].turn,
                    comment="话术礼貌性不足，缺少电话沟通中的安抚或确认表达。",
                    rule_id="text.politeness",
                    score_delta=-3,
                )
            )

        return max(0.0, min(20.0, round(score, 2))), evidence

    def _score_with_llm(self, task: TaskSpec, trace: DialogueTrace) -> tuple[float, list[Evidence]]:
        api_key = self.settings.judge_model_api_key
        if not api_key or api_key == "local-placeholder":
            api_key = self.settings.deepseek_api_key
        if not api_key:
            raise RuntimeError("JUDGE_MODEL_API_KEY or DEEPSEEK_API_KEY is required when ENABLE_LLM_JUDGE=true")

        transcript = "\n".join(
            f"{message.role}: {message.content}" for message in trace.transcript
        )
        prompt = f"""
你是多轮外呼对话评测裁判。只返回 JSON，不要输出 Markdown。
评分范围 0-20，按以下量化标准：
- 0-5: 基本不能完成沟通，严重偏题或缺少回复。
- 6-10: 能回应但明显机械、过短或缺少关键解释。
- 11-15: 能覆盖主要意图，但追问、确认、异议处理不足。
- 16-20: 语言自然、简短、电话感强，能根据用户反应追问、确认和解释。

任务角色: {task.role}
任务目标: {task.task}
约束: 每轮回复建议不超过 {task.constraints.max_reply_chars} 字，语气 {task.constraints.tone}

对话:
{transcript}

返回格式:
{{"score": 0-20, "reason": "一句中文原因"}}
""".strip()

        url = self.settings.judge_model_base_url.rstrip("/") + "/chat/completions"
        with httpx.Client(timeout=45) as client:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": self.settings.judge_model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "max_tokens": 200,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]

        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Judge model returned non-JSON content: {content}") from exc

        score = float(payload.get("score", 0))
        reason = str(payload.get("reason", "LLM 裁判未返回原因"))
        judge_turn = _representative_turn(trace)
        return max(0.0, min(20.0, score)), [
            Evidence(
                type="turn",
                turn=judge_turn,
                comment=f"LLM 文本裁判: {reason}",
                rule_id="text.llm_judge",
            )
        ]


def _first_turn_with_any(messages, keywords: list[str]) -> int | None:
    for message in messages:
        if any(keyword in message.content for keyword in keywords):
            return message.turn
    return messages[0].turn if messages else None


def _representative_turn(trace: DialogueTrace) -> int | None:
    agent_turns = [message.turn for message in trace.transcript if message.role == "agent"]
    if not agent_turns:
        return None
    return agent_turns[len(agent_turns) // 2]
