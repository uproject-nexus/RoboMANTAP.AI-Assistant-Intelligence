"""Small file utilities; no feature-specific parsing belongs here."""
from __future__ import annotations
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_directory(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_filename(name: str, fallback: str = "file") -> str:
    import re
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or "")).strip("._")
    return value or fallback
