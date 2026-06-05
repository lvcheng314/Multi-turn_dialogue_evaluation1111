from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"

    model_provider: str = "deepseek"
    model_base_url: str = "https://api.deepseek.com/v1"
    model_api_key: str = Field(default="", repr=False)
    model_name: str = "deepseek-chat"

    judge_model_provider: str = "deepseek"
    judge_model_base_url: str = "https://api.deepseek.com/v1"
    judge_model_api_key: str = Field(default="", repr=False)
    judge_model_name: str = "deepseek-chat"

    deepseek_api_key: str = Field(default="", repr=False)
    scenario_match_model_base_url: str = "https://api.deepseek.com/v1"
    scenario_match_model_api_key: str = Field(default="", repr=False)
    scenario_match_model_name: str = "deepseek-chat"
    scenario_match_confidence_threshold: float = 0.90

    runs_dir: str = "./database"
    archive_db_path: str = "./database/eval_archive.sqlite3"
    enable_llm_judge: bool = True
    scenario_count: int = 15
    max_turns: int = 20

    @property
    def effective_model_api_key(self) -> str:
        """返回主对话模型实际使用的 API Key。"""
        if self.model_api_key:
            return self.model_api_key
        return self.deepseek_api_key

    @property
    def effective_scenario_match_api_key(self) -> str:
        """返回场景识别模型实际使用的 API Key。"""
        if self.scenario_match_model_api_key:
            return self.scenario_match_model_api_key
        if self.model_api_key:
            return self.model_api_key
        return self.deepseek_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
