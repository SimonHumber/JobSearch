from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Always load backend/.env, not "whatever/.env" the shell cwd points at.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    rapid_api_key: str = ""
    jsearch_host: str = "jsearch.p.rapidapi.com"
    jsearch_base: str = "https://jsearch.p.rapidapi.com"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"


def get_settings() -> Settings:
    return Settings()
