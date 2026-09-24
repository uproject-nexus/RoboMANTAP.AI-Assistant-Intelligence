"""Image/file helpers only; no image-generation behavior is added here."""
from __future__ import annotations
from pathlib import Path


def image_suffix(path: str | Path) -> str:
    return Path(path).suffix.lower()
