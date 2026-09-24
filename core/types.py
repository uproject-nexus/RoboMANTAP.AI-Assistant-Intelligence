"""Shared lightweight type contracts."""
from __future__ import annotations
from typing import Any, TypedDict

Quiz = list[dict[str, Any]]

class QuizQuestion(TypedDict, total=False):
    id: int | str
    question: str
    options: list[str]
    correct_answer: str
    explanation: str

class SessionReview(TypedDict, total=False):
    session_id: str
    nama_siswa: str
    jenjang: str
    mapel: str
    nilai_akhir: int
    status: str
    detail_jawaban: list[dict[str, Any]]
