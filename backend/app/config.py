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

    google_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    database_url: str = "postgresql://postgres:postgres@localhost:5432/jobsearch"
    supabase_url: str = ""
    supabase_secret: str = ""
    serpapi_key: str = ""
    map_api_key: str = ""
    serpapi_base: str = "https://serpapi.com/search.json"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def postgres_url(self) -> str:
        for candidate in (self.supabase_url, self.database_url):
            value = (candidate or "").strip()
            if value:
                return value
        return ""


def get_settings() -> Settings:
    return Settings()
