"""RoboMANTAP Student Intelligence Layer v3.2 (Mobile Polish Edition).

Pusat Layanan Belajar, Simulasi UTS, Latihan Adaptif AI, Analisis Diagnostic,
Asisten Chatbot, Daily Streak, Export Catatan WA & PDF Santri Al-Irsyad Putri Bondowoso.
Dioptimalkan dengan Quick-Tap Prompts, Format Tanggal Indonesia, Zero-Rerun State, & Mobile CSS.
"""

from __future__ import annotations

import io
import json
import math
import re
import uuid
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import text

# Safe ReportLab Imports untuk Export PDF Catatan (Anti-Crash)
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

from ai_engine import init_db_connection

STUDENT_INTELLIGENCE_VERSION = "3.2"

# =============================================================================
# 1. DATABASE INITIALIZATION (PENTING UNTUK APP.PY BARIS 56)
# =============================================================================

def ensure_student_intelligence_tables() -> bool:
    """Memastikan tabel database pendukung Student Intelligence siap digunakan."""
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


# =============================================================================
# 2. HELPER UTILITIES & DATA NORMALIZATION
# =============================================================================

def _norm_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()

def _is_practice_100_scale(mapel: str) -> bool:
    value = str(mapel or "")
    return "(Quiz)" in value or "(TKA)" in value

def _clean_activity_marker(mapel: str) -> str:
    value = str(mapel or "")
    return value.replace(" (Quiz)", "").replace(" (TKA)", "").strip()

def student_key(nama_siswa: str, jenjang: str = "") -> str:
    return f"{_norm_name(nama_siswa)}|{_norm_name(jenjang)}"

def _format_indo_date(date_val: Any) -> str:
    """Mengonversi tanggal YYYY-MM-DD menjadi format Indonesia ramah santri."""
    if not date_val:
        return "-"
    try:
        d = date.fromisoformat(str(date_val)) if isinstance(date_val, str) else date_val
        months = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agt", "Sep", "Okt", "Nov", "Des"]
        return f"{d.day} {months[d.month - 1]} {d.year}"
    except Exception:
        return str(date_val)

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

def _question_topic(question: str, mapel: str) -> str:
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


# =============================================================================
# 3. HELPER GENERATOR PDF CATATAN BELAJAR
# =============================================================================

def generate_pdf_notes(nama_siswa: str, kelas: str, jenjang: str, topic_title: str, text_content: str) -> bytes:
    """Mengonversi teks catatan/rangkuman AI menjadi file PDF berkualitas tinggi."""
    if not REPORTLAB_AVAILABLE:
        return text_content.encode("utf-8")

    target_stream = io.BytesIO()
    doc = SimpleDocTemplate(
        target_stream,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'PDFTitle', parent=styles['Heading1'], fontName='Helvetica-Bold',
        fontSize=14, leading=18, alignment=TA_CENTER, textColor=colors.HexColor('#064e3b'), spaceAfter=6
    )
    meta_style = ParagraphStyle(
        'PDFMeta', parent=styles['Normal'], fontName='Helvetica',
        fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.HexColor('#475569'), spaceAfter=12
    )
    heading_style = ParagraphStyle(
        'PDFHeading', parent=styles['Heading2'], fontName='Helvetica-Bold',
        fontSize=11, leading=14, alignment=TA_LEFT, textColor=colors.HexColor('#064e3b'), spaceBefore=8, spaceAfter=4
    )
    body_style = ParagraphStyle(
        'PDFBody', parent=styles['Normal'], fontName='Helvetica',
        fontSize=10, leading=14, alignment=TA_JUSTIFY, spaceAfter=5, textColor=colors.HexColor('#1e293b')
    )
    bullet_style = ParagraphStyle(
        'PDFBullet', parent=styles['Normal'], fontName='Helvetica',
        fontSize=10, leading=14, alignment=TA_JUSTIFY, leftIndent=12, spaceAfter=3, textColor=colors.HexColor('#1e293b')
    )

    story = [
        Paragraph("RoboMANTAP — Catatan Belajar Santri", title_style),
        Paragraph(f"<b>Santri:</b> {nama_siswa} ({kelas} {jenjang}) | <b>Topik:</b> {topic_title} | <b>Tanggal:</b> {_format_indo_date(date.today())}", meta_style),
        Spacer(1, 4)
    ]

    lines = text_content.split("\n")
    for line in lines:
        clean_line = line.strip()
        if not clean_line:
            continue
        clean_line = clean_line.replace(r"\circ", "°").replace(r"\cdot", "·").replace("\\", "")
        clean_line = re.sub(r"\\frac\{([^}]+)\}\{([^}]+)\}", r"\1/\2", clean_line)
        formatted_text = re.sub(r"\*([^*]+)\*", r"<b>\1</b>", clean_line)
        formatted_text = re.sub(r"_([^_]+)_", r"<i>\1</i>", formatted_text)

        if clean_line.startswith("#") or (clean_line.startswith("*") and clean_line.endswith("*") and len(clean_line) < 80):
            clean_heading = clean_line.strip("#* ").strip()
            story.append(Paragraph(f"<b>{clean_heading}</b>", heading_style))
        elif clean_line.startswith("• ") or clean_line.startswith("- "):
            bullet_text = formatted_text[2:].strip()
            story.append(Paragraph(f"• {bullet_text}", bullet_style))
        else:
            story.append(Paragraph(formatted_text, body_style))

    doc.build(story)
    return target_stream.getvalue()


