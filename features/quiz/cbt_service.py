"""Application service for the student CBT workspace.

The service owns CBT business rules; HTTP routes only translate requests and
responses. Existing timing, answer persistence, anti-cheat and scoring rules
are preserved from the audited FastAPI implementation.
"""
from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from infrastructure.ai.policy import normalize_custom_timer_config
from infrastructure.database.quiz import get_custom_quiz_from_db, load_session_review_from_db
from infrastructure.database.monitoring import update_progress_siswa, touch_session_heartbeat
from infrastructure.ai.quiz import get_ai_hint_stream
from infrastructure.database.schema import create_table_if_not_exists
from .session_store import get_session, put_session

STREAMLIT_URL = "https://robomantap-intelligence.streamlit.app/"


def initialize_database() -> None:
    try:
        create_table_if_not_exists()
    except Exception as exc:
        print(f"[DB INIT WARN] {exc}")


def parse_wib_datetime(dt_str):
    if not dt_str:
        return None
    try:
        s = str(dt_str).strip().replace(" ", "T")
        dt_raw = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt_raw.tzinfo is not None:
            return dt_raw.astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)
        return dt_raw
    except Exception as exc:
        print(f"[DATE PARSE ERROR] Gagal parse tanggal '{dt_str}': {exc}")
        return None


def normalize_jenjang(value: str) -> str:
    value = str(value or "MA").strip()
    upper = value.upper()
    if "MTS" in upper:
        return "MTs"
    if "MA" in upper:
        return "MA"
    return value


def build_detail_answers(sess: dict):
    quiz = sess.get("quiz", []) if isinstance(sess, dict) else []
    answers = sess.get("answers", {}) if isinstance(sess, dict) else {}
    detail = []
    for idx, item in enumerate(quiz):
        user_ans = answers.get(idx) or answers.get(str(idx))
        if user_ans is None:
            detail.append(None)
            continue
        correct_ans = item.get("correct_answer") or item.get("key")
        detail.append(user_ans == correct_ans)
    return detail


def normalized_anti_cheat(sess: dict) -> dict:
    current = sess.get("anti_cheat") if isinstance(sess, dict) else None
    if not isinstance(current, dict):
        current = {}
    return {
        "detected": bool(current.get("detected", False)),
        "reason": str(current.get("reason", "") or ""),
        "violation_count": max(0, int(current.get("violation_count", 0) or 0)),
        "max_violations": max(1, int(current.get("max_violations", 3) or 3)),
    }


def verify_and_create_session(nama: str, kelas: str, absen: str, token: str):
    clean_token = token.strip().upper()
    nama_clean, kelas_clean, absen_clean = nama.strip(), kelas.strip(), absen.strip()
    quiz_package = get_custom_quiz_from_db(clean_token)
    if not quiz_package:
        return {"ok": False, "error": "❌ Kode Kuis tidak ditemukan atau belum diterbitkan!"}

    config = normalize_custom_timer_config(quiz_package.get("config", {}) or {})
    now_wib = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)
    active_from_raw, active_until_raw = config.get("active_from"), config.get("active_until")
    if active_from_raw and active_until_raw:
        dt_from, dt_until = parse_wib_datetime(active_from_raw), parse_wib_datetime(active_until_raw)
        if dt_from and now_wib < dt_from:
            time_start = config.get("time_start_str", dt_from.strftime("%H:%M"))
            return {"ok": False, "error": f"⏰ Kuis Belum Dibuka! Kuis baru dapat diakses pada pukul {time_start} WIB."}
        if dt_until and now_wib > dt_until:
            time_end = config.get("time_end_str", dt_until.strftime("%H:%M"))
            return {"ok": False, "error": f"❌ Kode Kuis Sudah Kedaluwarsa! Masa aktif kuis ini telah berakhir pada pukul {time_end} WIB."}

    master_quiz = quiz_package.get("quiz", []) or []
    packages = config.get("packages") or [master_quiz]
    selected_quiz = random.choice(packages) if packages else master_quiz
    session_id = str(uuid.uuid4())[:8]
    anti_cheat = {"detected": False, "reason": "", "violation_count": 0, "max_violations": 3}
    put_session(session_id, {
        "nama": nama_clean, "kelas": kelas_clean, "absen": absen_clean,
        "token": clean_token, "config": config, "quiz": selected_quiz,
        "answers": {}, "current_index": 0, "start_time": datetime.now(timezone.utc),
        "anti_cheat": anti_cheat,
    })
    try:
        update_progress_siswa(session_id=session_id, nama=nama_clean,
            jenjang=normalize_jenjang(config.get("jenjang", "MA")),
            mapel=config.get("mapel", "Kuis"), soal_sekarang=1,
            detail_jawaban=[None] * len(selected_quiz), status="BERJALAN",
            is_custom=True, anti_cheat=anti_cheat)
    except Exception as exc:
        print(f"⚠️ Warning Sync Supabase (Start Exam): {exc}")
    return {"ok": True, "session_id": session_id}


