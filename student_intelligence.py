"""RoboMANTAP Student Intelligence Layer v3.0 (Full Master Edition).

Pusat Layanan Belajar, Simulasi UTS, Latihan Adaptif AI, Analisis Diagnostic,
Asisten Chatbot, Daily Streak, Export Catatan WA & PDF Santri Al-Irsyad Putri Bondowoso.
"""

from __future__ import annotations

import io
import json
import html
import hashlib
import secrets
import math
import re
import uuid
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta, timezone
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

from ai_engine import init_db_connection, stream_ai_text, get_gemini_clients, STREAM_MODELS

STUDENT_INTELLIGENCE_VERSION = "3.0"

# =============================================================================
# 1. DATABASE INITIALIZATION (PENTING UNTUK APP.PY)
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
        """
        ALTER TABLE wa_identities ADD COLUMN IF NOT EXISTS username VARCHAR(32)
        """,
        """
        ALTER TABLE wa_identities ADD COLUMN IF NOT EXISTS pin_hash TEXT
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_wa_identities_username_unique
        ON wa_identities (LOWER(BTRIM(username)))
        WHERE username IS NOT NULL AND BTRIM(username) <> ''
        """,
        """
        CREATE TABLE IF NOT EXISTS student_portal_login_challenges (
            token_hash VARCHAR(64) PRIMARY KEY,
            username VARCHAR(32) NOT NULL,
            wa_number VARCHAR(40) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            verified_at TIMESTAMPTZ,
            consumed_at TIMESTAMPTZ
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_portal_login_challenge_expiry
        ON student_portal_login_challenges (expires_at)
        """,
        """
        CREATE TABLE IF NOT EXISTS student_portal_preferences (
            wa_number VARCHAR(40) PRIMARY KEY,
            morning_alert_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            night_alert_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
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
        fontSize=15, leading=19, alignment=TA_CENTER, textColor=colors.HexColor('#064e3b'), spaceAfter=6
    )
    meta_style = ParagraphStyle(
        'PDFMeta', parent=styles['Normal'], fontName='Helvetica',
        fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.HexColor('#475569'), spaceAfter=15
    )
    heading_style = ParagraphStyle(
        'PDFHeading', parent=styles['Heading2'], fontName='Helvetica-Bold',
        fontSize=11, leading=15, alignment=TA_LEFT, textColor=colors.HexColor('#064e3b'), spaceBefore=10, spaceAfter=4
    )
    body_style = ParagraphStyle(
        'PDFBody', parent=styles['Normal'], fontName='Helvetica',
        fontSize=10, leading=14, alignment=TA_JUSTIFY, spaceAfter=6, textColor=colors.HexColor('#1e293b')
    )
    bullet_style = ParagraphStyle(
        'PDFBullet', parent=styles['Normal'], fontName='Helvetica',
        fontSize=10, leading=14, alignment=TA_JUSTIFY, leftIndent=15, spaceAfter=3, textColor=colors.HexColor('#1e293b')
    )

    story = [
        Paragraph("RoboMANTAP — Catatan Belajar Santri", title_style),
        Paragraph(f"<b>Santri:</b> {nama_siswa} (Kelas {kelas} {jenjang}) | <b>Topik:</b> {topic_title} | <b>Tanggal:</b> {datetime.now().strftime('%d %B %Y')}", meta_style),
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
# 4. QUERY DATABASE INTEGRATED (wa_identities, uts_schedules & sessions)
# =============================================================================

def normalize_username(value: str) -> str:
    """Canonical username: lowercase, no spaces, limited safe characters."""
    return re.sub(r"[^a-z0-9._]", "", str(value or "").strip().casefold())


def validate_username(value: str) -> tuple[bool, str]:
    raw = str(value or "").strip()
    normalized = normalize_username(raw)
    if not raw:
        return False, "Masukkan username kamu."
    if len(normalized) < 3 or len(normalized) > 24:
        return False, "Username harus terdiri dari 3–24 karakter."
    if normalized != raw.casefold():
        return False, "Gunakan hanya huruf, angka, titik (.) atau garis bawah (_), tanpa spasi."
    if not re.match(r"^[a-z0-9][a-z0-9._]{2,23}$", normalized):
        return False, "Username harus diawali huruf/angka dan hanya berisi huruf, angka, titik, atau garis bawah."
    return True, normalized


def verify_student_pin(pin: str, encoded_hash: str) -> bool:
    """Verify PBKDF2 PIN hash; PIN asli tidak pernah disimpan di database."""
    try:
        algorithm, rounds_raw, salt, expected = str(encoded_hash or "").split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        rounds = int(rounds_raw)
        if rounds < 100000 or rounds > 1000000 or not re.fullmatch(r"\d{6}", str(pin or "")):
            return False
        actual = hashlib.pbkdf2_hmac("sha256", str(pin).encode("utf-8"), salt.encode("utf-8"), rounds).hex()
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False


def fetch_student_wa_identity_by_username(username: str) -> dict | None:
    """Lookup identitas siswa berdasarkan username unik dari wa_identities."""
    conn = init_db_connection()
    normalized = normalize_username(username)
    if not conn or not normalized:
        return None

    query = """
        SELECT wa_number, person_id, role, nama, metadata, status, username, pin_hash
        FROM wa_identities
        WHERE LOWER(BTRIM(username)) = :username
          AND UPPER(role) = 'SISWA'
          AND UPPER(status) = 'ACTIVE'
        LIMIT 1
    """
    try:
        with conn.session as session:
            row = session.execute(text(query), {"username": normalized}).mappings().first()
            if row:
                return dict(row)
        return None
    except Exception as exc:
        print(f"[STUDENT INTELLIGENCE] username lookup error: {exc}")
        return None


def fetch_uts_schedules_db(kelas: str, jenjang: str) -> list[dict]:
    """Ambil jadwal resmi dari uts_schedules; fallback ke nama alternatif uts_schedule."""
    conn = init_db_connection()
    if not conn or not kelas:
        return []

    queries = [
        """
        SELECT *
        FROM uts_schedules
        WHERE TRIM(kelas::text) = TRIM(:kelas)
          AND UPPER(TRIM(jenjang)) = UPPER(TRIM(:jenjang))
        ORDER BY tanggal_ujian ASC
        """,
        """
        SELECT *
        FROM uts_schedule
        WHERE TRIM(kelas::text) = TRIM(:kelas)
          AND UPPER(TRIM(jenjang)) = UPPER(TRIM(:jenjang))
        ORDER BY tanggal_ujian ASC
        """,
    ]
    for query in queries:
        try:
            with conn.session as session:
                rows = session.execute(
                    text(query), {"kelas": str(kelas), "jenjang": str(jenjang)}
                ).mappings().all()
                return [dict(row) for row in rows]
        except Exception as exc:
            print(f"[STUDENT INTELLIGENCE] schedule query fallback: {exc}")
    return []


def create_portal_login_challenge(username: str, wa_number: str) -> str | None:
    """Create a short-lived WhatsApp confirmation token; raw token is never stored."""
    conn = init_db_connection()
    if not conn or not wa_number:
        return None
    token = secrets.token_urlsafe(24)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now_utc = datetime.now(timezone.utc)
    expires_at = now_utc + timedelta(minutes=5)
    try:
        with conn.session as session:
            session.execute(text("""
                INSERT INTO student_portal_login_challenges
                    (token_hash, username, wa_number, created_at, expires_at)
                VALUES (:token_hash, :username, :wa_number, :created_at, :expires_at)
            """), {
                "token_hash": token_hash,
                "username": normalize_username(username),
                "wa_number": str(wa_number).strip(),
                "created_at": now_utc,
                "expires_at": expires_at,
            })
            session.commit()
        return token
    except Exception as exc:
        print(f"[STUDENT INTELLIGENCE] challenge create error: {exc}")
        return None


def consume_verified_portal_login(token: str) -> bool:
    """Atomically consume a confirmed, unexpired challenge exactly once."""
    conn = init_db_connection()
    if not conn or not token:
        return False
    token_hash = hashlib.sha256(str(token).encode("utf-8")).hexdigest()
    now_utc = datetime.now(timezone.utc)
    try:
        with conn.session as session:
            # Single atomic UPDATE prevents a stale read/race between checking and consuming.
            # RETURNING means login succeeds only if a verified, live challenge was actually consumed.
            row = session.execute(text("""
                UPDATE student_portal_login_challenges
                SET consumed_at = :now_utc
                WHERE token_hash = :token_hash
                  AND verified_at IS NOT NULL
                  AND consumed_at IS NULL
                  AND expires_at > :now_utc
                RETURNING token_hash
            """), {"token_hash": token_hash, "now_utc": now_utc}).first()
            if not row:
                session.rollback()
                # Diagnostic read distinguishes an unverified/expired token from DB errors in logs.
                try:
                    state = session.execute(text("""
                        SELECT verified_at, expires_at, consumed_at
                        FROM student_portal_login_challenges
                        WHERE token_hash = :token_hash
                        LIMIT 1
                    """), {"token_hash": token_hash}).mappings().first()
                    if state:
                        print(
                            "[STUDENT INTELLIGENCE] challenge not consumable: "
                            f"verified={bool(state.get('verified_at'))}, "
                            f"expires_at={state.get('expires_at')}, "
                            f"consumed={bool(state.get('consumed_at'))}"
                        )
                    else:
                        print("[STUDENT INTELLIGENCE] challenge token not found in portal database")
                except Exception as diagnostic_exc:
                    print(f"[STUDENT INTELLIGENCE] challenge diagnostic error: {diagnostic_exc}")
                return False
            session.commit()
        return True
    except Exception as exc:
        print(f"[STUDENT INTELLIGENCE] challenge consume error: {exc}")
        return False


def get_student_portal_preferences(wa_number: str) -> dict:
    defaults = {"morning_alert_enabled": True, "night_alert_enabled": True}
    conn = init_db_connection()
    if not conn or not wa_number:
        return defaults
    try:
        with conn.session as session:
            row = session.execute(text("""
                SELECT morning_alert_enabled, night_alert_enabled
                FROM student_portal_preferences WHERE wa_number = :wa_number
            """), {"wa_number": str(wa_number).strip()}).mappings().first()
            if row:
                return {
                    "morning_alert_enabled": bool(row.get("morning_alert_enabled", True)),
                    "night_alert_enabled": bool(row.get("night_alert_enabled", True)),
                }
    except Exception as exc:
        print(f"[STUDENT INTELLIGENCE] preference read error: {exc}")
    return defaults


def save_student_portal_preferences(wa_number: str, morning_enabled: bool, night_enabled: bool) -> bool:
    conn = init_db_connection()
    if not conn or not wa_number:
        return False
    try:
        with conn.session as session:
            session.execute(text("""
                INSERT INTO student_portal_preferences
                    (wa_number, morning_alert_enabled, night_alert_enabled, updated_at)
                VALUES (:wa_number, :morning_enabled, :night_enabled, NOW())
                ON CONFLICT (wa_number) DO UPDATE SET
                    morning_alert_enabled = EXCLUDED.morning_alert_enabled,
                    night_alert_enabled = EXCLUDED.night_alert_enabled,
                    updated_at = NOW()
            """), {
                "wa_number": str(wa_number).strip(),
                "morning_enabled": bool(morning_enabled),
                "night_enabled": bool(night_enabled),
            })
            session.commit()
        return True
    except Exception as exc:
        print(f"[STUDENT INTELLIGENCE] preference save error: {exc}")
        return False


def update_and_get_daily_streak(student_key: str, profile_data: dict) -> tuple[int, bool]:
    """Menghitung dan memperbarui Daily Learning Streak siswa secara otomatis."""
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

def fetch_student_sessions(nama_siswa: str, limit: int = 80, jenjang: str | None = None) -> list[dict]:
    conn = init_db_connection()
    if not conn or not nama_siswa.strip():
        return []

    query = """
        SELECT id_sesi, nama_siswa, jenjang, mapel, soal_sekarang,
               detail_jawaban, jumlah_benar, jumlah_salah, nilai_akhir,
               status, created_at, updated_at
        FROM sesi_ujian
        WHERE LOWER(TRIM(nama_siswa)) = LOWER(TRIM(:nama))
          AND (:jenjang IS NULL OR UPPER(TRIM(jenjang)) = UPPER(TRIM(:jenjang)))
          AND status NOT IN ('TRIAL', 'ARCHIVED', 'HIDDEN', 'DRAFT')
        ORDER BY COALESCE(updated_at, created_at) DESC
        LIMIT :limit
    """
    try:
        with conn.session as s:
            rows = s.execute(
                text(query),
                {"nama": nama_siswa.strip(), "limit": limit, "jenjang": jenjang},
            ).mappings().all()
        return [dict(row) for row in rows]
    except Exception as exc:
        print(f"[STUDENT INTELLIGENCE] fetch sessions warning: {exc}")
        return []


# =============================================================================
# 5. DIAGNOSTIC PROFILING & ACTION RECORDING
# =============================================================================

def build_student_profile(sessions: list[dict], existing_profile: dict | None = None) -> dict:
    """Membangun profil diagnostik lengkap mencakup materi terlemah, tren, risiko, & statistik."""
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
            if value is True:
                correct_total += 1
            elif value is False:
                wrong_total += 1
            else:
                blank_total += 1

        if str(session.get("status", "")).upper() == "SELESAI":
            score = float(session.get("nilai_akhir") or 0)
            if not _is_practice_100_scale(session.get("mapel") or "") and score <= 40:
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
    if not conn:
        return False
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
                "key": key,
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
    """Menghubungkan generator kuis adaptif dari ai_engine."""
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
# 6. POP-UP MODAL SAPAAN HANGAT & JADWAL UTS
# =============================================================================

@st.dialog("✨ Assalamu’alaikum, Santri Sholihat! 🌸")
def show_welcome_modal(nama_siswa: str, kelas: str, jenjang: str, streak: int, wa_number: str, schedules: list[dict]):
    """Pop-up Sapaan Hangat, Motivasi, Daily Streak, dan Jadwal UTS Realtime."""
    today_str = date.today().isoformat()
    
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #022c22 0%, #064e3b 100%); border: 1px solid #10b981; border-radius: 12px; padding: 16px; margin-bottom: 15px; color: #f8fafc;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="font-size: 16px; font-weight: 800; color: #a7f3d0;">Haloo, {nama_siswa}! 👋</div>
            <div style="background: rgba(245, 158, 11, 0.2); border: 1px solid #f59e0b; color: #fbbf24; border-radius: 20px; padding: 4px 12px; font-weight: 800; font-size: 13px;">
                🔥 {streak} Hari Streak
            </div>
        </div>
        <div style="font-size: 12px; color: #cbd5e1; margin-top: 6px;">
            Kelas <b>{kelas} {jenjang}</b> • No. WA: <span style="color:#60a5fa;">{wa_number or 'Terhubung'}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 📅 Jadwal Resmi UTS Kamu")
    if schedules:
        today_exam = None
        upcoming_exams = []
        for s in schedules:
            tgl = str(s.get("tanggal_ujian"))
            if tgl == today_str:
                today_exam = s
            elif tgl > today_str:
                upcoming_exams.append(s)

        if today_exam:
            st.success(f"🔥 **HARI INI UJIAN ({today_exam.get('tanggal_ujian')}):** {today_exam.get('mapel')}")
        else:
            st.info(f"💡 **Hari Ini:** Tidak ada jadwal ujian UTS. Fokus persiapkan materi ujian mendatang!")

        if upcoming_exams:
            st.markdown("**Mata Pelajaran Selanjutnya:**")
            for item in upcoming_exams[:3]:
                st.markdown(f"• **{item.get('tanggal_ujian')}**: {item.get('mapel')}")
    else:
        st.caption("Belum ada jadwal UTS terdaftar di database untuk kelasmu.")

    st.markdown("""
    ---
    💡 **Motivasi Pagi:**
    *"Barangsiapa menelusuri jalan untuk mencari ilmu, Allah akan mudahkan baginya jalan menuju surga."*  
    Semangat belajar dan manfaatkan Portal SantriMANTAP untuk latihan & rangkuman materi ya!
    """)

    if st.button("🚀 Masuk ke Portal Belajar Saya", type="primary", use_container_width=True):
        st.rerun()


# =============================================================================
# 7. SUB-RENDERERS TABS INTERNAL
# =============================================================================

def _generate_student_ai_response(prompt: str, nama_siswa: str, kelas: str, jenjang: str, uploaded_file=None) -> str:
    """Generate a grounded study answer; supports text, image stimulus, and searchable PDF text."""
    context = (
        "Kamu adalah RoboMANTAP, asisten belajar yang ramah, teliti, dan jujur. "
        "Jawab dalam Bahasa Indonesia yang jelas sesuai tingkat siswa. Berikan langkah penjelasan "
        "dan contoh seperlunya. Jangan mengarang jadwal resmi; rujuk agenda portal untuk jadwal. "
        f"Identitas siswa: {nama_siswa}, kelas {kelas} {jenjang}. "
        f"Waktu lokal: {datetime.now().strftime('%Y-%m-%d %H:%M')} WIB. "
        f"Pertanyaan siswa: {prompt}"
    )
    if uploaded_file is not None:
        data = uploaded_file.getvalue()
        file_name = str(getattr(uploaded_file, "name", "lampiran")).lower()
        if file_name.endswith(".pdf"):
            try:
                import fitz
                with fitz.open(stream=data, filetype="pdf") as pdf:
                    extracted = "\\n".join(page.get_text("text") for page in pdf)
                context += "\\n\\nTeks dari dokumen siswa (potongan maksimal 14000 karakter):\\n" + extracted[:14000]
            except Exception as exc:
                print(f"[STUDENT INTELLIGENCE] PDF extraction error: {exc}")
                context += "\\nCatatan: teks PDF tidak berhasil diekstrak; jelaskan berdasarkan pertanyaan saja."
        elif file_name.endswith((".png", ".jpg", ".jpeg", ".webp")):
            try:
                from PIL import Image as PILImage
                image_obj = PILImage.open(io.BytesIO(data)).convert("RGB")
                clients = get_gemini_clients()
                for client in clients:
                    for model_name in STREAM_MODELS:
                        try:
                            response = client.models.generate_content(
                                model=model_name,
                                contents=[context + "\\nAnalisis gambar terlampir dengan teliti.", image_obj],
                            )
                            answer = str(getattr(response, "text", "") or "").strip()
                            if answer:
                                return answer
                        except Exception:
                            continue
                context += "\\nCatatan: analisis gambar tidak berhasil; jawab berdasarkan pertanyaan teks saja."
            except Exception as exc:
                print(f"[STUDENT INTELLIGENCE] image analysis error: {exc}")
                context += "\\nCatatan: gambar tidak berhasil dibaca; jawab berdasarkan pertanyaan teks saja."
    answer = "".join(str(chunk) for chunk in stream_ai_text(context, max_output_tokens=1800)).strip()
    return answer or "Maaf, AI belum memberikan jawaban. Coba kirim pertanyaan yang lebih spesifik."


def render_ai_chatbot_workspace(nama_siswa: str, kelas: str, jenjang: str, wa_number: str):
    """TAB 1: Asisten AI RoboMANTAP dengan Diskusi, Upload Tugas, Share ke WA & Download PDF."""
    st.markdown('<div style="font-size: 18px; font-weight: 700; color: #f8fafc; margin-bottom: 4px;">💬 Asisten & Catatan AI RoboMANTAP</div>', unsafe_allow_html=True)
    st.caption("Tanyakan konsep, minta buatkan rangkuman UTS, analisis tugas, lalu simpan ke WA atau unduh PDF!")

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {"role": "assistant", "content": f"Assalamu’alaikum Santri Sholihat *{nama_siswa}*! 🧕🏼✨ Ada materi atau soal UTS yang ingin kita bahas bersama hari ini?"}
        ]

    chat_container = st.container(height=350)
    with chat_container:
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    uploaded_file = st.file_uploader("📎 Upload Gambar Soal / Dokumen Tugas (Opsional)", type=["png", "jpg", "jpeg", "pdf"])

    if prompt := st.chat_input("Tanyakan sesuatu ke RoboMANTAP..."):
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)

        ai_response = ""
        try:
            ai_response = _generate_student_ai_response(
                prompt, nama_siswa, kelas, jenjang, uploaded_file=uploaded_file
            )
        except Exception as exc:
            print(f"[STUDENT INTELLIGENCE] AI chat error: {exc}")
            ai_response = "Maaf, Asisten AI sedang mengalami kendala koneksi. Silakan coba kembali beberapa saat lagi."

        st.session_state.chat_messages.append({"role": "assistant", "content": ai_response})
        st.session_state.last_ai_note = ai_response
        st.session_state.last_ai_topic = prompt
        st.rerun()

    if "last_ai_note" in st.session_state:
        st.divider()
        st.markdown("### 📄 Opsi Simpan Catatan AI Terakhir")
        
        c1, c2 = st.columns(2)
        with c1:
            pesan_wa = f"📌 *CATATAN BELAJAR ROBOMANTAP*\n👤 *Santri:* {nama_siswa} ({kelas} {jenjang})\n📚 *Topik:* {st.session_state.get('last_ai_topic', 'Rangkuman')}\n──────────────────────────────\n\n{st.session_state.last_ai_note}"
            pesan_enc = urllib.parse.quote(pesan_wa)
            target_wa = wa_number if wa_number else "6283141694735"
            wa_share_url = f"https://wa.me/{target_wa}?text={pesan_enc}"
            
            st.markdown(f"""
            <a href="{wa_share_url}" target="_blank" style="text-decoration: none;">
                <div style="background: #25D366; color: #022c22; font-weight: 800; padding: 10px; border-radius: 8px; text-align: center; font-size: 13px;">
                    📲 Kirim Catatan ke WhatsApp Saya
                </div>
            </a>
            """, unsafe_allow_html=True)

        with c2:
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
    """TAB 2: Progress, Scorecards, Diagnostic Analytics & Latihan Adaptif"""
    avg = profile.get("average_score", 0)
    attempts = profile.get("attempts", 0)
    completion = profile.get("answer_completion", 100)
    trend_raw = profile.get("trend", "stable")
    risk = profile.get("risk_label", "ON TRACK")

    trend_icon = {"improving": "📈", "declining": "📉", "stable": "➡️"}.get(trend_raw, "➡️")
    trend_title = {"improving": "Meningkat", "declining": "Menurun", "stable": "Stabil"}.get(trend_raw, "Stabil")

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
        <div class="eval-card" style="background: linear-gradient(135deg, rgba(120, 53, 15, 0.45) 0%, rgba(69, 26, 3, 0.75) 100%); border: 1px solid rgba(245, 158, 11, 0.5);">
            <div class="eval-title" style="color: #fde68a;">🎯 Rata-Rata</div>
            <div class="eval-value" style="color: #fbbf24;">{avg:.0f}%</div>
        </div>
        <div class="eval-card" style="background: linear-gradient(135deg, rgba(6, 78, 59, 0.45) 0%, rgba(2, 44, 34, 0.75) 100%); border: 1px solid rgba(5, 150, 105, 0.45);">
            <div class="eval-title" style="color: #a7f3d0;">🎓 Sesi Selesai</div>
            <div class="eval-value" style="color: #34d399;">{attempts}</div>
        </div>
        <div class="eval-card" style="background: linear-gradient(135deg, rgba(30, 58, 138, 0.4) 0%, rgba(15, 23, 42, 0.75) 100%); border: 1px solid rgba(59, 130, 246, 0.45);">
            <div class="eval-title" style="color: #bfdbfe;">✅ Akurasi Jawaban</div>
            <div class="eval-value" style="color: #60a5fa;">{completion:.0f}%</div>
        </div>
        <div class="eval-card" style="{trend_card_bg}">
            <div class="eval-title" style="color: {trend_title_color};">{trend_icon} Perkembangan</div>
            <div class="eval-value" style="color: {trend_val_color}; font-size: 18px;">{trend_title}</div>
        </div>
    </div>
    """
    
    st.markdown('<div style="font-size: 18px; font-weight: 700; color: #f8fafc; margin-bottom: 8px;">🎯 Kondisi Belajar Saat Ini</div>', unsafe_allow_html=True)
    st.markdown(eval_html, unsafe_allow_html=True)

    if risk == "HIGH ATTENTION":
        st.markdown("""
        <div class="status-banner status-banner-red">
            <span style="font-size: 18px;">🚨</span>
            <div><b>PERLU PERHATIAN EKSTRA</b> — Ada beberapa materi yang nilainya masih di bawah target. Yuk luangkan waktu untuk mempelajari dan latihan ulang topik tersebut!</div>
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
            <div><b>PERFORMA SANGAT BAIK</b> — Luar biasa! Progres dan nilai belajarmu sudah sangat baik serta konsisten. Pertahankan semangat belajarmu!</div>
        </div>
        """, unsafe_allow_html=True)

    left, right = st.columns(2)
    with left:
        st.markdown('<div style="font-size: 16px; font-weight: 700; color: #f8fafc; margin-bottom: 6px;">📚 Pemahaman Mata Pelajaran</div>', unsafe_allow_html=True)
        st.markdown('<div style="font-size: 11px; color: #94a3b8; margin-bottom: 10px;">Rata-rata nilai akhir ujian, kuis, atau pengerjaan keseluruhan</div>', unsafe_allow_html=True)
        if profile.get("subject_mastery"):
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
        st.markdown('<div style="font-size: 16px; font-weight: 700; color: #f8fafc; margin-bottom: 6px;">🧩 Topik Perlu Perhatian</div>', unsafe_allow_html=True)
        st.markdown('<div style="font-size: 11px; color: #94a3b8; margin-bottom: 10px;">Akurasi kebenaran menjawab soal di bawah 80% (&lt; 80%)</div>', unsafe_allow_html=True)
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

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div style="font-size: 16px; font-weight: 700; color: #f8fafc; margin-bottom: 8px;">🚀 Rekomendasi Langkah Selanjutnya</div>', unsafe_allow_html=True)
    recommendations = _subject_recommendations(profile)
    for idx, rec_text in enumerate(recommendations, 1):
        rec_html = f"""
        <div class="rec-card">
            <div class="rec-num">{idx}</div>
            <div>{rec_text}</div>
        </div>
        """
        st.markdown(rec_html, unsafe_allow_html=True)

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

    with st.expander("🔎 Lihat riwayat sesi yang menjadi dasar analisis"):
        rows = []
        for s in sessions[:20]:
            score = float(s.get("nilai_akhir") or 0)
            if not _is_practice_100_scale(s.get("mapel") or "") and score <= 40:
                score = max(0.0, min(100.0, score / 40 * 100))
            rows.append({
                "Waktu": s.get("updated_at") or s.get("created_at"),
                "Mapel": _clean_activity_marker(s.get("mapel") or ""),
                "Status": s.get("status"),
                "Skor": round(score, 1),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_uts_simulation():
    """TAB 3: Modul Simulasi & Diagnostic UTS Interaktif"""
    st.markdown('<div style="font-size: 18px; font-weight: 700; color: #f8fafc; margin-bottom: 4px;">🎯 Simulasi & Diagnostic Kesiapan UTS</div>', unsafe_allow_html=True)
    st.caption("Uji kemampuanmu H-1 sebelum menghadapi lembar ujian resmi esok hari.")

    c1, c2 = st.columns(2)
    with c1:
        jenjang_sim = st.selectbox("Pilih Jenjang", ["MTs (Kelas 7-9)", "MA (Kelas 10-12)"], key="sim_jenjang")
    with c2:
        mapel_sim = st.selectbox(
            "Pilih Mata Pelajaran UTS",
            ["Matematika", "IPA", "Fisika", "Kimia", "Bahasa Inggris", "Bahasa Arab", "Fiqih", "Akidah", "Nahwu"],
            key="sim_mapel"
        )

    st.info(f"📌 **Mode Drill H-1 UTS**: 3 Soal Esensial {mapel_sim} ({jenjang_sim})")

    if st.button("🚀 Mulai Simulasi UTS (10 Menit)", type="primary", use_container_width=True):
        st.session_state.start_uts_quiz = True

    if st.session_state.get("start_uts_quiz", False):
        st.divider()
        with st.form("form_simulasi_uts"):
            st.subheader(f"📝 Lembar Soal Simulasi: {mapel_sim}")
            
            if "Matematika" in mapel_sim:
                q1 = st.radio("1. Hasil dari (-4) + 8 × (-2) adalah...", ["-20", "-12", "12", "20"], key="uts_q1")
                q2 = st.radio("2. Bentuk sederhana dari √50 adalah...", ["5√2", "2√5", "10√2", "25√2"], key="uts_q2")
                q3 = st.radio("3. Penyelesaian dari |x - 2| = 5 adalah...", ["x = 7 atau x = -3", "x = 5 atau x = -5", "x = 3 atau x = -7"], key="uts_q3")
                correct_answers = ["-20", "5√2", "x = 7 atau x = -3"]
            elif "IPA" in mapel_sim or "Fisika" in mapel_sim or "Kimia" in mapel_sim:
                q1 = st.radio("1. Satuan SI untuk suhu adalah...", ["Celsius", "Kelvin", "Fahrenheit", "Reamur"], key="uts_q1")
                q2 = st.radio("2. Organel sel yang berfungsi sebagai tempat respirasi sel adalah...", ["Mitokondria", "Ribosom", "Lisosom"], key="uts_q2")
                q3 = st.radio("3. Alat untuk mengukur kuat arus listrik adalah...", ["Voltmeter", "Amperemeter", "Thermometer"], key="uts_q3")
                correct_answers = ["Kelvin", "Mitokondria", "Amperemeter"]
            elif "Inggris" in mapel_sim:
                q1 = st.radio("1. Choose the correct sentence.", ["She go to school.", "She goes to school.", "She going school."], key="uts_q1")
                q2 = st.radio("2. The closest meaning of 'important' is...", ["Significant", "Tiny", "Late"], key="uts_q2")
                q3 = st.radio("3. The past form of 'write' is...", ["Writed", "Written", "Wrote"], key="uts_q3")
                correct_answers = ["She goes to school.", "Significant", "Wrote"]
            else:
                q1 = st.radio("1. Kata sapaan 'Selamat Pagi' dalam Bahasa Arab adalah...", ["Sabahal Khair", "Masaal Khair", "Ahlan wa Sahlan"], key="uts_q1")
                q2 = st.radio("2. Kedudukan Na'at dalam tata bahasa Arab harus mengikuti...", ["Man'ut", "Mubtada'", "Khabar"], key="uts_q2")
                q3 = st.radio("3. Seseorang yang menyampaikan/meriwayatkan hadist disebut...", ["Rawi", "Sanad", "Matan"], key="uts_q3")
                correct_answers = ["Sabahal Khair", "Man'ut", "Rawi"]

            submit_sim = st.form_submit_button("Selesaikan Ujian & Lihat Diagnostic", use_container_width=True)
            
            if submit_sim:
                st.session_state.start_uts_quiz = False
                answers = [q1, q2, q3]
                correct_count = sum(
                    1 for answer, expected in zip(answers, correct_answers)
                    if answer == expected
                )
                score = round(correct_count / len(correct_answers) * 100)
                st.session_state["last_uts_drill_result"] = {
                    "mapel": mapel_sim,
                    "jenjang": jenjang_sim,
                    "correct": correct_count,
                    "total": len(correct_answers),
                    "score": score,
                    "completed_at": datetime.now().isoformat(timespec="seconds"),
                }
                st.balloons()
                st.success("Simulasi selesai. Skor dihitung dari jawaban yang kamu pilih.")

                sc1, sc2 = st.columns(2)
                with sc1:
                    st.metric("Skor Simulasi", f"{score} / 100", f"{correct_count}/{len(correct_answers)} benar")
                with sc2:
                    status = "Siap berlatih lanjut" if score >= 80 else ("Perlu penguatan" if score >= 60 else "Perlu belajar ulang")
                    st.metric("Diagnosis", status)

                if score >= 80:
                    st.success("Fondasi materi pada drill singkat ini cukup baik. Lanjutkan latihan dengan variasi soal.")
                elif score >= 60:
                    st.warning("Kamu sudah memahami sebagian materi. Ulangi konsep yang salah, lalu coba lagi.")
                else:
                    st.warning("Jangan khawatir. Pelajari kembali konsep dasar dan minta RoboMANTAP menjelaskan langkahnya.")
                st.caption("Catatan: drill ini hanya 3 soal singkat dan bukan nilai resmi atau prediksi hasil UTS.")



def render_student_automation(wa_number: str = ""):
    """Persist student preferences for the existing morning/night WhatsApp alert endpoints."""
    st.markdown('<div style="font-size: 18px; font-weight: 700; color: #f8fafc; margin-bottom: 4px;">⚙️ Pengaturan Pengingat WhatsApp</div>', unsafe_allow_html=True)
    st.caption("Pilihan ini disimpan berdasarkan nomor WhatsApp terverifikasi dan dipakai oleh automasi pengingat RoboMANTAP.")
    if not wa_number:
        st.warning("Nomor WhatsApp belum terhubung pada akun ini. Hubungi admin untuk menyinkronkan identitas.")
        return

    current = get_student_portal_preferences(wa_number)
    with st.form("student_portal_notification_preferences"):
        morning_enabled = st.checkbox(
            "Pengingat pagi dan agenda hari ini",
            value=current["morning_alert_enabled"],
            help="Mengontrol pengingat pagi yang dijalankan melalui endpoint morning-alert."
        )
        night_enabled = st.checkbox(
            "Pengingat malam H-1 UTS",
            value=current["night_alert_enabled"],
            help="Mengontrol pengingat jadwal UTS untuk hari berikutnya."
        )
        submitted = st.form_submit_button("Simpan Pengaturan", type="primary", use_container_width=True)
    if submitted:
        if save_student_portal_preferences(wa_number, morning_enabled, night_enabled):
            st.success("Pengaturan pengingat berhasil disimpan dan akan dibaca oleh WA Bot.")
        else:
            st.error("Pengaturan belum tersimpan. Periksa koneksi database dan tabel student_portal_preferences.")


def render_concept_sheets():
    """TAB 5: Rangkuman Materi & Rumus Cepat H-1 UTS"""
    st.markdown('<div style="font-size: 18px; font-weight: 700; color: #f8fafc; margin-bottom: 4px;">📚 Concept Sheet & Rumus Cepat H-1</div>', unsafe_allow_html=True)
    st.caption("Ulas kembali rumus penting dan materi kunci secara cepat sebelum ujian dimulai.")

    st.text_input("🔍 Cari Rumus / Konsep Cepat...", placeholder="contoh: Pythagoras, Bentuk Akar, Na'at Man'ut")

    with st.expander("📖 Matematika (MTs & MA) — Eksponen, Akar & Logaritma"):
        st.markdown("""
        * **Perkalian Eksponen**: $a^m \\times a^n = a^{m+n}$
        * **Pembagian Eksponen**: $a^m \\div a^n = a^{m-n}$
        * **Bentuk Akar**: $\\sqrt{a \\times b} = \\sqrt{a} \\times \\sqrt{b}$ (contoh: $\\sqrt{50} = \\sqrt{25 \\times 2} = 5\\sqrt{2}$)
        * **Persamaan Kuadrat**: Rumus Diskriminan $D = b^2 - 4ac$
        """)

    with st.expander("📖 IPA Terpadu & Fisika — Besaran, Satuan & Hukum Newton"):
        st.markdown("""
        * **7 Besaran Pokok**: Panjang (m), Massa (kg), Waktu (s), Suhu (K), Kuat Arus (A), Intensitas Cahaya (cd), Jumlah Zat (mol).
        * **Hukum I Newton**: $\\Sigma F = 0$ (Kelembaman/Inersia)
        * **Hukum II Newton**: $F = m \\times a$
        """)

    with st.expander("📖 Bahasa Arab & Nahwu — Tanda Isim & Kalimat"):
        st.markdown("""
        * **Tanda-tanda Isim**: Kemasukan Tanwin, Kemasukan Alif Lam (ال), diawali huruf Jar.
        * **Dhomir (Kata Ganti Utama)**: Huwa (هُوَ = Dia Laki-laki), Hiya (هِيَ = Dia Perempuan), Anta (أَنْتَ = Kamu Laki-laki).
        """)


def render_uts_schedule_panel(schedules: list[dict], kelas: str, jenjang: str) -> None:
    """Prominent, database-driven UTS agenda for the next two weeks."""
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Jakarta")).date()
    upcoming = []
    for row in schedules or []:
        raw_date = row.get("tanggal_ujian")
        try:
            if isinstance(raw_date, datetime):
                exam_date = raw_date.date()
            elif isinstance(raw_date, date):
                exam_date = raw_date
            else:
                exam_date = date.fromisoformat(str(raw_date)[:10])
        except Exception:
            continue
        if today <= exam_date <= today + timedelta(days=14):
            upcoming.append((exam_date, row))

    upcoming.sort(key=lambda item: item[0])
    st.markdown("### 🗓️ Agenda UTS Santri")
    st.caption(f"Jadwal resmi database • Kelas {kelas} {jenjang} • 14 hari ke depan")
    if not upcoming:
        st.info("Belum ada jadwal UTS mendatang yang cocok dengan kelas dan jenjang akunmu. Jadwal akan muncul otomatis setelah tersedia di database.")
        return

    for exam_date, row in upcoming:
        days_left = (exam_date - today).days
        status = "HARI INI" if days_left == 0 else ("BESOK" if days_left == 1 else f"{days_left} HARI LAGI")
        hari_id = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"][exam_date.weekday()]
        bulan_id = [
            "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember"
        ][exam_date.month - 1]
        date_label = f"{hari_id}, {exam_date.day} {bulan_id} {exam_date.year}"
        mapel = html.escape(str(row.get("mapel") or "Mata pelajaran belum ditentukan"))
        st.markdown(
            f'<div style="border:1px solid rgba(16,185,129,.3);border-radius:12px;'
            f'padding:12px 14px;margin:8px 0;background:rgba(6,78,59,.18);">'
            f'<div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;">'
            f'<strong>{mapel}</strong><span style="font-size:11px;font-weight:800;color:#34d399;">{status}</span></div>'
            f'<div style="font-size:12px;opacity:.82;margin-top:5px;">{date_label}</div></div>',
            unsafe_allow_html=True,
        )


# =============================================================================
# 8. MAIN DASHBOARD ENTRY POINT
# =============================================================================

def render_student_intelligence_dashboard(nama_siswa: str = "", jenjang: str = "Semua Jenjang") -> None:
    """Entry point utama Portal SantriMANTAP dengan World-Class Glassmorphism UI."""
    
    # Inisialisasi Otomatis Tabel Database Jika Belum Ada
    ensure_student_intelligence_tables()

    # Mobile-first visual system. Keep the existing database/authentication and
    # learning functions unchanged; this layer only modernizes presentation.
    ui_css = """
    <style>
    :root { --si-ink:#10233f; --si-muted:#60708a; --si-green:#087f5b; --si-mint:#d8f7e9; --si-yellow:#fff0b3; --si-line:rgba(100,116,139,.20); }
    .main-hero { position:relative; isolation:isolate; overflow:hidden; margin:2px 0 20px; padding:clamp(22px,4vw,38px); border-radius:26px; color:#fff; background:radial-gradient(circle at 88% 10%,rgba(255,255,255,.22),transparent 26%),radial-gradient(circle at 10% 100%,rgba(45,212,191,.24),transparent 30%),linear-gradient(125deg,#123b65 0%,#087f70 56%,#16a085 100%); box-shadow:0 16px 36px rgba(8,79,92,.16); }
    .main-hero:after { content:'✦'; position:absolute; z-index:-1; right:6%; bottom:-36px; font-size:150px; color:rgba(255,255,255,.09); transform:rotate(-12deg); }
    .hero-kicker { font-size:10px; font-weight:850; letter-spacing:2px; color:#c6ffeb; text-transform:uppercase; }
    .hero-title { margin:10px 0 8px; font-size:clamp(28px,5vw,42px); line-height:1.08; letter-spacing:-1.2px; font-weight:900; color:#fff; }
    .hero-title span { color:#ffe58a; }
    .hero-subtitle { max-width:680px; font-size:14px; line-height:1.7; color:#e8fffa; }
    .portal-login-card { margin:14px 0; padding:clamp(18px,4vw,28px); border:1px solid rgba(16,185,129,.20); border-radius:22px; background:linear-gradient(135deg,rgba(220,252,231,.78),rgba(240,253,250,.7)); }
    .portal-login-card h2 { margin:8px 0; color:#123b50; font-size:clamp(22px,4vw,30px); line-height:1.2; letter-spacing:-.5px; }
    .portal-login-card p { margin:0; color:#52677b; font-size:14px; line-height:1.7; }
    .portal-login-kicker { color:#087f5b; font-size:10px; font-weight:900; letter-spacing:1.8px; }
    .portal-login-foot { margin-top:12px; padding:13px 15px; border:1px solid var(--si-line); border-radius:14px; background:rgba(148,163,184,.07); color:var(--si-muted); font-size:13px; line-height:1.65; }
    div[data-testid="stForm"] { padding:clamp(14px,3vw,22px); border:1px solid var(--si-line); border-radius:20px; background:rgba(255,255,255,.66); box-shadow:0 8px 24px rgba(15,23,42,.035); }
    div[data-testid="stFormSubmitButton"] button, div[data-testid="stButton"] button { min-height:45px; border-radius:13px; font-weight:750; transition:transform .15s ease,box-shadow .15s ease; }
    div[data-testid="stFormSubmitButton"] button:hover, div[data-testid="stButton"] button:hover { transform:translateY(-1px); box-shadow:0 7px 18px rgba(16,185,129,.16); }
    div[data-testid="stTabs"] { margin-top:8px; }
    div[data-testid="stTabs"] div[role="tablist"] { gap:6px; padding:5px; border-radius:15px; background:rgba(148,163,184,.09); }
    div[data-testid="stTabs"] button[role="tab"] { min-height:42px; padding:9px 13px; border-radius:11px; font-size:13px; font-weight:750; }
    div[data-testid="stMetric"] { padding:14px; border:1px solid var(--si-line); border-radius:17px; background:rgba(255,255,255,.58); box-shadow:0 5px 18px rgba(15,23,42,.025); }
    div[data-testid="stAlert"] { border-radius:14px; }
    section[data-testid="stMain"] > div { padding-top:clamp(12px,2.5vw,28px); }
    @media (max-width:760px) {
      .main-hero { border-radius:21px; padding:22px 19px; margin-bottom:15px; }
      .hero-title { font-size:30px; letter-spacing:-.8px; }
      .hero-subtitle { font-size:13px; line-height:1.65; }
      .portal-login-card { border-radius:18px; padding:19px 17px; }
      div[data-testid="stTabs"] div[role="tablist"] { overflow-x:auto; flex-wrap:nowrap; scrollbar-width:thin; }
      div[data-testid="stTabs"] button[role="tab"] { flex:0 0 auto; white-space:nowrap; font-size:12px; padding:8px 10px; }
      div[data-testid="stMetric"] { padding:11px; }
    }
    @media (prefers-reduced-motion: reduce) { * { transition:none !important; scroll-behavior:auto !important; } }
    </style>
    """
    st.markdown(ui_css, unsafe_allow_html=True)

    # HERO HEADER
    st.markdown("""
    <div class="main-hero">
      <div class="hero-kicker">RUANG BELAJAR PERSONAL • ROBOMANTAP</div>
      <div class="hero-title">Halo, Santri!<br/>Saatnya jadi <span>MANTAP.</span> ✨</div>
      <div class="hero-subtitle">Satu ruang untuk belajar, berlatih, melihat perkembangan, menyiapkan ujian, dan mendapatkan bantuan saat kamu membutuhkannya.</div>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.get("student_intelligence_authenticated"):
        if st.button("↩️ Keluar dari Portal", key="student_intelligence_logout", use_container_width=True):
            for key in (
                "student_intelligence_authenticated",
                "student_intelligence_identity",
                "student_intelligence_username",
                "student_intelligence_name",
                "student_intelligence_grade",
                "student_intelligence_pending_token",
                "student_intelligence_pending_username",
                "student_intelligence_pending_phone",
                "chat_messages",
                "last_ai_note",
                "last_ai_topic",
            ):
                st.session_state.pop(key, None)
            st.rerun()

    # Login harian menggunakan username + PIN. WhatsApp hanya dipakai untuk registrasi/pemulihan.
    if not st.session_state.get("student_intelligence_authenticated"):
        st.markdown("""
        <section class="portal-login-card">
          <div class="portal-login-kicker">RUANG BELAJAR PERSONAL</div>
          <h2>Senang bertemu kamu, Santri! ✨</h2>
          <p>Masuk untuk melihat agenda, melanjutkan belajar, dan bertanya kepada Asisten AI RoboMANTAP.</p>
        </section>
        """, unsafe_allow_html=True)
        with st.form("student_intelligence_login_form", clear_on_submit=False):
            entered_username = st.text_input(
                "Username Santri", placeholder="contoh: santri.aisyah",
                help="Username yang kamu buat saat mendaftar melalui WhatsApp."
            )
            entered_pin = st.text_input(
                "PIN Santri (6 angka)", placeholder="Masukkan PIN kamu",
                type="password", max_chars=6,
                help="PIN rahasia kamu. Jangan bagikan kepada siapa pun."
            )
            submitted = st.form_submit_button("Masuk ke Portal Santri  →", type="primary", use_container_width=True)

        if not submitted:
            st.markdown('<div class="portal-login-foot">Belum punya akun? Daftar melalui <b>Hubungi WA Sekarang</b> di halaman utama.</div>', unsafe_allow_html=True)
            return

        valid, username_or_message = validate_username(entered_username)
        if not valid:
            st.error(username_or_message)
            return
        if not re.fullmatch(r"\d{6}", str(entered_pin or "")):
            st.error("PIN harus tepat 6 angka.")
            return

        identity_data = fetch_student_wa_identity_by_username(username_or_message)
        if not identity_data:
            st.error("Username belum ditemukan atau akun belum aktif. Selesaikan pendaftaran di halaman utama.")
            st.info("Buka bagian **Hubungi WA Sekarang**, lalu selesaikan pendaftaran melalui WhatsApp.")
            return
        pin_hash = str(identity_data.get("pin_hash") or "")
        if not pin_hash:
            st.warning("Akun ini dibuat sebelum sistem PIN tersedia. Silakan perbarui pendaftaran melalui halaman utama agar PIN tersimpan.")
            return
        # Small per-session throttle to discourage repeated guesses.
        now_ts = datetime.now(timezone.utc).timestamp()
        attempts = st.session_state.get("student_pin_attempts", 0)
        last_attempt = st.session_state.get("student_pin_last_attempt", 0.0)
        if attempts >= 5 and now_ts - float(last_attempt or 0.0) < 300:
            st.error("Terlalu banyak percobaan. Tunggu 5 menit sebelum mencoba lagi.")
            return
        if not verify_student_pin(entered_pin, pin_hash):
            attempts = attempts + 1 if now_ts - float(last_attempt or 0.0) < 300 else 1
            st.session_state.student_pin_attempts = attempts
            st.session_state.student_pin_last_attempt = now_ts
            st.error("Username atau PIN tidak cocok. Periksa kembali lalu coba lagi.")
            return

        st.session_state.student_pin_attempts = 0
        st.session_state.student_pin_last_attempt = 0.0
        st.session_state.student_intelligence_authenticated = True
        st.session_state.student_intelligence_identity = identity_data
        st.session_state.student_intelligence_username = username_or_message
        st.session_state.student_intelligence_name = str(identity_data.get("nama") or "")
        st.session_state.student_intelligence_grade = str((identity_data.get("metadata") or {}).get("jenjang") or jenjang or "MTs")
        st.rerun()
        return

    identity_data = st.session_state.get("student_intelligence_identity") or {}
    meta = identity_data.get("metadata") or {}
    name = str(identity_data.get("nama") or st.session_state.get("student_intelligence_name") or "").strip()
    if not name:
        st.session_state.student_intelligence_authenticated = False
        st.session_state.pop("student_intelligence_identity", None)
        st.error("Identitas akun tidak lengkap. Silakan masuk kembali.")
        return

    kelas = str(meta.get("kelas") or "Belum diatur")
    jenjang_detected = str(meta.get("jenjang") or st.session_state.get("student_intelligence_grade") or "MTs").upper()
    wa_number = str(identity_data.get("wa_number") or "")

    # Refresh identity by username so revoked/disabled registrations are not trusted indefinitely.
    fresh_identity = fetch_student_wa_identity_by_username(
        st.session_state.get("student_intelligence_username", "")
    )
    if not fresh_identity:
        st.session_state.student_intelligence_authenticated = False
        st.session_state.pop("student_intelligence_identity", None)
        st.session_state.pop("student_intelligence_username", None)
        st.error("Akun tidak aktif atau tidak dapat diverifikasi. Silakan masuk kembali.")
        return
    identity_data = fresh_identity
    meta = identity_data.get("metadata") or {}
    name = str(identity_data.get("nama") or name).strip()
    kelas = str(meta.get("kelas") or kelas)
    jenjang_detected = str(meta.get("jenjang") or jenjang_detected).upper()
    wa_number = str(identity_data.get("wa_number") or "")

    uts_schedules = fetch_uts_schedules_db(kelas, jenjang_detected)
    sessions = fetch_student_sessions(name, jenjang=jenjang_detected)
    profile = build_student_profile(sessions)
    student_key_str = student_key(name, jenjang_detected)
    streak, is_new_day = update_and_get_daily_streak(student_key_str, profile)
    save_student_profile(name, jenjang_detected, profile)

    st.session_state.student_intelligence_name = name
    st.session_state.student_intelligence_grade = jenjang_detected

    if "welcomed_today" not in st.session_state or st.session_state.get("welcomed_user") != name:
        st.session_state.welcomed_today = True
        st.session_state.welcomed_user = name
        show_welcome_modal(name, kelas, jenjang_detected, streak, wa_number, uts_schedules)

    # Compact student identity strip: visible on mobile without taking over the page.
    st.markdown(
        f"""<div style="display:flex;align-items:center;gap:12px;margin:0 0 16px;padding:14px 16px;border:1px solid rgba(100,116,139,.18);border-radius:18px;background:linear-gradient(110deg,rgba(209,250,229,.58),rgba(240,253,250,.55));">
        <div style="display:flex;align-items:center;justify-content:center;flex:0 0 46px;height:46px;border-radius:15px;background:#d1fae5;font-size:23px;">🎓</div>
        <div style="min-width:0;flex:1;">
          <div style="font-size:10px;font-weight:850;letter-spacing:1.3px;text-transform:uppercase;color:#087f5b;">RUANG BELAJAR SAYA</div>
          <div style="font-size:18px;line-height:1.25;font-weight:850;color:#123b50;overflow-wrap:anywhere;">{html.escape(name)}</div>
          <div style="font-size:12px;color:#60708a;">Kelas {html.escape(kelas)} · {html.escape(jenjang_detected)}</div>
        </div>
        <div style="flex:0 0 auto;text-align:center;padding:8px 10px;border-radius:13px;background:#fff4c2;color:#795c00;">
          <div style="font-size:17px;font-weight:900;">🔥 {int(streak)}</div><div style="font-size:10px;font-weight:750;">hari aktif</div>
        </div>
        </div>""",
        unsafe_allow_html=True,
    )

    render_uts_schedule_panel(uts_schedules, kelas, jenjang_detected)

    # TABS UTAMA INTEGRATED
    tab_simulasi, tab_ai, tab_analytics, tab_materi, tab_automasi = st.tabs([
        "🎯 Latihan & UTS",
        "💬 Asisten AI",
        "📈 Progress Saya",
        "📚 Materi Ringkas",
        "📱 WhatsApp"
    ])

    with tab_ai:
        render_ai_chatbot_workspace(name, kelas, jenjang_detected, wa_number)

    with tab_analytics:
        if not sessions:
            st.warning("⚠️ Belum ditemukan sesi belajar dengan nama tersebut. Kerjakan simulasi UTS atau latihan adaptif untuk mulai membentuk grafik analitikal belajarmu.")
        else:
            render_learning_analytics(name, jenjang_detected, profile, sessions)

    with tab_simulasi:
        render_uts_simulation()

    with tab_automasi:
        render_student_automation(wa_number)

    with tab_materi:
        render_concept_sheets()

    st.caption(f"Portal SantriMANTAP v{STUDENT_INTELLIGENCE_VERSION} • Engineered by U.Project Nexus")