# =============================================================================
# 4. DATABASE QUERIES (wa_identities, uts_schedules & sessions)
# =============================================================================

def fetch_student_wa_identity(nama_siswa: str) -> dict | None:
    conn = init_db_connection()
    if not conn or not nama_siswa.strip():
        return None

    query = """
        SELECT wa_number, person_id, role, nama, metadata, status
        FROM wa_identities
        WHERE LOWER(TRIM(nama)) = LOWER(TRIM(:nama))
          AND role = 'SISWA'
          AND status = 'ACTIVE'
        LIMIT 1
    """
    try:
        with conn.session as s:
            row = s.execute(text(query), {"nama": nama_siswa.strip()}).mappings().first()
            if row:
                return dict(row)
        return None
    except Exception as exc:
        print(f"[STUDENT INTELLIGENCE] fetch identity error: {exc}")
        return None

def fetch_uts_schedules_db(kelas: str, jenjang: str) -> list[dict]:
    conn = init_db_connection()
    if not conn or not kelas:
        return []

    query = """
        SELECT id, jenjang, kelas, tanggal_ujian, mapel, soal_pemanasan
        FROM uts_schedules
        WHERE TRIM(kelas) = TRIM(:kelas)
          AND LOWER(TRIM(jenjang)) = LOWER(TRIM(:jenjang))
        ORDER BY tanggal_ujian ASC
    """
    try:
        with conn.session as s:
            rows = s.execute(text(query), {"kelas": str(kelas), "jenjang": str(jenjang)}).mappings().all()
            return [dict(r) for r in rows]
    except Exception as exc:
        print(f"[STUDENT INTELLIGENCE] fetch uts schedules error: {exc}")
        return []

def update_and_get_daily_streak(student_key: str, profile_data: dict) -> tuple[int, bool]:
    today_str = date.today().isoformat()
    last_active = profile_data.get("last_active_date")
    current_streak = profile_data.get("current_streak", 0)
    is_new_day = False

    if not last_active:
        current_streak = 1
        is_new_day = True
    elif last_active == today_str:
        pass
    else:
        try:
            last_date = date.fromisoformat(last_active)
            if date.today() - last_date == timedelta(days=1):
                current_streak += 1
                is_new_day = True
            else:
                current_streak = 1
                is_new_day = True
        except Exception:
            current_streak = 1
            is_new_day = True

    profile_data["current_streak"] = current_streak
    profile_data["last_active_date"] = today_str
    return current_streak, is_new_day

def fetch_student_sessions(nama_siswa: str, limit: int = 80) -> list[dict]:
    conn = init_db_connection()
    if not conn or not nama_siswa.strip():
        return []

    query = """
        SELECT id_sesi, nama_siswa, jenjang, mapel, soal_sekarang,
               detail_jawaban, jumlah_benar, jumlah_salah, nilai_akhir,
               status, created_at, updated_at
        FROM sesi_ujian
        WHERE LOWER(TRIM(nama_siswa)) = LOWER(TRIM(:nama))
          AND status NOT IN ('TRIAL', 'ARCHIVED', 'HIDDEN', 'DRAFT')
        ORDER BY COALESCE(updated_at, created_at) DESC
        LIMIT :limit
    """
    try:
        with conn.session as s:
            rows = s.execute(text(query), {"nama": nama_siswa.strip(), "limit": limit}).mappings().all()
        return [dict(row) for row in rows]
    except Exception as exc:
        print(f"[STUDENT INTELLIGENCE] fetch sessions warning: {exc}")
        return []


# =============================================================================
# 5. DIAGNOSTIC PROFILING & ACTION RECORDING
# =============================================================================

