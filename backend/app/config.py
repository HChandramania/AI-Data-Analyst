from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DBO_", extra="forbid")

    environment: Literal["development", "test", "production"] = "development"
    data_dir: Path = Path("data")
    sqlite_busy_timeout_ms: int = Field(default=3000, ge=100, le=10000)
    public_origin: str = "http://localhost:3000"
    allow_insecure_cookies: bool = False
    gemini_api_key: SecretStr | None = None
    gemini_model: str = Field(default="gemini-3.8-flash", min_length=1)
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str = Field(default="openai/gpt-4o-mini", min_length=1)
    groq_api_key: SecretStr | None = None
    groq_model: str = Field(default="openai/gpt-oss-120b", min_length=1)
    provider_timeout_seconds: int = Field(default=30, ge=1, le=60)
    query_timeout_seconds: int = Field(default=5, ge=1, le=30)
    runtime_env_file: Path | None = None

    @field_validator("data_dir", mode="before")
    @classmethod
    def nonempty_path(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise ValueError("Data directory must not be empty")
        return value

    @field_validator("gemini_model", "openrouter_model", "groq_model")
    @classmethod
    def nonempty_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Gemini model must not be empty")
        return value

    @property
    def database_path(self) -> Path:
        return self.data_dir.resolve() / "metadata.db"


class RuntimeConfigError(ValueError):
    """A watched environment file cannot be applied safely."""


def default_runtime_env_file() -> Path | None:
    """Find the local runtime file regardless of whether the server starts in backend or the repo root."""
    candidates = (Path(".env"), PROJECT_ROOT / ".env", PROJECT_ROOT / "backend" / ".env")
    return next((candidate for candidate in candidates if candidate.is_file()), None)


RUNTIME_FIELDS = {
    "DBO_GEMINI_API_KEY": "gemini_api_key",
    "DBO_GEMINI_MODEL": "gemini_model",
    "DBO_OPENROUTER_API_KEY": "openrouter_api_key",
    "DBO_OPENROUTER_MODEL": "openrouter_model",
    "DBO_GROQ_API_KEY": "groq_api_key",
    "DBO_GROQ_MODEL": "groq_model",
    "DBO_PROVIDER_TIMEOUT_SECONDS": "provider_timeout_seconds",
    "DBO_QUERY_TIMEOUT_SECONDS": "query_timeout_seconds",
}


def load_runtime_settings(base: Settings, env_file: Path) -> Settings:
    """Validate an entire provider/query snapshot before using any edited values."""
    try:
        values = dotenv_values(env_file, interpolate=False)
    except (OSError, UnicodeError) as exc:
        raise RuntimeConfigError("Runtime environment file is unavailable.") from exc
    if not env_file.is_file():
        raise RuntimeConfigError("Runtime environment file is unavailable.")
    current = base.model_dump()
    for name, field in RUNTIME_FIELDS.items():
        # A deleted key must not keep an old Compose-injected secret in memory.
        current[field] = values.get(name, Settings.model_fields[field].default)
    try:
        return Settings.model_validate(current)
    except ValueError as exc:
        raise RuntimeConfigError("Runtime environment file has invalid provider/query settings.") from exc
