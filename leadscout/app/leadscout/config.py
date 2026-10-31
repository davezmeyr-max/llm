"""Runtime configuration, read once from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # LLM endpoint (vLLM OpenAI-compatible server, reached through the SSH tunnel)
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "http://127.0.0.1:8001/v1"))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", "change-me"))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "leadscout"))
    llm_thinking: bool = field(default_factory=lambda: _bool("LLM_THINKING", False))
    llm_timeout_s: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT_S", "180")))

    # Agent limits
    max_steps: int = field(default_factory=lambda: int(os.getenv("AGENT_MAX_STEPS", "24")))
    page_char_limit: int = field(default_factory=lambda: int(os.getenv("PAGE_CHAR_LIMIT", "12000")))

    # Tools
    searxng_url: str = field(default_factory=lambda: os.getenv("SEARXNG_URL", "http://127.0.0.1:8888"))
    opencorporates_token: str = field(default_factory=lambda: os.getenv("OPENCORPORATES_API_TOKEN", ""))
    user_agent: str = field(
        default_factory=lambda: os.getenv(
            "FETCH_USER_AGENT",
            "LeadScout/0.1 (business research; contact: admin@example.com)",
        )
    )

    # Storage / API
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "/data/leadscout.db"))
    api_token: str = field(default_factory=lambda: os.getenv("API_TOKEN", ""))

    # Worker
    poll_interval_s: float = field(default_factory=lambda: float(os.getenv("POLL_INTERVAL_S", "10")))
    notify_webhook: str = field(default_factory=lambda: os.getenv("NOTIFY_WEBHOOK_URL", ""))


settings = Settings()