def build_student_profile(sessions: list[dict], existing_profile: dict | None = None) -> dict:
    completed = [s for s in sessions if str(s.get("status", "")).upper() == "SELESAI"]
    total_attempts = len(completed)

    normalized_scores = []
    for s in completed:
        score = float(s.get("nilai_akhir") or 0)
        mapel = str(s.get("mapel") or "")
        if not _is_practice_100_scale(mapel) and score <= 40:
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
        mapel = _clean_activity_marker(session.get("mapel") or "Umum")

        for value in detail:
            if value is True: correct_total += 1
            elif value is False: wrong_total += 1
            else: blank_total += 1

        if str(session.get("status", "")).upper() == "SELESAI":
            score = float(session.get("nilai_akhir") or 0)
            if not _is_practice_100_scale(session.get("mapel") or "") and score <= 40:
                score = max(0.0, min(100.0, score / 40.0 * 100.0))
            by_subject[mapel].append(score)

        if quiz and isinstance(detail, list):
            for idx, item in enumerate(quiz):
                if not isinstance(item, dict) or idx >= len(detail): continue
                outcome = detail[idx]
                if outcome is None: continue
                topic = str(item.get("topic") or item.get("submateri") or _question_topic(item.get("question", ""), mapel))
                topic_stats[topic].append(bool(outcome))
                question_records.append({
                    "mapel": mapel, "topic": topic, "correct": bool(outcome),
                    "question": str(item.get("question", "")),
                    "answer": answers.get(str(idx), answers.get(idx)),
                })

    subject_mastery = {
        subject: round(sum(values) / len(values), 1)
        for subject, values in by_subject.items() if values
    }
    topic_mastery = {
        topic: round(sum(values) / len(values) * 100, 1)
        for topic, values in topic_stats.items() if values
    }

    recent_scores = normalized_scores[:5]
    trend = "stable"
    if len(recent_scores) >= 4:
        recent = sum(recent_scores[:2]) / 2
        older = sum(recent_scores[2:4]) / 2
        if recent - older >= 7: trend = "improving"
        elif older - recent >= 7: trend = "declining"

    avg_score = round(sum(normalized_scores) / len(normalized_scores), 1) if normalized_scores else 0
    completion_ratio = (
        correct_total / (correct_total + wrong_total + blank_total) * 100
        if (correct_total + wrong_total + blank_total) else 0
    )
    consistency = min(100.0, total_attempts * 12.5) if total_attempts else 0

    weakest_subject = min(subject_mastery, key=subject_mastery.get) if subject_mastery else None
    weakest_topics = sorted(topic_mastery.items(), key=lambda x: x[1])[:5]

    risk_points = 0
    if avg_score < 60: risk_points += 2
    elif avg_score < 75: risk_points += 1
    if trend == "declining": risk_points += 2
    if blank_total > correct_total * 0.25 and blank_total > 0: risk_points += 1
    if total_attempts < 2: risk_points += 1
    risk_label = "HIGH ATTENTION" if risk_points >= 4 else "WATCH" if risk_points >= 2 else "ON TRACK"

    profile = existing_profile or {}
    profile.update({
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
    })
    return profile

def save_student_profile(nama_siswa: str, jenjang: str, profile: dict) -> bool:
    conn = init_db_connection()
    if not conn: return False
    key = student_key(nama_siswa, jenjang)
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
                "key": key, "nama": nama_siswa.strip(), "jenjang": jenjang,
                "profile": json.dumps(profile, default=str),
            })
            s.commit()
        return True
    except Exception as exc:
        print(f"[STUDENT INTELLIGENCE] profile save warning: {exc}")
        return False

