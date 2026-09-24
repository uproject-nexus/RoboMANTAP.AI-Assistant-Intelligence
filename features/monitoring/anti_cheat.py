"""Anti-cheat policy helpers independent from UI and HTTP."""
from __future__ import annotations

DEFAULT_MAX_VIOLATIONS = 3


def normalize_state(current: dict | None) -> dict:
    current = current if isinstance(current, dict) else {}
    return {
        "detected": bool(current.get("detected", False)),
        "reason": str(current.get("reason", "") or ""),
        "violation_count": max(0, int(current.get("violation_count", 0) or 0)),
        "max_violations": max(1, int(current.get("max_violations", DEFAULT_MAX_VIOLATIONS) or DEFAULT_MAX_VIOLATIONS)),
    }


def register_violation(current: dict | None, count: int = 1, reason: str = "Pindah tab") -> dict:
    state = normalize_state(current)
    state["violation_count"] = min(
        state["max_violations"],
        max(state["violation_count"], max(0, int(count or 0))),
    )
    if state["violation_count"] > 0:
        state["reason"] = str(reason or "Pindah tab").strip()[:100] or "Pindah tab"
    state["detected"] = state["violation_count"] >= state["max_violations"]
    return state
