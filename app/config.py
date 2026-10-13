from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr

from app.features import CREATION_RATE_LIMIT

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseModel):
    database_url: str = "sqlite:///./var/url_shortener.db"
    app_base_url: str = "http://localhost:8000"
    agent_data_dir: Path = PROJECT_ROOT / "var" / "agentic"
    llm_provider: Literal["gemini", "openai", "offline"] = "gemini"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = ""
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_json_mode: bool = True
    demo_mode: bool = False
    dns_check: bool = True
    creation_rate_limit: int = Field(default=CREATION_RATE_LIMIT, ge=1, le=1000)
    max_agent_retries: int = Field(default=2, ge=0, le=2)
    agent_timeout_seconds: int = Field(default=60, ge=1, le=120)
    log_level: str = "INFO"


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value.lower() == "true"


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./var/url_shortener.db"),
        app_base_url=os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/"),
        agent_data_dir=Path(
            os.getenv("AGENT_DATA_DIR", str(PROJECT_ROOT / "var/agentic"))
        ).resolve(),
        llm_provider=os.getenv("LLM_PROVIDER", "gemini"),
        gemini_api_key=SecretStr(os.getenv("GEMINI_API_KEY", "")),
        gemini_model=os.getenv("GEMINI_MODEL", ""),
        openai_api_key=SecretStr(os.getenv("OPENAI_API_KEY", "")),
        openai_model=os.getenv("OPENAI_MODEL", ""),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        openai_json_mode=env_bool("OPENAI_JSON_MODE", True),
        demo_mode=env_bool("DEMO_MODE", False),
        dns_check=env_bool("URL_DNS_CHECK", True),
        creation_rate_limit=int(os.getenv("CREATION_RATE_LIMIT", str(CREATION_RATE_LIMIT))),
        max_agent_retries=int(os.getenv("MAX_AGENT_RETRIES", "2")),
        agent_timeout_seconds=int(os.getenv("AGENT_TIMEOUT_SECONDS", "60")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
