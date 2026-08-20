"""Environment-driven app configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str
    readonly_database_url: str
    llm_provider: str
    llm_model: str
    llm_api_key: str


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Copy .env.example to .env and fill in the values."
        )
    return value


def load_settings() -> Settings:
    return Settings(
        database_url=_require("DATABASE_URL"),
        readonly_database_url=_require("READONLY_DATABASE_URL"),
        # LLM settings are validated when the LLM client is actually constructed (Phase 9),
        # not here -- the DB layer and schema tooling shouldn't require an LLM provider to run.
        llm_provider=os.getenv("LLM_PROVIDER", ""),
        llm_model=os.getenv("LLM_MODEL", ""),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
    )


settings = load_settings()
