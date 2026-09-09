"""Application configuration, loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
WEBAPP_DIR = BASE_DIR / "webapp"
LOCALES_DIR = Path(__file__).resolve().parent / "locales"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Telegram ---
    bot_token: str = Field(default="", alias="BOT_TOKEN")
    owner_id: int = Field(default=0, alias="OWNER_ID")

    # --- Web / webhook ---
    webhook_base: str = Field(default="", alias="WEBHOOK_BASE")
    webhook_secret: str = Field(default="dev-webhook-secret", alias="WEBHOOK_SECRET")
    session_secret: str = Field(default="dev-session-secret", alias="SESSION_SECRET")
    webapp_url_override: str = Field(default="", alias="WEBAPP_URL")
    use_polling: bool = Field(default=False, alias="USE_POLLING")
    port: int = Field(default=8080, alias="PORT")

    # --- Database ---
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/bot.db", alias="DATABASE_URL"
    )

    # --- Language ---
    default_language: str = Field(default="uz", alias="DEFAULT_LANGUAGE")

    # --- AI ---
    ai_provider: str = Field(default="", alias="AI_PROVIDER")
    ai_fallback: str = Field(default="", alias="AI_FALLBACK")
    openai_base_url: str = Field(default="", alias="OPENAI_BASE_URL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="llama-3.3-70b-versatile", alias="OPENAI_MODEL")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL")
    ollama_base_url: str = Field(default="", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3.1", alias="OLLAMA_MODEL")
    ai_rate_per_hour: int = Field(default=20, alias="AI_RATE_PER_HOUR")
    max_upload_mb: int = Field(default=8, alias="MAX_UPLOAD_MB")

    # --- Session token lifetime (seconds) ---
    session_ttl: int = 60 * 60 * 12
    # Max age of Telegram initData (seconds) accepted by /api/auth.
    initdata_ttl: int = 60 * 60 * 24

    SUPPORTED_LANGUAGES: tuple[str, ...] = ("uz", "ru", "en", "kaa")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def webapp_url(self) -> str:
        if self.webapp_url_override:
            return self.webapp_url_override.rstrip("/")
        if self.webhook_base:
            return self.webhook_base.rstrip("/") + "/app"
        return ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def webhook_path(self) -> str:
        # Secret is part of the path as a second layer alongside the header check.
        return f"/webhook/{self.webhook_secret}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def webhook_url(self) -> str:
        if not self.webhook_base:
            return ""
        return self.webhook_base.rstrip("/") + self.webhook_path

    @property
    def ai_configured(self) -> bool:
        return bool(self._provider_ready(self.ai_provider) or self._provider_ready(self.ai_fallback))

    def _provider_ready(self, name: str) -> bool:
        name = (name or "").strip().lower()
        if name in ("groq", "openai"):
            return bool(self.openai_api_key and self.openai_base_url)
        if name == "gemini":
            return bool(self.gemini_api_key)
        if name == "ollama":
            return bool(self.ollama_base_url)
        return False

    @property
    def default_lang(self) -> str:
        lang = (self.default_language or "uz").lower()
        return lang if lang in self.SUPPORTED_LANGUAGES else "uz"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
