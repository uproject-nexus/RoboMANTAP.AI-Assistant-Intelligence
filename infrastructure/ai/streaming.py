"""Low-level Gemini streaming adapter."""
from __future__ import annotations
import time
from collections.abc import Iterator

from config.settings import STREAM_MODELS
from infrastructure.ai.client import get_gemini_clients


def stream_config(model_name: str, max_output_tokens: int):
    from google.genai import types
    if model_name.startswith("gemini-3."):
        return types.GenerateContentConfig(
            max_output_tokens=max_output_tokens,
            thinking_config=types.ThinkingConfig(thinking_level="high"),
        )
    return types.GenerateContentConfig(
        max_output_tokens=max_output_tokens,
        thinking_config=types.ThinkingConfig(thinking_budget=0, include_thoughts=False),
    )


def buffer_stream_text(source, min_chars: int = 2, flush_seconds: float = 0.01) -> Iterator[str]:
    buffer: list[str] = []
    size = 0
    last_flush = time.monotonic()
    for chunk in source:
        if not chunk:
            continue
        buffer.append(chunk)
        size += len(chunk)
        now = time.monotonic()
        if size >= min_chars or now - last_flush >= flush_seconds:
            yield "".join(buffer)
            buffer.clear()
            size = 0
            last_flush = now
    if buffer:
        yield "".join(buffer)


def stream_prompt(prompt: str, max_output_tokens: int) -> Iterator[str]:
    clients = get_gemini_clients()
    if not clients:
        yield "⚠️ Tidak ada koneksi AI yang aktif."
        return
    for client in clients:
        for model_name in STREAM_MODELS:
            try:
                response = client.models.generate_content_stream(
                    model=model_name,
                    contents=prompt,
                    config=stream_config(model_name, max_output_tokens),
                )
                emitted = False
                for piece in buffer_stream_text(
                    getattr(chunk, "text", None) for chunk in response
                ):
                    emitted = True
                    yield piece
                if emitted:
                    return
            except Exception:
                continue
    yield "⚠️ Maaf, koneksi AI sedang bermasalah atau kuota sedang penuh."
