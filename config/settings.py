"""Central runtime configuration.

This module intentionally contains configuration only. It does not initialize
Streamlit, Gemini, SQLAlchemy, or any feature service at import time.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

QUIZ_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
STREAM_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
STREAM_HINT_MAX_TOKENS = 9000
STREAM_SOLUTION_MAX_TOKENS = 9000
STREAM_TIMEOUT_MS = 90_000


def get_database_url() -> str | None:
    return os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")


def get_gemini_api_keys() -> list[str]:
    """Read Gemini keys from environment only.

    Streamlit secrets are deliberately handled by the infrastructure adapter,
    not by this pure configuration module.
    """
    raw = os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY")
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(k).strip() for k in raw if str(k).strip()]

    value = str(raw).strip()
    if value.startswith("["):
        import json
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(k).strip() for k in parsed if str(k).strip()]
        except Exception:
            value = value.strip("[]")
    if "," in value:
        return [k.strip(" \\\"'") for k in value.split(",") if k.strip(" \\\"'")]
    return [value.strip(" \\\"'")] if value else []


@dataclass(frozen=True)
class AppSettings:
    quiz_models: tuple[str, ...] = QUIZ_MODELS
    stream_models: tuple[str, ...] = STREAM_MODELS
    stream_hint_max_tokens: int = STREAM_HINT_MAX_TOKENS
    stream_solution_max_tokens: int = STREAM_SOLUTION_MAX_TOKENS
    stream_timeout_ms: int = STREAM_TIMEOUT_MS
