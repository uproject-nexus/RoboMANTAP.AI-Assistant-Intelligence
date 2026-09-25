"""Application service for the HTMX OMI CBT flow."""
from __future__ import annotations

from infrastructure.ai.quiz import generate_quiz_batch, get_ai_hint_stream, get_ai_solution_stream
from .config import QUESTION_COUNT, STAGES, normalize_jenjang, validate_subject
from .scoring import score_answers
from .session import create_session, get_session, mark_finished, public_quiz


def validate_start(nama: str, jenjang: str, mapel: str, stage: str, selected_submateri: list[str]) -> tuple[bool, str]:
    if len([c for c in (nama or "") if c.isalpha()]) < 4:
        return False, "⚠️ Masukkan nama lengkap yang valid."
    try:
        jenjang_norm = normalize_jenjang(jenjang)
        available = validate_subject(jenjang_norm, mapel)
    except ValueError as exc:
        return False, f"⚠️ {exc}"
    if stage not in STAGES:
        return False, "⚠️ Tahap pembinaan tidak valid."
    invalid = [x for x in selected_submateri if x not in available]
    if invalid:
        return False, "⚠️ Ada submateri yang tidak sesuai dengan bidang OMI."
    return True, ""


def start_omi(nama: str, jenjang: str, mapel: str, stage: str, selected_submateri: list[str]):
    ok, error = validate_start(nama, jenjang, mapel, stage, selected_submateri)
    if not ok:
        return None, error
    quiz = generate_quiz_batch(normalize_jenjang(jenjang), mapel, stage, selected_submateri)
    if not quiz or len(quiz) != QUESTION_COUNT:
        return None, "⚠️ Paket soal belum berhasil dibuat. Silakan coba lagi."
    sess = create_session(
        nama=nama, jenjang=normalize_jenjang(jenjang), mapel=mapel, stage=stage,
        selected_submateri=selected_submateri, quiz=quiz,
    )
    return sess, ""


def result_for(session_id: str) -> dict | None:
    sess = get_session(session_id)
    if not sess:
        return None
    score = score_answers(sess.get("quiz", []), sess.get("answers", {}))
    return {"sess": sess, **score, "nama": sess.get("nama", "Santri MANTAP").split()[0]}


def submit(session_id: str) -> dict | None:
    sess = mark_finished(session_id)
    if not sess:
        return None
    return result_for(session_id)


def hint_for(session_id: str, q_index: int, attempt: str) -> str:
    sess = get_session(session_id)
    if not sess:
        return "⚠️ Sesi OMI tidak ditemukan."
    if sess.get("finished"):
        return "⚠️ Sesi OMI sudah selesai."
    attempt = str(attempt or "").strip()
    if not attempt:
        return "💡 Tolong ketik sedikit ide kamu dulu ya, biar RoboMANTAP bisa kasih petunjuk yang pas!"
    quiz = sess.get("quiz", [])
    if q_index < 0 or q_index >= len(quiz):
        return "⚠️ Nomor soal tidak valid."
    question = quiz[q_index].get("question", "")
    try:
        text = "".join(get_ai_hint_stream(question, attempt, sess.get("mapel", "OMI")))
        return text or "RoboMANTAP belum mendapatkan petunjuk. Coba lagi ya."
    except Exception as exc:
        return f"⚠️ Maaf, RoboMANTAP sedang sibuk sebentar. Coba lagi ya. ({exc})"


def solution_for(session_id: str, q_index: int) -> str:
    sess = get_session(session_id)
    if not sess:
        return "⚠️ Sesi OMI tidak ditemukan."
    if not sess.get("finished"):
        return "⚠️ Pembahasan tersedia setelah sesi selesai."
    quiz = sess.get("quiz", [])
    if q_index < 0 or q_index >= len(quiz):
        return "⚠️ Nomor soal tidak valid."
    item = quiz[q_index]
    try:
        text = "".join(get_ai_solution_stream(item.get("question", ""), item.get("correct_answer", ""), sess.get("mapel", "OMI")))
        return text or "Pembahasan belum tersedia."
    except Exception as exc:
        return f"⚠️ Maaf, pembahasan sedang sibuk sebentar. Coba lagi ya. ({exc})"
