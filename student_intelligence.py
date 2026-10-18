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

STUDENT_INTELLIGENCE_VERSION = "5.0"

# Seluruh tanggal operasional siswa menggunakan zona waktu resmi Indonesia Barat.
# Timestamp autentikasi/token tetap menggunakan UTC untuk konsistensi server.
try:
    from zoneinfo import ZoneInfo
    JAKARTA_TZ = ZoneInfo("Asia/Jakarta")
except Exception:  # fallback untuk runtime Python minimal
    JAKARTA_TZ = timezone(timedelta(hours=7))

_HARI_ID = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
_BULAN_ID = ("Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember")

def jakarta_now() -> datetime:
    """Waktu saat ini dengan zona waktu Asia/Jakarta, tidak bergantung zona server."""
    return datetime.now(JAKARTA_TZ)

def jakarta_today() -> date:
    return jakarta_now().date()

def format_tanggal_id(value: date) -> str:
    return f"{_HARI_ID[value.weekday()]}, {value.day} {_BULAN_ID[value.month - 1]} {value.year}"

def parse_schedule_date(value: Any) -> date | None:
    """Normalisasi tanggal database; timestamp aware dikonversi ke WIB sebelum tanggal diambil."""
    if value is None:
        return None
    try:
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                return value.astimezone(JAKARTA_TZ).date()
            return value.date()
        if isinstance(value, date):
            return value
        raw = str(value).strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if "T" in raw or " " in raw:
                if parsed.tzinfo is not None:
                    return parsed.astimezone(JAKARTA_TZ).date()
                return parsed.date()
        except ValueError:
            pass
        return date.fromisoformat(raw[:10])
    except Exception:
        return None

# =============================================================================
# 1. DATABASE INITIALIZATION (PENTING UNTUK APP.PY)
# =============================================================================

@st.cache_resource(show_spinner=False)
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

def _normalized_session_score(session: dict) -> float | None:
    """Normalisasi skor legacy OMI (skala 40) dan Quiz/TKA (skala 100), lalu batasi 0–100."""
    raw = session.get("nilai_akhir")
    if raw is None or str(raw).strip() == "":
        return None
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(score):
        return None
    mapel = str(session.get("mapel") or "")
    # Skor sesi OMI legacy tersimpan pada skala 40; Quiz/TKA sudah memakai skala 100.
    if not _is_practice_100_scale(mapel) and 0 <= score <= 40:
        score = score / 40.0 * 100.0
    return round(max(0.0, min(100.0, score)), 2)

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
        Paragraph(f"<b>Santri:</b> {nama_siswa} (Kelas {kelas} {jenjang}) | <b>Topik:</b> {topic_title} | <b>Tanggal:</b> {jakarta_now().strftime('%d %B %Y')}", meta_style),
        Spacer(1, 4)
    ]

    lines = text_content.split("\n")
    for line in lines:
        clean_line = line.strip()
        if not clean_line:
            continue
        clean_line = clean_line.replace(r"\circ", "°").replace(r"\cdot", "·").replace("\\", "")
        clean_line = re.sub(r"\\frac\{([^}]+)\}\{([^}]+)\}", r"\1/\2", clean_line)
        # Escape user/AI text before adding the limited ReportLab markup we support.
        escaped_line = html.escape(clean_line, quote=False)
        formatted_text = re.sub(r"\*([^*]+)\*", r"<b>\1</b>", escaped_line)
        formatted_text = re.sub(r"_([^_]+)_", r"<i>\1</i>", formatted_text)

        if clean_line.startswith("#") or (clean_line.startswith("*") and clean_line.endswith("*") and len(clean_line) < 80):
            clean_heading = html.escape(clean_line.strip("#* ").strip(), quote=False)
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
    today_str = jakarta_today().isoformat()
    last_active = profile_data.get("last_active_date")
    try:
        current_streak = max(0, int(profile_data.get("current_streak", 0) or 0))
    except (TypeError, ValueError):
        current_streak = 0
    is_new_day = False

    if not last_active:
        current_streak = 1
        is_new_day = True
    elif last_active == today_str:
        pass
    else:
        try:
            last_date = date.fromisoformat(last_active)
            if jakarta_today() - last_date == timedelta(days=1):
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
    """Menyusun diagnostik dari sesi SELESAI saja; state streak lama tetap dipertahankan."""
    completed = [s for s in sessions if str(s.get("status", "")).strip().upper() == "SELESAI"]
    total_attempts = len(completed)
    normalized_scores = []
    for session in completed:
        score = _normalized_session_score(session)
        if score is not None:
            normalized_scores.append(score)

    by_subject: dict[str, list[float]] = defaultdict(list)
    correct_total = wrong_total = blank_total = 0
    question_records: list[dict] = []
    topic_stats: dict[str, list[bool]] = defaultdict(list)

    # Sesi berjalan/draft tidak boleh memengaruhi diagnosis, akurasi, atau rekomendasi.
    for session in completed:
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

        score = _normalized_session_score(session)
        if score is not None:
            by_subject[mapel].append(score)
        if isinstance(quiz, list) and isinstance(detail, list):
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
                    "answer": answers.get(str(idx), answers.get(idx)) if isinstance(answers, dict) else None,
                })

    subject_mastery = {subject: round(sum(values) / len(values), 1) for subject, values in by_subject.items() if values}
    topic_mastery = {topic: round(sum(values) / len(values) * 100, 1) for topic, values in topic_stats.items() if values}
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
    answered_total = correct_total + wrong_total + blank_total
    completion_ratio = correct_total / answered_total * 100 if answered_total else 0
    consistency = min(100.0, total_attempts * 12.5) if total_attempts else 0
    weakest_subject = min(subject_mastery, key=subject_mastery.get) if subject_mastery else None
    weakest_topics = sorted(topic_mastery.items(), key=lambda item: item[1])[:5]

    risk_points = 0
    if normalized_scores and avg_score < 60: risk_points += 2
    elif normalized_scores and avg_score < 75: risk_points += 1
    if trend == "declining": risk_points += 2
    if blank_total > correct_total * 0.25 and blank_total > 0: risk_points += 1
    if total_attempts < 2: risk_points += 1
    risk_label = "HIGH ATTENTION" if risk_points >= 4 else "WATCH" if risk_points >= 2 else "ON TRACK"

    profile = dict(existing_profile or {})
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
        "updated_at": jakarta_now().isoformat(timespec="seconds"),
    })
    return profile

