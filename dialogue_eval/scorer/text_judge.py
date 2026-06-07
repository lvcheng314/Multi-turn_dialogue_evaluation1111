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
        if _is_direct_transfer_case(trace):
            return 20.0, [
                Evidence(
                    type="turn",
                    turn=_representative_turn(trace),
                    comment="用户明确要求转人工，数字人已礼貌承接并立即转接，符合该场景的最佳处理。",
                    rule_id="text.direct_transfer_short_circuit",
                )
            ]
        if _is_wrong_contact_case(trace):
            return 20.0, [
                Evidence(
                    type="turn",
                    turn=_representative_turn(trace),
                    comment="用户明确表示非本人，数字人已致歉并停止继续通知，符合身份异常场景的合理处理。",
                    rule_id="text.identity_mismatch_short_circuit",
                )
            ]
        if _is_repeated_rejection_case(trace):
            return 20.0, [
                Evidence(
                    type="turn",
                    turn=_representative_turn(trace),
                    comment="用户已多次明确拒绝，数字人礼貌确认并停止打扰，符合拒绝场景的合理处理。",
                    rule_id="text.repeated_rejection_short_circuit",
                )
            ]
        if _is_complaint_ack_case(trace):
            return 20.0, [
                Evidence(
                    type="turn",
                    turn=_representative_turn(trace),
                    comment="用户表达不满后，数字人已及时致歉并承接问题，符合投诉开场场景的基本处理。",
                    rule_id="text.complaint_ack_short_circuit",
                )
            ]
        if config and config.enable_llm_judge:
            score, evidence = self._score_with_llm(task, trace)
            if not _has_effective_text_penalty(evidence):
                return 20.0, evidence
            return score, evidence
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
        direct_transfer_case = _is_direct_transfer_case(trace)

        if user_turns < 3 and not direct_transfer_case:
            score -= 5.0
            evidence.append(
                Evidence(
                    type="turn",
                    turn=last_turn,
                    comment="对话轮次偏短，表达质量可判断信息有限。",
                    rule_id="text.turn_depth",
                    score_delta=-5.0,
                )
            )
        elif user_turns < 5 and not direct_transfer_case:
            score -= 2.0
            evidence.append(
                Evidence(
                    type="turn",
                    turn=last_turn,
                    comment="对话轮次较短，表达质量判断样本有限。",
                    rule_id="text.turn_depth",
                    score_delta=-2.0,
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
                        score_delta=-3.0,
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
                    comment="话术保持礼貌，符合电话沟通习惯。",
                    rule_id="text.politeness",
                )
            )
        else:
            score -= 3.0
            evidence.append(
                Evidence(
                    type="turn",
                    turn=agent_messages[-1].turn,
                    comment="话术礼貌性不足，缺少电话沟通中的承接或确认表达。",
                    rule_id="text.politeness",
                    score_delta=-3.0,
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
你是多轮外呼对话的“话术质量”裁判。只评估表达质量，不评估任务流程是否完整，也不评估工具是否调用正确。
只返回 JSON，不要输出 Markdown。

评分范围 0-20：
- 0-5：基本无法沟通，明显跑题、失礼，或几乎没有有效回复。
- 6-10：能回应，但表达明显生硬、机械、难懂，或频繁答非所问。
- 11-15：整体能沟通，但自然度、礼貌性、解释清晰度存在明显问题。
- 16-20：表达自然、简洁、礼貌，符合电话沟通习惯，能回应用户当下问题。

重要规则：
1. 不要因为“没有主动追问”“没有主动确认是否理解”“没有主动询问是否还有其他问题”而单独扣分。
2. 不要因为“没有补充更多背景解释”而单独扣分，除非用户已经明确表示没听懂、提出疑问，而客服仍未回应关键疑点。
3. 开场在确认身份前先简要说明来意，属于常见电话场景，不能单独扣分。
4. 用户已经明确表示“知道了/明白了/好的”后，客服未再次确认，不单独扣分。
5. 如果客服已经直接、清楚地回答了用户当下问题，应倾向给高分，不要为了流程完整性苛扣。
6. 只有当表达本身存在明显问题时才扣分，例如：不自然、机械重复、语气生硬、解释混乱、明显忽视用户问题、长度极端失衡。
7. `details` 里只写真正的扣分项，最多 2 条；每条 `delta` 只能是负数。

任务角色: {task.role}
任务目标: {task.task}
约束: 每轮回复建议不超过 {task.constraints.max_reply_chars} 字，语气 {task.constraints.tone}

对话:
{transcript}

返回格式:
{{"score": 0-20, "reason": "综合评分原因", "details": [{{"turn": 轮次数字, "issue": "扣分原因", "delta": -1}}]}}
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

        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        start_brace = cleaned.find("{")
        end_brace = cleaned.rfind("}")
        if start_brace >= 0 and end_brace > start_brace:
            cleaned = cleaned[start_brace : end_brace + 1]
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Judge model returned non-JSON content: {content}") from exc

        score = float(payload.get("score", 0))
        reason = str(payload.get("reason", "LLM 文本裁判未返回原因"))
        evidence_list: list[Evidence] = []
        details_raw = payload.get("details", [])
        rule_flags = _collect_rule_flags(trace)
        if details_raw:
            for detail in details_raw:
                detail_turn = detail.get("turn")
                detail_issue = str(detail.get("issue", ""))
                detail_delta = float(detail.get("delta", 0) or 0)
                if _conflicts_with_rule_flags(detail_issue, detail_delta, rule_flags) or _is_non_penalizable_issue(
                    detail_issue, detail_delta
                ):
                    score -= detail_delta
                    continue
                if detail_delta >= 0 and any(token in detail_issue for token in ["无问题", "没问题", "正常", "良好"]):
                    continue
                evidence_list.append(
                    Evidence(
                        type="turn",
                        turn=int(detail_turn) if detail_turn else None,
                        comment="第 " + str(detail_turn or "-") + " 轮: " + detail_issue,
                        rule_id="text.llm_judge",
                        score_delta=detail_delta,
                    )
                )
        if not evidence_list:
            if score < 20:
                # If the judge cannot provide any concrete, displayable penalty,
                # treat the dialogue as full-score to keep the report explainable.
                score = 20.0
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
    longest = max(agent_msgs, key=lambda message: len(message.content))
    return longest.turn


def _is_direct_transfer_case(trace: DialogueTrace) -> bool:
    if not any(call.tool_name == "transfer_to_human" for call in trace.tool_calls):
        return False

    agent_text = " ".join(message.content for message in speaker_messages(trace, "agent"))
    user_text = " ".join(message.content for message in speaker_messages(trace, "user"))
    user_requests_transfer = any(token in user_text for token in ["转人工", "人工客服", "别跟我说了", "不要机器人", "找人工"])
    agent_acks_transfer = any(token in agent_text for token in ["理解", "好的", "马上", "转接", "人工客服", "请稍等"])
    return user_requests_transfer and agent_acks_transfer


def _is_wrong_contact_case(trace: DialogueTrace) -> bool:
    agent_text = " ".join(message.content for message in speaker_messages(trace, "agent"))
    user_text = " ".join(message.content for message in speaker_messages(trace, "user"))
    user_denies_identity = any(token in user_text for token in ["不是王老板", "不是本人", "打错了", "他员工", "找别人", "人不在"])
    agent_stops_politely = any(token in agent_text for token in ["不好意思", "打扰了", "不打扰", "再见", "记录一下情况", "明白了"])
    return user_denies_identity and agent_stops_politely


def _is_repeated_rejection_case(trace: DialogueTrace) -> bool:
    user_messages = [message.content for message in speaker_messages(trace, "user")]
    agent_messages = [message.content for message in speaker_messages(trace, "agent")]
    if len(user_messages) < 2 or not agent_messages:
        return False

    rejection_tokens = ["不方便", "不想听", "不用了", "不需要", "别再打了", "别再打来", "拒绝"]
    user_rejection_count = sum(1 for content in user_messages if any(token in content for token in rejection_tokens))
    agent_stop_politely = any(
        any(token in content for token in ["不再打扰", "记录一下", "明白了", "好的", "再见", "祝您"])
        for content in agent_messages[-2:]
    )
    return user_rejection_count >= 2 and agent_stop_politely


def _is_complaint_ack_case(trace: DialogueTrace) -> bool:
    user_text = " ".join(message.content for message in speaker_messages(trace, "user"))
    agent_text = " ".join(message.content for message in speaker_messages(trace, "agent"))
    user_complains = any(token in user_text for token in ["出问题", "开不出来", "烦死了", "不满", "投诉", "太差", "有问题"])
    agent_acks = any(token in agent_text for token in ["抱歉", "不好意思", "给您带来不便", "理解", "非常抱歉"])
    return user_complains and agent_acks


def _has_availability_check(trace: DialogueTrace) -> bool:
    agent_text = " ".join(message.content for message in speaker_messages(trace, "agent"))
    return any(token in agent_text for token in ["方便接听", "方便说两句", "现在方便", "请问现在方便", "方便吗", "有空吗"])


def _collect_rule_flags(trace: DialogueTrace) -> set[str]:
    flags: set[str] = set()
    if _has_availability_check(trace):
        flags.add("availability_checked")
    if _has_official_verification_guidance(trace):
        flags.add("official_verification_guided")
    if _is_direct_transfer_case(trace):
        flags.add("direct_transfer")
    if _is_wrong_contact_case(trace):
        flags.add("wrong_contact")
    if _is_repeated_rejection_case(trace):
        flags.add("repeated_rejection")
    if _is_complaint_ack_case(trace):
        flags.add("complaint_acknowledged")
    return flags


def _conflicts_with_rule_flags(issue: str, delta: float, rule_flags: set[str]) -> bool:
    if delta >= 0:
        return False

    if "availability_checked" in rule_flags and any(
        token in issue for token in ["方便接听", "方便说两句", "是否方便", "主动确认用户是否方便", "未确认是否方便", "未询问是否方便"]
    ):
        return True

    normalized_issue = issue or ""

    if "direct_transfer" in rule_flags and any(
        token in normalized_issue for token in ["转人工", "转接", "人工", "帮助中心", "回访", "简要说明更新", "未完成通知"]
    ):
        return True

    if "wrong_contact" in rule_flags and any(token in normalized_issue for token in ["非本人", "打错", "留信息", "未完成通知", "未继续说明"]):
        return True

    if "repeated_rejection" in rule_flags and any(
        token in normalized_issue for token in ["预约回访", "帮助中心", "确认用户是否理解", "直接结束", "未继续通知"]
    ):
        return True

    if "complaint_acknowledged" in rule_flags and any(
        token in normalized_issue for token in ["仅道歉", "未安抚", "未解释新功能优势", "未深入了解具体问题"]
    ):
        return True

    if "official_verification_guided" in rule_flags and any(
        token in normalized_issue for token in ["未提供替代验证方案", "未提供具体验证步骤", "仅建议回拨", "质疑身份", "解释略显生硬"]
    ):
        return True

    return False


def _has_official_verification_guidance(trace: DialogueTrace) -> bool:
    agent_text = " ".join(message.content for message in speaker_messages(trace, "agent"))
    return any(token in agent_text for token in ["官方app", "官方App", "官方渠道", "回拨确认", "验证身份"])


def _is_non_penalizable_issue(issue: str, delta: float) -> bool:
    if delta >= 0:
        return False

    direct_allow_phrases = [
        "开场未先简要说明来意",
        "未先简要说明来意",
        "直接进入主题",
        "略显突兀",
        "未确认客户当前是否方便沟通",
        "未确认是否方便沟通",
        "没有确认客户当前是否方便沟通",
        "未先询问是否方便",
    ]
    if any(token in (issue or "") for token in direct_allow_phrases):
        return True

    normalized_issue = (issue or "").replace(" ", "")
    mild_repetition_tokens = [
        "稍后回呼",
        "稍后联系",
        "回呼",
        "回访",
        "表述略重复",
        "表达略重复",
        "轻微重复",
        "收口重复",
    ]
    if any(token in normalized_issue for token in mild_repetition_tokens):
        return True
    non_penalizable_tokens = [
        "未主动追问",
        "未主动确认",
        "未进一步确认",
        "未确认用户是否理解",
        "未确认用户是否还有疑问",
        "未询问是否还有其他问题",
        "未主动询问是否有其他问题",
        "未主动询问用户是否有疑问",
        "未补充解释为何",
        "未进一步解释为何",
        "未进一步解释之前为什么",
        "未继续解释",
        "未主动解释",
        "开场直接告知更新",
        "未先确认用户身份",
        "身份确认前先说明来意",
        "结尾未主动收口确认",
        "缺乏礼貌性收尾",
        "直接结束对话",
        "显得生硬",
        "未提供替代验证方案",
        "未主动提供具体验证步骤",
        "仅建议回拨",
        "用户质疑身份时",
    ]
    return any(token in normalized_issue for token in non_penalizable_tokens)


def _has_effective_text_penalty(evidence_list: list[Evidence]) -> bool:
    return any((item.score_delta or 0) < 0 for item in evidence_list)
