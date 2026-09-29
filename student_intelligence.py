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
        recs.append(f"🎯 <b>[PRIORITAS UTAMA]</b> Alokasikan 60% waktu belajar berikutnya untuk <b>{weakest}</b> sebelum berpindah ke matapelajaran baru.")
        
    for topic, mastery in profile.get("weakest_topics", [])[:2]:
        if mastery < 70:
            recs.append(f"🧩 <b>[PEMAHAMAN KONSEP]</b> Kuatkan kembali topik <b>{topic}</b> (Akurasi: {mastery:.0f}%). Gunakan metode latihan bertahap dari soal dasar ke penalaran.")
    if profile.get("trend") == "declining":
        recs.append("⏱️ <b>[MANAJEMEN ENERGI]</b> Performa tercatat menurun. Terapkan teknik <b>Pomodoro</b> (25 menit latihan + 5 menit istirahat) dan evaluasi setiap pembahasan.")
    if profile.get("answer_completion", 100) < 80:
        recs.append("⚡ <b>[STRATEGI EKSEKUSI]</b> Akurasi jawaban masih di bawah 80%. Prioritaskan <b>eliminasi jawaban</b> yang pasti salah sebelum memilih opsi akhir.")
    if not recs:
        recs.append("🌟 <b>[OPTIMASI PERFORMA]</b> Pemahaman dasar sudah sangat baik, Tantang dirimu dengan simulasi soal tingkat kesulitan tinggi.")
    return recs[:4]