def exam_context(session_id: str):
    sess = get_session(session_id)
    if not sess:
        return None, None
    if sess.get("finished") or normalized_anti_cheat(sess).get("detected"):
        return sess, {"redirect": f"{STREAMLIT_URL.rstrip('/')}/?review_session={session_id}"}
    config = normalize_custom_timer_config(sess.get("config", {}) or {})
    sess["config"] = config
    duration_seconds = int(config.get("timer_seconds", 0) or 0)
    start_time = sess.get("start_time") or datetime.now(timezone.utc)
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    remaining_s = max(0, int(duration_seconds - max(0.0, (datetime.now(timezone.utc) - start_time).total_seconds()))) if duration_seconds > 0 else 0
    duration_label = (
        f"{duration_seconds // 3600} jam {(duration_seconds % 3600) // 60} menit" if duration_seconds >= 3600 and duration_seconds % 60 == 0 else
        f"{duration_seconds // 3600} jam {(duration_seconds % 3600) // 60} menit {duration_seconds % 60} detik" if duration_seconds >= 3600 else
        f"{duration_seconds // 60} menit {duration_seconds % 60} detik" if duration_seconds > 0 else "Tanpa batas waktu"
    )
    return sess, {
        "session_id": session_id, "sess": sess,
        "mapel": config.get("mapel", "Kuis RoboMANTAP"), "materi": config.get("materi", "Umum"),
        "nama": sess.get("nama", "Siswa"), "kelas": sess.get("kelas", "-"), "absen": sess.get("absen", "-"),
        "jumlah_soal": len(sess.get("quiz", [])), "durasi_menit": (duration_seconds + 59) // 60 if duration_seconds > 0 else 0,
        "duration_seconds": duration_seconds, "durasi_label": duration_label,
        "quiz_json": json.dumps(sess.get("quiz", [])), "answers_json": json.dumps(sess.get("answers", {})),
        "remaining_seconds": remaining_s, "anti_cheat_json": json.dumps(normalized_anti_cheat(sess)),
    }


def save_answer(session_id: str, q_index: int, answer: str):
    sess = get_session(session_id)
    if not sess:
        return 404, ""
    if sess.get("finished"):
        return 409, ""
    config = normalize_custom_timer_config(sess.get("config", {}) or {})
    sess["config"] = config
    duration_seconds = int(config.get("timer_seconds", 0) or 0)
    start_time = sess.get("start_time")
    if duration_seconds > 0 and start_time:
        if start_time.tzinfo is None: start_time = start_time.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - start_time).total_seconds() >= duration_seconds:
            return 409, "TIMEOUT"
    quiz = sess.get("quiz", []) or []
    if q_index < 0 or q_index >= len(quiz): return 400, ""
    sess.setdefault("answers", {})[q_index] = str(answer).strip()
    sess["answers"][str(q_index)] = str(answer).strip()
    sess["current_index"] = q_index
    try:
        update_progress_siswa(session_id=session_id, nama=sess.get("nama", "Siswa"),
            jenjang=normalize_jenjang(config.get("jenjang", "Kuis")), mapel=config.get("mapel", "Kuis"),
            soal_sekarang=q_index + 1, detail_jawaban=build_detail_answers(sess), status="BERJALAN",
            is_custom=True, anti_cheat=normalized_anti_cheat(sess))
    except Exception as exc: print(f"⚠️ Warning Sync Supabase (Save Answer): {exc}")
    return 200, ""


def heartbeat(session_id: str):
    sess = get_session(session_id)
    if not sess: return 404
    if sess.get("finished"): return 204
    try: touch_session_heartbeat(session_id)
    except Exception as exc: print(f"⚠️ Warning Heartbeat: {exc}")
    return 204


