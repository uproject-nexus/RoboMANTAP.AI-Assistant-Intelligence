"""RoboMANTAP Student Intelligence Layer.

This module is intentionally additive: it reads the existing `sesi_ujian`
records and builds a student-facing intelligence layer without changing the
existing CBT/Teacher workflows.
"""
from __future__ import annotations

import json
import math
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import text

from ai_engine import init_db_connection


STUDENT_INTELLIGENCE_VERSION = "1.0"


def ensure_student_intelligence_tables() -> bool:
    """Create only the additive tables used by Student Intelligence."""
    conn = init_db_connection()
    if not conn:
        return False

    statements = [
        """
        CREATE TABLE IF NOT EXISTS student_intelligence_profiles (
            student_key VARCHAR(180) PRIMARY KEY,
            nama_siswa VARCHAR(150) NOT NULL,
            jenjang VARCHAR(80),
            profile_data JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS student_intelligence_actions (
            id BIGSERIAL PRIMARY KEY,
            student_key VARCHAR(180) NOT NULL,
            action_type VARCHAR(60) NOT NULL,
            title VARCHAR(200) NOT NULL,
            payload JSONB DEFAULT '{}'::jsonb,
            status VARCHAR(30) DEFAULT 'OPEN',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_student_intel_actions_student
            ON student_intelligence_actions (student_key, created_at DESC)
        """,
    ]
    try:
        with conn.session as s:
            for statement in statements:
                s.execute(text(statement))
                s.commit()
        return True
    except Exception as exc:
        print(f"[STUDENT INTELLIGENCE] table init warning: {exc}")
        return False


def _norm_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def student_key(nama_siswa: str, jenjang: str = "") -> str:
    return f"{_norm_name(nama_siswa)}|{_norm_name(jenjang)}"


def _json_value(value: Any, fallback: Any):
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _payload(row: Any) -> dict:
    raw = row.get("detail_jawaban") if isinstance(row, dict) else None
    raw = _json_value(raw, raw)
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {"detail_boolean": raw, "user_answers": {}, "quiz_data": []}
    return {"detail_boolean": [], "user_answers": {}, "quiz_data": []}


def fetch_student_sessions(nama_siswa: str, jenjang: str | None = None, limit: int = 80) -> list[dict]:
    conn = init_db_connection()
    if not conn or not nama_siswa.strip():
        return []

    where = "LOWER(TRIM(nama_siswa)) = LOWER(TRIM(:nama))"
    params = {"nama": nama_siswa.strip(), "limit": int(limit)}
    if jenjang and jenjang != "Semua Jenjang":
        where += " AND LOWER(TRIM(COALESCE(jenjang,''))) = LOWER(TRIM(:jenjang))"
        params["jenjang"] = jenjang

    query = f"""
        SELECT id_sesi, nama_siswa, jenjang, mapel, soal_sekarang,
               detail_jawaban, jumlah_benar, jumlah_salah, nilai_akhir,
               status, created_at, updated_at
        FROM sesi_ujian
        WHERE {where}
          AND status NOT IN ('TRIAL', 'ARCHIVED', 'HIDDEN', 'DRAFT')
        ORDER BY COALESCE(updated_at, created_at) DESC
        LIMIT :limit
    """
    try:
        with conn.session as s:
            rows = s.execute(text(query), params).mappings().all()
        return [dict(row) for row in rows]
    except Exception as exc:
        print(f"[STUDENT INTELLIGENCE] fetch warning: {exc}")
        return []


def _question_topic(question: str, mapel: str) -> str:
    """Lightweight topic label; never claims an AI-generated topic."""
    q = re.sub(r"\s+", " ", str(question or "")).strip()
    if not q:
        return str(mapel or "Umum")
    # Prefer explicit educational phrases when present.
    patterns = [
        r"(?:materi|topik|konsep)\s*[:\-]\s*([^.!?]{3,60})",
        r"tentang\s+([^.!?]{3,60})",
    ]
    for pattern in patterns:
        m = re.search(pattern, q, flags=re.I)
        if m:
            return m.group(1).strip()[:70]
    return str(mapel or "Umum")


