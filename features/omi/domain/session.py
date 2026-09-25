"""OMI session state and persistence boundary.

Active sessions are kept in memory for fast interaction and mirrored to the
existing ``sesi_ujian`` table. The existing table/schema is intentionally
reused; no database migration is required for this OMI move.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from infrastructure.database.connection import init_db_connection
from infrastructure.database.monitoring import update_progress_siswa, touch_session_heartbeat
from .config import normalize_jenjang

SESSIONS: dict[str, dict[str, Any]] = {}
MAX_ANTI_CHEAT = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _detail(quiz: list[dict], answers: dict) -> list[bool | None]:
    out: list[bool | None] = []
    for idx, item in enumerate(quiz):
        answer = answers.get(idx, answers.get(str(idx)))
        if not answer:
            out.append(None)
        else:
            out.append(answer == item.get("correct_answer"))
    return out


def _persist(sess: dict, status: str = "BERJALAN") -> None:
    try:
        update_progress_siswa(
            session_id=sess["session_id"],
            nama=sess["nama"],
            jenjang=normalize_jenjang(sess["jenjang"]),
            mapel=sess["mapel"],
            soal_sekarang=int(sess.get("current_index", 0)) + 1,
            detail_jawaban=_detail(sess["quiz"], sess.get("answers", {})),
            status=status,
            is_custom=False,
            user_answers_dict=dict(sess.get("answers", {})),
            quiz_data_list=list(sess.get("quiz", [])),
            anti_cheat=dict(sess.get("anti_cheat", {})),
            session_mode="OMI",
        )
    except Exception as exc:
        print(f"[OMI DB WARN] {exc}")


def create_session(*, nama: str, jenjang: str, mapel: str, stage: str, selected_submateri: list[str], quiz: list[dict]) -> dict:
    session_id = str(uuid.uuid4())
    sess = {
        "session_id": session_id,
        "nama": nama.strip(),
        "jenjang": normalize_jenjang(jenjang),
        "mapel": mapel,
        "stage": stage,
        "selected_submateri": list(selected_submateri or []),
        "quiz": list(quiz),
        "answers": {},
        "current_index": 0,
        "start_time": _now(),
        "finished": False,
        "anti_cheat": {"detected": False, "reason": "", "violation_count": 0, "max_violations": MAX_ANTI_CHEAT},
    }
    SESSIONS[session_id] = sess
    _persist(sess, "BERJALAN")
    return sess


def _load_from_db(session_id: str) -> dict | None:
    conn = init_db_connection()
    if not conn:
        return None
    query = """
    SELECT id_sesi, nama_siswa, jenjang, mapel, soal_sekarang, detail_jawaban, status, created_at
    FROM sesi_ujian
    WHERE id_sesi = :id
    LIMIT 1
    """
    try:
        with conn.session as s:
            row = s.execute(text(query), {"id": session_id}).fetchone()
        if not row:
            return None
        raw = row[5]
        if isinstance(raw, str):
            raw = json.loads(raw)
        raw = raw if isinstance(raw, dict) else {}
        quiz = raw.get("quiz_data", []) if isinstance(raw.get("quiz_data", []), list) else []
        answers = raw.get("user_answers", {}) if isinstance(raw.get("user_answers", {}), dict) else {}
        anti = raw.get("anti_cheat", {}) if isinstance(raw.get("anti_cheat", {}), dict) else {}
        try:
            start_time = row[7].replace(tzinfo=timezone.utc) if row[7] and row[7].tzinfo is None else row[7]
        except Exception:
            start_time = _now()
        sess = {
            "session_id": row[0], "nama": row[1] or "Siswa", "jenjang": row[2] or "MA",
            "mapel": row[3] or "OMI", "stage": raw.get("stage", "Internal"),
            "selected_submateri": raw.get("selected_submateri", []) if isinstance(raw.get("selected_submateri", []), list) else [],
            "quiz": quiz, "answers": {int(k) if str(k).isdigit() else k: v for k, v in answers.items()},
            "current_index": max(0, int(row[4] or 1) - 1), "start_time": start_time or _now(),
            "finished": str(row[6] or "").upper() == "SELESAI", "anti_cheat": anti,
            "session_mode": str(raw.get("session_mode", "OMI") or "OMI").upper(),
        }
        # Older payloads may not contain OMI metadata. It is safe to use defaults.
        SESSIONS[session_id] = sess
        return sess
    except Exception as exc:
        print(f"[OMI DB LOAD WARN] {exc}")
        return None


def get_session(session_id: str) -> dict | None:
    return SESSIONS.get(session_id) or _load_from_db(session_id)


def save_answer(session_id: str, q_index: int, answer: str) -> dict:
    sess = get_session(session_id)
    if not sess:
        return {"ok": False, "status": 404, "message": "Sesi OMI tidak ditemukan."}
    if sess.get("finished"):
        return {"ok": False, "status": 409, "message": "Sesi OMI sudah selesai."}
    quiz = sess.get("quiz", [])
    if q_index < 0 or q_index >= len(quiz):
        return {"ok": False, "status": 400, "message": "Nomor soal tidak valid."}
    options = quiz[q_index].get("options", [])
    if answer not in options:
        return {"ok": False, "status": 400, "message": "Pilihan jawaban tidak valid."}
    sess.setdefault("answers", {})[q_index] = answer
    sess["current_index"] = q_index
    _persist(sess, "BERJALAN")
    return {"ok": True, "status": 200, "message": "Jawaban tersimpan."}


def heartbeat(session_id: str) -> int:
    sess = get_session(session_id)
    if not sess:
        return 404
    if sess.get("finished"):
        return 204
    try:
        touch_session_heartbeat(session_id)
    except Exception as exc:
        print(f"[OMI HEARTBEAT WARN] {exc}")
    return 204


def anti_cheat(session_id: str, violation_count: int, reason: str = "Pindah tab") -> dict:
    sess = get_session(session_id)
    if not sess:
        return {"ok": False, "status": 404, "forced": False, "count": 0}
    state = sess.setdefault("anti_cheat", {"detected": False, "reason": "", "violation_count": 0, "max_violations": MAX_ANTI_CHEAT})
    current = max(0, int(state.get("violation_count", 0) or 0))
    requested = max(0, int(violation_count or 0))
    count = min(MAX_ANTI_CHEAT, max(current, requested))
    state.update({"violation_count": count, "reason": str(reason or "Pindah tab")[:100], "max_violations": MAX_ANTI_CHEAT})
    forced = count >= MAX_ANTI_CHEAT
    state["detected"] = forced
    if forced:
        sess["finished"] = True
        _persist(sess, "SELESAI")
    else:
        _persist(sess, "BERJALAN")
    return {"ok": True, "status": 200, "forced": forced, "count": count, "max": MAX_ANTI_CHEAT}


def mark_finished(session_id: str) -> dict | None:
    sess = get_session(session_id)
    if not sess:
        return None
    sess["finished"] = True
    _persist(sess, "SELESAI")
    return sess


def public_quiz(sess: dict) -> list[dict]:
    public = []
    for item in sess.get("quiz", []):
        public.append({"id": item.get("id"), "question": item.get("question", ""), "options": item.get("options", [])})
    return public