def anti_cheat_event(session_id: str, violation_count: int = 0, reason: str = "Pindah tab"):
    sess = get_session(session_id)
    if not sess: return 404, ""
    anti_cheat = normalized_anti_cheat(sess)
    effective_count = min(max(anti_cheat["violation_count"], max(0, int(violation_count or 0))), anti_cheat["max_violations"])
    anti_cheat["violation_count"] = effective_count
    if effective_count > 0: anti_cheat["reason"] = str(reason or "Pindah tab").strip()[:100] or "Pindah tab"
    is_forced_stop = effective_count >= anti_cheat["max_violations"]
    anti_cheat["detected"] = is_forced_stop
    sess["anti_cheat"] = anti_cheat
    try:
        update_progress_siswa(session_id=session_id, nama=sess.get("nama", "Siswa"),
            jenjang=normalize_jenjang(sess.get("config", {}).get("jenjang", "MA")), mapel=sess.get("config", {}).get("mapel", "Kuis"),
            soal_sekarang=max(1, int(sess.get("current_index", 0)) + 1), detail_jawaban=build_detail_answers(sess),
            status="SELESAI" if is_forced_stop else "BERJALAN", is_custom=True,
            user_answers_dict=sess.get("answers", {}) if is_forced_stop else None,
            quiz_data_list=sess.get("quiz", []) if is_forced_stop else None, anti_cheat=anti_cheat)
    except Exception as exc: print(f"⚠️ Warning Sync Supabase (Anti-Cheat): {exc}")
    if is_forced_stop:
        sess["finished"] = True
        return 200, "STOP"
    return 200, "WARN"


def submit_exam(session_id: str, anti_cheat_detected: str = "0", anti_cheat_reason: str = "", anti_cheat_count: int = 0):
    sess = get_session(session_id)
    if not sess: return None
    quiz, answers = sess.get("quiz", []) or [], sess.get("answers", {}) or {}
    nama_lengkap = sess.get("nama", "").strip()
    benar = salah = kosong = 0
    detail_ans = []
    for idx, item in enumerate(quiz):
        user_ans = answers.get(idx) or answers.get(str(idx)); correct_ans = item.get("correct_answer") or item.get("key")
        if not user_ans: kosong += 1; detail_ans.append(False)
        elif user_ans == correct_ans: benar += 1; detail_ans.append(True)
        else: salah += 1; detail_ans.append(False)
    total_soal = len(quiz); skor = int(round((benar / total_soal) * 100)) if total_soal else 0
    anti_cheat = normalized_anti_cheat(sess)
    form_detected = str(anti_cheat_detected).strip().lower() in {"1", "true", "yes", "on"}
    form_count = max(0, int(anti_cheat_count or 0))
    if form_detected or form_count > 0:
        anti_cheat["violation_count"] = min(anti_cheat["max_violations"], max(anti_cheat["violation_count"], form_count))
        if anti_cheat["violation_count"] > 0: anti_cheat["reason"] = str(anti_cheat_reason or "Pindah tab").strip()[:100] or "Pindah tab"
        anti_cheat["detected"] = form_detected or anti_cheat["violation_count"] >= anti_cheat["max_violations"]
    sess["anti_cheat"] = anti_cheat
    try:
        update_progress_siswa(session_id=session_id, nama=nama_lengkap,
            jenjang=normalize_jenjang(sess.get("config", {}).get("jenjang", "MA")), mapel=sess.get("config", {}).get("mapel", "Matematika"),
            soal_sekarang=total_soal, detail_jawaban=detail_ans, status="SELESAI", is_custom=True,
            user_answers_dict=answers, quiz_data_list=quiz, anti_cheat=anti_cheat)
    except Exception as exc: print(f"⚠️ Warning Sync Supabase (Submit Exam): {exc}")
    sess["finished"] = True
    return {"nama": nama_lengkap.split()[0] if nama_lengkap else "Santri MANTAP", "skor": skor,
            "benar": benar, "salah": salah, "kosong": kosong, "total": total_soal,
            "streamlit_url": f"{STREAMLIT_URL.rstrip('/')}/?review_session={session_id}"}


_hint_cache = {}
def hint(curr_idx: int, mapel: str, question: str, attempt_input: str):
    attempt_str = attempt_input.strip()
    if not attempt_str:
        return '<div class="p-2.5 bg-blue-950/40 border border-blue-500/30 text-blue-300 rounded-lg text-xs mt-2">💡 Tolong ketik sedikit ide kamu dulu ya, biar RoboMANTAP bisa kasih petunjuk yang pas!</div>'
    key = (mapel, curr_idx, question, attempt_str)
    if key in _hint_cache: hint_text = _hint_cache[key]
    else:
        try:
            hint_text = "".join(get_ai_hint_stream(question, attempt_str, mapel))
            if hint_text and "⚠️" not in hint_text: _hint_cache[key] = hint_text
        except Exception as exc:
            hint_text = f"⚠️ Maaf, RoboMANTAP sedang sibuk sebentar. Coba tekan tombol diskusi lagi ya! ({exc})"
    return f'<div class="p-3 bg-slate-900 border border-slate-800 rounded-lg text-slate-200 text-xs leading-relaxed mt-2 animate-fade-in"><div class="font-bold text-emerald-400 mb-1">🧕🏼 RoboMANTAP:</div><div>{hint_text}</div></div>'