def build_student_profile(sessions: list[dict]) -> dict:
    completed = [s for s in sessions if str(s.get("status", "")).upper() == "SELESAI"]
    total_attempts = len(completed)
    scores = [float(s.get("nilai_akhir") or 0) for s in completed]

    # Custom quizzes use 0-100. Standard OMI uses 40 max. Normalize to 0-100.
    normalized_scores = []
    for s in completed:
        score = float(s.get("nilai_akhir") or 0)
        mapel = str(s.get("mapel") or "")
        if "(Quiz)" not in mapel and score <= 40:
            score = max(0.0, min(100.0, score / 40.0 * 100.0))
        normalized_scores.append(score)

    by_subject: dict[str, list[float]] = defaultdict(list)
    correct_total = wrong_total = blank_total = 0
    question_records: list[dict] = []
    topic_stats: dict[str, list[bool]] = defaultdict(list)

    for session in sessions:
        payload = _payload(session)
        detail = payload.get("detail_boolean") or []
        answers = payload.get("user_answers") or {}
        quiz = payload.get("quiz_data") or []
        mapel = str(session.get("mapel") or "Umum").replace(" (Quiz)", "").strip()

        for value in detail:
            if value is True:
                correct_total += 1
            elif value is False:
                wrong_total += 1
            else:
                blank_total += 1

        if str(session.get("status", "")).upper() == "SELESAI":
            score = float(session.get("nilai_akhir") or 0)
            if "(Quiz)" not in str(session.get("mapel") or "") and score <= 40:
                score = max(0.0, min(100.0, score / 40.0 * 100.0))
            by_subject[mapel].append(score)

        if quiz and isinstance(detail, list):
            for idx, item in enumerate(quiz):
                if not isinstance(item, dict) or idx >= len(detail):
                    continue
                outcome = detail[idx]
                if outcome is None:
                    continue
                topic = str(item.get("topic") or item.get("submateri") or _question_topic(item.get("question", ""), mapel))
                topic_stats[topic].append(bool(outcome))
                question_records.append({
                    "mapel": mapel,
                    "topic": topic,
                    "correct": bool(outcome),
                    "question": str(item.get("question", "")),
                    "answer": answers.get(str(idx), answers.get(idx)),
                })

    subject_mastery = {
        subject: round(sum(values) / len(values), 1)
        for subject, values in by_subject.items()
        if values
    }
    topic_mastery = {
        topic: round(sum(values) / len(values) * 100, 1)
        for topic, values in topic_stats.items()
        if values
    }

    recent_scores = normalized_scores[:5]
    trend = "stable"
    if len(recent_scores) >= 4:
        recent = sum(recent_scores[:2]) / 2
        older = sum(recent_scores[2:4]) / 2
        if recent - older >= 7:
            trend = "improving"
        elif older - recent >= 7:
            trend = "declining"

    avg_score = round(sum(normalized_scores) / len(normalized_scores), 1) if normalized_scores else 0
    completion_ratio = (
        correct_total / (correct_total + wrong_total + blank_total) * 100
        if (correct_total + wrong_total + blank_total) else 0
    )
    consistency = min(100.0, total_attempts * 12.5) if total_attempts else 0

    weakest_subject = min(subject_mastery, key=subject_mastery.get) if subject_mastery else None
    weakest_topics = sorted(topic_mastery.items(), key=lambda x: x[1])[:5]

    # Risk is descriptive, not a clinical/disciplinary judgement.
    risk_points = 0
    if avg_score < 60:
        risk_points += 2
    elif avg_score < 75:
        risk_points += 1
    if trend == "declining":
        risk_points += 2
    if blank_total > correct_total * 0.25 and blank_total > 0:
        risk_points += 1
    if total_attempts < 2:
        risk_points += 1
    risk_label = "HIGH ATTENTION" if risk_points >= 4 else "WATCH" if risk_points >= 2 else "ON TRACK"

    return {
        "version": STUDENT_INTELLIGENCE_VERSION,
        "attempts": total_attempts,
        "average_score": avg_score,
        "recent_scores": recent_scores,
        "trend": trend,
        "correct": correct_total,
        "wrong": wrong_total,
        "blank": blank_total,
        "answer_completion": round(completion_ratio, 1),
        "consistency": round(consistency, 1),
        "subject_mastery": subject_mastery,
        "topic_mastery": topic_mastery,
        "weakest_subject": weakest_subject,
        "weakest_topics": weakest_topics,
        "risk_label": risk_label,
        "question_records": question_records[-60:],
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def save_student_profile(nama_siswa: str, jenjang: str, profile: dict) -> bool:
    conn = init_db_connection()
    if not conn:
        return False
    query = """
        INSERT INTO student_intelligence_profiles
            (student_key, nama_siswa, jenjang, profile_data, updated_at)
        VALUES (:key, :nama, :jenjang, :profile, NOW() AT TIME ZONE 'Asia/Jakarta')
        ON CONFLICT (student_key) DO UPDATE SET
            nama_siswa = EXCLUDED.nama_siswa,
            jenjang = EXCLUDED.jenjang,
            profile_data = EXCLUDED.profile_data,
            updated_at = NOW() AT TIME ZONE 'Asia/Jakarta'
    """
    try:
        with conn.session as s:
            s.execute(text(query), {
                "key": student_key(nama_siswa, jenjang),
                "nama": nama_siswa.strip(),
                "jenjang": jenjang,
                "profile": json.dumps(profile, default=str),
            })
            s.commit()
        return True
    except Exception as exc:
        print(f"[STUDENT INTELLIGENCE] profile save warning: {exc}")
        return False


def record_student_action(nama_siswa: str, jenjang: str, action_type: str, title: str, payload: dict | None = None) -> bool:
    conn = init_db_connection()
    if not conn:
        return False
    query = """
        INSERT INTO student_intelligence_actions
            (student_key, action_type, title, payload, status, created_at)
        VALUES (:key, :type, :title, :payload, 'OPEN', NOW() AT TIME ZONE 'Asia/Jakarta')
    """
    try:
        with conn.session as s:
            s.execute(text(query), {
                "key": student_key(nama_siswa, jenjang),
                "type": action_type,
                "title": title,
                "payload": json.dumps(payload or {}, default=str),
            })
            s.commit()
        return True
    except Exception as exc:
        print(f"[STUDENT INTELLIGENCE] action save warning: {exc}")
        return False


def _subject_recommendations(profile: dict) -> list[str]:
    recs = []
    weakest = profile.get("weakest_subject")
    if weakest:
        recs.append(f"Fokuskan sesi berikutnya pada {weakest} sebelum menambah target baru.")
    for topic, mastery in profile.get("weakest_topics", [])[:2]:
        if mastery < 70:
            recs.append(f"Latih kembali topik {topic} dengan soal bertahap dari dasar ke aplikasi.")
    if profile.get("trend") == "declining":
        recs.append("Gunakan sesi pendek 20–30 menit dan review kesalahan setelah latihan.")
    if profile.get("answer_completion", 100) < 80:
        recs.append("Latih strategi penyelesaian agar lebih banyak soal terjawab sebelum waktu berakhir.")
    if not recs:
        recs.append("Pertahankan pola latihan dan gunakan pembahasan untuk memperdalam konsep yang masih ragu.")
    return recs[:4]


def _start_adaptive_practice(name: str, grade: str, profile: dict) -> tuple[bool, str]:
    """Generate a real practice session from the student's weakest recorded areas."""
    focus = profile.get("weakest_subject")
    topics = [topic for topic, mastery in profile.get("weakest_topics", []) if mastery < 80][:3]
    if not focus or grade == "Semua Jenjang":
        return False, "Pilih jenjang yang spesifik agar generator latihan dapat memilih kisi-kisi yang tepat."

    # Custom teacher quizzes are not silently converted into OMI subjects.
    if "(Quiz)" in str(focus):
        return False, "Area terlemah berasal dari Kuis GuruMANTAP. Gunakan latihan adaptif dari sesi guru terlebih dahulu; generator OMI tidak akan mengubah kuis custom secara otomatis."

    try:
        from ai_engine import generate_quiz_batch, update_progress_siswa
        quiz = generate_quiz_batch(grade, focus, "Internal", topics)
        if not quiz or len(quiz) != 10:
            return False, "Generator belum berhasil membuat 10 soal adaptif. Silakan coba lagi."

        session_id = str(uuid.uuid4())
        st.session_state.jenjang = grade
        st.session_state.mapel = focus
        st.session_state.stage = "Internal"
        st.session_state.selected_submateri = topics
        st.session_state.quiz_data = quiz
        st.session_state.user_answers = {}
        st.session_state.current_index = 0
        st.session_state.session_id = session_id
        st.session_state.nama_siswa = name
        st.session_state.is_custom_quiz = False
        st.session_state.ai_hint_cache = {}
        st.session_state.ai_solution_cache = {}
        update_progress_siswa(
            session_id, name, grade, focus, 1, [], "BERJALAN",
            is_custom=False, user_answers_dict={}, quiz_data_list=quiz
        )
        st.session_state.page = "quiz"
        return True, "Latihan adaptif siap."
    except Exception as exc:
        print(f"[STUDENT INTELLIGENCE] adaptive practice warning: {exc}")
        return False, "Latihan adaptif gagal dibuat. Silakan coba lagi beberapa saat."


def render_student_intelligence_dashboard(nama_siswa: str = "", jenjang: str = "Semua Jenjang") -> None:
    """Render the additive Student Intelligence workspace."""
    st.markdown("""
    <div class="premium-hero automation-hero">
      <div class="premium-kicker">ROBO MANTAP • STUDENT INTELLIGENCE</div>
      <div class="premium-title">My Learning <span>Intelligence</span></div>
      <div class="premium-subtitle">Bukan sekadar melihat nilai. Sistem membaca riwayat pengerjaanmu untuk membantu menentukan fokus belajar berikutnya.</div>
      <div class="premium-pills">
        <span class="chip chip-green">🧠 Mastery</span>
        <span class="chip chip-blue">🎯 Prioritas</span>
        <span class="chip chip-purple">🔄 Adaptive Practice</span>
        <span class="chip chip-gold">🚨 Early Signal</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    with st.form("student_intelligence_identity", clear_on_submit=False):
        c1, c2 = st.columns([2.2, 1.2])
        with c1:
            entered_name = st.text_input("Nama siswa", value=nama_siswa, placeholder="Masukkan nama yang digunakan saat kuis")
        with c2:
            grade = st.selectbox("Jenjang", ["Semua Jenjang", "MTs (Sederajat SMP)", "MA (Sederajat SMA)"], index=(["Semua Jenjang", "MTs (Sederajat SMP)", "MA (Sederajat SMA)"].index(jenjang) if jenjang in ["Semua Jenjang", "MTs (Sederajat SMP)", "MA (Sederajat SMA)"] else 0))
        submitted = st.form_submit_button("🧠 BUKA INTELLIGENCE SAYA", type="primary", use_container_width=True)

    if not submitted and not entered_name.strip():
        st.info("Masukkan nama siswa untuk membaca riwayat belajar yang sudah tersimpan.")
        return

    name = entered_name.strip()
    sessions = fetch_student_sessions(name, grade)
    if not sessions:
        st.warning("Belum ditemukan sesi belajar dengan nama tersebut. Pastikan nama sama seperti saat mengerjakan kuis.")
        return

    profile = build_student_profile(sessions)
    save_student_profile(name, grade, profile)

    # Persist identity only for this active app session.
    st.session_state.student_intelligence_name = name
    st.session_state.student_intelligence_grade = grade

    avg = profile["average_score"]
    risk = profile["risk_label"]
    trend_icon = {"improving": "📈", "declining": "📉", "stable": "➡️"}.get(profile["trend"], "➡️")

    st.markdown("### 🎯 Kondisi Belajar Saat Ini")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Rata-rata", f"{avg:.0f}%")
    m2.metric("Sesi Selesai", profile["attempts"])
    m3.metric("Kelengkapan Jawaban", f"{profile['answer_completion']:.0f}%")
    m4.metric("Tren", f"{trend_icon} {profile['trend'].title()}")

    if risk == "HIGH ATTENTION":
        st.warning("🚨 **HIGH ATTENTION** — terdapat beberapa sinyal akademik yang layak ditindaklanjuti pada sesi belajar berikutnya.")
    elif risk == "WATCH":
        st.info("👀 **WATCH** — ada beberapa area yang sebaiknya dipantau dan dilatih kembali.")
    else:
        st.success("🟢 **ON TRACK** — pola belajar yang tercatat relatif stabil berdasarkan data yang tersedia.")

    left, right = st.columns(2)
    with left:
        st.markdown("### 📚 Mastery per Mata Pelajaran")
        if profile["subject_mastery"]:
            df_subject = pd.DataFrame(
                [{"Mata Pelajaran": k, "Mastery (%)": v} for k, v in profile["subject_mastery"].items()]
            ).sort_values("Mastery (%)")
            st.bar_chart(df_subject.set_index("Mata Pelajaran"))
        else:
            st.caption("Data mastery per mata pelajaran belum cukup.")

    with right:
        st.markdown("### 🧩 Topik yang Perlu Perhatian")
        weak = profile["weakest_topics"]
        if weak:
            for topic, mastery in weak[:5]:
                st.markdown(f"**{topic}** — {mastery:.0f}%")
                st.progress(min(1.0, max(0.0, mastery / 100)))
        else:
            st.caption("Detail topik akan semakin kaya setelah sesi baru menyimpan data soal.")

    st.markdown("### 🚀 What Should I Do Now?")
    recommendations = _subject_recommendations(profile)
    for idx, recommendation in enumerate(recommendations, 1):
        st.markdown(f"**{idx}.** {recommendation}")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 MULAI LATIHAN ADAPTIF", type="primary", use_container_width=True):
            record_student_action(name, grade, "ADAPTIVE_PRACTICE", "Mulai latihan adaptif", {"weakest_subject": profile.get("weakest_subject"), "weakest_topics": profile.get("weakest_topics", [])})
            with st.spinner("RoboMANTAP sedang merancang latihan berdasarkan area yang perlu diperkuat..."):
                ok, message = _start_adaptive_practice(name, grade, profile)
            if ok:
                st.success(message)
                st.rerun()
            else:
                st.warning(message)
    with c2:
        if st.button("📝 SIMPAN RENCANA BELAJAR", use_container_width=True):
            record_student_action(name, grade, "STUDY_PLAN", "Rencana belajar siswa", {"recommendations": recommendations})
            st.success("Rencana belajar tersimpan sebagai aktivitas Student Intelligence.")

    with st.expander("🔎 Lihat riwayat sesi yang menjadi dasar analisis"):
        rows = []
        for s in sessions[:20]:
            score = float(s.get("nilai_akhir") or 0)
            if "(Quiz)" not in str(s.get("mapel") or "") and score <= 40:
                score = max(0.0, min(100.0, score / 40 * 100))
            rows.append({
                "Waktu": s.get("updated_at") or s.get("created_at"),
                "Mapel": str(s.get("mapel") or "").replace(" (Quiz)", ""),
                "Status": s.get("status"),
                "Skor": round(score, 1),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.caption(f"Student Intelligence Engine v{STUDENT_INTELLIGENCE_VERSION} • Analisis dibuat dari data sesi yang tersimpan di RoboMANTAP.")
