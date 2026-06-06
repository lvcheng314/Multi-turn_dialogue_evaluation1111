from __future__ import annotations

import json

import httpx

from dialogue_eval.config import Settings, get_settings
from dialogue_eval.schemas import DialogueTrace, Evidence, ScoringConfig, TaskSpec
from dialogue_eval.scorer.speaker import likely_agent_role, speaker_messages


class TextJudgeScorer:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def score(
        self,
        task: TaskSpec,
        trace: DialogueTrace,
        config: ScoringConfig | None = None,
    ) -> tuple[float, list[Evidence]]:
        direct_transfer = _is_direct_transfer_case(trace)
        if direct_transfer:
            return 20.0, [
                Evidence(
                    type="turn",
                    turn=_representative_turn(trace),
                    comment="用户明确要求转人工，数字人已承接并立即转接，符合该场景的最优短流程。",
                    rule_id="text.direct_transfer_short_circuit",
                )
            ]
        wrong_contact = _is_wrong_contact_case(trace)
        if wrong_contact:
            return 20.0, [
                Evidence(
                    type="turn",
                    turn=_representative_turn(trace),
                    comment="用户明确表示非本人，数字人已道歉并停止继续通知，符合身份异常场景的最优处理。",
                    rule_id="text.identity_mismatch_short_circuit",
                )
            ]
        repeated_rejection = _is_repeated_rejection_case(trace)
        if repeated_rejection:
            return 20.0, [
                Evidence(
                    type="turn",
                    turn=_representative_turn(trace),
                    comment="用户已再次明确拒绝，数字人礼貌确认并停止打扰，符合拒绝场景的最优处理。",
                    rule_id="text.repeated_rejection_short_circuit",
                )
            ]
        if config and config.enable_llm_judge:
            return self._score_with_llm(task, trace)
        return self._score_with_rules(task, trace)

    def _score_with_rules(self, task: TaskSpec, trace: DialogueTrace) -> tuple[float, list[Evidence]]:
        agent_messages = speaker_messages(trace, "agent")
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
        user_turns = len(speaker_messages(trace, "user"))
        last_turn = trace.transcript[-1].turn if trace.transcript else None
        full_agent_text = " ".join(message.content for message in agent_messages)
        full_user_text = " ".join(message.content for message in speaker_messages(trace, "user"))
        direct_transfer_case = any(token in full_user_text for token in ["转人工", "人工客服", "别跟我说了", "不要机器人"]) and any(
            token in full_agent_text for token in ["理解", "马上", "转接", "人工客服", "请稍等"]
        )

        if user_turns < 3 and not direct_transfer_case:
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
        elif user_turns < 5 and not direct_transfer_case:
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

        if direct_transfer_case:
            score = max(score, 18.0)

        return max(0.0, min(20.0, round(score, 2))), evidence

    def _score_with_llm(self, task: TaskSpec, trace: DialogueTrace) -> tuple[float, list[Evidence]]:
        api_key = self.settings.judge_model_api_key
        if not api_key or api_key == "local-placeholder":
            api_key = self.settings.deepseek_api_key
        if not api_key:
            raise RuntimeError("JUDGE_MODEL_API_KEY or DEEPSEEK_API_KEY is required when ENABLE_LLM_JUDGE=true")

        inferred_agent_role = likely_agent_role(trace)
        transcript = "\n".join(
            f"{'agent' if message.role == inferred_agent_role else 'user'}: {message.content}"
            for message in trace.transcript
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
{{"score": 0-20, "reason": "综合评分原因", "details": [{{"turn": 轮次数字, "issue": "扣分原因", "delta": -负数}}]}}
""".strip()

        url = self.settings.judge_model_base_url.rstrip("/") + "/chat/completions"
        with httpx.Client(timeout=45, trust_env=False) as client:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": self.settings.judge_model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "max_tokens": 500,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]

        # Strip markdown code block wrappers if present
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        start_brace = cleaned.find("{")
        end_brace = cleaned.rfind("}")
        if start_brace >= 0 and end_brace > start_brace:
            cleaned = cleaned[start_brace:end_brace+1]
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Judge model returned non-JSON content: {content}") from exc

        score = float(payload.get("score", 0))
        reason = str(payload.get("reason", "LLM 裁判未返回原因"))
        evidence_list = []
        details_raw = payload.get("details", [])
        if details_raw:
            for d in details_raw:
                dturn = d.get("turn")
                dissue = str(d.get("issue", ""))
                ddelta = float(d.get("delta", 0) or 0)
                # Skip no-op detail items like "无问题" to keep report evidence high-signal.
                if ddelta >= 0 and any(token in dissue for token in ["无问题", "没问题", "正常", "良好"]):
                    continue
                evidence_list.append(
                    Evidence(
                        type="turn",
                        turn=int(dturn) if dturn else None,
                        comment="第" + str(dturn or "-") + "轮: " + dissue,
                        rule_id="text.llm_judge",
                        score_delta=ddelta,
                    )
                )
        if not evidence_list:
            evidence_list.append(
                Evidence(
                    type="turn",
                    turn=None,
                    comment="LLM 文本裁判(整段对话): " + reason,
                    rule_id="text.llm_judge",
                )
            )
        return max(0.0, min(20.0, score)), evidence_list

def _first_turn_with_any(messages, keywords: list[str]) -> int | None:
    for message in messages:
        if any(keyword in message.content for keyword in keywords):
            return message.turn
    return messages[0].turn if messages else None


def _representative_turn(trace: DialogueTrace) -> int | None:
    agent_msgs = speaker_messages(trace, "agent")
    if not agent_msgs:
        return None
    # 选回复最长的轮次（信息量最大）
    longest = max(agent_msgs, key=lambda m: len(m.content))
    return longest.turn


def _is_direct_transfer_case(trace: DialogueTrace) -> bool:
    if not any(call.tool_name == "transfer_to_human" for call in trace.tool_calls):
        return False

    agent_text = " ".join(message.content for message in speaker_messages(trace, "agent"))
    user_text = " ".join(message.content for message in speaker_messages(trace, "user"))

    user_requests_transfer = any(
        token in user_text for token in ["转人工", "人工客服", "别跟我说了", "不要机器人", "找人工"]
    )
    agent_acks_transfer = any(
        token in agent_text for token in ["理解", "好的", "马上", "转接", "人工客服", "请稍等"]
    )
    return user_requests_transfer and agent_acks_transfer


def _is_wrong_contact_case(trace: DialogueTrace) -> bool:
    agent_text = " ".join(message.content for message in speaker_messages(trace, "agent"))
    user_text = " ".join(message.content for message in speaker_messages(trace, "user"))

    user_denies_identity = any(
        token in user_text for token in ["不是王老板", "不是本人", "打错了", "他员工", "找别人", "人不在"]
    )
    agent_stops_politely = any(
        token in agent_text for token in ["不好意思", "打扰了", "不打扰", "再见", "记录一下情况", "明白了"]
    )
    return user_denies_identity and agent_stops_politely


def _is_repeated_rejection_case(trace: DialogueTrace) -> bool:
    user_messages = [message.content for message in speaker_messages(trace, "user")]
    agent_messages = [message.content for message in speaker_messages(trace, "agent")]
    if len(user_messages) < 2 or not agent_messages:
        return False

    rejection_tokens = ["不方便", "不想听", "不用了", "不需要", "别再打了", "别再打来了", "拒绝"]
    user_rejection_count = sum(1 for content in user_messages if any(token in content for token in rejection_tokens))
    agent_stop_politely = any(
        any(token in content for token in ["不再打扰", "记录一下", "明白了", "好的", "再见", "祝您"])
        for content in agent_messages[-2:]
    )
    return user_rejection_count >= 2 and agent_stop_politely
