"""Centralized application configuration.

Environment variables are loaded from a `.env` file (via python-dotenv /
pydantic-settings). Nothing is hardcoded; every tunable lives here so the rest
of the codebase imports a single, validated `settings` object.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
load_dotenv(APP_DIR.parent / ".env")

LLMProvider = Literal["gemini", "anthropic", "openai"]


class Settings(BaseSettings):
    """Validated application settings sourced from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM provider selection ---
    # One of: "gemini" | "anthropic" | "openai". The tester can swap providers
    # by changing this and supplying the matching API key.
    llm_provider: LLMProvider = Field(default="gemini")
    agent_max_iterations: int = Field(default=8, ge=1, le=25)

    # Gemini (raw REST via httpx).
    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-2.5-flash")
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta"
    )

    # Anthropic (official SDK).
    anthropic_api_key: str = Field(default="")
    anthropic_model: str = Field(default="claude-haiku-4-5-20251001")

    # OpenAI (official SDK).
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")
    openai_base_url: str | None = Field(default=None)  # optional override

    # --- Persistence ---
    db_path: str = Field(default=str(APP_DIR / "data" / "refund.db"))
    policy_path: str = Field(default=str(APP_DIR / "policy.txt"))

    # --- API ---
    cors_origins: str = Field(default="http://localhost:3000")

    # --- Auth ---
    auth_secret: str = Field(default="dev-only-change-me-in-production")
    token_ttl_seconds: int = Field(default=86400, ge=300)
    admin_username: str = Field(default="admin")
    admin_password: str = Field(default="admin123")

    # --- Rate limiting (per-IP, applied to /auth/login and /admin/login) ---
    login_rate_limit: str = Field(default="5/minute")

    # --- Media uploads ---
    media_max_image_bytes: int = Field(default=2 * 1024 * 1024)  # 2 MB
    media_max_video_bytes: int = Field(default=100 * 1024 * 1024)  # 100 MB
    media_max_video_seconds: float = Field(default=60.0)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def db_file(self) -> Path:
        return Path(self.db_path)

    @property
    def policy_file(self) -> Path:
        return Path(self.policy_path)

    @property
    def active_llm_model(self) -> str:
        if self.llm_provider == "anthropic":
            return self.anthropic_model
        if self.llm_provider == "openai":
            return self.openai_model
        return self.gemini_model

    @property
    def active_llm_key_configured(self) -> bool:
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        return bool(self.gemini_api_key)


settings = Settings()
