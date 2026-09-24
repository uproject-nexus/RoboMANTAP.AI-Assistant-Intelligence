"""Monitoring progress calculations kept independent from persistence."""
from __future__ import annotations


def progress_percent(current_index: int, total_questions: int) -> float:
    total = max(0, int(total_questions or 0))
    if total <= 0:
        return 0.0
    current = min(total, max(0, int(current_index or 0)))
    return round(current / total * 100.0, 1)


def answer_counts(detail: list | None) -> dict:
    values = detail if isinstance(detail, list) else []
    return {
        "answered": sum(v is not None for v in values),
        "correct": sum(v is True for v in values),
        "wrong": sum(v is False for v in values),
        "total": len(values),
    }
