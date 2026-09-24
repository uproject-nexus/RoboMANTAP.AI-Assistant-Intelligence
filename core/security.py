"""Security boundary for authentication and anti-copy/session controls.

Concrete application rules stay in the existing feature/API implementation
until their dedicated migration stage.
"""
from __future__ import annotations
import re


def normalize_identifier(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
