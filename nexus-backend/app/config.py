"""Application configuration via environment variables. No defaults for secrets."""

from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _strip_str(v: str | object) -> str | object:
    """Strip whitespace from env strings to avoid trailing-space issues."""
    return v.strip() if isinstance(v, str) else v


class Settings(BaseSettings):
    """NEXUS settings. All API keys and URLs are required (no defaults)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Mode: live | mock_ai | mock_human (formerly CALLPILOT_MODE)
    NEXUS_MODE: Literal["live", "mock_ai", "mock_human"]

    # Data stores
    DATABASE_URL: str
    REDIS_URL: str

    # Twilio
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_PHONE_NUMBER: str

    # ElevenLabs
    ELEVENLABS_API_KEY: str
    ELEVENLABS_VOICE_ID: str
    ELEVENLABS_AGENT_ID: str | None = None  # Conversational AI agent (WebSocket URL); if unset, voice_id is used as fallback

    # OpenAI
    OPENAI_API_KEY: str

    # Google OAuth (optional — set in .env to enable login + user calendar)
    # Accepts GOOGLE_OAUTH_CLIENT_ID or GOOGLE_CLIENT_ID (same for secret/redirect)
    GOOGLE_OAUTH_CLIENT_ID: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_CLIENT_ID"),
    )
    GOOGLE_OAUTH_CLIENT_SECRET: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_CLIENT_SECRET"),
    )
    GOOGLE_OAUTH_REDIRECT_URI: str = Field(
        default="http://localhost:8000/api/auth/callback",
        validation_alias=AliasChoices("GOOGLE_OAUTH_REDIRECT_URI", "GOOGLE_REDIRECT_URI"),
    )

    @field_validator(
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_REDIRECT_URI",
        mode="before",
    )
    @classmethod
    def strip_google_oauth_strings(cls, v: str | object) -> str | object:
        """Read .env without trailing/leading spaces for OAuth credentials."""
        return _strip_str(v)

    # Session & encryption (set in production; dev defaults allow app to start)
    SESSION_SECRET_KEY: str = "dev-session-secret-min-32-chars-change-in-prod"
    ENCRYPTION_KEY: str | None = None  # Fernet key; if unset, refresh tokens stored unencrypted (dev only)
    SESSION_COOKIE_SECURE: bool = True  # set False for localhost without HTTPS

    # Google APIs (Places + Distance Matrix; optional for fallback to mock)
    GOOGLE_API_KEY: str | None = None

    # ElevenLabs outbound (Twilio)
    ELEVENLABS_AGENT_PHONE_NUMBER_ID: str | None = None  # required for outbound dial

    # Frontend (SPA): origin for CORS and post-login redirect (e.g. http://localhost:5173)
    FRONTEND_ORIGIN: str = ""

    # Optional (mock_human): single number or comma-separated list for testing multiple recipients
    TARGET_PHONE_NUMBER: str | None = None
    TARGET_PHONE_NUMBERS: str | None = None  # e.g. +16175551111,+16175552222
    MOCK_HUMAN_MAX_CALLS: int = 3  # RFC 4.3: max concurrent calls in mock_human mode

    def get_target_phones(self) -> list[str]:
        """For mock_human: list of numbers to dial (round-robin). From TARGET_PHONE_NUMBERS or single TARGET_PHONE_NUMBER."""
        multi = [s.strip() for s in (self.TARGET_PHONE_NUMBERS or "").split(",") if s.strip()]
        if multi:
            return multi
        return [self.TARGET_PHONE_NUMBER] if self.TARGET_PHONE_NUMBER else []


def get_settings() -> Settings:
    """Load and validate settings. Fails on first missing required variable."""
    return Settings()