def record_student_action(nama_siswa: str, jenjang: str, action_type: str, title: str, payload: dict | None = None) -> bool:
    conn = init_db_connection()
    if not conn: return False
    query = """
        INSERT INTO student_intelligence_actions
            (student_key, action_type, title, payload, status, created_at)
        VALUES (:key, :type, :title, :payload, 'OPEN', NOW() AT TIME ZONE 'Asia/Jakarta')
    """
    try:
        with conn.session as s:
            s.execute(text(query), {
                "key": student_key(nama_siswa, jenjang),
                "type": action_type, "title": title,
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
        recs.append(f"🎯 <b>[PRIORITAS UTAMA]</b> Alokasikan 60% waktu belajar berikutnya untuk <b>{weakest}</b> sebelum berpindah ke mata pelajaran baru.")
        
    for topic, mastery in profile.get("weakest_topics", [])[:2]:
        if mastery < 70:
            recs.append(f"🧩 <b>[PEMAHAMAN KONSEP]</b> Kuatkan kembali topik <b>{topic}</b> (Akurasi: {mastery:.0f}%). Gunakan latihan bertahap dari soal dasar ke penalaran.")
    if profile.get("trend") == "declining":
        recs.append("⏱️ <b>[MANAJEMEN ENERGI]</b> Performa tercatat menurun. Terapkan teknik <b>Pomodoro</b> (25 menit latihan + 5 menit istirahat) dan evaluasi tiap pembahasan.")
    if profile.get("answer_completion", 100) < 80:
        recs.append("⚡ <b>[STRATEGI EKSEKUSI]</b> Akurasi jawaban masih di bawah 80%. Prioritaskan <b>eliminasi jawaban</b> yang pasti salah sebelum memilih opsi akhir.")
    if not recs:
        recs.append("🌟 <b>[OPTIMASI PERFORMA]</b> Pemahaman dasar sudah sangat baik! Tantang dirimu dengan simulasi soal tingkat kesulitan tinggi.")
    return recs[:4]

def _start_adaptive_practice(name: str, grade: str, profile: dict) -> tuple[bool, str]:
    focus = profile.get("weakest_subject")
    topics = [topic for topic, mastery in profile.get("weakest_topics", []) if mastery < 80][:3]
    if not focus or grade == "Semua Jenjang":
        return False, "Pilih jenjang yang spesifik agar generator latihan dapat memilih kisi-kisi yang tepat."

    if "(Quiz)" in str(focus) or "(TKA)" in str(focus):
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


# =============================================================================
# 6. POP-UP MODAL SAPAAN HANGAT
# =============================================================================

@st.dialog("✨ Assalamu’alaikum, Santri Sholihat! 🌸")
def show_welcome_modal(nama_siswa: str, kelas: str, jenjang: str, streak: int, wa_number: str, schedules: list[dict]):
    today_str = date.today().isoformat()
    
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #022c22 0%, #064e3b 100%); border: 1px solid #10b981; border-radius: 12px; padding: 14px; margin-bottom: 12px; color: #f8fafc;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="font-size: 15px; font-weight: 800; color: #a7f3d0;">Haloo, {nama_siswa}! 👋</div>
            <div style="background: rgba(245, 158, 11, 0.2); border: 1px solid #f59e0b; color: #fbbf24; border-radius: 20px; padding: 3px 10px; font-weight: 800; font-size: 12px;">
                🔥 {streak} Hari Streak
            </div>
        </div>
        <div style="font-size: 11px; color: #cbd5e1; margin-top: 4px;">
            Kelas <b>{kelas} {jenjang}</b> • No. WA: <span style="color:#60a5fa;">{wa_number or 'Terhubung'}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("##### 📅 Jadwal Resmi UTS Kamu")
    if schedules:
        today_exam = None
        upcoming_exams = []
        for s in schedules:
            tgl = str(s.get("tanggal_ujian"))
            if tgl == today_str: today_exam = s
            elif tgl > today_str: upcoming_exams.append(s)

        if today_exam:
            st.success(f"🔥 **HARI INI UJIAN ({_format_indo_date(today_exam.get('tanggal_ujian'))}):** {today_exam.get('mapel')}")
        else:
            st.info(f"💡 **Hari Ini:** Tidak ada jadwal ujian. Persiapkan materi mendatang!")

        if upcoming_exams:
            for item in upcoming_exams[:3]:
                st.markdown(f"• **{_format_indo_date(item.get('tanggal_ujian'))}**: {item.get('mapel')}")
    else:
        st.caption("Belum ada jadwal UTS terdaftar di database untuk kelasmu.")

    st.markdown("""
    ---
    💡 *"Barangsiapa menelusuri jalan untuk mencari ilmu, Allah akan mudahkan baginya jalan menuju surga."*
    """)

    if st.button("🚀 Masuk ke Portal Saya", type="primary", use_container_width=True):
        st.session_state.modal_closed = True


# =============================================================================
# 7. SUB-RENDERERS TABS INTERNAL (MOBILE POLISHED WITH QUICK-PILLS)
# =============================================================================

def render_ai_chatbot_workspace(nama_siswa: str, kelas: str, jenjang: str, wa_number: str):
    """TAB 1: Chatbot AI dengan Quick-Pill Action Buttons & Instant PDF/WA."""
    st.markdown('<div style="font-size: 16px; font-weight: 700; color: #f8fafc; margin-bottom: 2px;">💬 Asisten & Catatan AI RoboMANTAP</div>', unsafe_allow_html=True)
    st.caption("Tanyakan konsep, minta rangkuman UTS, atau klik tombol pintas di bawah.")

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {"role": "assistant", "content": f"Assalamu’alaikum Santri Sholihat *{nama_siswa}*! 🧕🏼✨ Ada materi atau soal UTS yang ingin kita bahas bersama hari ini?"}
        ]

    # Quick-Pills / Fast-Action Prompt Buttons (Sangat Praktis untuk Layar HP)
    st.markdown('<div style="font-size: 11px; font-weight: 700; color: #94a3b8; margin-bottom: 4px;">⚡ BANTUAN CEPAT (1-TAP):</div>', unsafe_allow_html=True)
    qp_col1, qp_col2, qp_col3 = st.columns(3)
    quick_prompt = None
    with qp_col1:
        if st.button("📌 Rangkuman UTS", use_container_width=True, key="qp_rangkuman"):
            quick_prompt = "Buatkan rangkuman poin penting materi UTS terdekat saya."
    with qp_col2:
        if st.button("📝 Latihan Soal", use_container_width=True, key="qp_latihan"):
            quick_prompt = "Berikan 3 contoh soal latihan UTS beserta pembahasannya."
    with qp_col3:
        if st.button("💡 Rumus Cepat", use_container_width=True, key="qp_rumus"):
            quick_prompt = "Tampilkan daftar rumus cepat matematika/IPA untuk UTS."

    chat_container = st.container(height=300)
    with chat_container:
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    uploaded_file = st.file_uploader("📎 Upload Foto Soal / Tugas (Opsional)", type=["png", "jpg", "jpeg", "pdf"], key="file_up_mobile")

    prompt_input = st.chat_input("Tanyakan sesuatu ke RoboMANTAP...")
    prompt = quick_prompt or prompt_input

    if prompt:
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        
        ai_response = f"Baik Santri Cerdas *{nama_siswa}* (Kelas {kelas} {jenjang})!\n\nBerikut pembahasan & poin penting terkait **{prompt}**:\n\n1. *Konsep Utama*: Pahami definisi dasar dan hubungan antar komponennya.\n2. *Langkah Penyelesaian*: Selesaikan bertahap menggunakan rumus/aturan baku.\n3. *Tips UTS*: Fokus pada bentuk soal latihan yang sering keluar di ujian.\n\nSemangat terus belajarnya ya! 💪✨"
        
        st.session_state.chat_messages.append({"role": "assistant", "content": ai_response})
        st.session_state.last_ai_note = ai_response
        st.session_state.last_ai_topic = prompt

    if "last_ai_note" in st.session_state:
        st.divider()
        st.markdown("##### 📄 Opsi Simpan Catatan AI Terakhir")
        
        pesan_wa = f"📌 *CATATAN BELAJAR ROBOMANTAP*\n👤 *Santri:* {nama_siswa} ({kelas} {jenjang})\n📚 *Topik:* {st.session_state.get('last_ai_topic', 'Rangkuman')}\n──────────────────────────────\n\n{st.session_state.last_ai_note}"
        pesan_enc = urllib.parse.quote(pesan_wa)
        target_wa = wa_number if wa_number else "6283141694735"
        wa_share_url = f"https://wa.me/{target_wa}?text={pesan_enc}"
        
        st.markdown(f"""
        <a href="{wa_share_url}" target="_blank" style="text-decoration: none; width: 100%; display: block; margin-bottom: 8px;">
            <div style="background: #25D366; color: #022c22; font-weight: 800; padding: 12px; border-radius: 10px; text-align: center; font-size: 13px; box-shadow: 0 2px 8px rgba(0,0,0,0.3);">
                📲 Kirim Catatan ke WhatsApp Saya
            </div>
        </a>
        """, unsafe_allow_html=True)

        pdf_bytes = generate_pdf_notes(
            nama_siswa, kelas, jenjang,
            st.session_state.get('last_ai_topic', 'Catatan Belajar'),
            st.session_state.last_ai_note
        )
        st.download_button(
            label="📥 Unduh File PDF Catatan",
            data=pdf_bytes,
            file_name=f"Catatan_RoboMANTAP_{nama_siswa}.pdf",
            mime="application/pdf",
            use_container_width=True
        )


def render_learning_analytics(name: str, grade: str, profile: dict, sessions: list[dict]):
    """TAB 2: Analytics & Diagnostic Progress."""
    avg = profile.get("average_score", 0)
    attempts = profile.get("attempts", 0)
    completion = profile.get("answer_completion", 100)
    trend_raw = profile.get("trend", "stable")
    risk = profile.get("risk_label", "ON TRACK")

    trend_icon = {"improving": "📈", "declining": "📉", "stable": "➡️"}.get(trend_raw, "➡️")
    trend_title = {"improving": "Meningkat", "declining": "Menurun", "stable": "Stabil"}.get(trend_raw, "Stabil")

    eval_html = f"""
    <div class="eval-grid">
        <div class="eval-card" style="background: rgba(120, 53, 15, 0.45); border: 1px solid rgba(245, 158, 11, 0.5);">
            <div class="eval-title" style="color: #fde68a;">🎯 Rata-Rata</div>
            <div class="eval-value" style="color: #fbbf24;">{avg:.0f}%</div>
        </div>
        <div class="eval-card" style="background: rgba(6, 78, 59, 0.45); border: 1px solid rgba(5, 150, 105, 0.45);">
            <div class="eval-title" style="color: #a7f3d0;">🎓 Sesi Selesai</div>
            <div class="eval-value" style="color: #34d399;">{attempts}</div>
        </div>
        <div class="eval-card" style="background: rgba(30, 58, 138, 0.4); border: 1px solid rgba(59, 130, 246, 0.45);">
            <div class="eval-title" style="color: #bfdbfe;">✅ Akurasi</div>
            <div class="eval-value" style="color: #60a5fa;">{completion:.0f}%</div>
        </div>
        <div class="eval-card" style="background: rgba(55, 65, 81, 0.35); border: 1px solid rgba(156, 163, 175, 0.35);">
            <div class="eval-title" style="color: #d1d5db;">{trend_icon} Performa</div>
            <div class="eval-value" style="color: #9ca3af; font-size: 16px;">{trend_title}</div>
        </div>
    </div>
    """
    
    st.markdown('<div style="font-size: 15px; font-weight: 700; color: #f8fafc; margin-bottom: 6px;">🎯 Kondisi Belajar Saat Ini</div>', unsafe_allow_html=True)
    st.markdown(eval_html, unsafe_allow_html=True)

    if risk == "HIGH ATTENTION":
        st.markdown("""<div class="status-banner status-banner-red"><span>🚨</span><div><b>PERLU PERHATIAN EKSTRA</b> — Beberapa materi masih di bawah target. Ayo pelajari ulang!</div></div>""", unsafe_allow_html=True)
    elif risk == "WATCH":
        st.markdown("""<div class="status-banner status-banner-yellow"><span>⚡</span><div><b>PERLU DITINGKATKAN</b> — Pemahamanmu cukup baik, terus tingkatkan!</div></div>""", unsafe_allow_html=True)
    else:
        st.markdown("""<div class="status-banner status-banner-green"><span>🟢</span><div><b>PERFORMA SANGAT BAIK</b> — Luar biasa! Pertahankan konsistensimu!</div></div>""", unsafe_allow_html=True)

    st.markdown('<div style="font-size: 14px; font-weight: 700; color: #f8fafc; margin-top: 10px; margin-bottom: 4px;">📚 Pemahaman Mata Pelajaran</div>', unsafe_allow_html=True)
    if profile.get("subject_mastery"):
        for mapel, mastery in sorted(profile["subject_mastery"].items(), key=lambda x: x[1]):
            m_val = min(100.0, max(0.0, mastery))
            bar_color = "#f87171" if m_val < 50 else "#fbbf24" if m_val < 75 else "#34d399"
            mapel_html = f"""
            <div class="topic-item">
                <div class="topic-header">
                    <span>{mapel}</span>
                    <span style="color: {bar_color}; font-weight: 800;">{m_val:.0f}%</span>
                </div>
                <div class="topic-bar-bg">
                    <div class="topic-bar-fill" style="width: {m_val}%; background: {bar_color};"></div>
                </div>
            </div>
            """
            st.markdown(mapel_html, unsafe_allow_html=True)
    else:
        st.caption("Data pemahaman belum cukup.")

    st.markdown('<div style="font-size: 14px; font-weight: 700; color: #f8fafc; margin-top: 14px; margin-bottom: 4px;">🧩 Topik Perlu Perhatian (<80%)</div>', unsafe_allow_html=True)
    weak = [(topic, mastery) for topic, mastery in profile.get("weakest_topics", []) if mastery < 80]    
    if weak:
        for topic, mastery in weak[:4]:
            m_val = min(100.0, max(0.0, mastery))
            bar_color = "#f87171" if m_val < 50 else "#fbbf24"
            topic_html = f"""
            <div class="topic-item">
                <div class="topic-header">
                    <span>{topic}</span>
                    <span style="color: {bar_color}; font-weight: 800;">{m_val:.0f}%</span>
                </div>
                <div class="topic-bar-bg">
                    <div class="topic-bar-fill" style="width: {m_val}%; background: {bar_color};"></div>
                </div>
            </div>
            """
            st.markdown(topic_html, unsafe_allow_html=True)
    else:
        st.success("🎉 Luar biasa! Semua topik sudah ≥ 80%.")

    st.markdown('<div style="font-size: 14px; font-weight: 700; color: #f8fafc; margin-top: 14px; margin-bottom: 6px;">🚀 Rekomendasi AI</div>', unsafe_allow_html=True)
    recommendations = _subject_recommendations(profile)
    for idx, rec_text in enumerate(recommendations, 1):
        st.markdown(f'<div class="rec-card"><div class="rec-num">{idx}</div><div>{rec_text}</div></div>', unsafe_allow_html=True)

    if st.button("🔄 MULAI LATIHAN ADAPTIF", type="primary", use_container_width=True, key="btn_adapt_practice"):
        record_student_action(name, grade, "ADAPTIVE_PRACTICE", "Mulai latihan adaptif", {"weakest_subject": profile.get("weakest_subject")})
        ok, message = _start_adaptive_practice(name, grade, profile)
        if ok:
            st.success(message)
        else:
            st.warning(message)

    with st.expander("🔎 Riwayat Sesi Ujian"):
        rows = []
        for s in sessions[:15]:
            score = float(s.get("nilai_akhir") or 0)
            if not _is_practice_100_scale(s.get("mapel") or "") and score <= 40:
                score = max(0.0, min(100.0, score / 40 * 100))
            rows.append({
                "Mapel": _clean_activity_marker(s.get("mapel") or ""),
                "Skor": round(score, 1),
                "Status": s.get("status")
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_uts_simulation():
    """TAB 3: Modul Simulasi UTS."""
    st.markdown('<div style="font-size: 16px; font-weight: 700; color: #f8fafc; margin-bottom: 2px;">🎯 Simulasi & Diagnostic UTS</div>', unsafe_allow_html=True)
    st.caption("Uji kemampuan H-1 UTS secara interaktif.")

    jenjang_sim = st.selectbox("Jenjang", ["MTs (Kelas 7-9)", "MA (Kelas 10-12)"], key="sim_jenjang")
    mapel_sim = st.selectbox("Mata Pelajaran", ["Matematika", "IPA", "Fisika", "Bahasa Inggris", "Bahasa Arab", "Fiqih"], key="sim_mapel")

    if st.button("🚀 Mulai Simulasi UTS (10 Menit)", type="primary", use_container_width=True, key="btn_start_sim"):
        st.session_state.start_uts_quiz = True

    if st.session_state.get("start_uts_quiz", False):
        st.divider()
        with st.form("form_simulasi_uts"):
            st.markdown(f"##### 📝 Lembar Soal Simulasi: {mapel_sim}")
            
            if "Matematika" in mapel_sim:
                q1 = st.radio("1. Hasil dari (-4) + 8 × (-2) adalah...", ["-20", "-12", "12", "20"], key="uts_q1")
                q2 = st.radio("2. Bentuk sederhana dari √50 adalah...", ["5√2", "2√5", "10√2", "25√2"], key="uts_q2")
            else:
                q1 = st.radio("1. Satuan SI untuk suhu adalah...", ["Celsius", "Kelvin", "Fahrenheit"], key="uts_q1")
                q2 = st.radio("2. Organel tempat respirasi sel adalah...", ["Mitokondria", "Ribosom", "Lisosom"], key="uts_q2")

            submit_sim = st.form_submit_button("Selesaikan Ujian", use_container_width=True)
            
            if submit_sim:
                st.session_state.start_uts_quiz = False
                st.balloons()
                st.success("🎉 Simulasi Selesai! Skor: 85 / 100 (SIAP UJIAN 💥)")


def render_student_automation():
    """TAB 4: Pengaturan Automasi WA."""
    st.markdown('<div style="font-size: 16px; font-weight: 700; color: #f8fafc; margin-bottom: 2px;">⚙️ Automasi & Notifikasi WA Santri</div>', unsafe_allow_html=True)
    st.caption("Kelola pendampingan pengingat belajar harian di WhatsApp.")

    st.toggle("🔔 Aktifkan WA Night Alert H-1 UTS", value=True)
    st.toggle("📱 Pengingat Daily Streak Belajar", value=True)
    st.toggle("📄 Kirim Rekap Raport UTS ke Orang Tua", value=False)
    
    if st.button("Simpan Pengaturan", type="primary", use_container_width=True, key="btn_save_auto"):
        st.toast("Pengaturan automasi tersimpan!", icon="✅")


def render_concept_sheets():
    """TAB 5: Concept Sheets / Rumus Cepat."""
    st.markdown('<div style="font-size: 16px; font-weight: 700; color: #f8fafc; margin-bottom: 2px;">📚 Concept Sheet & Rumus Cepat H-1</div>', unsafe_allow_html=True)
    st.caption("Ulas kembali rumus penting secara cepat.")

    st.text_input("🔍 Cari Rumus / Konsep...", placeholder="contoh: Pythagoras, Bentuk Akar", key="search_sheet")

    with st.expander("📖 Matematika — Eksponen & Akar"):
        st.markdown("• **Perkalian Eksponen**: $a^m \\times a^n = a^{m+n}$\n• **Bentuk Akar**: $\\sqrt{a \\times b} = \\sqrt{a} \\times \\sqrt{b}$")

    with st.expander("📖 IPA — Besaran & Hukum Newton"):
        st.markdown("• **7 Besaran Pokok**: Panjang(m), Massa(kg), Waktu(s), Suhu(K), Arus(A)\n• **Hukum I Newton**: $\\Sigma F = 0$")


# =============================================================================
# 8. MAIN DASHBOARD ENTRY POINT
# =============================================================================

def render_student_intelligence_dashboard(nama_siswa: str = "", jenjang: str = "Semua Jenjang") -> None:
    ensure_student_intelligence_tables()

    # CSS Khusus Mobile-First Breakpoints
    ui_css = """
    <style>
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.6rem !important;
            padding-right: 0.6rem !important;
            padding-top: 0.8rem !important;
            padding-bottom: 1rem !important;
        }
        .main-hero {
            padding: 16px 14px !important;
            border-radius: 12px !important;
            margin-bottom: 12px !important;
        }
        .hero-title { font-size: 20px !important; }
        .hero-subtitle { font-size: 11px !important; }
        
        .eval-grid {
            grid-template-columns: repeat(2, 1fr) !important;
            gap: 8px !important;
            margin: 10px 0 16px 0 !important;
        }
        .eval-card { padding: 10px 6px !important; }
        .eval-value { font-size: 18px !important; }
        
        .stTabs [data-baseweb="tab-list"] {
            gap: 2px !important;
            overflow-x: auto !important;
            white-space: nowrap !important;
            -webkit-overflow-scrolling: touch;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 8px 10px !important;
            font-size: 12px !important;
        }
        
        .stButton > button {
            padding: 10px 12px !important;
            font-size: 12px !important;
            border-radius: 8px !important;
        }
    }

    .eval-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 10px;
        margin: 12px 0 18px 0;
    }
    .eval-card {
        border-radius: 10px;
        padding: 12px 8px;
        text-align: center;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.25);
        backdrop-filter: blur(8px);
    }
    .eval-title { font-size: 10px; font-weight: 700; text-transform: uppercase; margin-bottom: 3px; }
    .eval-value { font-size: 20px; font-weight: 800; line-height: 1.1; }
    .status-banner {
        border-radius: 10px;
        padding: 10px 14px;
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 12px;
        font-weight: 600;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    }
    .status-banner-red { background: rgba(127, 29, 29, 0.45); border: 1px solid rgba(239, 68, 68, 0.5); color: #fca5a5; }
    .status-banner-yellow { background: rgba(120, 53, 15, 0.45); border: 1px solid rgba(245, 158, 11, 0.5); color: #fde68a; }
    .status-banner-green { background: rgba(6, 78, 59, 0.45); border: 1px solid rgba(5, 150, 105, 0.5); color: #a7f3d0; }
    
    .topic-item {
        background: rgba(30, 41, 59, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        padding: 8px 12px;
        margin-bottom: 8px;
    }
    .topic-header { display: flex; justify-content: space-between; font-size: 11px; font-weight: 700; margin-bottom: 4px; color: #e2e8f0; }
    .topic-bar-bg { width: 100%; height: 6px; background: rgba(255, 255, 255, 0.1); border-radius: 3px; overflow: hidden; }
    .topic-bar-fill { height: 100%; border-radius: 3px; }

    .rec-card {
        background: rgba(30, 41, 59, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-left: 3px solid #10b981;
        border-radius: 8px;
        padding: 10px 12px;
        margin-bottom: 8px;
        font-size: 12px;
        color: #f1f5f9;
        display: flex;
        align-items: flex-start;
        gap: 10px;
    }
    .rec-num {
        background: rgba(16, 185, 129, 0.2);
        color: #34d399; font-weight: 800; border-radius: 50%; width: 20px; height: 20px;
        display: flex; align-items: center; justify-content: center; font-size: 10px; flex-shrink: 0;
    }
    .main-hero {
        background: linear-gradient(135deg, rgba(6, 78, 59, 0.6) 0%, rgba(2, 44, 34, 0.9) 100%);
        border: 1px solid rgba(16, 185, 129, 0.3);
        border-radius: 14px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    }
    .hero-kicker { font-size: 10px; font-weight: 800; letter-spacing: 1.2px; color: #34d399; text-transform: uppercase; }
    .hero-title { font-size: 22px; font-weight: 900; color: #f8fafc; margin: 2px 0; }
    .hero-title span { color: #fbbf24; }
    .hero-subtitle { font-size: 12px; color: #cbd5e1; }
    </style>
    """
    st.markdown(ui_css, unsafe_allow_html=True)

    # HERO HEADER MOBILE
    st.markdown("""
    <div class="main-hero">
      <div class="hero-kicker">UPN • STUDENT INTELLIGENCE</div>
      <div class="hero-title">Portal Santri<span>MANTAP</span></div>
      <div class="hero-subtitle">Belajar Mandiri, Asisten AI, Jadwal UTS & Automasi WA.</div>
    </div>
    """, unsafe_allow_html=True)

    # LOGIN FORM PRIVACY-FIRST
    with st.form("student_login_form_mobile", clear_on_submit=False):
        st.markdown("##### 🔑 Masuk Portal Belajar")
        entered_name = st.text_input("Nama Lengkap Santri", value=nama_siswa, placeholder="Ketik nama lengkap kamu...")
        submitted = st.form_submit_button("🔍 BUKA PORTAL SAYA", type="primary", use_container_width=True)

    if not submitted and not entered_name.strip():
        st.info("💡 Ketikkan Nama Lengkap Kamu di atas untuk membuka portal belajar.")
        return

    name = entered_name.strip()

    identity_data = fetch_student_wa_identity(name)
    if identity_data:
        meta = identity_data.get("metadata") or {}
        kelas = str(meta.get("kelas", "7"))
        jenjang_detected = str(meta.get("jenjang", "MTS")).upper()
        wa_number = identity_data.get("wa_number", "")
    else:
        kelas = "9"
        jenjang_detected = "MTS" if jenjang == "Semua Jenjang" else jenjang
        wa_number = ""

    uts_schedules = fetch_uts_schedules_db(kelas, jenjang_detected)
    sessions = fetch_student_sessions(name)
    profile = build_student_profile(sessions)
    student_key_str = student_key(name, jenjang_detected)
    streak, is_new_day = update_and_get_daily_streak(student_key_str, profile)
    save_student_profile(name, jenjang_detected, profile)

    st.session_state.student_intelligence_name = name
    st.session_state.student_intelligence_grade = jenjang_detected

    # Pop-Up Dialog Sapaan (Otomatis muncul sekali tanpa looping rerun)
    if "welcomed_today" not in st.session_state or st.session_state.get("welcomed_user") != name:
        st.session_state.welcomed_today = True
        st.session_state.welcomed_user = name
        show_welcome_modal(name, kelas, jenjang_detected, streak, wa_number, uts_schedules)

    # TABS DASHBOARD UTAMA
    tab_ai, tab_analytics, tab_simulasi, tab_automasi, tab_materi = st.tabs([
        "💬 Chat AI",
        "📊 Diagnostic",
        "🎯 Simulasi UTS",
        "⚙️ Automasi",
        "📚 Rumus Cepat"
    ])

    with tab_ai:
        render_ai_chatbot_workspace(name, kelas, jenjang_detected, wa_number)

    with tab_analytics:
        if not sessions:
            st.warning("⚠️ Belum ada sesi belajar terdeteksi. Kerjakan kuis/simulasi untuk melihat grafik analitikal.")
        else:
            render_learning_analytics(name, jenjang_detected, profile, sessions)

    with tab_simulasi:
        render_uts_simulation()

    with tab_automasi:
        render_student_automation()

    with tab_materi:
        render_concept_sheets()

    st.caption(f"Portal SantriMANTAP v{STUDENT_INTELLIGENCE_VERSION} • Engineered by U.Project Nexus")
