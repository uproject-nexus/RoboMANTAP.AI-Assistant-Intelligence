"""AI response normalization utilities."""
from __future__ import annotations
import json
import re


def clean_json_text(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def loads_json(value: str):
    return json.loads(clean_json_text(value), strict=False)
