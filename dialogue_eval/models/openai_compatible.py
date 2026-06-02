from __future__ import annotations

from dataclasses import dataclass, field
import json
from collections.abc import Iterator

import httpx

from dialogue_eval.config import Settings
from dialogue_eval.schemas import ScenarioSpec, TaskSpec


@dataclass
class OpenAICompatibleResponse:
    content: str
    tool_name: str | None = None
    tool_arguments: dict = field(default_factory=dict)


class OpenAICompatibleAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def opening(self, task: TaskSpec) -> OpenAICompatibleResponse:
        return OpenAICompatibleResponse(task.opening_line)

    def respond(
        self,
        task: TaskSpec,
        scenario: ScenarioSpec,
        user_input: str,
        history: list[dict[str, str]] | None = None,
    ) -> OpenAICompatibleResponse:
        prompt = (
            "你是外呼数字人。请严格遵循当前任务，不泄露隐私，不越权承诺。"
            "回复必须像真实电话沟通：有承接、有解释、有确认，不能机械复读。"
            "每一句不要太长，但要把当前问题说清楚。"
        )
        flow = "\n".join(f"- {step.description}" for step in task.flow_steps)
        faq = "\n".join(f"- 问: {item.question}\n  答: {item.answer}" for item in task.faq)
        history_text = "\n".join(
            f"{item['role']}: {item['content']}" for item in (history or [])
        )
        content = self._chat(
            base_url=self.settings.model_base_url,
            api_key=self.settings.effective_model_api_key,
            model=self.settings.model_name,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        f"角色: {task.role}\n"
                        f"任务: {task.task}\n"
                        f"流程要求:\n{flow}\n"
                        f"FAQ:\n{faq}\n"
                        f"话术约束: 每次回复约 {task.constraints.max_reply_chars} 字以内；{task.constraints.tone}\n"
                        f"当前测试场景: {scenario.persona}\n"
                        f"已发生对话:\n{history_text}\n"
                        f"用户刚才说: {user_input}\n"
                        "请只输出数字人下一句回复，不要解释，不要输出 JSON。"
                    ),
                },
            ],
        )
        return OpenAICompatibleResponse(content=content)

    def closing(
        self,
        task: TaskSpec,
        scenario: ScenarioSpec,
        final_status: str | None,
    ) -> OpenAICompatibleResponse:
        prompt = "你是外呼数字人。请为当前通话生成一句礼貌结束语，必须符合任务上下文，不要串到其他业务。"
        content = self._chat(
            base_url=self.settings.model_base_url,
            api_key=self.settings.effective_model_api_key,
            model=self.settings.model_name,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        f"角色: {task.role}\n任务: {task.task}\n"
                        f"场景: {scenario.persona}\n最终状态: {final_status}\n"
                        f"约束: {task.constraints.tone}，约 {task.constraints.max_reply_chars} 字以内。\n"
                        "请只输出一句自然电话结束语。"
                    ),
                },
            ],
        )
        return OpenAICompatibleResponse(content=content)

    @staticmethod
    def _chat(base_url: str, api_key: str, model: str, messages: list[dict]) -> str:
        return OpenAICompatibleAgent._chat_with_options(base_url, api_key, model, messages)

    @staticmethod
    def _chat_with_options(
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict],
        response_format: dict | None = None,
        temperature: float = 0.2,
        max_tokens: int = 200,
    ) -> str:
        if not api_key:
            raise RuntimeError("MODEL_API_KEY or DEEPSEEK_API_KEY is required for real model calls")
        url = base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format
        with httpx.Client(timeout=30) as client:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    @staticmethod
    def stream_chat_with_options(
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> Iterator[str]:
        if not api_key:
            raise RuntimeError("MODEL_API_KEY or DEEPSEEK_API_KEY is required for real model calls")
        url = base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        with httpx.Client(timeout=60) as client:
            with client.stream(
                "POST",
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = payload.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        yield content
