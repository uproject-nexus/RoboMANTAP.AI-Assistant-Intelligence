"""Low-level Gemini client lifecycle.

The SDK is imported lazily so configuration and tests remain importable even
when optional runtime dependencies are not installed in the audit environment.
"""
from __future__ import annotations
from typing import Any

from config.settings import STREAM_TIMEOUT_MS, get_gemini_api_keys

_clients_cache: list[Any] | None = None


def get_gemini_clients() -> list[Any]:
    global _clients_cache
    if _clients_cache is not None:
        return _clients_cache
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return []

    clients: list[Any] = []
    for key in get_gemini_api_keys():
        try:
            clients.append(genai.Client(api_key=key, http_options=types.HttpOptions(
                timeout=STREAM_TIMEOUT_MS,
                retry_options=types.HttpRetryOptions(attempts=1),
            )))
        except Exception:
            continue
    _clients_cache = clients
    return clients


def reset_client_cache() -> None:
    global _clients_cache
    _clients_cache = None
