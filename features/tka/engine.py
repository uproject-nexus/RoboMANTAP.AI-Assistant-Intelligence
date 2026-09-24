"""TKA domain boundary. The Stage-5 baseline contains no standalone TKA source module.
This module intentionally exposes capability status instead of inventing an implementation.
"""
from pathlib import Path

SOURCE_CANDIDATES=[Path(__file__).resolve().parents[2]/"legacy"/"tka_sim.py",Path(__file__).resolve().parents[2]/"tka_sim.py"]
def available()->bool: return any(p.exists() for p in SOURCE_CANDIDATES)
def source_path():
    return next((p for p in SOURCE_CANDIDATES if p.exists()),None)
__all__=["available","source_path"]
