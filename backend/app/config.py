from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DBO_", extra="forbid")

    environment: Literal["development", "test", "production"] = "development"
    data_dir: Path = Path("data")
    sqlite_busy_timeout_ms: int = Field(default=3000, ge=100, le=10000)
    public_origin: str = "http://localhost:3000"
    allow_insecure_cookies: bool = False

    @field_validator("data_dir", mode="before")
    @classmethod
    def nonempty_path(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise ValueError("Data directory must not be empty")
        return value

    @property
    def database_path(self) -> Path:
        return self.data_dir.resolve() / "metadata.db"