def fetch_student_profile(nama_siswa: str, jenjang: str) -> dict:
    """Muat state profil personal agar streak dan preferensi tidak hilang saat rerun."""
    conn = init_db_connection()
    if not conn:
        return {}
    try:
        with conn.session as session:
            row = session.execute(text("""
                SELECT profile_data FROM student_intelligence_profiles
                WHERE student_key = :key LIMIT 1
            """), {"key": student_key(nama_siswa, jenjang)}).mappings().first()
            if not row:
                return {}
            data = row.get("profile_data")
            if isinstance(data, dict):
                return data
            return _json_value(data, {}) if data else {}
    except Exception as exc:
        print(f"[STUDENT INTELLIGENCE] profile read warning: {exc}")
        return {}


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
        safe_subject = html.escape(str(weakest))
        recs.append(f"🎯 <b>[PRIORITAS UTAMA]</b> Alokasikan 60% waktu belajar berikutnya untuk <b>{safe_subject}</b> sebelum berpindah ke mata pelajaran baru.")
        
    for topic, mastery in profile.get("weakest_topics", [])[:2]:
        if mastery < 70:
            safe_topic = html.escape(str(topic))
            recs.append(f"🧩 <b>[PEMAHAMAN KONSEP]</b> Kuatkan kembali topik <b>{safe_topic}</b> (Akurasi: {float(mastery):.0f}%). Gunakan latihan bertahap dari soal dasar ke penalaran.")
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

# =============================================================================
# 6. LEARNING WORKSPACES
# =============================================================================

