from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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

    runs_dir: str = "./runs"
    archive_db_path: str = "./runs/eval_archive.sqlite3"
    enable_llm_judge: bool = False
    scenario_count: int = 15
    max_turns: int = 20

    @property
    def effective_model_api_key(self) -> str:
        if self.model_api_key:
            return self.model_api_key
        return self.deepseek_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
