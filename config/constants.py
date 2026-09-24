"""Stable application constants and policy values.

These values mirror the currently audited application. No new assessment
policy is introduced by the refactor stage.
"""

OPTION_LABELS_MTS = ("A", "B", "C", "D")
OPTION_LABELS_MA = ("A", "B", "C", "D", "E")


def option_labels_for_jenjang(jenjang: str) -> tuple[str, ...]:
    """Return the existing madrasah answer-option policy."""
    value = str(jenjang or "").strip().lower()
    if "ma" in value or "aliyah" in value:
        return OPTION_LABELS_MA
    return OPTION_LABELS_MTS


def option_count_for_jenjang(jenjang: str) -> int:
    return len(option_labels_for_jenjang(jenjang))