def _generate_student_ai_response(prompt: str, nama_siswa: str, kelas: str, jenjang: str, uploaded_file=None) -> str:
    """Generate a grounded study answer; supports text, image stimulus, and searchable PDF text."""
    context = (
        "Kamu adalah RoboMANTAP, asisten belajar yang ramah, teliti, dan jujur. "
        "Jawab dalam Bahasa Indonesia yang jelas sesuai tingkat siswa. Berikan langkah penjelasan "
        "dan contoh seperlunya. Jangan mengarang jadwal resmi; rujuk agenda portal untuk jadwal. "
        f"Identitas siswa: {nama_siswa}, kelas {kelas} {jenjang}. "
        f"Waktu lokal: {jakarta_now().strftime('%A, %d %B %Y pukul %H:%M WIB')} WIB. "
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
    """Tutor belajar multimodal: diskusi materi, analisis lampiran, dan penyimpanan catatan."""
    st.markdown('<div class="pi-kicker2">Tutor belajar personal</div><div class="pi-h2">Tanya, pahami, lalu praktikkan.</div>', unsafe_allow_html=True)
    st.caption("AI membantu menjelaskan konsep, membahas foto soal atau PDF, dan menyusun catatan yang bisa kamu simpan.")

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
    
    st.markdown('<div class="pi-analytics-heading">🎯 Kondisi Belajar Saat Ini</div>', unsafe_allow_html=True)
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
        st.markdown('<div class="pi-analytics-heading" style="font-size:16px">📚 Pemahaman Mata Pelajaran</div>', unsafe_allow_html=True)
        st.markdown('<div class="pi-analytics-subtitle">Rata-rata nilai akhir ujian, kuis, atau pengerjaan keseluruhan</div>', unsafe_allow_html=True)
        if profile.get("subject_mastery"):
            for mapel, mastery in sorted(profile["subject_mastery"].items(), key=lambda x: x[1]):
                m_val = min(100.0, max(0.0, mastery))
                bar_color = "#f87171" if m_val < 50 else "#fbbf24" if m_val < 75 else "#34d399"
                mapel_html = f"""
                <div class="topic-item" style="margin-bottom: 8px;">
                    <div class="topic-header">
                        <span style="font-size: 12px; font-weight: 700;">{html.escape(str(mapel))}</span>
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
        st.markdown('<div class="pi-analytics-heading" style="font-size:16px">🧩 Topik Perlu Perhatian</div>', unsafe_allow_html=True)
        st.markdown('<div class="pi-analytics-subtitle">Akurasi kebenaran menjawab soal di bawah 80% (&lt; 80%)</div>', unsafe_allow_html=True)
        weak = [(topic, mastery) for topic, mastery in profile.get("weakest_topics", []) if mastery < 80]    
        if weak:
            for topic, mastery in weak[:5]:
                m_val = min(100.0, max(0.0, mastery))
                bar_color = "#f87171" if m_val < 50 else "#fbbf24"
                topic_html = f"""
                <div class="topic-item" style="margin-bottom: 8px;">
                    <div class="topic-header">
                        <span style="font-size: 12px; font-weight: 700;">{html.escape(str(topic))}</span>
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
    st.markdown('<div class="pi-analytics-heading" style="font-size:16px">🚀 Rekomendasi Langkah Selanjutnya</div>', unsafe_allow_html=True)
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
            score = _normalized_session_score(s)
            rows.append({
                "Waktu": s.get("updated_at") or s.get("created_at"),
                "Mapel": _clean_activity_marker(s.get("mapel") or ""),
                "Status": s.get("status"),
                "Skor": round(score, 1) if score is not None else None,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


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


def render_concept_sheets(nama_siswa: str = "Santri", kelas: str = "", jenjang: str = "MTs") -> None:
    """Studio materi personal: membuat penjelasan sesuai topik, tujuan, dan jenjang siswa."""
    st.markdown('<div class="sm-section-kicker">Materi yang menyesuaikan kebutuhanmu</div><div class="sm-section-title">Studio Materi Personal.</div>', unsafe_allow_html=True)
    st.markdown('<div class="sm-muted">Tidak lagi sekadar daftar rumus statis. Tulis topik yang sedang dipelajari, pilih bentuk bantuan, lalu RoboMANTAP menyusun materi untuk jenjangmu.</div>', unsafe_allow_html=True)
    with st.form("portal_personal_material_form", clear_on_submit=False):
        subject = st.selectbox("Mata pelajaran", ["Matematika", "Bahasa Indonesia", "Bahasa Inggris", "IPA", "Fisika", "Kimia", "Biologi", "Ekonomi", "Sejarah", "Geografi", "Sosiologi", "Bahasa Arab", "Nahwu", "Fikih", "Akidah Akhlak", "Lainnya"], key="portal_material_subject")
        topic = st.text_input("Topik yang ingin dipahami", placeholder="Contoh: persamaan linear, ide pokok, hukum Newton, i'rab na'at", key="portal_material_topic")
        purpose = st.selectbox("Bentuk bantuan", ["Jelaskan konsep dari dasar", "Rangkuman belajar singkat", "Contoh soal dan pembahasan bertahap", "Latihan mandiri dengan kunci dan pembahasan", "Persiapan ujian: konsep inti dan kesalahan umum"], key="portal_material_purpose")
        submitted = st.form_submit_button("✨ Buat materi untuk saya", type="primary", use_container_width=True)
    if submitted:
        if not str(topic or "").strip():
            st.warning("Tulis dulu topik yang ingin kamu pelajari agar materinya tepat sasaran.")
        else:
            prompt = (
                f"Buat materi belajar personal untuk mata pelajaran {subject}, topik {str(topic).strip()}, "
                f"jenjang {jenjang}, kelas {kelas}. Tujuan: {purpose}. "
                "Gunakan Bahasa Indonesia yang jelas sesuai usia siswa. Susun dengan judul, konsep inti, "
                "penjelasan bertahap, contoh yang benar dan relevan, lalu ringkasan 3 poin. "
                "Jika membuat latihan, berikan kunci dan alasan pembahasan di bagian terpisah. "
                "Jangan mengklaim materi ini berasal dari dokumen guru atau kisi-kisi resmi jika tidak diberikan. "
                "Jika ada informasi yang bergantung pada kurikulum lokal, nyatakan asumsi dengan jujur."
            )
            with st.spinner("RoboMANTAP sedang menyusun materi berdasarkan topikmu…"):
                try:
                    result = _generate_student_ai_response(prompt, nama_siswa, kelas, jenjang)
                except Exception as exc:
                    print(f"[STUDENT INTELLIGENCE] material generation error: {exc}")
                    result = ""
            if result:
                st.session_state.portal_personal_material = result
                st.session_state.portal_personal_material_topic = f"{subject} · {str(topic).strip()}"
                st.session_state.last_ai_note = result
                st.session_state.last_ai_topic = f"{subject} · {str(topic).strip()}"
                record_student_action(nama_siswa, jenjang, "PERSONAL_MATERIAL", f"Materi: {str(topic).strip()[:120]}", {"mapel": subject, "topic": str(topic).strip(), "purpose": purpose})
    material = st.session_state.get("portal_personal_material")
    if material:
        st.divider()
        st.markdown(f"### 📘 {html.escape(str(st.session_state.get('portal_personal_material_topic') or 'Materi personal'))}")
        st.markdown(material)
        pdf_bytes = generate_pdf_notes(nama_siswa, kelas, jenjang, str(st.session_state.get("portal_personal_material_topic") or "Rangkuman Belajar"), str(material))
        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(nama_siswa or "Santri")).strip("_") or "Santri"
        st.download_button("⬇️ Unduh rangkuman PDF", data=pdf_bytes, file_name=f"Rangkuman_RoboMANTAP_{safe_name}.pdf", mime="application/pdf", type="primary", use_container_width=True)
    else:
        st.info("Materi yang kamu buat akan tampil di sini. Mulai dengan satu topik yang paling membingungkanmu.")


def render_uts_schedule_panel(schedules: list[dict], kelas: str, jenjang: str, compact: bool = False) -> None:
    """Agenda resmi berbasis DB, dihitung relatif terhadap tanggal Asia/Jakarta."""
    today = jakarta_today()
    upcoming = []
    for row in schedules or []:
        exam_date = parse_schedule_date(row.get("tanggal_ujian"))
        if exam_date is not None and today <= exam_date <= today + timedelta(days=30):
            upcoming.append((exam_date, row))
    upcoming.sort(key=lambda item: (item[0], str(item[1].get("jam_mulai") or "")))

    st.markdown("### 🗓️ Agenda akademik" if compact else "## 🗓️ Agenda ujian kamu")
    st.caption(f"Jadwal dari database • Kelas {kelas} {jenjang} • Acuan waktu Asia/Jakarta")
    if not upcoming:
        st.info("Belum ada ujian terjadwal untuk kelas dan jenjang akunmu. Informasi ini akan muncul setelah jadwal resmi tersedia.")
        return
    for exam_date, row in upcoming[:5 if compact else 12]:
        days_left = (exam_date - today).days
        status = "HARI INI" if days_left == 0 else "BESOK" if days_left == 1 else f"{days_left} hari lagi"
        mapel = html.escape(str(row.get("mapel") or "Mata pelajaran belum ditentukan"))
        jam = html.escape(str(row.get("jam_mulai") or row.get("waktu_mulai") or ""))
        detail = format_tanggal_id(exam_date) + (f" • {jam} WIB" if jam else "")
        st.markdown(
            f'<div class="portal-agenda-card"><div class="portal-agenda-date"><span>{exam_date.day:02d}</span><small>{_BULAN_ID[exam_date.month-1][:3].upper()}</small></div>'
            f'<div class="portal-agenda-body"><strong>{mapel}</strong><div>{html.escape(detail)}</div></div>'
            f'<span class="portal-agenda-status">{html.escape(status)}</span></div>',
            unsafe_allow_html=True,
        )


# =============================================================================
# 8. MAIN DASHBOARD ENTRY POINT
# =============================================================================

def _navigate_student_portal(section: str) -> None:
    """Widget callback: ubah navigasi sebelum radio dibuat ulang pada rerun berikutnya."""
    st.session_state.student_portal_section = section


def render_student_intelligence_dashboard(nama_siswa: str = "", jenjang: str = "Semua Jenjang") -> None:
    """Portal SantriMANTAP: pengalaman belajar siswa berbasis tujuan dan data nyata."""
    ensure_student_intelligence_tables()
    st.markdown(r"""
    <style>
    :root { --portal-ink:#12243a; --portal-muted:#64748b; --portal-line:#e2e8f0; --portal-green:#087f5b; }
    .stApp { background:radial-gradient(ellipse at 0% 0%,rgba(45,212,191,.12),transparent 34%),#f7fafc; }
    .block-container { max-width:1220px;padding-top:1rem;padding-bottom:3rem; }
    .pi-hero { position:relative;overflow:hidden;border-radius:28px;padding:clamp(22px,4vw,42px);color:#f8fafc;background:linear-gradient(118deg,#10243d 0%,#104b57 54%,#087f5b 100%);box-shadow:0 18px 48px rgba(16,36,61,.16);margin-bottom:18px; }
    .pi-hero:after { content:"";position:absolute;width:250px;height:250px;right:-65px;top:-105px;border-radius:50%;border:1px solid #ffffff30;box-shadow:0 0 0 28px #ffffff0c,0 0 0 60px #ffffff09; }
    .pi-kicker {font-size:10px;font-weight:900;letter-spacing:1.8px;text-transform:uppercase;opacity:.8;}
    .pi-title {font-size:clamp(28px,4.5vw,44px);line-height:1.08;font-weight:900;letter-spacing:-1.3px;margin:10px 0;}
    .pi-sub {max-width:700px;color:#e1f5f1;font-size:14px;line-height:1.65;}
    .pi-chip {display:inline-block;margin:12px 6px 0 0;padding:7px 11px;border-radius:99px;border:1px solid #ffffff38;background:#ffffff12;font-size:11px;font-weight:800;}
    .pi-kicker2 {color:#087f5b;font-size:10px;letter-spacing:1.6px;font-weight:900;text-transform:uppercase;margin-bottom:5px;}
    .pi-h2 {color:var(--portal-ink);font-size:clamp(22px,3vw,30px);font-weight:900;letter-spacing:-.6px;line-height:1.2;margin:0 0 7px;}
    .pi-muted {color:var(--portal-muted);font-size:13px;line-height:1.65;}
    .pi-card {height:100%;border:1px solid var(--portal-line);border-radius:20px;padding:18px;background:#fff;box-shadow:0 7px 24px #10243d08;}
    .pi-icon {width:44px;height:44px;border-radius:15px;background:#e5f7ef;display:flex;align-items:center;justify-content:center;font-size:22px;margin-bottom:12px;}
    .pi-card-title {color:var(--portal-ink);font-size:15px;font-weight:900;margin-bottom:6px;}
    .pi-stats-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;width:100%;margin:12px 0 18px;box-sizing:border-box;}
    .pi-stat {height:100%;min-width:0;box-sizing:border-box;border:1px solid #dbe7f1;border-radius:17px;padding:14px;background:linear-gradient(145deg,#ffffff 0%,#f0fbf7 100%);box-shadow:0 5px 16px rgba(23,66,83,.06);overflow-wrap:anywhere;}
    .pi-stat-label {color:#52657b;font-size:11px;font-weight:800;line-height:1.4;}
    .pi-stat-value {color:#12334a;font-size:clamp(23px,3vw,31px);font-weight:900;line-height:1.2;margin-top:5px;overflow-wrap:anywhere;}
    .pi-stat:nth-child(2){background:linear-gradient(145deg,#fff 0%,#eef6ff 100%);border-color:#d8e8ff}
    .pi-stat:nth-child(3){background:linear-gradient(145deg,#fff 0%,#fff8e9 100%);border-color:#f4e5b8}
    .pi-stat:nth-child(4){background:linear-gradient(145deg,#fff 0%,#f7f0ff 100%);border-color:#e8dcff}
    .pi-stat .pi-muted{color:#5b6d80;font-size:11px;line-height:1.45;margin-top:4px;}
    .portal-agenda-card{display:grid;grid-template-columns:58px minmax(0,1fr) auto;align-items:center;gap:12px;padding:13px;margin:10px 0;border:1px solid #dce9f4;border-radius:18px;background:linear-gradient(110deg,#ffffff 0%,#f1fbff 55%,#f4fff8 100%);box-shadow:0 5px 16px rgba(30,64,90,.06);min-width:0;box-sizing:border-box}
    .portal-agenda-date{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:58px;border-radius:14px;background:linear-gradient(145deg,#d9f6eb,#dceeff);color:#145c54;font-weight:900}
    .portal-agenda-date span{font-size:24px;line-height:1.1}.portal-agenda-date small{font-size:10px;letter-spacing:.08em}
    .portal-agenda-body{min-width:0;overflow-wrap:anywhere}.portal-agenda-body strong{display:block;color:#18364e;font-size:14px;line-height:1.4;margin-bottom:4px}.portal-agenda-body div{color:#5b7084;font-size:12px;line-height:1.5}
    .portal-agenda-status{display:inline-flex;align-items:center;justify-content:center;max-width:100%;padding:6px 9px;border-radius:999px;background:#e2f8ed;color:#176849;font-size:10px;font-weight:900;text-align:center;white-space:normal}
    .eval-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:12px 0 16px}
    .eval-card{min-width:0;box-sizing:border-box;padding:14px;border-radius:17px;box-shadow:0 5px 16px rgba(23,66,83,.06);overflow-wrap:anywhere}
    .eval-title{font-size:12px;font-weight:850;line-height:1.45;color:#324b60!important}.eval-value{font-size:25px;font-weight:900;line-height:1.25;margin-top:7px;color:#173b52!important}
    .status-banner{display:flex;align-items:flex-start;gap:10px;padding:14px;border-radius:16px;margin:12px 0 18px;font-size:13px;line-height:1.6;color:#29465b!important}
    .status-banner b{color:#18364e!important}.status-banner-red{background:#fff0ed;border:1px solid #ffd1c9}.status-banner-yellow{background:#fff8df;border:1px solid #f4e2a5}.status-banner-green{background:#e8fbf0;border:1px solid #bcebd0}
    .topic-item{background:#fff;border:1px solid #e2ebf2;border-radius:13px;padding:10px 11px;color:#243e54;box-shadow:0 3px 10px rgba(23,66,83,.04)}
    .topic-header{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:7px;color:#29465b;overflow-wrap:anywhere}.topic-header span:first-child{min-width:0;overflow-wrap:anywhere}.topic-bar-bg{width:100%;background:#e8eef4;border-radius:999px;overflow:hidden}.topic-bar-fill{height:100%;border-radius:999px}
    .rec-card{display:flex;align-items:flex-start;gap:11px;background:linear-gradient(110deg,#fff 0%,#f4fbff 100%);border:1px solid #dceaf4;border-radius:15px;padding:13px;margin:9px 0;color:#2b465b;font-size:13px;line-height:1.6;box-shadow:0 4px 13px rgba(23,66,83,.04)}
    .rec-num{flex:0 0 29px;width:29px;height:29px;border-radius:10px;display:grid;place-items:center;background:#dff7ed;color:#087f5b;font-weight:900}
    .pi-analytics-heading{font-size:18px;font-weight:900;color:#17384e;margin:12px 0 7px}.pi-analytics-subtitle{font-size:12px;color:#5b7084;line-height:1.6;margin-bottom:10px}
    @media(max-width:760px){.pi-stats-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.pi-stat{padding:11px 10px;border-radius:14px}.pi-stat-label{font-size:10px}.pi-stat-value{font-size:22px}.pi-stat .pi-muted{font-size:10px}.eval-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.eval-card{padding:12px;border-radius:14px}.eval-value{font-size:22px}.portal-agenda-card{grid-template-columns:48px minmax(0,1fr);gap:9px;padding:10px;border-radius:15px}.portal-agenda-date{grid-row:span 2;min-height:52px}.portal-agenda-date span{font-size:21px}.portal-agenda-status{grid-column:2;justify-self:start;font-size:9px;padding:5px 8px}.portal-agenda-body strong{font-size:13px}.portal-agenda-body div{font-size:11px}.status-banner{padding:12px;font-size:12px}.rec-card{padding:11px;font-size:12px}}
    @media(max-width:360px){.pi-stats-grid{gap:6px}.pi-stat{padding:9px 8px}.pi-stat-value{font-size:19px}.eval-grid{gap:6px}.eval-card{padding:10px}.eval-title{font-size:11px}.eval-value{font-size:19px}.portal-agenda-card{grid-template-columns:42px minmax(0,1fr);gap:8px}.portal-agenda-date span{font-size:19px}}
    div[data-testid="stForm"] {border:1px solid var(--portal-line);border-radius:20px;padding:clamp(14px,3vw,22px);background:#ffffffd9;}
    div[data-testid="stButton"] button,div[data-testid="stFormSubmitButton"] button,div[data-testid="stDownloadButton"] button {min-height:44px;border-radius:13px;font-weight:800;}
    div[role="radiogroup"] {gap:7px;}
    div[role="radiogroup"] label {border:1px solid var(--portal-line);border-radius:13px;padding:9px 12px;background:#fff;}
    div[data-testid="stMetric"] {border:1px solid var(--portal-line);border-radius:15px;padding:12px;background:#fff;}

    /* === MOBILE-FIRST: Portal SantriMANTAP === */
    @media (max-width: 768px) {
        /* Override ui_theme.py only for the 4 compact student-stat cards. */
        div[data-testid="stAppViewBlockContainer"] div[data-testid="stHorizontalBlock"]:has(.pi-stat) {
            display:flex !important;
            flex-direction:row !important;
            flex-wrap:wrap !important;
            align-items:stretch !important;
            gap:8px !important;
            min-width:0 !important;
        }
        div[data-testid="stAppViewBlockContainer"] div[data-testid="stHorizontalBlock"]:has(.pi-stat) > div[data-testid="column"] {
            flex:0 0 calc(50% - 4px) !important;
            width:calc(50% - 4px) !important;
            min-width:0 !important;
            max-width:calc(50% - 4px) !important;
            box-sizing:border-box !important;
        }
        div[data-testid="stAppViewBlockContainer"] div[data-testid="stHorizontalBlock"]:has(.pi-stat) > div[data-testid="column"] > div {
            width:100% !important; max-width:100% !important; min-width:0 !important;
        }
        .pi-stat {
            height:100% !important;
            min-height:104px;
            padding:11px 10px !important;
            border-radius:14px !important;
            overflow-wrap:anywhere;
            box-sizing:border-box !important;
        }
        .pi-stat-label {font-size:clamp(10px,2.8vw,12px) !important;line-height:1.35 !important;overflow-wrap:anywhere;}
        .pi-stat-value {font-size:clamp(19px,5.6vw,24px) !important;line-height:1.2 !important;overflow-wrap:anywhere;}
        .pi-muted {font-size:11px !important;line-height:1.45 !important;overflow-wrap:anywhere;}
        /* Six navigation options: two touch-friendly columns instead of a long horizontal strip. */
        div[data-testid="stAppViewBlockContainer"] [data-testid="stRadio"] div[role="radiogroup"] {
            display:grid !important;
            grid-template-columns:repeat(2,minmax(0,1fr)) !important;
            align-items:stretch !important;
            gap:7px !important;
            width:100% !important;
        }
        div[data-testid="stAppViewBlockContainer"] [data-testid="stRadio"] div[role="radiogroup"] > label {
            display:flex !important;
            align-items:center !important;
            min-width:0 !important;
            width:100% !important;
            min-height:43px !important;
            padding:9px 8px !important;
            margin:0 !important;
            box-sizing:border-box !important;
            white-space:normal !important;
            overflow-wrap:anywhere !important;
            border:1px solid var(--portal-line) !important;
            border-radius:12px !important;
            background:#fff !important;
        }
        div[data-testid="stAppViewBlockContainer"] [data-testid="stRadio"] label p {font-size:12px !important;line-height:1.3 !important;margin:0 !important;}
        .pi-hero {width:100%;box-sizing:border-box;border-radius:21px;padding:22px 18px;margin-bottom:15px;}
        .pi-title {font-size:clamp(27px,7.5vw,34px);line-height:1.12;overflow-wrap:anywhere;}
        .pi-sub {font-size:13px;line-height:1.55;max-width:100%;}
        .pi-chip {font-size:10px;padding:7px 9px;line-height:1.3;}
        .pi-card {height:auto;min-width:0;padding:15px;border-radius:16px;box-sizing:border-box;overflow-wrap:anywhere;}
        .pi-card-title {font-size:14px;line-height:1.35;overflow-wrap:anywhere;}
        .pi-h2 {font-size:clamp(21px,5.8vw,27px);line-height:1.22;overflow-wrap:anywhere;}
        div[data-testid="stForm"] {width:100%;max-width:100%;padding:13px!important;box-sizing:border-box;}
        div[data-testid="stButton"] button,div[data-testid="stFormSubmitButton"] button,div[data-testid="stDownloadButton"] button {width:100%;min-height:44px;white-space:normal;line-height:1.3;padding:10px 12px;}
        [data-testid="stDataFrame"],[data-testid="stTable"] {max-width:100%;min-width:0;overflow-x:auto;}
        [data-testid="stMarkdownContainer"] table {display:block;max-width:100%;overflow-x:auto;white-space:nowrap;}
        [data-testid="stMarkdownContainer"] img {max-width:100%;height:auto;}
    }
    @media(max-width:420px) {
        div[data-testid="stAppViewBlockContainer"] {padding-left:10px!important;padding-right:10px!important;}
        .pi-hero {padding:19px 14px;border-radius:18px;}
        .pi-stat {padding:10px 8px!important;min-height:100px;}
        .pi-stat-value {font-size:clamp(18px,5.4vw,22px)!important;}
        div[data-testid="stAppViewBlockContainer"] [data-testid="stRadio"] div[role="radiogroup"] {gap:6px!important;}
        div[data-testid="stAppViewBlockContainer"] [data-testid="stRadio"] div[role="radiogroup"] > label {padding:8px 6px!important;min-height:42px!important;}
        div[data-testid="stAppViewBlockContainer"] [data-testid="stRadio"] label p {font-size:11px!important;}
        .pi-card {padding:13px;border-radius:14px;}
    }
    @media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
    </style>
    """, unsafe_allow_html=True)

    now = jakarta_now()
    today = now.date()
    st.markdown(f"""<section class="pi-hero"><div class="pi-kicker">U.Project Nexus · RoboMANTAP Intelligence</div><div class="pi-title">Hai, Santri!<br/>Hari ini kita naik level.</div><div class="pi-sub">Ruang belajar seru serba ada: tanya Tutor AI RoboMANTAP, latihan pintar, dan buat rangkuman materi yang kamu inginkan! ✨</div><span class="pi-chip">📅 {format_tanggal_id(today)}</span><span class="pi-chip">🕒 {now.strftime('%H:%M')} WIB</span><span class="pi-chip">✦ AI Learning Companion</span></section>""", unsafe_allow_html=True)

    if st.session_state.get("student_intelligence_authenticated"):
        top_left, top_right = st.columns([5, 1])
        with top_left:
            ident = st.session_state.get("student_intelligence_identity") or {}
            imeta = ident.get("metadata") or {}
            st.caption(f"Akun: **{html.escape(str(ident.get('nama') or st.session_state.get('student_intelligence_name') or 'Santri'))}** · {html.escape(str(imeta.get('kelas') or 'Kelas belum diatur'))} {html.escape(str(imeta.get('jenjang') or st.session_state.get('student_intelligence_grade') or ''))}")
        with top_right:
            if st.button("Keluar", key="student_intelligence_logout", use_container_width=True):
                for key in ("student_intelligence_authenticated","student_intelligence_identity","student_intelligence_username","student_intelligence_name","student_intelligence_grade","student_intelligence_pending_token","student_intelligence_pending_username","student_intelligence_pending_phone","chat_messages","last_ai_note","last_ai_topic","student_pin_attempts","student_pin_last_attempt"):
                    st.session_state.pop(key, None)
                st.rerun()

    if not st.session_state.get("student_intelligence_authenticated"):
        st.markdown('<div class="pi-card"><div class="pi-kicker2">Ruang belajar personal</div><div class="pi-h2">Masuk untuk mulai belajar!</div><div class="pi-muted">Gunakan username dan PIN dari pendaftaran akun bersama WA-RoboMANTAP.</div></div>', unsafe_allow_html=True)
        with st.form("student_intelligence_login_form", clear_on_submit=False):
            entered_username = st.text_input("Username Santri", placeholder="contoh: santri.aisyah", help="Username yang didaftarkan melalui WhatsApp RoboMANTAP.")
            entered_pin = st.text_input("PIN Santri · 6 angka", placeholder="Masukkan PIN rahasia", type="password", max_chars=6)
            submitted = st.form_submit_button("Masuk ke ruang belajar →", type="primary", use_container_width=True)
        if not submitted:
            st.info("Belum punya akun? Selesaikan pendaftaran melalui menu pendaftaran WhatsApp di halaman utama.", icon="👋")
            return
        valid, username_or_message = validate_username(entered_username)
        if not valid:
            st.error(username_or_message); return
        if not re.fullmatch(r"\d{6}", str(entered_pin or "")):
            st.error("PIN harus tepat 6 angka."); return
        identity_data = fetch_student_wa_identity_by_username(username_or_message)
        if not identity_data:
            st.error("Username belum ditemukan atau akun belum aktif.")
            st.info("Selesaikan pendaftaran melalui halaman utama RoboMANTAP."); return
        pin_hash = str(identity_data.get("pin_hash") or "")
        if not pin_hash:
            st.warning("Akun ini belum memiliki PIN. Perbarui pendaftaran melalui halaman utama."); return
        now_ts = datetime.now(timezone.utc).timestamp()
        attempts = st.session_state.get("student_pin_attempts", 0)
        last_attempt = st.session_state.get("student_pin_last_attempt", 0.0)
        if attempts >= 5 and now_ts - float(last_attempt or 0.0) < 300:
            st.error("Terlalu banyak percobaan. Tunggu 5 menit sebelum mencoba lagi."); return
        if not verify_student_pin(entered_pin, pin_hash):
            attempts = attempts + 1 if now_ts - float(last_attempt or 0.0) < 300 else 1
            st.session_state.student_pin_attempts = attempts; st.session_state.student_pin_last_attempt = now_ts
            st.error("Username atau PIN tidak cocok. Periksa kembali lalu coba lagi."); return
        st.session_state.student_pin_attempts = 0; st.session_state.student_pin_last_attempt = 0.0
        st.session_state.student_intelligence_authenticated = True
        st.session_state.student_intelligence_identity = identity_data
        st.session_state.student_intelligence_username = username_or_message
        st.session_state.student_intelligence_name = str(identity_data.get("nama") or "")
        st.session_state.student_intelligence_grade = str((identity_data.get("metadata") or {}).get("jenjang") or jenjang or "MTs")
        st.rerun(); return

    identity_data = st.session_state.get("student_intelligence_identity") or {}
    fresh_identity = fetch_student_wa_identity_by_username(st.session_state.get("student_intelligence_username", ""))
    if not fresh_identity:
        st.session_state.student_intelligence_authenticated = False
        st.session_state.pop("student_intelligence_identity", None)
        st.session_state.pop("student_intelligence_username", None)
        st.error("Akun tidak aktif atau tidak dapat diverifikasi. Silakan masuk kembali."); return
    identity_data = fresh_identity
    meta = identity_data.get("metadata") or {}
    name = str(identity_data.get("nama") or "").strip()
    if not name:
        st.session_state.student_intelligence_authenticated = False
        st.session_state.pop("student_intelligence_identity", None)
        st.error("Identitas akun tidak lengkap. Silakan masuk kembali."); return
    kelas = str(meta.get("kelas") or "Belum diatur")
    jenjang_detected = str(meta.get("jenjang") or st.session_state.get("student_intelligence_grade") or "MTs").upper()
    wa_number = str(identity_data.get("wa_number") or "")
    st.session_state.student_intelligence_identity = identity_data
    st.session_state.student_intelligence_name = name
    st.session_state.student_intelligence_grade = jenjang_detected

    uts_schedules = fetch_uts_schedules_db(kelas, jenjang_detected)
    sessions = fetch_student_sessions(name, jenjang=jenjang_detected)
    stored_profile = fetch_student_profile(name, jenjang_detected)
    profile = build_student_profile(sessions, existing_profile=stored_profile)
    student_key_str = student_key(name, jenjang_detected)
    streak, is_new_day = update_and_get_daily_streak(student_key_str, profile)
    save_student_profile(name, jenjang_detected, profile)
    avg = float(profile.get("average_score") or 0)
    attempts_count = int(profile.get("attempts") or 0)
    weakest_subject = profile.get("weakest_subject")
    weak_topics = [(topic, value) for topic, value in profile.get("weakest_topics", []) if float(value or 0) < 80]
    upcoming_dates = [(parse_schedule_date(row.get("tanggal_ujian")), row) for row in uts_schedules]
    upcoming_dates = [(d, row) for d, row in upcoming_dates if d is not None and d >= today]
    upcoming_dates.sort(key=lambda x: x[0])
    next_exam = upcoming_dates[0] if upcoming_dates else None
    days_to_exam = (next_exam[0] - today).days if next_exam else None

    st.markdown(f'<div class="pi-kicker2">Dashboard pribadimu</div><div class="pi-h2">Assalamu’alaikum, {html.escape(name.split()[0])}! 👋</div><div class="pi-muted">{html.escape(kelas)} {html.escape(jenjang_detected)} · {"Aktivitas hari ini mulai dihitung—ayo buat satu kemajuan kecil." if is_new_day else "Setiap sesi belajar membantumu mengenali cara belajar yang lebih efektif."}</div>', unsafe_allow_html=True)
    exam_label = ("Hari ini" if days_to_exam == 0 else "Besok" if days_to_exam == 1 else f"H-{days_to_exam}") if next_exam else "—"
    exam_subject = str(next_exam[1].get("mapel") or "Ujian") if next_exam else "Belum ada agenda"
    # HTML grid sengaja dipakai agar aturan global st.columns tidak memaksa metrik menjadi 1 kolom di HP.
    st.markdown(f'''<div class="pi-stats-grid">
      <div class="pi-stat"><div class="pi-stat-label">📊 Rata-rata hasil</div><div class="pi-stat-value">{avg:.0f}<small style="font-size:13px">%</small></div><div class="pi-muted">Dari sesi tersimpan</div></div>
      <div class="pi-stat"><div class="pi-stat-label">📚 Sesi belajar</div><div class="pi-stat-value">{attempts_count}</div><div class="pi-muted">Riwayat yang ditemukan</div></div>
      <div class="pi-stat"><div class="pi-stat-label">🔥 Konsistensi</div><div class="pi-stat-value">{streak}</div><div class="pi-muted">Hari beruntun</div></div>
      <div class="pi-stat"><div class="pi-stat-label">🗓️ Ujian terdekat</div><div class="pi-stat-value" style="font-size:23px">{html.escape(exam_label)}</div><div class="pi-muted">{html.escape(exam_subject)}</div></div>
    </div>''', unsafe_allow_html=True)

    nav_options = ["🏡 Hari Ini", "🧠 Pahami Materi", "🎯 Latihan Pintar", "📄 Rangkuman PDF", "🗓️ Jadwal Ujian", "✨ Insight Saya"]
    if st.session_state.get("student_portal_section") not in nav_options:
        st.session_state.student_portal_section = nav_options[0]
    section = st.radio("Ruang belajar", nav_options, key="student_portal_section", horizontal=True, label_visibility="collapsed")
    st.divider()

    if section == "🏡 Hari Ini":
        left, right = st.columns([1.25, 1], gap="large")
        with left:
            st.markdown('<div class="pi-kicker2">Rekomendasi berikutnya</div><div class="pi-h2">Satu langkah kecil, hasil nyata.</div>', unsafe_allow_html=True)
            if attempts_count == 0:
                headline = "Mulai dengan satu latihan"
                detail = "Belum ada hasil latihan tersimpan yang bisa dianalisis. Mulailah dengan topik yang sedang dipelajari; setelah hasil tercatat, rekomendasi akan menjadi lebih personal."
            elif weakest_subject:
                headline = f"Prioritaskan {html.escape(str(weakest_subject))}"
                detail = "Prioritas ini berasal dari riwayat hasil belajarmu, bukan nilai contoh. Gunakan Tutor AI untuk memahami konsep lalu kerjakan latihan terarah."
            else:
                headline = "Pertahankan ritme belajarmu"
                detail = "Data saat ini belum menunjukkan satu mata pelajaran yang jelas tertinggal. Pilih materi yang akan kamu hadapi berikutnya dan belajar secara konsisten."
            st.markdown(f'<div class="pi-card"><div class="pi-icon">🧭</div><div class="pi-card-title">{headline}</div><div class="pi-muted">{detail}</div></div>', unsafe_allow_html=True)
            st.write("")
            a, b = st.columns(2)
            with a: st.button("🧠 Pahami topik", type="primary", use_container_width=True, key="pi_home_learn", on_click=_navigate_student_portal, args=("🧠 Pahami Materi",))
            with b: st.button("🎯 Mulai latihan", use_container_width=True, key="pi_home_practice", on_click=_navigate_student_portal, args=("🎯 Latihan Pintar",))
            st.write("")
            st.markdown('<div class="pi-card"><div class="pi-icon">📄</div><div class="pi-card-title">Bawa materi ke mana saja</div><div class="pi-muted">Buat rangkuman singkat dari topik pelajaranmu dan unduh sebagai PDF rapi dengan paragraf justify untuk dibaca atau dicetak.</div></div>', unsafe_allow_html=True)
            st.button("Buat rangkuman PDF", use_container_width=True, key="pi_home_pdf", on_click=_navigate_student_portal, args=("📄 Rangkuman PDF",))
        with right:
            st.markdown('<div class="pi-kicker2">Agenda akademik</div><div class="pi-h2">Persiapan yang terarah.</div>', unsafe_allow_html=True)
            if next_exam:
                exam_date, exam_row = next_exam
                st.markdown(f'<div class="pi-card"><div class="pi-icon">🗓️</div><div class="pi-card-title">{html.escape(str(exam_row.get("mapel") or "Ujian"))}</div><div class="pi-muted">{html.escape(format_tanggal_id(exam_date))}</div><p style="font-weight:900;color:#087f5b">{"Berlangsung hari ini" if days_to_exam == 0 else "Persiapan besok" if days_to_exam == 1 else f"Waktu persiapan: H-{days_to_exam}"}</p></div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="pi-card"><div class="pi-icon">🌱</div><div class="pi-card-title">Mulai belajar tanpa menunggu ujian</div><div class="pi-muted">Belum ada jadwal ujian yang cocok dengan kelasmu di database. Materi, latihan, dan rangkuman tetap bisa digunakan.</div></div>', unsafe_allow_html=True)
            st.write("")
            st.markdown('<div class="pi-card"><div class="pi-icon">✨</div><div class="pi-card-title">AI yang belajar dari aktivitasmu</div><div class="pi-muted">Portal memakai riwayat sesi yang tersedia untuk menyarankan fokus. Jika datanya belum cukup, portal menyatakannya dengan jujur—bukan membuat skor atau diagnosis palsu.</div></div>', unsafe_allow_html=True)

    elif section == "🧠 Pahami Materi":
        st.markdown('<div class="pi-kicker2">Teman belajar 24/7</div><div class="pi-h2">Pahami sampai benar-benar mengerti.</div><div class="pi-muted">Tanyakan konsep dari dasar, kirim foto soal atau PDF tugas, minta langkah penyelesaian, lalu simpan jawaban penting menjadi catatan.</div>', unsafe_allow_html=True)
        render_ai_chatbot_workspace(name, kelas, jenjang_detected, wa_number)

    elif section == "🎯 Latihan Pintar":
        st.markdown('<div class="pi-kicker2">Latihan yang punya tujuan</div><div class="pi-h2">Berlatih berdasarkan kebutuhanmu.</div><div class="pi-muted">RoboMANTAP akan menggunakan hasil tersimpan untuk memilih fokus latihan bila tersedia. Hasil dan riwayat mengikuti mekanisme kuis yang sudah ada.</div>', unsafe_allow_html=True)
        if weakest_subject:
            st.info(f"Fokus yang terdeteksi dari riwayat: **{weakest_subject}**" + (f" · Topik prioritas: {', '.join(str(t) for t, _ in weak_topics[:3])}" if weak_topics else ""))
        else:
            st.info("Belum cukup data untuk mengidentifikasi kelemahan personal. Latihan pertama akan membantu membangun riwayat belajar.")
        with st.container(border=True):
            st.markdown("#### 🚀 Mulai sesi latihan adaptif")
            st.write("Latihan dibuat melalui generator kuis RoboMANTAP yang sudah tersedia. Jika generator tidak dapat membuat paket yang valid, portal akan menampilkan kendala dan tidak mengklaim latihan berhasil.")
            if st.button("Buat latihan untuk saya", type="primary", use_container_width=True, key="pi_adaptive_start"):
                record_student_action(name, jenjang_detected, "ADAPTIVE_PRACTICE", "Mulai latihan adaptif", {"weakest_subject": weakest_subject, "weakest_topics": weak_topics[:3]})
                with st.spinner("AI sedang menyiapkan latihan berdasarkan data yang tersedia…"):
                    ok, message = _start_adaptive_practice(name, jenjang_detected, profile)
                if ok:
                    st.success(message); st.rerun()
                else:
                    st.warning(message)
        if weak_topics:
            st.markdown("#### Topik yang layak diulang")
            for topic_name, mastery in weak_topics[:5]:
                st.progress(max(0.0, min(1.0, float(mastery or 0) / 100)), text=f"{topic_name} · indikator {float(mastery or 0):.0f}%")
        st.caption("Catatan: nilai indikator topik hanya ditampilkan bila tersedia dari sesi yang tersimpan.")

    elif section == "📄 Rangkuman PDF":
        st.markdown('<div class="pi-kicker2">Perpustakaan yang kamu bangun sendiri</div><div class="pi-h2">Rangkuman singkat, rapi, siap diunduh.</div><div class="pi-muted">Masukkan satu topik spesifik. AI menyusun inti konsep, penjelasan, contoh, dan poin ingatan; hasilnya dapat diunduh sebagai PDF dengan tata letak A4 dan paragraf rata kiri-kanan.</div>', unsafe_allow_html=True)
        render_concept_sheets(name, kelas, jenjang_detected)
        material = st.session_state.get("portal_personal_material")
        if material:
            title = str(st.session_state.get("portal_personal_material_topic") or "Rangkuman Belajar")
            st.caption("PDF memakai ukuran A4, metadata siswa, judul topik, dan paragraf justify agar nyaman dibaca maupun dicetak.")

    elif section == "🗓️ Jadwal Ujian":
        st.markdown('<div class="pi-kicker2">Agenda dari data akademik</div><div class="pi-h2">Tahu apa yang akan dihadapi.</div><div class="pi-muted">Daftar ini hanya menampilkan jadwal yang ditemukan untuk kelas dan jenjang akunmu. Gunakan Tutor AI untuk membuat rencana persiapan berdasarkan mapel dan sisa waktu.</div>', unsafe_allow_html=True)
        render_uts_schedule_panel(uts_schedules, kelas, jenjang_detected)
        if next_exam:
            exam_date, exam_row = next_exam
            days = (exam_date - today).days
            if st.button("Buat rencana persiapan dengan AI", type="primary", use_container_width=True, key="pi_exam_plan"):
                prompt = (f"Buat rencana belajar realistis untuk siswa kelas {kelas} jenjang {jenjang_detected} menghadapi ujian {exam_row.get('mapel') or 'mata pelajaran'} pada {format_tanggal_id(exam_date)}. Sisa waktu {days} hari. Buat jadwal harian ringkas, konsep yang perlu diperiksa, sesi latihan dan evaluasi. Jangan mengarang kisi-kisi resmi; minta siswa memasukkan kisi-kisi guru bila dibutuhkan.")
                with st.spinner("AI sedang menyusun rencana persiapan…"):
                    try: plan = _generate_student_ai_response(prompt, name, kelas, jenjang_detected)
                    except Exception as exc:
                        print(f"[STUDENT INTELLIGENCE] exam plan error: {exc}"); plan = ""
                if plan:
                    st.session_state.pi_exam_plan_result = plan
                    record_student_action(name, jenjang_detected, "AI_EXAM_PLAN", f"Rencana persiapan {exam_row.get('mapel') or 'ujian'}", {"tanggal": str(exam_date)})
            if st.session_state.get("pi_exam_plan_result"):
                st.markdown(st.session_state.pi_exam_plan_result)
                st.download_button("Unduh rencana persiapan (.txt)", data=st.session_state.pi_exam_plan_result, file_name="Rencana_Persiapan_Ujian_RoboMANTAP.txt", mime="text/plain", use_container_width=True)

    elif section == "✨ Insight Saya":
        st.markdown('<div class="pi-kicker2">Analisis dari aktivitas nyata</div><div class="pi-h2">Kenali pola belajarmu.</div><div class="pi-muted">Insight akan semakin berguna seiring bertambahnya hasil kuis dan sesi yang tersimpan.</div>', unsafe_allow_html=True)
        if not sessions:
            st.info("Belum ada sesi belajar yang cocok dengan identitas dan jenjang akunmu. Setelah mengerjakan kuis yang menyimpan hasil, ringkasan perkembangan akan muncul di sini.")
        else:
            render_learning_analytics(name, jenjang_detected, profile, sessions)
        with st.expander("Bagaimana intelligence bekerja?"):
            st.write("Portal menggabungkan riwayat sesi yang ditemukan, skor, topik yang tercatat, agenda ujian, dan permintaanmu ke AI. Data kosong tidak diganti dengan angka simulasi. Rekomendasi adalah bantuan belajar, bukan diagnosis psikologis atau jaminan nilai ujian.")
        if wa_number:
            st.divider()
            st.markdown("#### Pengingat WhatsApp (opsional)")
            st.caption("Pengingat bukan menu utama belajar. Pengaturan ini tersedia di sini sebagai pendukung, jika nomor WhatsApp sudah terhubung.")
            with st.expander("Atur pengingat agenda"):
                render_student_automation(wa_number)

    st.divider()
    st.caption(f"RoboMANTAP-Intelligence · Portal SantriMANTAP · Data personal berdasarkan akun terverifikasi · Waktu Asia/Jakarta")
