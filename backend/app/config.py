"""Application configuration validated at startup using Pydantic v2 Settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and backend/.env."""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Required database connection string
    database_url: str = Field(..., min_length=1)
    test_database_url: str | None = None

    # External AI / Speech / Vision providers (optional until LLM endpoints are called)
    groq_api_key: str = ""
    gemini_api_key: str = ""
    llm_model: str = "openai/gpt-oss-120b"
    stt_model: str = "whisper-large-v3"
    vision_model: str = "gemini-2.5-flash"

    # Security & App settings
    env: Literal["dev", "test", "prod"] = "dev"
    tz: str = "Asia/Dhaka"
    cors_origins: str = "http://localhost:3000"
    session_secret: str = Field(..., min_length=16)
    tick_secret: str = Field(..., min_length=8)

    # Web Push (VAPID)
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:harbor@example.com"

    # Email fallback (SMTP)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""

    # Dish scoring weights (SPEC §7.3 defaults)
    score_w1_stock: float = 0.25
    score_w2_expiry: float = 0.15
    score_w3_season: float = 0.10
    score_w4_health: float = 0.15
    score_w5_taste: float = 0.10
    score_w6_price: float = 0.15
    score_w7_repeat: float = 0.30

    # Reminder offsets in minutes relative to meal time (SPEC §12 Flow E)
    offset_after_food_min: int = 20
    offset_before_food_min: int = -30
    offset_with_food_min: int = 0
    offset_any_min: int = 0
    reminder_grace_minutes: int = 30

    @field_validator("database_url")
    @classmethod
    def validate_postgres_url(cls, value: str) -> str:
        """Ensure PostgreSQL is configured and SQLite is never used."""
        lowered = value.strip().lower()
        if "sqlite" in lowered:
            raise ValueError("SQLite is forbidden by Harbor architecture; use PostgreSQL.")
        if not lowered.startswith("postgresql"):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection string.")
        return value.strip()

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def score_weights(self) -> dict[str, float]:
        """Return scoring weights dictionary."""
        return {
            "stock_fit": self.score_w1_stock,
            "expiry_bonus": self.score_w2_expiry,
            "season_bonus": self.score_w3_season,
            "health_fit": self.score_w4_health,
            "taste": self.score_w5_taste,
            "price_fit": self.score_w6_price,
            "repeat_penalty": self.score_w7_repeat,
        }

    @property
    def reminder_offsets(self) -> dict[str, int]:
        """Return timing offset map in minutes."""
        return {
            "after_food": self.offset_after_food_min,
            "before_food": self.offset_before_food_min,
            "with_food": self.offset_with_food_min,
            "any": self.offset_any_min,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached validated Settings instance (fails fast on missing config)."""
    return Settings()  # type: ignore[call-arg]
