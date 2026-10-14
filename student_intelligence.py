"""RoboMANTAP Student Intelligence Layer v3.0.

Pusat Layanan Belajar, Simulasi UTS, Asisten AI Interaktif,
Export Catatan WA & PDF, serta Analisis Diagnostic Santri Al-Irsyad Putri Bondowoso.
"""

from __future__ import annotations

import io
import json
import math
import re
import uuid
import urllib.parse
from collections import defaultdict
from datetime import datetime, date, timedelta
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import text

# ReportLab Imports untuk Export PDF Catatan
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT

from ai_engine import init_db_connection

STUDENT_INTELLIGENCE_VERSION = "3.0"

# =============================================================================
# HELPER GENERATOR PDF CATATAN BELAJAR
# =============================================================================

def generate_pdf_notes(nama_siswa: str, kelas: str, jenjang: str, topic_title: str, text_content: str) -> bytes:
    """Mengonversi teks catatan/rangkuman AI menjadi file PDF berkualitas tinggi."""
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
        'PDFTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=19,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#064e3b'),
        spaceAfter=6
    )

    meta_style = ParagraphStyle(
        'PDFMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#475569'),
        spaceAfter=15
    )

    heading_style = ParagraphStyle(
        'PDFHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        alignment=TA_LEFT,
        textColor=colors.HexColor('#064e3b'),
        spaceBefore=10,
        spaceAfter=4
    )

    body_style = ParagraphStyle(
        'PDFBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
        textColor=colors.HexColor('#1e293b')
    )

    bullet_style = ParagraphStyle(
        'PDFBullet',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        alignment=TA_JUSTIFY,
        leftIndent=15,
        spaceAfter=3,
        textColor=colors.HexColor('#1e293b')
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
# DATABASE QUERY HELPERS (wa_identities & uts_schedules)
# =============================================================================

def fetch_student_wa_identity(nama_siswa: str) -> dict | None:
    """Mencari data siswa terdaftar dari tabel wa_identities (Privacy Preserved)."""
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
    """Mengambil jadwal UTS resmi dari tabel uts_schedules berdasarkan kelas & jenjang."""
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
    """Menghitung dan memperbarui Daily Learning Streak siswa."""
    today_str = date.today().isoformat()
    last_active = profile_data.get("last_active_date")
    current_streak = profile_data.get("current_streak", 0)
    is_new_day = False

    if not last_active:
        current_streak = 1
        is_new_day = True
    elif last_active == today_str:
        pass  # Sudah aktif hari ini
    else:
        last_date = date.fromisoformat(last_active)
        if date.today() - last_date == timedelta(days=1):
            current_streak += 1  # Streak bertambah
            is_new_day = True
        else:
            current_streak = 1   # Streak reset
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


def build_student_profile(sessions: list[dict], existing_profile: dict | None = None) -> dict:
    completed = [s for s in sessions if str(s.get("status", "")).upper() == "SELESAI"]
    total_attempts = len(completed)

    normalized_scores = []
    for s in completed:
        score = float(s.get("nilai_akhir") or 0)
        mapel = str(s.get("mapel") or "")
        if "(Quiz)" not in mapel and "(TKA)" not in mapel and score <= 40:
            score = max(0.0, min(100.0, score / 40.0 * 100.0))
        normalized_scores.append(score)

    by_subject: dict[str, list[float]] = defaultdict(list)
    correct_total = wrong_total = blank_total = 0

    for session in sessions:
        mapel = str(session.get("mapel") or "Umum").replace(" (Quiz)", "").replace(" (TKA)", "").strip()
        if str(session.get("status", "")).upper() == "SELESAI":
            score = float(session.get("nilai_akhir") or 0)
            if "(Quiz)" not in session.get("mapel", "") and score <= 40:
                score = max(0.0, min(100.0, score / 40.0 * 100.0))
            by_subject[mapel].append(score)

    subject_mastery = {
        subject: round(sum(values) / len(values), 1)
        for subject, values in by_subject.items() if values
    }

    avg_score = round(sum(normalized_scores) / len(normalized_scores), 1) if normalized_scores else 0
    weakest_subject = min(subject_mastery, key=subject_mastery.get) if subject_mastery else None

    profile = existing_profile or {}
    profile.update({
        "attempts": total_attempts,
        "average_score": avg_score,
        "subject_mastery": subject_mastery,
        "weakest_subject": weakest_subject,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    })
    return profile


def save_student_profile(nama_siswa: str, jenjang: str, profile: dict) -> bool:
    conn = init_db_connection()
    if not conn:
        return False
    key = f"{nama_siswa.strip().casefold()}|{jenjang.strip().casefold()}"
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


# =============================================================================
# POP-UP MODAL SAPAAN HARAT & JADWAL UTS
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
                🔥 {streak} Hari Streak!
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
            tgl = s.get("tanggal_ujian")
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
    💡
    *"Barangsiapa menelusuri jalan untuk mencari ilmu, Allah akan mudahkan baginya jalan menuju surga."*  
    Semangat belajar dan manfaatkan Portal SantriMANTAP untuk latihan & rangkuman materi ya!
    """)

    if st.button("🚀 Masuk ke Portal Belajar Saya", type="primary", use_container_width=True):
        st.rerun()


# =============================================================================
# SUB-RENDERERS UNTUK TAB
# =============================================================================

def render_ai_chatbot_workspace(nama_siswa: str, kelas: str, jenjang: str, wa_number: str):
    """TAB: Asisten AI RoboMANTAP dengan Diskusi, Upload Tugas, Share ke WA & Download PDF."""
    st.markdown('<div style="font-size: 18px; font-weight: 700; color: #f8fafc; margin-bottom: 4px;">💬 Asisten & Catatan AI RoboMANTAP</div>', unsafe_allow_html=True)
    st.caption("Tanyakan konsep, minta buatkan rangkuman UTS, analisis tugas, lalu simpan ke WA atau unduh PDF!")

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {"role": "assistant", "content": f"Assalamu’alaikum Santri Sholihat *{nama_siswa}*! 🧕🏼✨ Ada materi atau soal UTS yang ingin kita bahas bersama hari ini?"}
        ]

    # Area Chat History
    chat_container = st.container(height=350)
    with chat_container:
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # Upload File Tugas / Foto Soal
    uploaded_file = st.file_uploader("📎 Upload Gambar Soal / Dokumen Tugas (Opsional)", type=["png", "jpg", "jpeg", "pdf"])

    # Input Pesan
    if prompt := st.chat_input("Tanyakan sesuatu ke RoboMANTAP..."):
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)

        # Proses Jawaban AI Simulasi/Injeksi
        ai_response = f"Baik Santri Cerdas *{nama_siswa}* (Kelas {kelas} {jenjang})!\n\nBerikut pembahasan & poin penting terkait **{prompt}**:\n\n1. *Konsep Utama*: Pahami definisi dasar dan hubungan antar komponennya.\n2. *Langkah Penyelesaian*: Selesaikan bertahap menggunakan rumus/aturan baku.\n3. *Tips UTS*: Fokus pada bentuk soal latihan yang sering keluar di ujian.\n\nSemangat terus belajarnya ya! 💪✨"
        
        st.session_state.chat_messages.append({"role": "assistant", "content": ai_response})
        st.session_state.last_ai_note = ai_response
        st.session_state.last_ai_topic = prompt
        st.rerun()

    # SECTION ACTION: SHARE TO WA & DOWNLOAD PDF
    if "last_ai_note" in st.session_state:
        st.divider()
        st.markdown("### 📄 Opsi Simpan Catatan AI Terakhir")
        
        c1, c2 = st.columns(2)
        with c1:
            # Share to WhatsApp
            pesan_wa = f"*CATATAN BELAJAR ROBOMANTAP*\nSantri: {nama_siswa} ({kelas} {jenjang})\nTopik: {st.session_state.get('last_ai_topic', 'Rangkuman')}\n\n{st.session_state.last_ai_note}"
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
            # Download PDF
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

def render_learning_analytics_tab(profile: dict, streak: int):
    """TAB: Progress, Streak Counter & Analytics."""
    st.markdown('<div style="font-size: 18px; font-weight: 700; color: #f8fafc; margin-bottom: 8px;">🎯 Profil Performa & Streak Belajar</div>', unsafe_allow_html=True)
    
    avg = profile.get("average_score", 0)
    attempts = profile.get("attempts", 0)

    st.markdown(f"""
    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px;">
        <div style="background: rgba(6, 78, 59, 0.4); border: 1px solid #059669; border-radius: 12px; padding: 14px; text-align: center;">
            <div style="font-size: 11px; color: #a7f3d0; font-weight: 700;">🔥 DAILY STREAK</div>
            <div style="font-size: 24px; color: #34d399; font-weight: 800;">{streak} Hari</div>
        </div>
        <div style="background: rgba(120, 53, 15, 0.4); border: 1px solid #f59e0b; border-radius: 12px; padding: 14px; text-align: center;">
            <div style="font-size: 11px; color: #fde68a; font-weight: 700;">🎯 RATA-RATA SKOR</div>
            <div style="font-size: 24px; color: #fbbf24; font-weight: 800;">{avg:.0f}%</div>
        </div>
        <div style="background: rgba(30, 58, 138, 0.4); border: 1px solid #3b82f6; border-radius: 12px; padding: 14px; text-align: center;">
            <div style="font-size: 11px; color: #bfdbfe; font-weight: 700;">🎓 TOTAL SESI</div>
            <div style="font-size: 24px; color: #60a5fa; font-weight: 800;">{attempts}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 📚 Pemahaman Mata Pelajaran")
    mastery = profile.get("subject_mastery", {})
    if mastery:
        for mapel, val in mastery.items():
            st.write(f"**{mapel}**: {val}%")
            st.progress(int(min(100, max(0, val))))
    else:
        st.info("Belum ada riwayat pengerjaan kuis untuk dianalisis.")

def render_uts_simulation_tab():
    """TAB: Simulasi UTS."""
    st.markdown("### 🎯 Simulasi & Diagnostic UTS")
    mapel_sim = st.selectbox("Pilih Mata Pelajaran", ["Matematika", "IPA", "Bahasa Arab", "Fiqih"])
    if st.button("🚀 Mulai Latihan Kuis", type="primary"):
        st.success(f"Latihan {mapel_sim} dimulai! Jawab pertanyaan dengan teliti.")

def render_concept_sheets_tab():
    """TAB: Concept Sheet Rangkuman."""
    st.markdown("### 📚 Concept Sheet & Rumus Cepat H-1 UTS")
    with st.expander("📖 Matematika — Eksponen & Bentuk Akar"):
        st.markdown("• Perkalian Eksponen: a^m × a^n = a^(m+n)\n• Bentuk Akar: √(a × b) = √a × √b")
    with st.expander("📖 Bahasa Arab — Tanda Isim"):
        st.markdown("• Tanwin, Alif Lam (ال), dan diawali huruf Jar.")

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def render_student_intelligence_dashboard(nama_siswa: str = "", jenjang: str = "") -> None:
    """Entry point utama Portal SantriMANTAP dengan UI/UX Mewah."""

    # MEWAH GLASSMORPHISM STYLING
    ui_css = """
    <style>
    .stApp {
        background: linear-gradient(135deg, #022c22 0%, #0f172a 100%);
    }
    .main-hero {
        background: linear-gradient(135deg, rgba(6, 78, 59, 0.6) 0%, rgba(2, 44, 34, 0.9) 100%);
        border: 1px solid rgba(16, 185, 129, 0.3);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.37);
        backdrop-filter: blur(12px);
    }
    .hero-kicker {
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 1.5px;
        color: #34d399;
        text-transform: uppercase;
    }
    .hero-title {
        font-size: 26px;
        font-weight: 900;
        color: #f8fafc;
        margin: 4px 0;
    }
    .hero-title span {
        color: #fbbf24;
    }
    .hero-subtitle {
        font-size: 13px;
        color: #cbd5e1;
    }
    </style>
    """
    st.markdown(ui_css, unsafe_allow_html=True)

    # HERO BANNER
    st.markdown("""
    <div class="main-hero">
      <div class="hero-kicker">UPN • STUDENT INTELLIGENCE PLATFORM</div>
      <div class="hero-title">Portal Santri<span>MANTAP</span></div>
      <div class="hero-subtitle">Pusat Belajar Mandiri, Asisten AI, Jadwal UTS Realtime & Automasi WA.</div>
    </div>
    """, unsafe_allow_html=True)

    # DOORWAY / LOGIN (PRIVACY-FIRST: KETIK NAMA MANUALL)
    with st.form("form_login_santri"):
        st.markdown("#### 🔑 Masuk ke Portal Belajar Santri")
        entered_name = st.text_input("Nama Lengkap Santri", value=nama_siswa, placeholder="Masukkan nama lengkap kamu...")
        btn_login = st.form_submit_button("🔍 BUKA PORTAL SAYA", type="primary", use_container_width=True)

    if not btn_login and not entered_name.strip():
        st.info("💡 Ketikkan Nama Lengkap Kamu di atas untuk membuka portal belajar.")
        return

    name = entered_name.strip()
    
    # 1. FETCH DARI TABLE wa_identities
    identity_data = fetch_student_wa_identity(name)
    
    if identity_data:
        meta = identity_data.get("metadata") or {}
        kelas = str(meta.get("kelas", "7"))
        jenjang_detected = str(meta.get("jenjang", "MTS")).upper()
        wa_number = identity_data.get("wa_number", "")
    else:
        # Fallback jika nama belum sinkron di wa_identities
        kelas = "9"
        jenjang_detected = "MTS"
        wa_number = ""

    # 2. FETCH JADWAL UTS DARI TABLE uts_schedules
    uts_schedules = fetch_uts_schedules_db(kelas, jenjang_detected)

    # 3. FETCH SESI & UPDATE STREAK
    sessions = fetch_student_sessions(name)
    profile = build_student_profile(sessions)
    student_key = f"{name.casefold()}|{jenjang_detected.casefold()}"
    streak, is_new_day = update_and_get_daily_streak(student_key, profile)
    save_student_profile(name, jenjang_detected, profile)

    # TRIGGER POP-UP MODAL JIKA BARU LOGIN SARI HARI
    if "welcomed_today" not in st.session_state or st.session_state.get("welcomed_user") != name:
        st.session_state.welcomed_today = True
        st.session_state.welcomed_user = name
        show_welcome_modal(name, kelas, jenjang_detected, streak, wa_number, uts_schedules)

    # TABS DASHBOARD UTAMA
    tab_ai, tab_analytics, tab_simulasi, tab_materi = st.tabs([
        "💬 Asisten AI RoboMANTAP",
        "📊 Progress & Streak",
        "🎯 Simulasi UTS",
        "📚 Concept Sheets"
    ])

    with tab_ai:
        render_ai_chatbot_workspace(name, kelas, jenjang_detected, wa_number)

    with tab_analytics:
        render_learning_analytics_tab(profile, streak)

    with tab_simulasi:
        render_uts_simulation_tab()

    with tab_materi:
        render_concept_sheets_tab()

    st.caption(f"Portal SantriMANTAP v{STUDENT_INTELLIGENCE_VERSION} • Engineered by U.Project Nexus")
