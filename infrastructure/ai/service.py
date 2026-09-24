"""Gemini application services extracted from the legacy AI engine.

This module owns model invocation and AI-facing quiz/material orchestration; persistence and
document rendering live outside it. Behavior is intentionally preserved during refactor.
"""
from __future__ import annotations
import io, json, os, re, time, hashlib, subprocess, tempfile
from typing import Any
from config.settings import QUIZ_MODELS, STREAM_MODELS, STREAM_HINT_MAX_TOKENS, STREAM_SOLUTION_MAX_TOKENS
from infrastructure.ai.client import get_gemini_clients
try:
    from google.genai import types
except Exception:
    types = None

import pandas as pd

def vision_describe(image_bytes: bytes, mime_type: str, source_label: str) -> str:
    prompt=f"""Anda adalah Vision Reader RoboMANTAP. Sumber visual: {source_label}. Analisis hanya fakta yang benar-benar terlihat: teks, angka, label, tabel, diagram, grafik, rumus, dan struktur visual. Jangan mengarang bagian yang tidak terlihat. Gunakan Bahasa Indonesia rapi."""
    try:
        if types is None: return ""
        from infrastructure.ai.client import get_gemini_clients
        part=types.Part.from_bytes(data=image_bytes,mime_type=mime_type)
        for client in get_gemini_clients():
            for model_name in QUIZ_MODELS:
                try:
                    r=client.models.generate_content(model=model_name,contents=[prompt,part],config=types.GenerateContentConfig(max_output_tokens=5000))
                    if r and r.text: return str(r.text)[:8000]
                except Exception: continue
    except Exception: pass
    return ""

def show_error(msg: str):
    print(f"[AI ENGINE ERROR] {msg}")
    try:
        st.error(msg)
    except Exception:
        pass


def _stream_config(model_name: str, max_output_tokens: int):
    if model_name.startswith("gemini-3."):
        return types.GenerateContentConfig(
            max_output_tokens=max_output_tokens,
            thinking_config=types.ThinkingConfig(
                thinking_level="high"
            ),
        )

    return types.GenerateContentConfig(
        max_output_tokens=max_output_tokens,
        thinking_config=types.ThinkingConfig(
            thinking_budget=0,
            include_thoughts=False,
        ),
    )


def _buffer_stream_text(source, min_chars: int = 2, flush_seconds: float = 0.01):
    buffer = []
    size = 0
    last_flush = time.monotonic()

    for chunk in source:
        if not chunk:
            continue

        buffer.append(chunk)
        size += len(chunk)

        now = time.monotonic()
        if size >= min_chars or (now - last_flush) >= flush_seconds:
            yield "".join(buffer)
            buffer.clear()
            size = 0
            last_flush = now

    if buffer:
        yield "".join(buffer)


def _stream_from_clients(prompt: str, max_output_tokens: int):
    clients = get_gemini_clients()

    if not clients:
        yield "⚠️ Tidak ada koneksi yang aktif nih. Coba Kamu klik lagi.."
        return

    for client in clients:
        for model_name in STREAM_MODELS:
            try:
                response = client.models.generate_content_stream(
                    model=model_name,
                    contents=prompt,
                    config=_stream_config(model_name, max_output_tokens),
                )

                emitted = False

                def raw_stream():
                    for chunk in response:
                        chunk_text = getattr(chunk, "text", None)
                        if chunk_text:
                            yield chunk_text

                for piece in _buffer_stream_text(raw_stream()):
                    emitted = True
                    yield piece

                if emitted:
                    return

            except Exception:
                continue

    yield (
        "⚠️ Maaf ya, koneksi sedang bermasalah atau kuota sedang penuh nih. "
        "Silakan coba klik lagi ya!"
    )


def clean_json_text(text: str) -> str:
    if not text:
        return ""
    
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    def replace_slash(match):
        g = match.group(0)
        if g in (r'\\', r'\"'):
            return g 
        return r'\\' 

    return re.sub(r'\\\\|\\"|\\', replace_slash, text)


def call_gemini_with_rotation(prompt: str, is_json: bool = False):
    clients = get_gemini_clients()
    if not clients:
        return None

    for client in clients:
        for model_name in QUIZ_MODELS:
            try:
                config_kwargs = {}

                if is_json:
                    config_kwargs["response_mime_type"] = "application/json"

                if model_name.startswith("gemini-3."):
                    config_kwargs["thinking_config"] = types.ThinkingConfig(
                        thinking_level="high"
                    )
                else:
                    config_kwargs["thinking_config"] = types.ThinkingConfig(
                        thinking_budget=0,
                        include_thoughts=False,
                    )

                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_kwargs),
                )

                if response and response.text:
                    return response.text

            except Exception:
                continue

    return None


def stream_ai_text(prompt: str, max_output_tokens: int = STREAM_HINT_MAX_TOKENS):
    yield from _stream_from_clients(
        prompt,
        max_output_tokens=max_output_tokens,
    )
