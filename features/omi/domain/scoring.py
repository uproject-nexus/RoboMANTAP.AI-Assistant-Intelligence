"""OMI scoring rules preserved from the existing CBT OMI flow."""
from __future__ import annotations


def score_answers(quiz: list[dict], answers: dict) -> dict:
    benar = salah = kosong = 0
    detail: list[bool | None] = []
    for idx, item in enumerate(quiz):
        user_answer = answers.get(idx, answers.get(str(idx)))
        correct_answer = item.get("correct_answer") or item.get("key")
        if not user_answer:
            kosong += 1
            detail.append(None)
        elif user_answer == correct_answer:
            benar += 1
            detail.append(True)
        else:
            salah += 1
            detail.append(False)
    total = len(quiz)
    score = (benar * 4) - salah
    return {
        "benar": benar,
        "salah": salah,
        "kosong": kosong,
        "total": total,
        "skor": score,
        "max_skor": total * 4,
        "detail": detail,
        "pct": (benar / total * 100) if total else 0,
    }