def _start_adaptive_practice(name: str, grade: str, profile: dict) -> tuple[bool, str]:
    focus = profile.get("weakest_subject")
    topics = [topic for topic, mastery in profile.get("weakest_topics", []) if mastery < 80][:3]
    if not focus or grade == "Semua Jenjang":
        return False, "Pilih jenjang yang spesifik agar generator latihan dapat memilih kisi-kisi yang tepat."

    if "(Quiz)" in str(focus):
        return False, "Area terlemah berasal dari Kuis GuruMANTAP. Gunakan latihan adaptif dari sesi guru terlebih dahulu."

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
    """Render the additive Student Intelligence workspace with World-Class Responsive UI."""
    
    # -------------------------------------------------------------------------
    # 1. INJECT HIGH-END GLASSMORPHIC & SCORECARD CSS
    # -------------------------------------------------------------------------
    ui_css = """
    <style>
    /* Metric Scorecard Grid */
    .eval-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin: 15px 0 22px 0;
    }
    @media (max-width: 640px) {
        .eval-grid {
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
        }
    }
    .eval-card {
        border-radius: 12px;
        padding: 14px 10px;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.25);
        backdrop-filter: blur(8px);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .eval-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
    }
    .eval-title {
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 5px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .eval-value {
        font-size: 22px;
        font-weight: 800;
        line-height: 1.2;
    }

    /* Custom Glassmorphic Alert Banners */
    .status-banner {
        border-radius: 12px;
        padding: 14px 18px;
        margin-bottom: 25px;
        display: flex;
        align-items: center;
        gap: 12px;
        font-size: 13px;
        font-weight: 600;
        line-height: 1.5;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    .status-banner-red {
        background: linear-gradient(135deg, rgba(127, 29, 29, 0.4) 0%, rgba(69, 10, 10, 0.7) 100%);
        border: 1px solid rgba(239, 68, 68, 0.5);
        color: #fca5a5;
    }
    .status-banner-yellow {
        background: linear-gradient(135deg, rgba(120, 53, 15, 0.4) 0%, rgba(69, 26, 3, 0.7) 100%);
        border: 1px solid rgba(245, 158, 11, 0.5);
        color: #fde68a;
    }
    .status-banner-green {
        background: linear-gradient(135deg, rgba(6, 78, 59, 0.4) 0%, rgba(2, 44, 34, 0.7) 100%);
        border: 1px solid rgba(5, 150, 105, 0.5);
        color: #a7f3d0;
    }

    /* Modern Progress Bar Wrapper for Topics */
    .topic-item {
        background: rgba(30, 41, 59, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 10px 14px;
        margin-bottom: 10px;
    }
    .topic-header {
        display: flex;
        justify-content: space-between;
        font-size: 12px;
        font-weight: 700;
        margin-bottom: 6px;
        color: #e2e8f0;
    }
    .topic-bar-bg {
        width: 100%;
        height: 8px;
        background: rgba(255, 255, 255, 0.1);
        border-radius: 4px;
        overflow: hidden;
    }
    .topic-bar-fill {
        height: 100%;
        border-radius: 4px;
        transition: width 0.5s ease;
    }

    /* Action Recommendation List */
    .rec-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.4) 0%, rgba(15, 23, 42, 0.6) 100%);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-left: 4px solid #10b981;
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 10px;
        font-size: 13px;
        color: #f1f5f9;
        display: flex;
        align-items: flex-start;
        gap: 12px;
    }
    .rec-num {
        background: rgba(16, 185, 129, 0.2);
        color: #34d399;
        font-weight: 800;
        border-radius: 50%;
        width: 22px;
        height: 22px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 11px;
        flex-shrink: 0;
    }
    </style>
    """
    st.markdown(ui_css, unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # 2. HERO HEADER
    # -------------------------------------------------------------------------
    st.markdown("""
    <div class="premium-hero automation-hero" style="margin-bottom: 20px;">
      <div class="premium-kicker">UPN • STUDENT INTELLIGENCE</div>
      <div class="premium-title">My Learning <span>Intelligence</span></div>
      <div class="premium-subtitle">Bukan sekadar melihat nilai. Sistem RoboMANTAP membaca riwayat pengerjaan Kamu untuk membantu menentukan fokus belajar berikutnya!</div>
      <div class="premium-pills">
        <span class="chip chip-green">🎓 Mastery</span>
        <span class="chip chip-blue">🎯 Prioritas</span>
        <span class="chip chip-purple">🔄 Adaptive Practice</span>
        <span class="chip chip-gold">🚨 Early Signal</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # 3. IDENTITY FORM
    # -------------------------------------------------------------------------
    with st.form("student_intelligence_identity", clear_on_submit=False):
        c1, c2 = st.columns([2.2, 1.2])
        with c1:
            entered_name = st.text_input("Nama Siswa", value=nama_siswa, placeholder="Masukkan nama yang digunakan saat kuis")
        with c2:
            grade_options = ["Semua Jenjang", "MTs (Sederajat SMP)", "MA (Sederajat SMA)"]
            selected_index = grade_options.index(jenjang) if jenjang in grade_options else 0
            grade = st.selectbox("Jenjang", grade_options, index=selected_index)
        submitted = st.form_submit_button("🔍 BUKA INTELLIGENCE SAYA", type="primary", use_container_width=True)

    if not submitted and not entered_name.strip():
        st.info("💡 Masukkan Nama Lengkap Kamu untuk membaca riwayat belajar yang sudah tersimpan.")
        return

    name = entered_name.strip()
    sessions = fetch_student_sessions(name, grade)
    if not sessions:
        st.warning("⚠️ Belum ditemukan sesi belajar dengan nama tersebut. Pastikan nama sama seperti saat mengerjakan kuis.")
        return

    profile = build_student_profile(sessions)
    save_student_profile(name, grade, profile)

    st.session_state.student_intelligence_name = name
    st.session_state.student_intelligence_grade = grade

    # -------------------------------------------------------------------------
    # 4. SCORECARD GRID METRICS (MODERN MOBILE-FRIENDLY UI)
    # -------------------------------------------------------------------------
    avg = profile["average_score"]
    attempts = profile["attempts"]
    completion = profile["answer_completion"]
    trend_raw = profile["trend"]
    risk = profile["risk_label"]

    trend_icon = {"improving": "📈", "declining": "📉", "stable": "➡️"}.get(trend_raw, "➡️")
    trend_title = {"improving": "Meningkat", "declining": "Menurun", "stable": "Stabil"}.get(trend_raw, "Stable")

    # Dynamic styling for trend card
    if trend_raw == "improving":
        trend_card_bg = "background: linear-gradient(135deg, rgba(6, 78, 59, 0.45) 0%, rgba(2, 44, 34, 0.75) 100%); border: 1px solid rgba(5, 150, 105, 0.45);"
        trend_title_color = "#a7f3d0"
        trend_val_color = "#34d399"
    elif trend_raw == "declining":
        trend_card_bg = "background: linear-gradient(135deg, rgba(127, 29, 29, 0.35) 0%, rgba(69, 10, 10, 0.65) 100%); border: 1px solid rgba(239, 68, 68, 0.4);"
        trend_title_color = "#fca5a5"
        trend_val_color = "#f87171"
    else:
        trend_card_bg = "background: linear-gradient(135deg, rgba(55, 65, 81, 0.35) 0%, rgba(31, 41, 55, 0.65) 100%); border: 1px solid rgba(156, 163, 175, 0.35);"
        trend_title_color = "#d1d5db"
        trend_val_color = "#9ca3af"

    eval_html = f"""
    <div class="eval-grid">
        <!-- Rata-rata Skor -->
        <div class="eval-card" style="background: linear-gradient(135deg, rgba(120, 53, 15, 0.45) 0%, rgba(69, 26, 3, 0.75) 100%); border: 1px solid rgba(245, 158, 11, 0.5);">
            <div class="eval-title" style="color: #fde68a;">🎯 Rata-Rata</div>
            <div class="eval-value" style="color: #fbbf24;">{avg:.0f}%</div>
        </div>
        <!-- Sesi Selesai -->
        <div class="eval-card" style="background: linear-gradient(135deg, rgba(6, 78, 59, 0.45) 0%, rgba(2, 44, 34, 0.75) 100%); border: 1px solid rgba(5, 150, 105, 0.45);">
            <div class="eval-title" style="color: #a7f3d0;">🎓 Sesi Selesai</div>
            <div class="eval-value" style="color: #34d399;">{attempts}</div>
        </div>
        <!-- Kelengkapan Jawaban -->
        <div class="eval-card" style="background: linear-gradient(135deg, rgba(30, 58, 138, 0.4) 0%, rgba(15, 23, 42, 0.75) 100%); border: 1px solid rgba(59, 130, 246, 0.45);">
            <div class="eval-title" style="color: #bfdbfe;">✅ Akurasi Jawaban</div>
            <div class="eval-value" style="color: #60a5fa;">{completion:.0f}%</div>
        </div>
        <!-- Tren Performa -->
        <div class="eval-card" style="{trend_card_bg}">
            <div class="eval-title" style="color: {trend_title_color};">{trend_icon} Perkembangan</div>
            <div class="eval-value" style="color: {trend_val_color}; font-size: 18px;">{trend_title}</div>
        </div>
    </div>
    """
    
    st.markdown('<div style="font-size: 21px; font-weight: 700; color: #f8fafc; margin-bottom: 10px;">🎯 Kondisi Belajar Saat Ini</div>', unsafe_allow_html=True)
    st.markdown(eval_html, unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # 5. STATUS RISK BANNER
    # -------------------------------------------------------------------------
    if risk == "HIGH ATTENTION":
        st.markdown("""
        <div class="status-banner status-banner-red">
            <span style="font-size: 18px;">🚨</span>
            <div><b>PERLU PERHATIAN EKSTRA</b> — Ada beberapa materi yang nilainya masih di bawah target, Yuk luangkan waktu untuk mempelajari dan latihan ulang topik tersebut!</div>
        </div>
        """, unsafe_allow_html=True)
    elif risk == "WATCH":
        st.markdown("""
        <div class="status-banner status-banner-yellow">
            <span style="font-size: 18px;">⚡</span>
            <div><b>PERLU DITINGKATKAN</b> — Pemahamanmu sudah cukup baik, tapi masih ada beberapa materi yang bisa ditingkatkan lagi agar hasilmu makin maksimal.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="status-banner status-banner-green">
            <span style="font-size: 18px;">🟢</span>
            <div><b>PERFORMA SANGAT BAIK</b> — Luar biasa! Progres dan nilai belajarmu sudah sangat baik serta konsisten, Pertahankan semangat belajarmu!</div>
        </div>
        """, unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # 6. MASTERY & TOPIC BREAKDOWN
    # -------------------------------------------------------------------------
    left, right = st.columns(2)
    with left:
        # Judul Ringkas & Ukuran Pas untuk HP (15px)
        st.markdown('<div style="font-size: 21px; font-weight: 700; color: #f8fafc; margin-bottom: 10px;">📚 Pemahaman Mata Pelajaran</div>', unsafe_allow_html=True)
        st.markdown('<div style="font-size: 11px; color: #94a3b8; margin-bottom: 10px;">Rata-rata nilai akhir ujian, kuis atau pengerjaan secara keseluruhan</div>', unsafe_allow_html=True)
        if profile["subject_mastery"]:
            for mapel, mastery in sorted(profile["subject_mastery"].items(), key=lambda x: x[1]):
                m_val = min(100.0, max(0.0, mastery))
                bar_color = "#f87171" if m_val < 50 else "#fbbf24" if m_val < 75 else "#34d399"
                
                mapel_html = f"""
                <div class="topic-item" style="margin-bottom: 8px;">
                    <div class="topic-header">
                        <span style="font-size: 12px; font-weight: 700;">{mapel}</span>
                        <span style="color: {bar_color}; font-size: 12px; font-weight: 800;">{m_val:.0f}%</span>
                    </div>
                    <div class="topic-bar-bg" style="height: 8px;">
                        <div class="topic-bar-fill" style="width: {m_val}%; background: {bar_color};"></div>
                    </div>
                </div>
                """
                st.markdown(mapel_html, unsafe_allow_html=True)
        else:
            st.caption("Data pemahaman per mata pelajaran belum cukup.")

    with right:
        st.markdown('<div style="font-size: 21px; font-weight: 700; color: #f8fafc; margin-bottom: 10px;">🧩 Topik Perlu Perhatian</div>', unsafe_allow_html=True)
        st.markdown('<div style="font-size: 11px; color: #94a3b8; margin-bottom: 10px;">Akurasi kebenaran menjawab soal dibawah 80% (< 80%)</div>', unsafe_allow_html=True)
        weak = [(topic, mastery) for topic, mastery in profile.get("weakest_topics", []) if mastery < 80]    
        if weak:
            for topic, mastery in weak[:5]:
                m_val = min(100.0, max(0.0, mastery))
                bar_color = "#f87171" if m_val < 50 else "#fbbf24"
                
                topic_html = f"""
                <div class="topic-item" style="margin-bottom: 8px;">
                    <div class="topic-header">
                        <span style="font-size: 12px; font-weight: 700;">{topic}</span>
                        <span style="color: {bar_color}; font-size: 12px; font-weight: 800;">{m_val:.0f}%</span>
                    </div>
                    <div class="topic-bar-bg" style="height: 8px;">
                        <div class="topic-bar-fill" style="width: {m_val}%; background: {bar_color};"></div>
                    </div>
                </div>
                """
                st.markdown(topic_html, unsafe_allow_html=True)
        else:
            st.success("🎉 Luar biasa! Semua topik yang kamu kerjakan nilainya sudah di atas target (≥80%).")

    # -------------------------------------------------------------------------
    # 7. ACTION RECOMMENDATIONS & ADAPTIVE PRACTICE
    # -------------------------------------------------------------------------
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div style="font-size: 21px; font-weight: 700; color: #f8fafc; margin-bottom: 10px;">🚀 What Should I Do Now?</div>', unsafe_allow_html=True)
    recommendations = _subject_recommendations(profile)
    
    for idx, rec_text in enumerate(recommendations, 1):
        rec_html = f"""
        <div class="rec-card">
            <div class="rec-num">{idx}</div>
            <div>{rec_text}</div>
        </div>
        """
        st.markdown(rec_html, unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # BANNER WHATSAPP BOT INTEGRATION
    # -------------------------------------------------------------------------
    # 1. Masukkan nomor WhatsApp Bot Anda (Gunakan format internasional tanpa '+', contoh: 6281234567890)
    NO_WA_BOT = "6283141694735"  # <-- Ganti dengan nomor WA Bot Anda
    
    # 2. Pesan otomatis awal dari siswa
    # Pesan awal yang ringkas & bersih
    pesan_otomatis = f"Halo RoboMANTAP! Saya {name} ({grade}), ingin latihan soal dan belajar lewat WhatsApp."
    import urllib.parse
    pesan_encoded = urllib.parse.quote(pesan_otomatis)
    wa_link = f"https://wa.me/{NO_WA_BOT}?text={pesan_encoded}"
    
    # 3. HTML Banner Bergaya Modern & Responsive
    wa_card_html = f"""
    <a href="{wa_link}" target="_blank" style="text-decoration: none;">
        <div style="
            background: linear-gradient(135deg, rgba(6, 78, 59, 0.5) 0%, rgba(2, 44, 34, 0.8) 100%);
            border: 1px solid rgba(34, 197, 94, 0.4);
            border-radius: 12px;
            padding: 14px 18px;
            margin: 15px 0 20px 0;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 4px 15px rgba(0,0,0,0.25);
            transition: all 0.2s ease;
        ">
            <div style="display: flex; align-items: center; gap: 14px;">
                <div style="
                    background: #25D366; 
                    width: 42px; 
                    height: 42px; 
                    border-radius: 50%; 
                    display: flex; 
                    align-items: center; 
                    justify-content: center;
                    font-size: 22px;
                    flex-shrink: 0;
                ">💬</div>
                <div>
                    <div style="font-size: 14px; font-weight: 800; color: #a7f3d0; margin-bottom: 2px;">
                        Latihan Kuis via WhatsApp Bot
                    </div>
                    <div style="font-size: 11px; color: #cbd5e1; line-height: 1.3;">
                        Lebih praktis & hemat kuota. Kirim pesan ke RoboMANTAP Bot untuk mulai kuis langsung di WA!
                    </div>
                </div>
            </div>
            <div style="
                background: #25D366;
                color: #022c22;
                font-size: 12px;
                font-weight: 800;
                padding: 8px 14px;
                border-radius: 8px;
                white-space: nowrap;
                margin-left: 10px;
            ">
                Chat WA →
            </div>
        </div>
    </a>
    """
    
    st.markdown(wa_card_html, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
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
            st.success("✅ Rencana belajar tersimpan sebagai aktivitas Student Intelligence.")

    # -------------------------------------------------------------------------
    # 8. AUDIT SESSION HISTORY
    # -------------------------------------------------------------------------
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
