from dialogue_eval.config import Settings
from dialogue_eval.pipeline import _build_agent
from dialogue_eval.models import MockAgent, OpenAICompatibleAgent


def test_deepseek_model_uses_openai_compatible_agent() -> None:
    settings = Settings(model_provider="deepseek")
    assert isinstance(_build_agent(settings, None), OpenAICompatibleAgent)


def test_mock_model_uses_mock_agent() -> None:
    settings = Settings(model_provider="deepseek")
    assert isinstance(_build_agent(settings, "mock"), MockAgent)
