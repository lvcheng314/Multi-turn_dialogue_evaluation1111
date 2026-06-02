from dialogue_eval.config import Settings
from dialogue_eval.pipeline import _build_runner
from dialogue_eval.runner.deepseek_dialogue_generator import DeepSeekDialogueGenerator


def test_any_model_uses_deepseek_dialogue_generator() -> None:
    settings = Settings(model_provider="deepseek")
    assert isinstance(_build_runner(settings, None), DeepSeekDialogueGenerator)


def test_mock_model_no_longer_uses_mock_branch() -> None:
    settings = Settings(model_provider="deepseek")
    assert isinstance(_build_runner(settings, "mock"), DeepSeekDialogueGenerator)
