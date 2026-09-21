import io
import os
import re
import uuid
import html
import json
import base64
import random
import hashlib
import threading
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import tempfile                        # <--- Tambahkan ini
import matplotlib.pyplot as plt
from sqlalchemy import text
# from-import python-docx untuk generate Word dan Pdf berlogo
from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.pagesizes import A4
from datetime import datetime, timedelta
from docx.shared import Pt, RGBColor, Inches
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
)

from ai_engine import (
    generate_quiz_batch, get_ai_hint_stream, get_ai_solution_stream,
    create_table_if_not_exists, update_progress_siswa, init_db_connection,
    generate_lkpd_content, stream_ai_text, generate_custom_quiz_ai,
    publish_custom_quiz_to_db, get_custom_quiz_from_db, check_active_session_from_db,
    call_gemini_with_rotation, generate_corporate_executive_docx_report,
    generate_individual_analysis_ai, load_session_review_from_db,
    build_material_knowledge_pack, save_material_bundle_to_db, get_material_bundle_from_db,
    normalize_material_trigger, generate_media_ajar_ai, build_media_ajar_pptx,
    option_labels_for_jenjang, option_count_for_jenjang, normalize_quiz_options,
    normalize_custom_timer_config, build_language_guidance
)

# Interseptor Deep Link dari CBT Engine Render
if "review_session" in st.query_params:
    review_id = st.query_params["review_session"]
    
    # Mencegah pemanggilan ulang jika sudah di load
    if st.session_state.get("loaded_review_id") != review_id:
        review_data = load_session_review_from_db(review_id)
        if review_data and review_data["quiz_data"]:
            st.session_state.page = "result"
            st.session_state.quiz_data = review_data["quiz_data"]
            st.session_state.user_answers = review_data["user_answers"]
            st.session_state.mapel = review_data["mapel"]
            st.session_state.jenjang = review_data["jenjang"]
            st.session_state.nama_siswa = review_data["nama"]
            st.session_state.is_custom_quiz = True
            st.session_state.loaded_review_id = review_id

st.set_page_config(
    page_title="RoboMANTAP-Intelligence",
    page_icon="logo.png",
    layout="wide",
    initial_sidebar_state="auto"
)

# Inisialisasi Tabel Database saat aplikasi pertama kali dimuat
create_table_if_not_exists()
# ==============================================================================
# ANTI-COPAS & DISABLE KLIK KANAN (PERLINDUNGAN HALAMAN KUIS)
# ==============================================================================

st.markdown("""
    <style>
    /* Matikan seleksi teks pada soal & pilihan jawaban */
    body, html, iframe, [data-testid="stMarkdownContainer"] {
        -webkit-user-select: none !important;
        -moz-user-select: none !important;
        -ms-user-select: none !important;
        user-select: none !important;
    }
    </style>
    
    <script>
    // Matikan Klik Kanan
    document.addEventListener('contextmenu', event => event.preventDefault());
    
    // Matikan Shortcut Copy (Ctrl+C, Ctrl+A, Ctrl+U, Ctrl+S)
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey && (e.key === 'c' || e.key === 'u' || e.key === 's' || e.key === 'a')) {
            e.preventDefault();
        }
    });

    // Matikan Event Copy Teks
    document.addEventListener('copy', function(e) {
        e.preventDefault();
    });
    </script>
""", unsafe_allow_html=True)

components.html(
    """
    <script>
    if ('wakeLock' in navigator) {
        let wakeLock = null;
        const requestWakeLock = async () => {
            try {
                wakeLock = await navigator.wakeLock.request('screen');
            } catch (err) {
                console.log(`${err.name}, ${err.message}`);
            }
        };
        requestWakeLock();
        document.addEventListener('visibilitychange', async () => {
            if (wakeLock !== null && document.visibilityState === 'visible') {
                await requestWakeLock();
            }
        });
    }
    </script>
    """,
    height=0,
)

# Custom Styling 
st.markdown("""
    <style>

    @keyframes pulse-red {
    0% { opacity: 1; transform: scale(1); filter: drop-shadow(0px 0px 5px rgba(239, 68, 68, 0.8)); }
    50% { opacity: 0.35; transform: scale(0.92); filter: drop-shadow(0px 0px 1px rgba(239, 68, 68, 0.1)); }
    100% { opacity: 1; transform: scale(1); filter: drop-shadow(0px 0px 5px rgba(239, 68, 68, 0.8)); }
    }
    
    @keyframes pulse-green {
        0% { opacity: 1; transform: scale(1); filter: drop-shadow(0px 0px 5px rgba(16, 185, 129, 0.8)); }
        50% { opacity: 0.35; transform: scale(0.92); filter: drop-shadow(0px 0px 1px rgba(16, 185, 129, 0.1)); }
        100% { opacity: 1; transform: scale(1); filter: drop-shadow(0px 0px 5px rgba(16, 185, 129, 0.8)); }
    }
    
    .blinking-dot-red {
        display: inline-block;
        animation: pulse-red 1.8s ease-in-out infinite;
        vertical-align: middle;
    }
    
    .blinking-dot-green {
        display: inline-block;
        animation: pulse-green 1.8s ease-in-out infinite;
        vertical-align: middle;
    }
    .mode-card {
        background: linear-gradient(135deg, rgba(6, 78, 59, 0.45) 0%, rgba(2, 44, 34, 0.75) 100%);
        border: 1px solid rgba(5, 150, 105, 0.45);
        padding: 14px 16px;
        border-radius: 12px;
        text-align: center;
        margin-bottom: 8px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
    }
    .mode-card h2 {
        font-size: 18px !important;
        font-weight: 700;
        color: #ffffff !important;
        margin-bottom: 4px !important;
    }
    .mode-card p {
        color: #a7f3d0 !important;
        font-size: 12px !important;
        margin: 0 !important;
        opacity: 0.9;
    }
    .mapel-card {
        background-color: var(--secondary-background-color);
        border: 1px solid rgba(5, 150, 105, 0.3);
        padding: 16px;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 10px;
    }
    .school-header {
        background: linear-gradient(135deg, #064e3b 0%, #022c22 100%);
        border: 1px solid #059669;
        border-radius: 12px;
        padding: 16px;
        text-align: center;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(5, 150, 105, 0.15);
    }
    .school-title { color: #ffffff; font-weight: 800; font-size: 13px; margin: 0; }
    .school-subtitle { color: #6ee7b7; font-size: 11px; margin-top: 4px; font-weight: 500; }
    .stButton>button { width: 100%; min-height: 48px; font-size: 16px !important; border-radius: 8px !important; }
    
    /* Paksa Warna Tombol Utama Menjadi Hijau Emerald MANTAP */
    div.stButton > button[kind="primary"],
    div.stButton > button {
        background-color: #059669 !important;
        background-image: none !important;
        color: #ffffff !important;
        border: 1px solid #047857 !important;
        width: 100%;
        min-height: 48px;
        font-size: 16px !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        transition: all 0.3s ease;
    }
    
    /* Efek Hover Tombol saat Diarahkan Kursor */
    div.stButton > button[kind="primary"]:hover,
    div.stButton > button:hover {
        background-color: #047857 !important;
        border-color: #065f46 !important;
        box-shadow: 0 4px 12px rgba(5, 150, 105, 0.4) !important;
    }

    .guru-card {
        background: linear-gradient(135deg, #1e3a8a 0%, #172554 100%);
        color: white;
        border: 1px solid #3b82f6;
        padding: 18px;
        border-radius: 12px;
        text-align: center;
        margin-bottom: 15px;
    }

    /* =========================================================
       UPN LIVE TRACKING — MODERN MONITORING CARDS
       ========================================================= */
    .upn-live-hero {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 14px;
        margin: 18px 0 12px;
        padding: 14px 16px;
        border: 1px solid rgba(16,185,129,.22);
        border-radius: 16px;
        background: linear-gradient(135deg, rgba(2,44,34,.62), rgba(15,23,42,.82));
        box-shadow: 0 12px 35px rgba(0,0,0,.16);
    }
    .upn-live-hero-left {
        display: flex;
        align-items: center;
        gap: 11px;
        min-width: 0;
    }
    .upn-live-orb {
        width: 12px;
        height: 12px;
        border-radius: 999px;
        background: #10b981;
        box-shadow: 0 0 0 6px rgba(16,185,129,.10), 0 0 18px rgba(16,185,129,.55);
        flex: 0 0 auto;
    }
    .upn-live-eyebrow {
        font-size: 10px;
        letter-spacing: .11em;
        text-transform: uppercase;
        font-weight: 800;
        color: #6ee7b7;
        margin-bottom: 2px;
    }
    .upn-live-title {
        font-size: 21px;
        line-height: 1.18;
        font-weight: 850;
        color: #f8fafc;
        margin: 0;
    }
    .upn-live-subtitle {
        font-size: 11px;
        color: #94a3b8;
        margin-top: 4px;
    }
    .upn-live-count {
        border: 1px solid rgba(16,185,129,.28);
        background: rgba(16,185,129,.08);
        color: #a7f3d0;
        border-radius: 999px;
        padding: 6px 10px;
        font-size: 11px;
        font-weight: 800;
        white-space: nowrap;
    }
    .upn-live-card {
        background: linear-gradient(145deg, rgba(15,23,42,.96), rgba(2,44,34,.30));
        border: 1px solid rgba(148,163,184,.16);
        border-radius: 18px;
        padding: 15px;
        margin: 8px 0 10px;
        box-shadow: 0 10px 28px rgba(0,0,0,.14);
    }
    .upn-live-head {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
    }
    .upn-live-name {
        font-size: 17px;
        line-height: 1.25;
        color: #f8fafc;
        font-weight: 850;
        word-break: break-word;
    }
    .upn-live-tag {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        margin-left: 6px;
        padding: 3px 7px;
        border-radius: 999px;
        font-size: 9px;
        font-weight: 850;
        letter-spacing: .02em;
        vertical-align: middle;
    }
    .upn-tag-live {
        color: #a7f3d0;
        background: rgba(16,185,129,.11);
        border: 1px solid rgba(16,185,129,.22);
    }
    .upn-tag-warn {
        color: #fde68a;
        background: rgba(245,158,11,.11);
        border: 1px solid rgba(245,158,11,.24);
    }
    .upn-tag-cheat {
        color: #fecaca;
        background: rgba(239,68,68,.11);
        border: 1px solid rgba(239,68,68,.26);
    }
    .upn-tag-done {
        color: #bfdbfe;
        background: rgba(59,130,246,.11);
        border: 1px solid rgba(59,130,246,.22);
    }
    .upn-tag-off {
        color: #cbd5e1;
        background: rgba(100,116,139,.12);
        border: 1px solid rgba(100,116,139,.20);
    }
    .upn-live-sub {
        margin-top: 5px;
        color: #94a3b8;
        font-size: 10px;
        line-height: 1.45;
    }
    .upn-live-score {
        min-width: 68px;
        padding: 8px 10px;
        border-radius: 13px;
        border: 1px solid rgba(16,185,129,.22);
        background: rgba(16,185,129,.08);
        text-align: center;
        flex: 0 0 auto;
    }
    .upn-live-score small {
        display: block;
        color: #6ee7b7;
        font-size: 8px;
        font-weight: 850;
        letter-spacing: .09em;
        margin-bottom: 1px;
    }
    .upn-live-score strong {
        display: block;
        color: #f8fafc;
        font-size: 20px;
        line-height: 1;
        font-weight: 900;
    }
    .upn-live-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 7px;
        margin-top: 11px;
    }
    .upn-live-chip {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 4px 8px;
        border-radius: 999px;
        background: rgba(148,163,184,.07);
        border: 1px solid rgba(148,163,184,.12);
        color: #cbd5e1;
        font-size: 9px;
        font-weight: 650;
    }
    .upn-live-alert {
        margin-top: 10px;
        padding: 9px 10px;
        border-radius: 11px;
        font-size: 10px;
        font-weight: 700;
        line-height: 1.45;
    }
    .upn-alert-cheat {
        color: #fecaca;
        background: rgba(127,29,29,.28);
        border: 1px solid rgba(248,113,113,.24);
    }
    .upn-alert-warn {
        color: #fde68a;
        background: rgba(120,53,15,.22);
        border: 1px solid rgba(245,158,11,.22);
    }
    .upn-alert-off {
        color: #cbd5e1;
        background: rgba(51,65,85,.22);
        border: 1px solid rgba(100,116,139,.18);
    }
    .upn-progress-line {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        margin-top: 13px;
        margin-bottom: 6px;
        color: #94a3b8;
        font-size: 9px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: .05em;
    }
    .upn-progress-line b {
        color: #d1fae5;
        font-size: 9px;
        letter-spacing: 0;
        text-transform: none;
    }
    .upn-segments {
        display: grid;
        grid-template-columns: repeat(var(--segment-count), minmax(0,1fr));
        gap: 3px;
    }
    .upn-segment {
        height: 9px;
        border-radius: 4px;
        background: #334155;
        border: 1px solid rgba(255,255,255,.05);
    }
    .upn-segment-correct { background: #10b981; }
    .upn-segment-wrong { background: #ef4444; }
    .upn-segment-empty { background: #cbd5e1; }
    .upn-segment-current {
        box-shadow: 0 0 0 2px rgba(255,255,255,.08), 0 0 11px rgba(16,185,129,.18);
    }
    .upn-live-foot {
        display: flex;
        flex-wrap: wrap;
        gap: 7px;
        margin-top: 9px;
        color: #94a3b8;
        font-size: 9px;
    }
    .upn-live-foot span {
        padding: 4px 7px;
        border-radius: 7px;
        background: rgba(15,23,42,.65);
        border: 1px solid rgba(148,163,184,.10);
    }
    .upn-live-divider {
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(148,163,184,.14), transparent);
        margin: 14px 0;
    }
    @media (max-width: 640px) {
        .upn-live-hero { padding: 12px 13px; }
        .upn-live-title { font-size: 18px; }
        .upn-live-count { font-size: 10px; padding: 5px 8px; }
        .upn-live-card { padding: 13px; border-radius: 16px; }
        .upn-live-name { font-size: 16px; }
        .upn-live-score { min-width: 60px; }
    }
    </style>
""", unsafe_allow_html=True)

# Helper Base64 Image
def get_image_base64(path):
    if os.path.exists(path):
        with open(path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    return None


# Premium responsive UPN UI layer
st.markdown("""
<style>
.premium-hero{padding:22px 24px;border-radius:24px;margin:8px 0 18px;background:radial-gradient(circle at 84% 10%,rgba(16,185,129,.25),transparent 32%),linear-gradient(135deg,#081225 0%,#111827 56%,#0a3a2d 100%);border:1px solid rgba(110,231,183,.22);box-shadow:0 18px 50px rgba(0,0,0,.22);overflow:hidden}
.premium-kicker{font-size:10px;letter-spacing:.18em;font-weight:800;color:#a7f3d0;margin-bottom:5px}
.premium-title{font-size:30px;font-weight:900;line-height:1.05;color:#f8fafc}.premium-title span{background:linear-gradient(90deg,#6ee7b7,#c4b5fd);-webkit-background-clip:text;color:transparent}
.premium-subtitle{margin-top:8px;color:#cbd5e1;font-size:13px;max-width:840px}.premium-pills{display:flex;flex-wrap:wrap;gap:7px;margin-top:13px}.premium-pills span,.chip{display:inline-flex;align-items:center;border:1px solid rgba(148,163,184,.18);background:rgba(15,23,42,.55);border-radius:999px;padding:5px 9px;font-size:10px;color:#e2e8f0}.chip-green{border-color:rgba(16,185,129,.35);color:#a7f3d0}.chip-blue{border-color:rgba(59,130,246,.35);color:#bfdbfe}.chip-purple{border-color:rgba(168,85,247,.35);color:#ddd6fe}.chip-gold{border-color:rgba(245,158,11,.35);color:#fde68a}
.source-warning{padding:14px 16px;border:1px solid rgba(245,158,11,.24);background:linear-gradient(135deg,rgba(120,53,15,.18),rgba(15,23,42,.65));border-radius:16px;margin-bottom:15px}.source-warning-title{font-size:12px;font-weight:900;color:#fcd34d;margin-bottom:4px}.source-warning code{color:#a7f3d0;background:rgba(16,185,129,.11);padding:2px 6px;border-radius:6px}
.file-list,.hub-code,.hub-empty,.result-card,.story-card,.premium-footer-card,.answer-card{border:1px solid rgba(148,163,184,.12);background:rgba(15,23,42,.52);border-radius:16px}.file-list{padding:7px;margin-top:8px}.file-row{display:flex;justify-content:space-between;gap:12px;padding:8px 10px;border-bottom:1px solid rgba(148,163,184,.08);font-size:11px;color:#dbeafe}.file-row:last-child{border-bottom:none}.hub-code,.hub-empty{padding:16px;min-height:126px}.hub-code-label,.preview-label,.footer-kicker{font-size:9px;letter-spacing:.15em;font-weight:900;color:#94a3b8}.hub-code-value{font-size:24px;font-weight:900;color:#6ee7b7;letter-spacing:.08em;margin:6px 0}.hub-empty-title{font-size:17px;font-weight:800;color:#f8fafc;margin-top:8px}.hub-code-note,.footer-copy,.result-card-copy,.story-meta{font-size:10px;color:#94a3b8;line-height:1.5}.preview-hero{display:flex;justify-content:space-between;gap:15px;align-items:center;padding:16px 18px;border-radius:18px;background:linear-gradient(135deg,rgba(16,185,129,.12),rgba(59,130,246,.08),rgba(168,85,247,.08));border:1px solid rgba(110,231,183,.16);margin-bottom:12px}.preview-title{font-size:21px;font-weight:900;color:#f8fafc}.preview-meta{display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end}.answer-card{padding:10px 12px;margin:5px 0;color:#e5e7eb;font-size:12px;min-height:42px}.answer-card b{color:#6ee7b7;margin-right:5px}.result-card{padding:15px 16px;margin:10px 0}.result-card-title{font-size:16px;font-weight:900;color:#f8fafc}.story-card{display:flex;gap:12px;align-items:center;padding:10px 12px;margin:6px 0}.story-number{width:34px;height:34px;border-radius:11px;display:grid;place-items:center;background:linear-gradient(135deg,#059669,#2563eb);font-size:11px;font-weight:900;color:white}.premium-footer-card{padding:16px 18px;margin-top:18px;background:linear-gradient(135deg,rgba(15,23,42,.78),rgba(6,78,59,.12))}.footer-title{font-weight:900;font-size:15px;color:#f8fafc;margin:4px 0 3px}.automation-hero{background:radial-gradient(circle at 82% 10%,rgba(168,85,247,.18),transparent 30%),linear-gradient(135deg,#081225 0%,#121225 55%,#0a3a2d 100%)}
@media(max-width:760px){.premium-hero{padding:18px 16px;border-radius:20px}.premium-title{font-size:24px}.premium-subtitle{font-size:12px}.premium-pills{gap:5px}.premium-pills span{font-size:9px;padding:4px 7px}.preview-hero{display:block}.preview-meta{justify-content:flex-start;margin-top:9px}.hub-code,.hub-empty{min-height:auto}.answer-card{font-size:11px}.story-card{align-items:flex-start}}
</style>
""", unsafe_allow_html=True)

logo_mantap_b64 = get_image_base64("logo.png")
logo_nexus_b64 = get_image_base64("nexus_logo.png")

img_mantap_html = f'<img src="data:image/png;base64,{logo_mantap_b64}" style="height: 70px; margin-bottom: 8px;">' if logo_mantap_b64 else '<div style="font-size: 32px;">🎓</div>'

# Session States Initialization
if "page" not in st.session_state: st.session_state.page = "landing"
if "jenjang" not in st.session_state: st.session_state.jenjang = None
if "mapel" not in st.session_state: st.session_state.mapel = None
if "stage" not in st.session_state: st.session_state.stage = "Internal"
if "selected_submateri" not in st.session_state: st.session_state.selected_submateri = []
if "quiz_data" not in st.session_state: st.session_state.quiz_data = []
if "user_answers" not in st.session_state: st.session_state.user_answers = {}
if "current_index" not in st.session_state: st.session_state.current_index = 0

# Penambahan State untuk Integrasi Database Siswa & Guru
if "nama_siswa" not in st.session_state: st.session_state.nama_siswa = ""
if "session_id" not in st.session_state: st.session_state.session_id = str(uuid.uuid4())
if "guru_auth" not in st.session_state: st.session_state.guru_auth = False
if "ai_hint_cache" not in st.session_state: st.session_state.ai_hint_cache = {}
if "ai_solution_cache" not in st.session_state: st.session_state.ai_solution_cache = {}
if "material_bundle_code" not in st.session_state: st.session_state.material_bundle_code = ""
if "material_bundle" not in st.session_state: st.session_state.material_bundle = None
if "media_storyboard" not in st.session_state: st.session_state.media_storyboard = None
if "media_ppt_bytes" not in st.session_state: st.session_state.media_ppt_bytes = None
if "package_lkpd_bytes" not in st.session_state: st.session_state.package_lkpd_bytes = None
if "package_ppt_bytes" not in st.session_state: st.session_state.package_ppt_bytes = None

# ------------------------------------------------------------------------------
# RANDOMISASI PRODUCTION: URUTAN SOAL UNIK PER SESI SISWA
# ------------------------------------------------------------------------------
def _quiz_signature(quiz_data):
    """Fingerprint master quiz agar urutan tidak tertukar ketika paket berubah."""
    payload = []
    for idx, q in enumerate(quiz_data):
        payload.append({
            "id": q.get("id", idx + 1),
            "question": q.get("question", ""),
            "options": q.get("options", []),
            "correct_answer": q.get("correct_answer", ""),
        })
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _quiz_question_ids(quiz_data):
    """ID logis soal. Jika ID generator tidak valid/duplikat, gunakan indeks."""
    ids = []
    seen = set()
    for idx, q in enumerate(quiz_data):
        candidate = str(q.get("id", idx + 1))
        if not candidate or candidate in seen:
            candidate = f"IDX-{idx + 1}"
        seen.add(candidate)
        ids.append(candidate)
    return ids

def build_stable_student_quiz_order(quiz_data, session_id, question_order=None):
    """
    Mengembalikan quiz dalam urutan siswa yang stabil.
    question_order adalah daftar ID soal yang sudah disimpan di database.
    Fallback memakai seed session_id untuk kompatibilitas sesi lama.
    """
    if not quiz_data:
        return []

    if question_order:
        by_id = {str(q.get("id", i + 1)): q for i, q in enumerate(quiz_data)}
        ordered = [by_id[qid] for qid in map(str, question_order) if qid in by_id]
        if len(ordered) == len(quiz_data):
            return ordered

    # Fallback kompatibilitas dengan implementasi randomisasi sebelumnya.
    shuffled = list(quiz_data)
    random.Random(str(session_id)).shuffle(shuffled)
    return shuffled

def ensure_quiz_session_order_table():
    """
    Memastikan tabel persistensi urutan soal tersedia.

    Catatan penting: Streamlit SQLConnection/SQLAlchemy tidak selalu menerima
    beberapa statement DDL dalam satu execute(). Karena itu CREATE TABLE dan
    CREATE INDEX dijalankan terpisah agar kompatibel dengan deployment
    PostgreSQL/Supabase yang digunakan RoboMANTAP.
    """
    conn = init_db_connection()
    if conn is None:
        print("LOG DB quiz order init: koneksi PostgreSQL tidak tersedia.")
        return False

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS kuis_session_orders (
        session_id VARCHAR(100) PRIMARY KEY,
        kode_kuis VARCHAR(20) NOT NULL,
        quiz_signature VARCHAR(64) NOT NULL,
        question_order JSONB NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """

    create_index_sql = """
    CREATE INDEX IF NOT EXISTS idx_kuis_session_orders_kode
        ON kuis_session_orders (kode_kuis)
    """

    try:
        with conn.session as s:
            # Jalankan DDL satu per satu. Jangan menggabungkannya dalam satu
            # execute() karena driver/deployment tertentu menolak multi-statement.
            s.execute(text(create_table_sql))
            s.commit()

            s.execute(text(create_index_sql))
            s.commit()

        return True
    except Exception as e:
        print(f"LOG DB quiz order init error: {type(e).__name__}: {e}")
        return False

def _get_saved_quiz_order(session_id, quiz_signature):
    conn = init_db_connection()
    if not conn:
        return None
    try:
        with conn.session as s:
            row = s.execute(
                text("""
                    SELECT question_order
                    FROM kuis_session_orders
                    WHERE session_id = :session_id
                      AND quiz_signature = :quiz_signature
                    LIMIT 1
                """),
                {"session_id": session_id, "quiz_signature": quiz_signature},
            ).fetchone()
            if row:
                return row[0] if isinstance(row[0], list) else json.loads(row[0])
    except Exception as e:
        print(f"LOG DB get quiz order error: {e}")
    return None

def get_or_create_student_quiz_order(kode_kuis, mapel, quiz_data, session_id):
    """
    Versi Super Cepat (Anti-Lag / Zero DB Lock):
    Mengacak urutan soal secara unik berdasarkan session_id siswa di memori lokal.
    """
    if not quiz_data:
        return [], None

    # Gunakan session_id sebagai Seed agar pengacakan unik per siswa 
    # tetapi tetap konsisten (tidak berubah-ubah saat rerun/refresh)
    shuffled = list(quiz_data)
    random.Random(str(session_id)).shuffle(shuffled)
    
    return shuffled, None

# Database Kisi-Kisi Operasional OMI 2026
KISI_KISI_OMI = {
    "MTs (Sederajat SMP)": {
        "Matematika": ["Bilangan", "Aljabar", "Aritmetika Sosial", "Geometri", "Peluang", "Statistika", "Perbandingan & Proporsi", "Problem Solving", "Konteks OMI (Keislaman & Sains)"],
        "IPA Terintegrasi": ["Makhluk Hidup & Sel", "Sistem Organ", "Genetika & Keanekaragaman", "Ekologi", "Zat & Perubahannya", "Energi & Kalor", "Gerak & Gaya", "Getaran, Gelombang & Optik", "Listrik & Kemagnetan", "Bumi & Antariksa", "Eksperimen & Data", "Konteks OMI"],
        "IPS Terintegrasi": ["Geografi", "Kependudukan", "Ekonomi", "Sejarah Indonesia", "Sejarah Islam", "Sosial & Budaya", "Kewarganegaraan", "Lingkungan & Pembangunan", "Literasi Data", "Konteks OMI"]
    },
    "MA (Sederajat SMA)": {
        "Matematika Terintegrasi": ["Bilangan & Teori Bilangan", "Aljabar & Fungsi", "Geometri", "Kombinatorika & Peluang", "Statistika", "Problem Solving", "Konteks OMI"],
        "Biologi Terintegrasi": ["Sel & Biokimia", "Genetika", "Fisiologi", "Botani & Zoologi", "Ekologi", "Evolusi & Keanekaragaman", "Bioteknologi & Lingkungan", "Konteks OMI"],
        "Fisika Terintegrasi": ["Mekanika", "Fluida", "Getaran & Gelombang", "Optik", "Suhu & Kalor", "Listrik & Magnet", "Fisika Modern", "Eksperimen & Data", "Konteks OMI"],
        "Kimia Terintegrasi": ["Struktur Atom & Periodik", "Ikatan Kimia", "Stoikiometri", "Larutan & Asam-Basa", "Redoks", "Termokimia & Kinetika", "Kesetimbangan", "Organik & Lingkungan", "Konteks OMI"],
        "Ekonomi Terintegrasi": ["Ekonomi Dasar", "Mikroekonomi", "Makroekonomi", "Kebijakan Ekonomi", "Akuntansi", "Pasar Modal & Keuangan", "Ekonomi Digital", "Ekonomi Islam", "Analisis Data"],
        "Geografi Terintegrasi": ["Peta & Keruangan", "Geologi & Geomorfologi", "Atmosfer & Iklim", "Hidrosfer", "Biosfer", "Kependudukan", "Sumber Daya & Lingkungan", "Bencana", "SIG & Data Spasial", "Konteks OMI"]
    }
}

# Header Utama
st.markdown(f"""
<div class="school-header">
    <div style="text-align: center;">
        {img_mantap_html}
    </div>
    <div class="school-title">MA DAN MTs AL IRSYAD AL ISLAMIYYAH BONDOWOSO</div>
    <div class="school-subtitle">
        Madrasah Aliyah dan Tsanawiyah Al Irsyad Putri Bondowoso (MANTAP) &nbsp;•&nbsp; 
        <span style="color: #6ee7b7; font-weight: 600;">Powered by RoboMANTAP-Intelligence</span>
    </div>
</div>
""", unsafe_allow_html=True)

# Sidebar Control
with st.sidebar:
    st.markdown("""
    <div style="background: linear-gradient(135deg, #064e3b 0%, #022c22 100%); padding: 16px; border-radius: 12px; border: 1px solid #059669; text-align: center; margin-bottom: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
        <div style="font-size: 26px; margin-bottom: 4px;">🧕🏼</div>
        <div style="color: #ffffff; font-weight: 700; font-size: 16px; letter-spacing: 0.5px;">RoboMANTAP-Intelligence</div>
        <div style="color: #6ee7b7; font-size: 11px; font-weight: 500; margin-bottom: 6px;">Learning Intelligence Platform</div>
        <div style="font-size: 10px; color: #a7f3d0; opacity: 0.85; border-top: 1px solid rgba(255,255,255,0.15); padding-top: 4px; font-style: italic;">Engineered by U.Project Nexus</div>
    </div>

    """, unsafe_allow_html=True)
    # -------------------------------------------------------------------------
    # A. TAMPILAN SIDEBAR JIKA BERADA DI DASHBOARD GURU (PANEL FILTER)
    # -------------------------------------------------------------------------
    if st.session_state.page == "guru_dashboard":
        st.markdown("### ⚙️ Panel Kontrol & Filter")
        # Filter Rentang Waktu
        time_filter = st.radio("⏳ Rentang Waktu:", ["Hari Ini", "Kemarin", "3 Hari Terakhir"], key="filter_time")
        # Toggle Sesi & Auto-Refresh
        only_latest = st.toggle("🎯 Sesi Terbaru Saja", value=True, help="Gabungkan multi-sesi: 1 nama hanya muncul 1 kali (pengerjaan terbaru).", key="filter_latest")
        # Filter Jenjang & Mapel
        selected_jenjang_filter = st.selectbox("🏫 Filter Jenjang:", ["Semua Jenjang", "MTs (Sederajat SMP)", "MA (Sederajat SMA)"], key="filter_jenjang")
        # SETING KHUSUS KUIS

        # -------------------------------------------------------------------------
        # BACA KHUSUS MAPEL KUIS CUSTOM BERLABEL (Quiz) SECARA DINAMIS DARI DATABASE
        # -------------------------------------------------------------------------
        quiz_custom_mapels = []
        conn_filter = init_db_connection()
        if conn_filter:
            try:
                # Hanya tarik mapel yang mengandung kata '(Quiz)' di tabel sesi_ujian
                df_quiz_db = conn_filter.query(
                    """
                    SELECT DISTINCT mapel 
                    FROM sesi_ujian 
                    WHERE mapel LIKE '%(Quiz)%' 
                      AND status NOT IN ('ARCHIVED', 'TRIAL', 'DRAFT', 'HIDDEN')
                    """, 
                    ttl=5
                )
                if not df_quiz_db.empty:
                    quiz_custom_mapels = df_quiz_db['mapel'].dropna().tolist()
            except Exception:
                quiz_custom_mapels = []

        # Tentukan mapel dasar OMI berdasarkan jenjang
        if selected_jenjang_filter == "MTs (Sederajat SMP)":
            base_mapels = list(KISI_KISI_OMI["MTs (Sederajat SMP)"].keys())
        elif selected_jenjang_filter == "MA (Sederajat SMA)":
            base_mapels = list(KISI_KISI_OMI["MA (Sederajat SMA)"].keys())
        else:
            base_mapels = list(KISI_KISI_OMI["MTs (Sederajat SMP)"].keys()) + list(KISI_KISI_OMI["MA (Sederajat SMA)"].keys())

        # Gabungkan Mapel Standar OMI + Mapel Kuis Custom yang aktif
        combined_mapels = sorted(list(set(base_mapels + quiz_custom_mapels)))
        mapel_options = ["Semua Mapel"] + combined_mapels

        selected_mapel_filter = st.selectbox("📚 Filter Mata Pelajaran:", mapel_options, key="filter_mapel")
        selected_status_filter = st.selectbox("📌 Filter Status:", ["Semua Status", "BERJALAN", "SELESAI", "EXPIRED"], key="filter_status")

    else:
        st.markdown("""
        <div style="background: var(--secondary-background-color); border: 1px solid rgba(5, 150, 105, 0.3); padding: 12px 14px; border-radius: 10px; margin-bottom: 15px;">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                <span style="font-size: 11px; font-weight: 600; opacity: 0.7;">ENGINE STATUS</span>
                <span style="font-size: 10px; background: #059669; color: white; padding: 2px 8px; border-radius: 12px; font-weight: 700;">LIVE <span class="blinking-dot-green">🟢</span></span>
            </div>
            <div style="font-size: 11px; line-height: 1.6; opacity: 0.9;">
                ⚡ <b>Model:</b> U.Project Nexus Intelligence v3.6<br>
                🎯 <b>Core:</b> Bina Prestasi OMI 2026<br>
                ⏱️ <b>Response:</b> Real-time AI
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.session_state.jenjang and st.session_state.mapel:
            st.markdown(f"""
            <div style="background: rgba(5, 150, 105, 0.08); border-left: 4px solid #059669; padding: 10px 12px; border-radius: 6px; margin-bottom: 15px;">
                <div style="font-size: 10px; opacity: 0.6; text-transform: uppercase; font-weight: 700;">Sesi Aktif</div>
                <div style="font-size: 12px; font-weight: 700; color: var(--text-color);">{st.session_state.mapel}</div>
                <div style="font-size: 11px; opacity: 0.8;">{st.session_state.jenjang} • {st.session_state.stage}</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("""
        <div style="background: var(--secondary-background-color); border: 1px solid rgba(128,128,128,0.2); padding: 12px 14px; border-radius: 10px; margin-bottom: 15px;">
            <div style="font-size: 11px; font-weight: 700; opacity: 0.8; margin-bottom: 8px;">📋 ATURAN SKORING CBT</div>
            <div style="display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 4px;">
                <span>✅ Jawaban Benar</span>
                <b style="color: #059669;">+4 Poin</b>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 4px;">
                <span>❌ Jawaban Salah</span>
                <b style="color: #ef4444;">-1 Poin</b>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 11px;">
                <span>⚪ Tidak Dijawab</span>
                <b style="opacity: 0.6;">0 Poin</b>
            </div>
        </div>
        """, unsafe_allow_html=True)

    if st.button("🏠 Kembali ke Beranda Utama", use_container_width=True):
        st.session_state.page = "landing"
        st.session_state.jenjang = None
        st.session_state.mapel = None
        st.session_state.guru_auth = False
        st.rerun()

    sidebar_nexus_html = f'<div style="padding: 6px 14px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.08); display: inline-block; margin-bottom: 4px; border: 1px solid rgba(0,0,0,0.05);"><img src="data:image/png;base64,{logo_nexus_b64}" style="height: 42px; max-width: 100%; display: block; margin: 0 auto;"></div>' if logo_nexus_b64 else ''
    st.markdown(f"""
    <div style="text-align: center; margin-top: 20px; padding-top: 15px; border-top: 1px dashed rgba(128,128,128,0.2);">
        <div style="font-size: 10px; opacity: 0.7; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px;">Engineered by</div>
        {sidebar_nexus_html}
        <div style="font-size: 11px; opacity: 0.85; line-height: 1.3;">
            <b style="color: var(--text-color);">U.Project Nexus System</b><br>
            <span style="font-size: 10px; opacity: 0.7;">AI Integration & B2B Solutions</span><br>
            <span style="font-size: 9px; opacity: 0.5;">&copy; 2026 All Rights Reserved</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

#===========================================================
# GENERATOR DOCX. KUIS
#===========================================================
# PEMBERSIH
def clean_math_string(text: str) -> str:
    r"""Pembersih notasi matematika untuk Word; khususnya mencegah \circ -> circ/circl mentah."""
    if not text:
        return ""
    text = str(text)
    replacements = {
        r"\rightarrow": "→", r"\to": "→", r"\Rightarrow": "⇒",
        r"\leftarrow": "←", r"\leftrightarrow": "↔",
        r"\circ": "∘", r"\circl": "∘",
        r"\times": "×", r"\cdot": "·", r"\div": "÷", r"\neq": "≠",
        r"\leq": "≤", r"\geq": "≥", r"\le": "≤", r"\ge": "≥",
        r"\pm": "±", r"\mp": "∓", r"\infty": "∞", r"\pi": "π",
        r"\alpha": "α", r"\beta": "β", r"\theta": "θ", r"\lambda": "λ",
        r"\in": "∈", r"\notin": "∉", r"\forall": "∀", r"\exists": "∃",
        r"\emptyset": "∅", r"\angle": "∠", r"\perp": "⊥", r"\parallel": "∥",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"(?<![A-Za-z])circl(?![A-Za-z])", "∘", text)
    text = re.sub(r'\\left\b\s*[\(\[\{\.\|]?', '(', text)
    text = re.sub(r'\\right\b\s*[\)\]\}\.\|]?', ')', text)
    text = re.sub(r'\\(?:dots|cdots|ldots)', '…', text)
    text = re.sub(r'\\sqrt\{([^}]+)\}', r'√(\1)', text)
    text = re.sub(r'\\sqrt\s*([a-zA-Z0-9_]+)', r'√\1', text)
    sup_map = str.maketrans("0123456789+-=()nxyi", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿˣʸⁱ")
    sub_map = str.maketrans("0123456789+-=()nixy", "₀₁₂₃₄⁵₆₇₈₉₊₋₌₍₎ₙᵢₓᵧ")
    text = re.sub(r'\^\{([^}]+)\}|\^([\-0-9a-zA-Z])', lambda m: (m.group(1) or m.group(2)).translate(sup_map), text)
    text = re.sub(r'\_\{([^}]+)\}|\_([0-9a-zA-Z])', lambda m: (m.group(1) or m.group(2)).translate(sub_map), text)
    text = text.replace("$", "")
    text = text.replace("left(", "(").replace("right)", ")").replace("dots", "…")
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r'\\([a-zA-Z]+)', r'\1', text).replace("\\", "")
    return re.sub(r'\s+', ' ', text).strip()

clean_math_text = clean_math_string

def clean_solution_preview(text: str) -> str:
    """Pembersih KHUSUS Solution Basis pada preview Quiz Custom.

    Tujuannya bukan mengubah isi pembahasan, tetapi membuat notasi matematika/
    ilmiah yang dikirim AI tetap terbaca di Streamlit: arrow, relasi, komposisi,
    pecahan, akar, pangkat, indeks, dan token rusak seperti ``circl``.
    """
    if not text:
        return ""

    value = str(text).strip()

    # Token rusak yang sering muncul ketika LaTeX dipotong oleh model.
    value = re.sub(r"(?<![A-Za-z])circl(?![A-Za-z])", lambda _: r"\circ", value)

    # Perintah sederhana lebih aman ditampilkan sebagai Unicode pada preview,
    # sehingga tidak pernah terlihat sebagai backslash mentah.
    simple_math = {
        r"\longrightarrow": "→", r"\rightarrow": "→", r"\to": "→",
        r"\Longrightarrow": "⇒", r"\Rightarrow": "⇒",
        r"\leftarrow": "←", r"\leftrightarrow": "↔",
        r"\times": "×", r"\cdot": "·", r"\div": "÷",
        r"\neq": "≠", r"\leq": "≤", r"\le": "≤",
        r"\geq": "≥", r"\ge": "≥", r"\pm": "±",
        r"\infty": "∞", r"\circ": "∘", r"\perp": "⊥",
        r"\parallel": "∥", r"\angle": "∠", r"\in": "∈",
        r"\notin": "∉", r"\forall": "∀", r"\exists": "∃",
        r"\emptyset": "∅", r"\pi": "π", r"\alpha": "α",
        r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
        r"\theta": "θ", r"\lambda": "λ", r"\mu": "μ",
        r"\approx": "≈", r"\equiv": "≡", r"\propto": "∝",
        r"\sum": "Σ", r"\int": "∫", r"\partial": "∂",
        r"\Delta": "Δ", r"\Omega": "Ω", r"\degree": "°",
    }
    for old, new in simple_math.items():
        value = value.replace(old, new)

    value = value.replace(" -> ", " → ").replace(" => ", " ⇒ ")
    value = value.replace("->", "→").replace("=>", "⇒")
    value = re.sub(r"\\left\s*([\(\[\{])", r"\1", value)
    value = re.sub(r"\\right\s*([\)\]\}])", r"\1", value)
    value = re.sub(r"\\(?:mathrm|text|mathbf|operatorname)\{([^{}]+)\}", r"\1", value)
    value = re.sub(r"\\ce\{([^{}]+)\}", r"\1", value)

    # Pecahan/akar tetap memakai KaTeX agar tampil sebagai notasi matematika,
    # tetapi hanya bagian rumusnya yang dibungkus, bukan seluruh paragraf.
    def wrap_formula(match):
        expr = match.group(0)
        return f"${expr}$"

    value = re.sub(r"\\frac\{[^{}]+\}\{[^{}]+\}", wrap_formula, value)
    value = re.sub(r"\\sqrt(?:\{[^{}]+\}|[A-Za-z0-9]+)", wrap_formula, value)

    # Pangkat/indeks sederhana tanpa delimiter: ubah ke Unicode agar tidak mentah.
    sup_map = str.maketrans("0123456789+-=()nxyi", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿˣʸⁱ")
    sub_map = str.maketrans("0123456789+-=()nixy", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₙᵢₓᵧ")
    value = re.sub(r"\^\{([^}]+)\}|\^([A-Za-z0-9])", lambda m: (m.group(1) or m.group(2)).translate(sup_map), value)
    value = re.sub(r"_\{([^}]+)\}|_([A-Za-z0-9])", lambda m: (m.group(1) or m.group(2)).translate(sub_map), value)

    # Hapus delimiter math kosong yang kadang ditinggalkan generator.
    value = value.replace("$$$$", "")
    value = re.sub(r"\$\s*\$", "", value)
    return value.strip()


def contains_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]", str(text or "")))


def apply_arabic_paragraph_style(paragraph):
    """Aktifkan RTL untuk paragraf Word yang mengandung aksara Arab."""
    if not paragraph:
        return
    try:
        ppr = paragraph._p.get_or_add_pPr()
        bidi = parse_xml(r'<w:bidi xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" w:val="1"/>')
        ppr.append(bidi)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    except Exception:
        pass


def apply_arabic_run_style(run):
    """Gunakan font complex-script yang aman untuk aksara Arab di Word."""
    if not run:
        return
    try:
        run.font.name = "Traditional Arabic"
        rpr = run._r.get_or_add_rPr()
        rfonts = rpr.rFonts
        if rfonts is None:
            rfonts = parse_xml(r'<w:rFonts xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>')
            rpr.append(rfonts)
        rfonts.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}cs', 'Traditional Arabic')
        rfonts.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ascii', 'Aptos')
    except Exception:
        pass


def add_omml_fraction(paragraph, num_text: str, den_text: str):
    """Menyisipkan struktur Pecahan Tegak Resmi Microsoft Word (Equation)."""
    num_clean = clean_math_string(num_text)
    den_clean = clean_math_string(den_text)
    
    omml_xml = (
        f'<m:oMath {nsdecls("m")}>'
        f'  <m:f>'
        f'    <m:num><m:r><m:t>{num_clean}</m:t></m:r></m:num>'
        f'    <m:den><m:r><m:t>{den_clean}</m:t></m:r></m:den>'
        f'  </m:f>'
        f'</m:oMath>'
    )
    paragraph._p.append(parse_xml(omml_xml))

def add_omml_matrix(paragraph, matrix_type: str, content: str):
    """Menyisipkan struktur Matriks 2D Bertingkat Resmi Microsoft Word (Equation)."""
    beg_chr, end_chr = "(", ")"
    if matrix_type == "bmatrix":
        beg_chr, end_chr = "[", "]"
    elif matrix_type in ["vmatrix", "Vmatrix"]:
        beg_chr, end_chr = "|", "|"
    elif matrix_type == "matrix":
        beg_chr, end_chr = "", ""

    # Memecah baris (\\ atau \cr) dan kolom (&)
    rows = [r.strip() for r in re.split(r'\\\\|\\cr', content) if r.strip()]
    
    matrix_xml_rows = []
    for r in rows:
        cols = [c.strip() for c in r.split('&')]
        cols_xml = []
        for c in cols:
            cleaned_c = html.escape(clean_math_string(c))
            cols_xml.append(f'<m:e><m:r><m:t>{cleaned_c}</m:t></m:r></m:e>')
        matrix_xml_rows.append(f'<m:mr>{"".join(cols_xml)}</m:mr>')

    # Gunakan tag resmi OMML Word: <m:m>
    inner_matrix = f'<m:m>{"".join(matrix_xml_rows)}</m:m>'

    if beg_chr or end_chr:
        omml_xml = (
            f'<m:oMath {nsdecls("m")}>'
            f'  <m:d>'
            f'    <m:dPr>'
            f'      <m:begChr m:val="{beg_chr}"/>'
            f'      <m:endChr m:val="{end_chr}"/>'
            f'    </m:dPr>'
            f'    <m:e>{inner_matrix}</m:e>'
            f'  </m:d>'
            f'</m:oMath>'
        )
    else:
        omml_xml = f'<m:oMath {nsdecls("m")}>{inner_matrix}</m:oMath>'

    paragraph._p.append(parse_xml(omml_xml))


def append_text_with_fractions(paragraph, text: str, is_bold: bool = False, color_rgb: RGBColor = None):
    """Membagi paragraf: teks biasa, pecahan \\frac, dan matriks \\begin{...matrix}."""
    if not text:
        return

    math_pattern = re.compile(
        r'\\begin\{(?P<mtype>[pbvV]?matrix)\}(?P<mcontent>.*?)\\end\{(?P=mtype)\}|\\(?:f|tf)rac\{(?P<num>[^}]+)\}\{(?P<den>[^}]+)\}',
        re.DOTALL
    )
    last_idx = 0

    for match in math_pattern.finditer(text):
        start, end = match.span()
        
        # Cetak teks biasa sebelum rumus
        if start > last_idx:
            plain_part = clean_math_string(text[last_idx:start])
            if plain_part:
                run = paragraph.add_run(plain_part + " ")
                run.bold = is_bold
                if contains_arabic(plain_part):
                    apply_arabic_paragraph_style(paragraph)
                    apply_arabic_run_style(run)
                if color_rgb:
                    run.font.color.rgb = color_rgb

        # Jika Matriks -> Rendernya pakai add_omml_matrix
        if match.group('mtype'):
            add_omml_matrix(paragraph, match.group('mtype'), match.group('mcontent'))
            
        # Jika Pecahan -> Rendernya pakai add_omml_fraction (asli)
        elif match.group('num'):
            add_omml_fraction(paragraph, match.group('num'), match.group('den'))
        
        run_space = paragraph.add_run(" ")
        run_space.bold = is_bold

        last_idx = end

    # Cetak sisa teks setelah rumus terakhir
    if last_idx < len(text):
        plain_part = clean_math_string(text[last_idx:])
        if plain_part:
            run = paragraph.add_run(plain_part)
            run.bold = is_bold
            if contains_arabic(plain_part):
                apply_arabic_paragraph_style(paragraph)
                apply_arabic_run_style(run)
            if color_rgb:
                run.font.color.rgb = color_rgb

# GENERATOR KUIS
def generate_quiz_docx(config: dict, quiz_list: list) -> bytes:
    """Membuat file Word (.docx) berformat LKPD resmi lengkap dengan logo, kop instansi, dan layout rapi."""
    doc = Document()

    header_table = doc.add_table(rows=1, cols=2)
    header_table.autofit = False
    
    cells = header_table.rows[0].cells
    cells[0].width = Inches(1.6)
    cells[1].width = Inches(4.7)
    
    # Vertikal Center
    cells[0].vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    cells[1].vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    # Kolom Kiri: Logo Instansi
    p_logo = cells[0].paragraphs[0]
    p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    logo_path = "logo.png"  # File logo.png di root directory
    if os.path.exists(logo_path):
        p_logo.add_run().add_picture(logo_path, width=Inches(1.5))
    else:
        # Fallback jika file logo belum diunggah
        r_logo = p_logo.add_run("[LOGO MANTAP]")
        r_logo.bold = True
        r_logo.font.size = Pt(12)
        r_logo.font.color.rgb = RGBColor(6, 78, 59)

    # Kolom Kanan: Teks Kop Instansi
    p_title = cells[1].paragraphs[0]
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_after = Pt(2)
    
    r1 = p_title.add_run("LEMBAR KUIS GuruMANTAP\n")
    r1.bold = True
    r1.font.size = Pt(13)
    r1.font.color.rgb = RGBColor(6, 78, 59) # Warna Hijau Edukasi
    
    r2 = p_title.add_run("Madrasah Aliyah dan Tsanawiyah Al-Irsyad Al-Islamiyah Putri Bondowoso\n")
    r2.bold = True
    r2.font.size = Pt(10.5)
    
    # Ambil tanggal WIB presisi saat dokumen dibuat
    now_wib = datetime.utcnow() + timedelta(hours=7)
    nama_bulan = [
        "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]
    tgl_presisi = f"{now_wib.day} {nama_bulan[now_wib.month]} {now_wib.year}"
    # Teks Tanggal Terbit
    r3 = p_title.add_run(f"Tanggal: {tgl_presisi}")
    r3.italic = True
    r3.font.size = Pt(9.5)
    r3.font.color.rgb = RGBColor(100, 100, 100)

    # --- 2. GARIS PEMBATAS HIJAU SOLID DI BAWAH KOP ---
    p_div = doc.add_paragraph()
    p_div.paragraph_format.space_before = Pt(4)
    p_div.paragraph_format.space_after = Pt(10)
    pBdr = parse_xml(
        r'<w:pBdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        r'<w:bottom w:val="single" w:sz="20" w:space="1" w:color="064E3B"/>'
        r'</w:pBdr>'
    )
    p_div._p.get_or_add_pPr().append(pBdr)

    # --- 3. JUDUL PAKET KUIS ---
    p_paket = doc.add_paragraph()
    p_paket.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_paket.paragraph_format.space_after = Pt(10)
    r_paket = p_paket.add_run(f"PAKET KUIS {config.get('mapel', 'Mata Pelajaran').upper()}")
    r_paket.bold = True
    r_paket.font.size = Pt(13)
    r_paket.font.color.rgb = RGBColor(6, 78, 59)

    # --- 4. META INFO KUIS (Tabel 3 Kolom Lurus Sejajar) ---
    meta_items = [
        ("Jenjang / Kelas", f"{config.get('jenjang', '-')} ({config.get('kelas', '-')})"),
        ("Materi Utama", f"{clean_math_string(config.get('materi', '-'))}"),
        ("Jumlah Soal", f"{len(quiz_list)} Soal | Opsi: {'A-D' if option_count_for_jenjang(config.get('jenjang', 'MTs')) == 4 else 'A-E'} | Durasi: {timedelta(seconds=int(normalize_custom_timer_config(config).get('timer_seconds', 0)))}"),
        ("Masa Aktif Kuis", f"{config.get('time_start_str', '--:--')} hingga {config.get('time_end_str', '--:--')} WIB")
    ]

    meta_table = doc.add_table(rows=0, cols=3)
    meta_table.autofit = False

    for label, val in meta_items:
        row_cells = meta_table.add_row().cells
        
        # Kolom 1: Label (Bold)
        p0 = row_cells[0].paragraphs[0]
        r0 = p0.add_run(label)
        r0.bold = True
        p0.paragraph_format.space_before = Pt(2)
        p0.paragraph_format.space_after = Pt(2)
        row_cells[0].width = Inches(1.5)
        
        # Kolom 2: Titik Dua
        p1 = row_cells[1].paragraphs[0]
        r1 = p1.add_run(":")
        r1.bold = True
        p1.paragraph_format.space_before = Pt(2)
        p1.paragraph_format.space_after = Pt(2)
        row_cells[1].width = Inches(0.2)
        
        # Kolom 3: Teks Nilai
        p2 = row_cells[2].paragraphs[0]
        p2.add_run(val)
        p2.paragraph_format.space_before = Pt(2)
        p2.paragraph_format.space_after = Pt(2)
        row_cells[2].width = Inches(4.8)

    # Spasi Penghubung Pas menuju Soal (Tanpa Garis Pembatas Lagi)
    p_space = doc.add_paragraph()
    p_space.paragraph_format.space_before = Pt(12)
    p_space.paragraph_format.space_after = Pt(4)

    # --- 5. LOOP SOAL & PEMBAHASAN ---
    for idx, item in enumerate(quiz_list, start=1):
        # 1. Soal
        p_q = doc.add_paragraph()
        p_q.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p_q.paragraph_format.space_before = Pt(8)
        
        # Cetak Nomor + Teks Soal (Pecahan Tegak Otomatis)
        p_q.add_run(f"Soal {idx}. ").bold = True
        append_text_with_fractions(p_q, item.get('question', ''), is_bold=True)

        # 2. Opsi Jawaban
        for opt in item.get('options', []):
            p_opt = doc.add_paragraph()
            p_opt.paragraph_format.left_indent = Inches(0.25)
            p_opt.paragraph_format.space_after = Pt(2)
            append_text_with_fractions(p_opt, opt)

        # 3. Kunci Jawaban
        p_ans = doc.add_paragraph()
        p_ans.paragraph_format.left_indent = Inches(0.25)
        p_ans.add_run("Kunci Jawaban: ").bold = True
        append_text_with_fractions(p_ans, item.get('correct_answer', ''), is_bold=True, color_rgb=RGBColor(5, 150, 105))

        # 4. Pembahasan
        if item.get('solution_basis'):
            p_sol = doc.add_paragraph()
            p_sol.paragraph_format.left_indent = Inches(0.25)
            p_sol.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p_sol.add_run("Pembahasan: ").bold = True
            append_text_with_fractions(p_sol, item.get('solution_basis'))
            p_sol.paragraph_format.space_after = Pt(12)


    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()

# ===========================================================
# GENERATOR PDF. LKPD
# ===========================================================
# BACKGROUND LKPD
def draw_cover_background(canvas_obj, doc):
    canvas_obj.saveState()
    cover_path = "cover.png"
    if os.path.exists(cover_path):
        canvas_obj.drawImage(cover_path, 0, 0, width=A4[0], height=A4[1])
    canvas_obj.restoreState()

# HELPER MERAPIKAN LKPD
_PDF_FRAC_CACHE = {}

def generate_frac_image(num_str: str, den_str: str) -> str:
    """Membuat file gambar PNG pecahan tegak lurus untuk PDF."""
    cache_key = f"{num_str}_{den_str}"
    if cache_key in _PDF_FRAC_CACHE and os.path.exists(_PDF_FRAC_CACHE[cache_key]):
        return _PDF_FRAC_CACHE[cache_key]

    try:
        fig = plt.figure(figsize=(0.35, 0.35), dpi=200)
        fig.patch.set_alpha(0.0)
        ax = fig.add_subplot(111)
        ax.axis('off')

        math_str = f"$\\frac{{{num_str}}}{{{den_str}}}$"
        ax.text(0.5, 0.5, math_str, fontsize=11, ha='center', va='center', color='#1F2937')

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        plt.savefig(tmp.name, format='png', bbox_inches='tight', pad_inches=0.01, transparent=True)
        plt.close(fig)

        _PDF_FRAC_CACHE[cache_key] = tmp.name
        return tmp.name
    except Exception:
        return None

def clean_pdf_text(text: str) -> str:
    """
    Master Helper PDF (3 Lapis Anti-Kotak Hitam + Pecahan Campuran Presisi):
    Mengonversi LaTeX, Unicode Pangkat/Subscript, Logaritma, Kimia, dan Pecahan
    (termasuk pecahan campuran seperti 5⅓ atau 5 1/3) menjadi HTML ReportLab / PNG Inline.
    """
    if not text:
        return ""

    # Kamus Lengkap Pecahan Unicode
    frac_map = {
        "¼": ("1", "4"), "½": ("1", "2"), "¾": ("3", "4"),
        "⅐": ("1", "7"), "⅑": ("1", "9"), "⅒": ("1", "10"),
        "⅓": ("1", "3"), "⅔": ("2", "3"),
        "⅕": ("1", "5"), "⅖": ("2", "5"), "⅗": ("3", "5"), "⅘": ("4", "5"),
        "⅙": ("1", "6"), "⅚": ("5", "6"),
        "⅛": ("1", "8"), "⅜": ("3", "8"), "⅝": ("5", "8"), "⅞": ("7", "8")
    }

    # 0. Normalisasi Format Kurung Dulu: 5(1/3) -> 5 1/3
    text = re.sub(r'(\d+)\s*\(([0-9]{1,2})/([0-9]{1,2})\)', r'\1 \2/\3', text)

    # 1. Konversi Pecahan Unicode (Ditambah Penanganan Pecahan Campuran 5⅓)
    for uni, (num, den) in frac_map.items():
        if uni in text:
            img_path = generate_frac_image(num, den)
            if img_path:
                img_tag = f'<img src="{img_path}" height="13" valign="middle"/>'
            else:
                img_tag = f'<sup>{num}</sup>/<sub>{den}</sub>'

            # A. Jika Pecahan Campuran (ada angka bulat di depan, contoh: 5⅓ atau 5 ⅓)
            text = re.sub(rf'(\d+)\s*{re.escape(uni)}', rf'\1&nbsp;{img_tag}', text)
            
            # B. Jika Pecahan Berdiri Sendiri (contoh: ⅓)
            text = text.replace(uni, img_tag)

    # 2. Konversi Perintah LaTeX \frac{a}{b} dan \tfrac{a}{b}
    def repl_latex_frac(match):
        num, den = match.group(1).strip(), match.group(2).strip()
        img_path = generate_frac_image(num, den)
        if img_path:
            return f'<img src="{img_path}" height="13" valign="middle"/>'
        return f'<sup>{num}</sup>/<sub>{den}</sub>'

    text = re.sub(r'\\(?:f|tf)rac\{([^}]+)\}\{([^}]+)\}', repl_latex_frac, text)

    # 3A. Konversi Pecahan Campuran Miring (Contoh: 5 1/3 -> 5 <sup>1</sup>/<sub>3</sub>)
    def repl_mixed_slash_frac(match):
        whole, num, den = match.group(1), match.group(2), match.group(3)
        img_path = generate_frac_image(num, den)
        if img_path:
            return f'{whole}&nbsp;<img src="{img_path}" height="13" valign="middle"/>'
        return f'{whole}&nbsp;<sup>{num}</sup>/<sub>{den}</sub>'

    text = re.sub(r'(\d+)\s+([0-9]{1,2})/([0-9]{1,2})\b', repl_mixed_slash_frac, text)

    # 3B. Konversi Pecahan Biasa Miring (Contoh: 1/3, 3/8)
    def repl_slash_frac(match):
        num, den = match.group(1), match.group(2)
        img_path = generate_frac_image(num, den)
        if img_path:
            return f'<img src="{img_path}" height="13" valign="middle"/>'
        return f'<sup>{num}</sup>/<sub>{den}</sub>'

    text = re.sub(r'\b([0-9]{1,2})/([0-9]{1,2})\b', repl_slash_frac, text)

    # 4. SAPU BERSIH LAPIS TERAKHIR (Sweeper: Musnahkan sisa pecahan Unicode apapun)
    def sweep_unicode_fractions(match):
        ch = match.group(0)
        if ch in frac_map:
            n, d = frac_map[ch]
            return f'<sup>{n}</sup>/<sub>{d}</sub>'
        return f'<sup>?</sup>/<sub>?</sub>'

    text = re.sub(r'[\u2150-\u2189\u00bc-\u00be]', sweep_unicode_fractions, text)

    # 5. Konversi Unicode Superscript (⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻) -> <sup>...</sup>
    sup_chars = "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿˣʸⁱ"
    sup_trans = str.maketrans(sup_chars, "0123456789+-=()nxyi")
    text = re.sub(r'[' + re.escape(sup_chars) + r']+', lambda m: f"<sup>{m.group(0).translate(sup_trans)}</sup>", text)

    # 6. Konversi Unicode Subscript (₀₁₂₃₄₅₆₇₈₉₊₋) -> <sub>...</sub>
    sub_chars = "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₙᵢₓᵧ"
    sub_trans = str.maketrans(sub_chars, "0123456789+-=()nixy")
    text = re.sub(r'[' + re.escape(sub_chars) + r']+', lambda m: f"<sub>{m.group(0).translate(sub_trans)}</sub>", text)

    # 7. Konversi LaTeX Pangkat (^) dan Subscript (_) -> <sup> & <sub>
    text = re.sub(r'\^\{([^}]+)\}|\^([\-0-9a-zA-Z]+)', r'<sup>\1\2</sup>', text)
    text = re.sub(r'\_\{([^}]+)\}|\_([0-9a-zA-Z]+)', r'<sub>\1\2</sub>', text)

    # 8. Tangani Akar (\sqrt)
    text = re.sub(r'\\sqrt\{([^}]+)\}', r'√( \1 )', text)
    text = re.sub(r'\\sqrt\s*([a-zA-Z0-9_]+)', r'√\1', text)

    # 9. Tangani Panah & Simbol LaTeX
    text = re.sub(r'\\(?:rightarrow|to)\b', '→', text)
    text = re.sub(r'\\Rightarrow\b', '⇒', text)
    text = re.sub(r'\\leftarrow\b', '←', text)
    text = re.sub(r'\\(?:dots|cdots|ldots)', '…', text)
    text = re.sub(r'\\left\b\s*[\(\[\{\.\|]?', '(', text)
    text = re.sub(r'\\right\b\s*[\)\]\}\.\|]?', ')', text)

    # 10. Bersihkan Simbol Matematika Standar & Backslash
    replacements = {
        r"\times": "×", r"\cdot": "·", r"\div": "÷", r"\neq": "≠",
        r"\leq": "≤", r"\geq": "≥", r"\pm": "±", r"\infty": "∞",
        r"\pi": "π", r"\alpha": "α", r"\beta": "β", r"\theta": "θ",
        r"\log": "log", "$": ""
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    text = text.replace("{", "").replace("}", "")
    text = re.sub(r'\\([a-zA-Z]+)', r'\1', text).replace("\\", "")

    return re.sub(r'\s+', ' ', text).strip()
    
# GENERATOR LKPD
def create_lkpd_pdf_buffer(mapel, kelas, topik, ai_content, logo_path="logo.png"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=2.0 * cm, rightMargin=2.0 * cm,
        topMargin=2.0 * cm, bottomMargin=2.0 * cm
    )
    styles = getSampleStyleSheet()
    
    # Ambil Tanggal Presisi WIB saat PDF dibuat
    now_wib = datetime.utcnow() + timedelta(hours=7)
    nama_bulan = [
        "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]
    tgl_presisi = f"{now_wib.day} {nama_bulan[now_wib.month]} {now_wib.year}"
    
    # Custom Typography Styles
    style_cover_school = ParagraphStyle('CoverSchool', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, leading=14, textColor=colors.HexColor('#064E3B'), alignment=TA_CENTER)
    style_cover_title = ParagraphStyle('CoverTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=18, leading=22, textColor=colors.HexColor('#059669'), alignment=TA_CENTER)
    style_cover_sub = ParagraphStyle('CoverSub', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=13, textColor=colors.HexColor('#374151'), alignment=TA_CENTER)
    style_section_heading = ParagraphStyle('SecHeading', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, leading=14, textColor=colors.white)
    
    # Paragraf Body Rata Kanan-Kiri (JUSTIFY)
    style_body = ParagraphStyle('BodyTextCustom', parent=styles['Normal'], fontName='Helvetica', fontSize=9.5, leading=13.5, textColor=colors.HexColor('#1F2937'), alignment=TA_JUSTIFY)
    
    # Meta Info Styles (Label & Value)
    style_meta_label = ParagraphStyle('MetaLabel', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9.5, leading=13, textColor=colors.HexColor('#064E3B'))
    style_meta_val = ParagraphStyle('MetaVal', parent=styles['Normal'], fontName='Helvetica', fontSize=9.5, leading=13, textColor=colors.HexColor('#1F2937'))

    story = []
    story.append(Spacer(1, 1.5 * cm))

    # Header Logo
    if os.path.exists(logo_path):
        img_logo = Image(logo_path, width=3.8 * cm, height=2.2 * cm)
        img_logo.hAlign = 'CENTER'
        story.append(img_logo)
        story.append(Spacer(1, 0.4 * cm))

    # Header Instansi & Judul LKPD
    school_html = "Madrasah Aliyah dan Tsanawiyah<br/><b>Al-Irsyad Al-Islamiyah Putri Bondowoso</b>"
    story.append(Paragraph(school_html, style_cover_school))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph("LEMBAR KERJA PESERTA DIDIK", style_cover_title))
    story.append(Paragraph("(LKPD)", style_cover_title))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("Model Pembelajaran HOTS & Integrasi Nilai Keislaman", style_cover_sub))
    story.append(Spacer(1, 0.8 * cm))

    # Meta Info Box (Tabel 3 Kolom Lurus Sejajar)
    meta_rows = [
        [Paragraph("Mata Pelajaran", style_meta_label), Paragraph(":", style_meta_label), Paragraph(mapel, style_meta_val)],
        [Paragraph("Kelas / Jenjang", style_meta_label), Paragraph(":", style_meta_label), Paragraph(kelas, style_meta_val)],
        [Paragraph("Topik Utama", style_meta_label), Paragraph(":", style_meta_label), Paragraph(topik, style_meta_val)],
        [Paragraph("Tanggal", style_meta_label), Paragraph(":", style_meta_label), Paragraph(tgl_presisi, style_meta_val)],
        [Paragraph("Nama Siswa", style_meta_label), Paragraph(":", style_meta_label), Paragraph("......................................................................", style_meta_val)],
    ]
    
    t_meta_inner = Table(meta_rows, colWidths=[3.5 * cm, 0.4 * cm, 10.5 * cm])
    t_meta_inner.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))

    t_meta_box = Table([[t_meta_inner]], colWidths=[15.5 * cm])
    t_meta_box.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#ECFDF5')),
        ('BOX', (0,0), (-1,-1), 1.5, colors.HexColor('#059669')),
        ('PADDING', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
    ]))
    t_meta_box.hAlign = 'CENTER'
    story.append(t_meta_box)
    story.append(PageBreak())

    # --- HALAMAN 2: ISI LKPD ---
    # [A] TUJUAN PEMBELAJARAN
    head_a = Paragraph("[A] TUJUAN PEMBELAJARAN (HOTS)", style_section_heading)
    t_head_a = Table([[head_a]], colWidths=[16.5 * cm])
    t_head_a.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#059669')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(t_head_a)
    story.append(Spacer(1, 0.2 * cm))

    tujuan_list = ai_content.get("tujuan", [])
    tujuan_text = "<br/>".join([f"{i+1}. {clean_pdf_text(t)}" for i, t in enumerate(tujuan_list)])
    story.append(Paragraph(tujuan_text, style_body))
    story.append(Spacer(1, 0.5 * cm))

    # [B] APERSEPSI & EKSPLORASI KONSEP
    head_b = Paragraph("[B] APERSEPSI & EKSPLORASI KONSEP", style_section_heading)
    t_head_b = Table([[head_b]], colWidths=[16.5 * cm])
    t_head_b.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#059669')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(t_head_b)
    story.append(Spacer(1, 0.2 * cm))

    p_ringkasan = Paragraph(clean_pdf_text(ai_content.get("ringkasan", "")), style_body)
    t_box_b = Table([[p_ringkasan]], colWidths=[16.5 * cm])
    t_box_b.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F0F9FF')), ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#BAE6FD')), ('PADDING', (0,0), (-1,-1), 8)]))
    story.append(t_box_b)
    story.append(Spacer(1, 0.5 * cm))

    # [C] TUGAS EKSPLORASI MANDIRI (3 SOAL)
    head_c = Paragraph("[C] TUGAS EKSPLORASI MANDIRI", style_section_heading)
    t_head_c = Table([[head_c]], colWidths=[16.5 * cm])
    t_head_c.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#059669')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(t_head_c)
    story.append(Spacer(1, 0.3 * cm))

    # Loop 3 Soal Eksplorasi (range 1 hingga 4)
    for i in range(1, 6):
        soal_raw = ai_content.get(f'soal_{i}', f'Soal eksplorasi nomor {i} belum tersedia.')
        soal_clean = clean_pdf_text(soal_raw)
        story.append(Paragraph(f"<b>Soal {i}:</b> {soal_clean}", style_body))
        story.append(Spacer(1, 0.15 * cm))
        p_ans = Paragraph("<font color='#9CA3AF'><i>Lembar Jawaban:</i></font><br/><br/><br/><br/>", style_body)
        t_ans = Table([[p_ans]], colWidths=[16.5 * cm])
        t_ans.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F9FAFB')), ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#E5E7EB')), ('PADDING', (0,0), (-1,-1), 6)]))
        story.append(t_ans)
        story.append(Spacer(1, 0.4 * cm))

    # [D] REFLEKSI KEISLAMAN & HIKMAH
    head_d = Paragraph("[D] REFLEKSI KEISLAMAN & HIKMAH", style_section_heading)
    t_head_d = Table([[head_d]], colWidths=[16.5 * cm])
    t_head_d.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#D97706')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(t_head_d)
    story.append(Spacer(1, 0.2 * cm))
    refleksi_clean = clean_pdf_text(ai_content.get("refleksi", ""))
    p_refleksi = Paragraph(f'<i>"{refleksi_clean}"</i>', style_body)
    t_box_d = Table([[p_refleksi]], colWidths=[16.5 * cm])
    t_box_d.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#FEF3C7')), ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#FDE68A')), ('PADDING', (0,0), (-1,-1), 8)]))
    story.append(t_box_d)

    doc.build(story, onFirstPage=draw_cover_background, onLaterPages=draw_cover_background)
    buffer.seek(0)
    return buffer

# ========================================
# RENDER CUSTOM TIMER
# ========================================
@st.fragment(run_every="1s")
def render_custom_timer(start_time_wib, timer_seconds):
    sekarang_wib = datetime.utcnow() + timedelta(hours=7)
    terpakai_detik = int((sekarang_wib - start_time_wib).total_seconds())
    sisa_detik = timer_seconds - terpakai_detik

    if sisa_detik <= 0:
        st.session_state.is_timeout = True  # Set penanda kehabisan waktu
        st.session_state.page = "result"
        st.rerun()

    sisa_m = max(0, sisa_detik // 60)
    sisa_s = max(0, sisa_detik % 60)
    st.error(f"⏳ **Sisa Waktu Ujian:** {sisa_m:02d}:{sisa_s:02d}")

# ==============================================================================
# HELPER GENERATOR 5 PAKET SOAL PRE-GENERATED (ZERO-LAG FOR 60+ STUDENTS)
# ==============================================================================
def create_5_quiz_packages(master_quiz):
    """
    Membuat 5 variasi paket soal acak yang sudah difiksasi (Paket 1 - 5).
    Dijalankan sekali saja saat kuis diterbitkan oleh Guru.
    """
    if not master_quiz:
        return []
    
    packages = []
    for i in range(5):
        # Buat salinan list soal
        shuffled_list = list(master_quiz)
        # Gunakan seed acak unik per indeks paket
        r = random.Random(f"paket_seed_{i}_{len(master_quiz)}")
        r.shuffle(shuffled_list)
        packages.append(shuffled_list)
        
    return packages

# HELPER PEMBERSIH NOTASI MATEMATIKA
import re
import html


def clean_preview_math_scientific(text):
    """
    Cleaner khusus tampilan Preview Quiz Custom.
    Tidak mengubah data asli quiz/database.
    Fokus pada matematika, sains, notasi ilmiah, dan simbol umum.
    """
    if text is None:
        return ""

    text = str(text)

    # ---------------------------------------------------------
    # 1. NORMALISASI NOTASI LATEX UMUM
    # ---------------------------------------------------------
    replacements = {
        r"\rightarrow": "→",
        r"\to": "→",
        r"\Rightarrow": "⇒",
        r"\Longrightarrow": "⟹",
        r"\leftarrow": "←",
        r"\Leftarrow": "⇐",
        r"\leftrightarrow": "↔",
        r"\Leftrightarrow": "⇔",

        r"\circ": "∘",
        r"circl": "∘",

        r"\times": "×",
        r"\cdot": "·",
        r"\div": "÷",
        r"\pm": "±",
        r"\mp": "∓",

        r"\leq": "≤",
        r"\le": "≤",
        r"\geq": "≥",
        r"\ge": "≥",
        r"\neq": "≠",
        r"\ne": "≠",
        r"\approx": "≈",
        r"\equiv": "≡",

        r"\infty": "∞",
        r"\degree": "°",
        r"\angle": "∠",
        r"\perp": "⊥",
        r"\parallel": "∥",

        r"\therefore": "∴",
        r"\because": "∵",

        r"\sum": "Σ",
        r"\prod": "Π",
        r"\int": "∫",
        r"\partial": "∂",
        r"\nabla": "∇",

        r"\in": "∈",
        r"\notin": "∉",
        r"\subset": "⊂",
        r"\subseteq": "⊆",
        r"\supset": "⊃",
        r"\supseteq": "⊇",
        r"\cup": "∪",
        r"\cap": "∩",
        r"\emptyset": "∅",

        r"\alpha": "α",
        r"\beta": "β",
        r"\gamma": "γ",
        r"\delta": "δ",
        r"\epsilon": "ε",
        r"\theta": "θ",
        r"\lambda": "λ",
        r"\mu": "μ",
        r"\pi": "π",
        r"\sigma": "σ",
        r"\phi": "φ",
        r"\omega": "ω",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # ---------------------------------------------------------
    # 2. BERSIHKAN COMMAND FORMAT LATEX
    # ---------------------------------------------------------
    text = re.sub(r"\\mathrm\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\mathbf\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\text\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\operatorname\{([^{}]*)\}", r"\1", text)

    # ---------------------------------------------------------
    # 3. \frac{a}{b}
    # Dibuat menjadi bentuk linear yang tetap terbaca.
    # ---------------------------------------------------------
    def replace_frac(match):
        numerator = match.group(1).strip()
        denominator = match.group(2).strip()
        return f"({numerator})/({denominator})"

    text = re.sub(
        r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}",
        replace_frac,
        text
    )

    # ---------------------------------------------------------
    # 4. \sqrt{x}
    # ---------------------------------------------------------
    text = re.sub(
        r"\\sqrt\s*\{([^{}]*)\}",
        r"√(\1)",
        text
    )

    # ---------------------------------------------------------
    # 5. SUPERSCRIPT ANGKA / HURUF
    # x^2 -> x²
    # x^{-1} -> x⁻¹
    # ---------------------------------------------------------
    superscript_map = str.maketrans(
        "0123456789+-=()nixy",
        "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱˣʸ"
    )

    def superscript_replace(match):
        value = match.group(1)
        return value.translate(superscript_map)

    text = re.sub(
        r"\^\{([^{}]+)\}",
        superscript_replace,
        text
    )

    text = re.sub(
        r"\^([0-9+\-=()nixy]+)",
        lambda m: m.group(1).translate(superscript_map),
        text
    )

    # ---------------------------------------------------------
    # 6. SUBSCRIPT
    # H_2O -> H₂O
    # x_{1} -> x₁
    # ---------------------------------------------------------
    subscript_map = str.maketrans(
        "0123456789+-=()aeinorstu",
        "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑᵢₙₒᵣₛₜᵤ"
    )

    def subscript_replace(match):
        value = match.group(1)
        return value.translate(subscript_map)

    text = re.sub(
        r"_\{([^{}]+)\}",
        subscript_replace,
        text
    )

    text = re.sub(
        r"_([0-9]+)",
        lambda m: m.group(1).translate(subscript_map),
        text
    )

    # ---------------------------------------------------------
    # 7. NOTASI ILMIAH
    # 3 x 10^-8 / 3 × 10^{-8}
    # ---------------------------------------------------------
    text = re.sub(
        r"(\d+(?:[.,]\d+)?)\s*[x×]\s*10\s*([⁻⁺]?\d+)",
        lambda m: f"{m.group(1)} × 10{m.group(2)}",
        text,
        flags=re.IGNORECASE
    )

    # ---------------------------------------------------------
    # 8. SIMBOL RAW YANG SERING MUNCUL DARI AI
    # ---------------------------------------------------------
    raw_symbols = {
        "->": "→",
        "=>": "⇒",
        "<->": "↔",
        "<=": "≤",
        ">=": "≥",
        "!=": "≠",
        "+/-": "±",
        "inf": "∞",
    }

    for old, new in raw_symbols.items():
        text = text.replace(old, new)

    # ---------------------------------------------------------
    # 9. BERSIHKAN BACKSLASH YANG TERSISA
    # Jangan menghapus backslash pada escape yang tidak perlu.
    # ---------------------------------------------------------
    text = re.sub(r"\\([A-Za-z]+)", r"\1", text)

    # ---------------------------------------------------------
    # 10. RAPATKAN SPASI BERLEBIH
    # ---------------------------------------------------------
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()

# ==============================================================================
# 1. TAMPILAN AWAL (GERBANG SISWA & GURU)
# ==============================================================================
if st.session_state.page == "landing":

    st.markdown("<h3 style='text-align: center; font-size: 25px;'>🏆 BINA PRESTASI OMI 2026</h3>", unsafe_allow_html=True)
    st.markdown("<p style='font-size: 12px; text-align: center; opacity: 0.8;'>Pilih Jenjang Pendidikan untuk Memulai Pembinaan Olimpiade</p>", unsafe_allow_html=True)
    st.write("---")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div class="mode-card">
            <h2>🏫 TINGKAT MTs</h2>
            <p>Madrasah Tsanawiyah Al-Irsyad Putri</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Masuk Modul MTs ➔", key="btn_mts", use_container_width=True, type="primary"):
            st.session_state.jenjang = "MTs (Sederajat SMP)"
            st.session_state.page = "select_mapel"
            st.rerun()

    with col2:
        st.markdown("""
        <div class="mode-card">
            <h2>🏛️ TINGKAT MA</h2>
            <p>Madrasah Aliyah Al-Irsyad Putri</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Masuk Modul MA ➔", key="btn_ma", use_container_width=True, type="primary"):
            st.session_state.jenjang = "MA (Sederajat SMA)"
            st.session_state.page = "select_mapel"
            st.rerun()
            
    st.write("---")
    st.markdown("#### 📝 Sesi Quiz GuruMANTAP")
    st.caption("Klik tombol dibawah ini untuk menuju Portal Kuis!")
    
    # Tombol Futuristik Neon Emerald yang Mengarah ke Render
    st.markdown(
        """
        <a href="https://robomantap-intelligence-cbt.onrender.com" target="_blank" style="text-decoration: none;">
            <div style="
                background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                color: #020617;
                padding: 14px 24px;
                border-radius: 12px;
                text-align: center;
                font-weight: 800;
                font-size: 15px;
                letter-spacing: 0.5px;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                margin-top: 8px;
                margin-bottom: 20px;
                cursor: pointer;
            ">
                🚀 BUKA PORTAL KUIS →
            </div>
        </a>
        """,
        unsafe_allow_html=True
    )

    st.write("---")
    st.markdown("#### 🧕🏼 Portal GuruMANTAP")
    st.markdown("""
    <div class="guru-card">
        <h2 style="margin:0; font-size: 20px;"><span class="blinking-dot-red">🔴</span> Live Monitoring & AI Generator</h2>
        <p style="font-size: 10px; opacity:0.8; margin-top:5px;">Pantau skor siswa secara real-time, generate soal, dan integrasi WhatsApp</p>
    </div>
    """, unsafe_allow_html=True)
    if st.button("🔒 Masuk Portal Guru ➔", use_container_width=True):
        st.session_state.page = "guru_login"
        st.rerun()

# ==============================================================================
# 2. LOGIN GURU & DASHBOARD (NEW UPGRADE)
# ==============================================================================
#=========================================================================================================
elif st.session_state.page == "guru_login":
    st.subheader("🔒 Akses Portal GuruMANTAP")

    st.markdown("""
    <div style="background-color: rgba(28, 131, 225, 0.1); border-left: 4px solid #1c83e1; padding: 10px 12px; border-radius: 6px; font-size: 10px; color: var(--text-color); margin-bottom: 15px;">
        ⚠️ Fitur ini dilindungi PIN untuk menjaga kerahasiaan nilai siswa dan soal CBT
    </div>
    """, unsafe_allow_html=True)
    
    pin_input = st.text_input("Masukkan PIN Akses:", type="password", placeholder="Masukkan PIN GuruMANTAP...")
    if st.button("Login", type="primary"):
        if pin_input == "MANTAP2026":
            st.session_state.guru_auth = True
            st.session_state.page = "guru_dashboard"
            st.rerun()
        else:
            st.error("PIN Salah. Silakan coba lagi.")

elif st.session_state.page == "guru_dashboard":
    if not st.session_state.guru_auth:
        st.warning("Akses Ditolak.")
        st.stop()

    st.markdown("<p style='font-size: 27px; font-weight: bold; margin-bottom: 8px;'>🖥️ Dashboard GuruMANTAP</p>", unsafe_allow_html=True)
    tab1, tab2, tab3 = st.tabs(["🔴 Live Monitoring", "✨ Quiz Custom", "⚡ Automation"])
    with tab1:
        st.markdown("<p style='font-size: 18px; font-weight: bold; margin-bottom: 10px;'>Monitoring & Evaluasi Siswa</p>", unsafe_allow_html=True)

        time_filter = st.session_state.get("filter_time", "Hari Ini")
        selected_jenjang_filter = st.session_state.get("filter_jenjang", "Semua Jenjang")
        selected_mapel_filter = st.session_state.get("filter_mapel", "Semua Mapel")
        selected_status_filter = st.session_state.get("filter_status", "Semua Status")
 
        auto_refresh = st.toggle(
            "🔄 Live Now!",
            value=False,
            help="Nyalakan untuk memantau siswa secara real-time!"
        )

        # Indikator Status Auto-Refresh
        if auto_refresh:
            st.markdown(
                '<p style="font-size: 12px; opacity: 0.82;">'
                '<span class="blinking-dot-green">🟢</span> '
                '<b>Live aktif!</b> · memperbarui data secara real time, matikan Live bila Hp/Perangkat terasa Lemot'
                '</p>',
                unsafe_allow_html=True
            )
        else:
            st.caption(
                "⏸️ **Live dimatikan** · tampilan stabil dan nyaman untuk membaca laporan RoboMANTAP."
            )
        
        # Kondisi Dasar: Abaikan status uji coba internal jika ada
        where_clauses = ["status NOT IN ('ARCHIVED', 'TRIAL', 'DRAFT', 'HIDDEN')"]
        
        # Kondisi Tanggal PRESISI (Terkunci Waktu Indonesia Barat / WIB)
        if time_filter == "Hari Ini":
            where_clauses.append(
                "DATE(updated_at) = DATE(NOW() AT TIME ZONE 'Asia/Jakarta')"
            )
        elif time_filter == "Kemarin":
            where_clauses.append(
                "DATE(updated_at) = DATE(NOW() AT TIME ZONE 'Asia/Jakarta') - INTERVAL '1 day'"
            )
        else:
            where_clauses.append(
                "DATE(updated_at) >= DATE(NOW() AT TIME ZONE 'Asia/Jakarta') - INTERVAL '2 days'"
            )
        
        # FIX KRUSIAL: Mapping String Jenjang agar Cocok dengan Database ("MTs" / "MA")
        if selected_jenjang_filter != "Semua Jenjang":
            if "MTs" in selected_jenjang_filter:
                where_clauses.append("(jenjang = 'MTs' OR jenjang LIKE '%MTs%')")
            elif "MA" in selected_jenjang_filter:
                where_clauses.append("(jenjang = 'MA' OR jenjang LIKE '%MA%')")
            else:
                where_clauses.append(f"jenjang = '{selected_jenjang_filter}'")

        # Filter Mapel (Penting agar kuis antar-guru tidak tercampur!)
        if selected_mapel_filter != "Semua Mapel":
            where_clauses.append(f"mapel = '{selected_mapel_filter}'")
        
        # Filter Status
        if selected_status_filter != "Semua Status":
            where_clauses.append(f"status = '{selected_status_filter}'")
        
        where_sql = " AND ".join(where_clauses)

        # Helper Progress & Payload
        def parse_tracking_payload(raw_detail):
            if isinstance(raw_detail, str):
                try:
                    raw_detail = json.loads(raw_detail)
                except Exception:
                    raw_detail = []

            anti_cheat = {}
            user_answers = {}
            quiz_data = []

            if isinstance(raw_detail, dict):
                detail_boolean = raw_detail.get("detail_boolean", [])
                user_answers = raw_detail.get("user_answers", {}) or {}
                quiz_data = raw_detail.get("quiz_data", []) or []
                anti_cheat = raw_detail.get("anti_cheat", {}) or {}
            elif isinstance(raw_detail, list):
                detail_boolean = raw_detail
            else:
                detail_boolean = []

            if not isinstance(detail_boolean, list):
                detail_boolean = []

            if not isinstance(anti_cheat, dict):
                anti_cheat = {}

            return detail_boolean, user_answers, quiz_data, anti_cheat

        def render_progress_bar_html(detail_list, current_index=None):
            if not isinstance(detail_list, list) or len(detail_list) == 0:
                return '<div class="upn-live-foot"><span>Belum ada detail soal.</span></div>'

            total_soal = len(detail_list)
            current_index = int(current_index or 0)
            segments = []

            for i, val in enumerate(detail_list):
                if val is True:
                    cls = "upn-segment upn-segment-correct"
                    state = "Benar"
                elif val is False:
                    cls = "upn-segment upn-segment-wrong"
                    state = "Salah"
                else:
                    cls = "upn-segment upn-segment-empty"
                    state = "Belum dijawab"

                if i == current_index:
                    cls += " upn-segment-current"

                segments.append(
                    f'<span class="{cls}" title="Soal {i + 1}: {state}"></span>'
                )

            return (
                f'<div class="upn-segments" style="--segment-count:{total_soal};">'
                + "".join(segments)
                + "</div>"
            )

        # =========================================================================
        # 3. RENDER CONTENT DASHBOARD
        # =========================================================================
        def render_monitoring_content():
            conn = init_db_connection()
            if not conn:
                st.warning("Menunggu koneksi Database terhubung untuk Live Monitoring...")
                return

            try:
                # Penyusunan Query SQL Berdasarkan Toggle Deduplikasi
                if only_latest:
                    # Query Deduplikasi: Hanya Ambil Sesi Terbaru per Siswa & Mapel + Hitung Total Percobaan
                    query = f"""
                    SELECT DISTINCT ON (LOWER(TRIM(nama_siswa)), mapel)
                        id_sesi, nama_siswa, jenjang, mapel, soal_sekarang, detail_jawaban, nilai_akhir, created_at, updated_at,
                        CASE 
                            WHEN status = 'BERJALAN' AND updated_at < (NOW() AT TIME ZONE 'Asia/Jakarta') - INTERVAL '30 minutes' THEN 'EXPIRED'
                            ELSE status
                        END as status_real,
                        COUNT(*) OVER(PARTITION BY LOWER(TRIM(nama_siswa)), mapel) as total_percobaan
                    FROM sesi_ujian
                    WHERE {where_sql}
                    ORDER BY LOWER(TRIM(nama_siswa)), mapel, updated_at DESC
                    """
                else:
                    # Query Standard: Tampilkan Seluruh Riwayat Sesi Tanpa Filter Unik
                    query = f"""
                    SELECT 
                        id_sesi, nama_siswa, jenjang, mapel, soal_sekarang, detail_jawaban, nilai_akhir, created_at, updated_at,
                        CASE 
                            WHEN status = 'BERJALAN' AND updated_at < (NOW() AT TIME ZONE 'Asia/Jakarta') - INTERVAL '30 minutes' THEN 'EXPIRED'
                            ELSE status
                        END as status_real,
                        1 as total_percobaan
                    FROM sesi_ujian
                    WHERE {where_sql}
                    ORDER BY updated_at DESC
                    """

                df = conn.query(query, ttl=0)
                # Tambahkan 2 baris ini di baris 595 agar kuis terbaru SELALU melompat ke paling atas:
                if not df.empty:
                    df = df.sort_values(by='updated_at', ascending=False)         
                # Filter Status di sisi Pandas jika user memilih status tertentu
                if not df.empty and selected_status_filter != "Semua Status":
                    df = df[df['status_real'] == selected_status_filter]

                if df.empty:
                    st.info(f"🚫 Tidak ada data pengerjaan siswa yang sesuai! Silahkan seting Kontrol Panel & Filter di Sidebar (click pojok kiri atas)")
                    return
                # =========================================================================
                # MINI KPI CARDS ELEGAN (LAYOUT 3 + 2 SIMETRIS)
                # =========================================================================
                val_total = len(df['nama_siswa'].unique()) if only_latest else len(df)
                val_aktif = len(df[df['status_real'] == 'BERJALAN'])
                val_selesai = len(df[df['status_real'] == 'SELESAI'])
                
                # Logika Pemisah Pintar: Cek kata '(Custom)' ATAU jumlah kotak soal != 10
                def check_is_custom(row):
                    mapel_str = str(row['mapel'])
                    if "custom" in mapel_str.lower() or "kuis" in mapel_str.lower() or "quiz" in mapel_str.lower():
                        return True
                    try:
                        detail = row['detail_jawaban']
                        if isinstance(detail, str):
                            detail = json.loads(detail)
                        if isinstance(detail, list) and len(detail) > 0 and len(detail) != 10:
                            return True
                    except Exception:
                        pass
                    return False
                
                is_custom_mask = df.apply(check_is_custom, axis=1)
                df_custom = df[is_custom_mask]
                df_omi = df[~is_custom_mask]
                
                val_rata_omi = f"{df_omi['nilai_akhir'].mean():.1f}" if not df_omi.empty else "0.0"
                val_rata_custom = f"{df_custom['nilai_akhir'].mean():.1f}" if not df_custom.empty else "0.0"
                
                st.markdown(f"""
                <style>
                .kpi-grid-top {{
                    display: grid;
                    grid-template-columns: repeat(3, 1fr);
                    gap: 5px;
                    margin-bottom: 10px;
                }}
                .kpi-grid-bottom {{
                    display: grid;
                    grid-template-columns: repeat(2, 1fr);
                    gap: 10px;
                    margin-bottom: 15px;
                }}
                @media (max-width: 350px) {{
                    .kpi-grid-top {{
                        grid-template-columns: repeat(2, 1fr);
                        gap: 4px;
                    }}
                    .kpi-grid-bottom {{
                        grid-template-columns: repeat(2, 1fr);
                        gap: 8px;
                    }}
                }}
                .kpi-card {{
                    background: linear-gradient(135deg, rgba(6, 78, 59, 0.4) 0%, rgba(2, 44, 34, 0.7) 100%);
                    border: 1px solid rgba(5, 150, 105, 0.35);
                    border-radius: 10px;
                    padding: 10px 12px;
                    text-align: center;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.15);
                }}
                .kpi-title {{
                    font-size: 11px;
                    color: #a7f3d0;
                    font-weight: 600;
                    text-transform: uppercase;
                    letter-spacing: 0.3px;
                    margin-bottom: 4px;
                    white-space: nowrap;
                }}
                .kpi-value {{
                    font-size: 19px;
                    font-weight: 800;
                    color: #ffffff;
                    line-height: 1.2;
                }}
                </style>
                
                <!-- BARIS 1: 3 KOLOM METRIK AKTIVITAS -->
                <div class="kpi-grid-top">
                    <div class="kpi-card">
                        <div class="kpi-title">👥 Total Siswa</div>
                        <div class="kpi-value">{val_total}</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-title">⚡ Siswa Aktif</div>
                        <div class="kpi-value" style="color: #34d399;">{val_aktif}</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-title">✅ Sesi Selesai</div>
                        <div class="kpi-value" style="color: #60a5fa;">{val_selesai}</div>
                    </div>
                </div>
                
                <!-- BARIS 2: 2 KOLOM METRIK PERFORMA -->
                <div class="kpi-grid-bottom">
                    <div class="kpi-card">
                        <div class="kpi-title">🎯 Rata-rata OMI</div>
                        <div class="kpi-value" style="color: #f59e0b;">{val_rata_omi} <span style="font-size: 11px; color: #9ca3af;">/ 40</span></div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-title">📊 Rata-rata Quiz</div>
                        <div class="kpi-value" style="color: #10b981;">{val_rata_custom} <span style="font-size: 11px; color: #9ca3af;">/ 100</span></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                               
                if st.button("🚀 Generate Rekapitulasi Nilai & Laporan (.docx)", type="primary", use_container_width=True):
                    with st.spinner("RoboMANTAP sedang merender dokumen eksekutif..."):
                        data_siswa_list = df.to_dict('records')
                        cfg = {
                            "mapel": selected_mapel_filter if selected_mapel_filter != "Semua Mapel" else "Kuis Terintegrasi",
                            "jenjang": selected_jenjang_filter,
                            "kelas": "Semua Kelas"
                        }
                
                        # 1. Panggil Summary Kolektif AI Kelas
                        collective_summary = call_gemini_with_rotation(
                            f"Buatkan ringkasan diagnostik kelas secara singkat dan profesional untuk mata pelajaran {cfg['mapel']} berdasarkan performa {len(data_siswa_list)} siswa.",
                            is_json=False
                        )
                
                        # 2. Build Docx Bytes Kedinasan
                        docx_bytes = generate_corporate_executive_docx_report(
                            config=cfg,
                            data_siswa=data_siswa_list,
                            collective_ai_summary=collective_summary
                        )
                
                        st.session_state["docx_report_bytes"] = docx_bytes
                        st.success("✅ Dokumen Laporan Eksekutif (.docx) Berhasil Dibuat!")
                
                if "docx_report_bytes" in st.session_state:
                    st.download_button(
                        label="📥 Unduh Dokumen Rekap (.docx)",
                        data=st.session_state["docx_report_bytes"],
                        file_name=f"Laporan_CBT_RoboMANTAP_{selected_mapel_filter}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True
                    )

                # =========================================================================
                # 5. LIVE TRACKING — UPN MODERN MONITORING
                # =========================================================================
                st.write("---")
                def _row_duration(row):
                    try:
                        waktu_mulai_raw = (
                            row["created_at"]
                            if ("created_at" in row and pd.notna(row["created_at"]))
                            else row["updated_at"]
                        )

                        if isinstance(waktu_mulai_raw, str):
                            waktu_mulai_dt = datetime.strptime(
                                str(waktu_mulai_raw)[:19], "%Y-%m-%d %H:%M:%S"
                            )
                        else:
                            waktu_mulai_dt = pd.to_datetime(waktu_mulai_raw).to_pydatetime()

                        waktu_mulai_str = waktu_mulai_dt.strftime("%H:%M WIB")

                        if row["status_real"] == "BERJALAN":
                            waktu_sekarang_wib = datetime.utcnow() + timedelta(hours=7)
                            selisih_detik = max(
                                0,
                                int((waktu_sekarang_wib - waktu_mulai_dt).total_seconds())
                            )
                        else:
                            waktu_selesai_raw = row["updated_at"]
                            if isinstance(waktu_selesai_raw, str):
                                waktu_selesai_dt = datetime.strptime(
                                    str(waktu_selesai_raw)[:19], "%Y-%m-%d %H:%M:%S"
                                )
                            else:
                                waktu_selesai_dt = pd.to_datetime(waktu_selesai_raw).to_pydatetime()

                            selisih_detik = max(
                                0,
                                int((waktu_selesai_dt - waktu_mulai_dt).total_seconds())
                            )

                        menit = selisih_detik // 60
                        detik = selisih_detik % 60

                        if row["status_real"] == "BERJALAN":
                            if menit < 60:
                                durasi = f"Berjalan · {menit}m {detik:02d}s"
                            else:
                                durasi = f"Berjalan · {menit // 60}j {menit % 60}m"
                        elif row["status_real"] == "EXPIRED":
                            durasi = (
                                f"Terputus · {menit}m"
                                if menit > 0
                                else "Terputus · < 1m"
                            )
                        else:
                            durasi = (
                                f"Selesai · {menit}m"
                                if menit > 0
                                else "Selesai · < 1m"
                            )

                        return waktu_mulai_str, durasi
                    except Exception:
                        return "--:-- WIB", "Durasi tidak tersedia"

                tracking_rows = []
                for _, row in df.iterrows():
                    _, _, _, anti_meta = parse_tracking_payload(row["detail_jawaban"])
                    count = max(0, int(anti_meta.get("violation_count", 0) or 0))
                    detected = bool(anti_meta.get("detected", False))

                    if detected:
                        priority = 1
                    elif row["status_real"] == "BERJALAN":
                        priority = 0
                    elif row["status_real"] == "EXPIRED":
                        priority = 3
                    else:
                        priority = 2

                    tracking_rows.append((priority, count, row["updated_at"], row))

                tracking_rows.sort(
                    key=lambda item: (
                        item[0],
                        -item[1],
                        str(item[2]),
                    )
                )

                active_count = sum(
                    1 for _, _, _, r in tracking_rows if r["status_real"] == "BERJALAN"
                )
                cheat_count = sum(
                    1
                    for _, _, _, r in tracking_rows
                    if parse_tracking_payload(r["detail_jawaban"])[3].get("detected", False)
                )
                warning_count = sum(
                    1
                    for _, _, _, r in tracking_rows
                    if (
                        parse_tracking_payload(r["detail_jawaban"])[3].get("violation_count", 0)
                        and not parse_tracking_payload(r["detail_jawaban"])[3].get("detected", False)
                    )
                )

                st.markdown(
                    f"""
                    <div class="upn-live-hero">
                        <div class="upn-live-hero-left">
                            <span class="upn-live-orb"></span>
                            <div>
                                <div class="upn-live-eyebrow">UPN · CBT-Intelligence</div>
                                <div class="upn-live-title">Live Tracking Pengerjaan</div>
                                <div class="upn-live-subtitle">
                                    Pantau progress siswa secara real-time!
                                </div>
                            </div>
                        </div>
                        <div class="upn-live-count">● {active_count} aktif</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                status_chips = [
                    f"<span>⚠️ {warning_count} peringatan</span>",
                    f"<span>🚨 {cheat_count} dihentikan</span>",
                ]

                st.markdown(
                    '<div class="upn-live-foot" style="margin:0 0 8px;">'
                    + "".join(status_chips)
                    + "</div>",
                    unsafe_allow_html=True,
                )

                for _, _, _, row in tracking_rows:
                    safe_nama = html.escape(str(row["nama_siswa"]).strip().replace("*", ""))
                    mapel_label = html.escape(str(row["mapel"]))
                    jenjang_label = html.escape(str(row["jenjang"] or "")[:10])

                    detail_boolean, user_answers, quiz_data, anti_meta = parse_tracking_payload(
                        row["detail_jawaban"]
                    )

                    total_soal = len(detail_boolean)
                    if not total_soal:
                        total_soal = len(quiz_data) if quiz_data else 0

                    if total_soal and len(detail_boolean) < total_soal:
                        detail_boolean = detail_boolean + [None] * (
                            total_soal - len(detail_boolean)
                        )

                    score = int(row["nilai_akhir"] or 0)
                    is_custom_row = check_is_custom(row)
                    score_max = 100 if is_custom_row else 40

                    current_q = int(row["soal_sekarang"] or 0)
                    if total_soal > 0:
                        current_q = max(1, min(current_q, total_soal))
                        current_idx = current_q - 1
                    else:
                        current_q = 0
                        current_idx = None

                    violation_count = max(
                        0,
                        int(anti_meta.get("violation_count", 0) or 0)
                    )
                    anti_detected = bool(anti_meta.get("detected", False))
                    anti_reason = html.escape(
                        str(anti_meta.get("reason", "Pindah tab") or "Pindah tab")
                    )

                    if anti_detected:
                        status_badge = "🚨 DIHENTIKAN · KECURANGAN"
                        status_class = "upn-tag-cheat"
                        alert_html = (
                            f'<div class="upn-live-alert upn-alert-cheat">'
                            f'⚠️ {violation_count}× {anti_reason} · Ujian dihentikan otomatis.</div>'
                        )
                    elif row["status_real"] == "EXPIRED":
                        status_badge = "⏸ TERPUTUS"
                        status_class = "upn-tag-off"
                        alert_html = (
                            '<div class="upn-live-alert upn-alert-off">'
                            'Sesi tidak menerima heartbeat dalam batas waktu monitoring.</div>'
                        )
                    elif violation_count > 0:
                        status_badge = (
                            f"⚠️ SELESAI · {violation_count}/3 PERINGATAN"
                            if row["status_real"] == "SELESAI"
                            else f"⚠️ PERINGATAN {violation_count}"
                        )
                        status_class = "upn-tag-warn"
                        finish_note = (
                            " · ujian selesai"
                            if row["status_real"] == "SELESAI"
                            else ""
                        )
                        alert_html = (
                            f'<div class="upn-live-alert upn-alert-warn">'
                            f'Pelanggaran tercatat: {violation_count}/3 · {anti_reason}'
                            f'{finish_note}.</div>'
                        )
                    elif row["status_real"] == "BERJALAN":
                        status_badge = "🟢 BERJALAN"
                        status_class = "upn-tag-live"
                        alert_html = ""
                    else:
                        status_badge = "✅ SELESAI"
                        status_class = "upn-tag-done"
                        alert_html = ""

                    waktu_mulai_str, durasi_str = _row_duration(row)

                    percobaan_text = (
                        f"Percobaan ke-{int(row.get('total_percobaan', 1))}"
                        if only_latest
                        else "Riwayat sesi"
                    )

                    detail_bar = render_progress_bar_html(
                        detail_boolean,
                        current_index=current_idx
                    )

                    b_cnt = sum(1 for x in detail_boolean if x is True)
                    s_cnt = sum(1 for x in detail_boolean if x is False)
                    k_cnt = sum(1 for x in detail_boolean if x is None)

                    progress_label = (
                        f"Soal {current_q} / {total_soal}"
                        if total_soal
                        else "Belum dimulai"
                    )

                    st.html(
                        f"""
                        <div class="upn-live-card">
                            <div class="upn-live-head">
                                <div style="min-width:0;flex:1;">
                                    <div class="upn-live-name">
                                        {safe_nama}
                                        <span class="upn-live-tag {status_class}">{status_badge}</span>
                                    </div>
                                    <div class="upn-live-sub">
                                        {mapel_label} · {jenjang_label} · {html.escape(percobaan_text)}
                                    </div>
                                </div>
                                <div class="upn-live-score">
                                    <small>SKOR</small>
                                    <strong>{score}</strong>
                                    <div style="font-size:8px;color:#64748b;margin-top:2px;">/ {score_max}</div>
                                </div>
                            </div>

                            <div class="upn-live-meta">
                                <span class="upn-live-chip">🕒 Mulai {html.escape(waktu_mulai_str)}</span>
                                <span class="upn-live-chip">⏱ {html.escape(durasi_str)}</span>
                                <span class="upn-live-chip">🧩 {total_soal} soal</span>
                            </div>

                            {alert_html}

                            <div class="upn-progress-line">
                                <span>Progress pengerjaan</span>
                                <b>{progress_label}</b>
                            </div>

                            {detail_bar}

                            <div class="upn-live-foot">
                                <span>✅ {b_cnt} benar</span>
                                <span>❌ {s_cnt} salah</span>
                                <span>◻ {k_cnt} belum</span>
                            </div>
                        </div>
                        """,
                    )

                    action_col, spacer_col = st.columns([1.45, 5.55])
                    with action_col:
                        with st.popover("📊 Analisis"):
                            st.markdown(f"**Analisis Siswa:** {safe_nama}")
                            st.caption(
                                f"Mapel: {row['mapel']} | Sesi Ke-{row.get('total_percobaan', 1)}"
                            )

                            has_data = (
                                len(detail_boolean) > 0
                                or row.get("status") == "SELESAI"
                                or row.get("nilai_akhir", 0) > 0
                            )

                            if has_data:
                                total_soal_sis = (
                                    len(detail_boolean)
                                    if len(detail_boolean) > 0
                                    else 5
                                )

                                if is_custom_row:
                                    pct = (
                                        (b_cnt / total_soal_sis) * 100
                                        if total_soal_sis > 0
                                        else 0
                                    )
                                else:
                                    skor_omi = (b_cnt * 4) - (s_cnt * 1)
                                    pct = max(0, (skor_omi / 40) * 100)

                                # Display Kartu Ringkas
                                st.markdown(f"""
                                <div style="display: flex; gap: 6px; margin: 10px 0;">
                                    <div style="flex: 1; background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; padding: 6px; text-align: center;">
                                        <div style="font-size: 10px; color: #34d399; font-weight: 600;">Benar</div>
                                        <div style="font-size: 16px; font-weight: 800;">{b_cnt}</div>
                                    </div>
                                    <div style="flex: 1; background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; padding: 6px; text-align: center;">
                                        <div style="font-size: 10px; color: #f87171; font-weight: 600;">Salah</div>
                                        <div style="font-size: 16px; font-weight: 800;">{s_cnt}</div>
                                    </div>
                                    <div style="flex: 1; background: rgba(156, 163, 175, 0.12); border: 1px solid rgba(156, 163, 175, 0.3); border-radius: 8px; padding: 6px; text-align: center;">
                                        <div style="font-size: 10px; color: #9ca3af; font-weight: 600;">Kosong</div>
                                        <div style="font-size: 16px; font-weight: 800;">{k_cnt}</div>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)

                                if anti_detected:
                                    st.error(
                                        f"🚨 Sesi dihentikan karena kecurangan: "
                                        f"{violation_count}× {anti_meta.get('reason', 'Pindah tab')}"
                                    )
                                elif violation_count > 0:
                                    st.warning(
                                        f"⚠️ Peringatan kecurangan: "
                                        f"{violation_count}/3 · {anti_meta.get('reason', 'Pindah tab')}"
                                    )

                                if pct >= 80:
                                    st.success(f"🌟 Kesiapan tinggi · {pct:.0f}%")
                                elif pct >= 40:
                                    st.warning(f"⚠️ Berkembang · {pct:.0f}%")
                                else:
                                    st.info(f"🌱 Perlu intervensi · {pct:.0f}%")
                            else:
                                st.info("Pengerjaan belum dimulai.")

                            nama_depan = safe_nama.split()[0] if safe_nama else "Santri"
                            st.markdown(
                                f"**🧕🏼 Cek Diagnosis Pedagogis {nama_depan}**"
                            )

                            if st.button(
                                "⚡ Hasilkan Analisis RoboMANTAP Preskriptif",
                                key=f"btn_ai_{row['id_sesi']}",
                                use_container_width=True,
                            ):
                                with st.spinner(
                                    "RoboMANTAP sedang menganalisis miskonsepsi kognitif siswa..."
                                ):
                                    laporan_ai = generate_individual_analysis_ai(
                                        nama_siswa=row["nama_siswa"],
                                        mapel=row["mapel"],
                                        jenjang=row["jenjang"],
                                        nilai=row["nilai_akhir"],
                                        detail_jawaban_list=detail_boolean,
                                        quiz_data=quiz_data,
                                        user_answers=user_answers,
                                    )

                                    if laporan_ai:
                                        st.session_state[f"ai_report_{row['id_sesi']}"] = laporan_ai
                                    else:
                                        st.error(
                                            "⚠️ Gagal menghasilkan analisis AI. Coba klik lagi."
                                        )

                            cached_report = st.session_state.get(
                                f"ai_report_{row['id_sesi']}"
                            )
                            if cached_report:
                                st.markdown("---")
                                st.markdown(cached_report)

                                st.download_button(
                                    label="📋 Unduh Ringkasan Laporan (.txt)",
                                    data=cached_report,
                                    file_name=(
                                        f"Diagnosis_AI_"
                                        f"{str(row['nama_siswa']).replace(' ', '_')}.txt"
                                    ),
                                    mime="text/plain",
                                    key=f"dl_ai_{row['id_sesi']}",
                                )

                            st.markdown("---")
                            if st.button(
                                "🗑️ Hapus Sesi Ini",
                                key=f"del_sesi_{row['id_sesi']}",
                                type="secondary",
                                use_container_width=True,
                            ):
                                conn2 = init_db_connection()
                                if conn2:
                                    try:
                                        with conn2.session as s:
                                            s.execute(
                                                text("""
                                                    UPDATE sesi_ujian
                                                    SET status = 'TRIAL'
                                                    WHERE id_sesi = :sid
                                                """),
                                                {"sid": row["id_sesi"]},
                                            )
                                            s.commit()

                                        st.success("Sesi percobaan berhasil disembunyikan dari monitoring.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Gagal menghapus sesi: {e}")

                    st.markdown('<div class="upn-live-divider"></div>', unsafe_allow_html=True)

            except Exception as e:
                st.error(f"Gagal mengambil data dari database: {e}")


        # Fragment Execution Logic
        if auto_refresh:
            @st.fragment(run_every="1s")
            def active_live_view():
                render_monitoring_content()
            active_live_view()
        else:
            render_monitoring_content()


    with tab2:
        custom_cfg = st.session_state.get("custom_quiz_config", {})
        custom_quiz = st.session_state.get("custom_quiz_draft", [])
        material_code = st.session_state.get("material_bundle_code", "")
        material_pack = st.session_state.get("material_bundle", None)

        st.markdown("""
        <div class="premium-hero">
            <div class="premium-kicker">UPN • QUIZ-Intelligence</div>
            <div class="premium-title">🧩 RoboMANTAP <span>Quiz Custom</span></div>
            <div class="premium-subtitle">Susun soal presisi dari topik manual atau langsung dari materi GuruMANTAP yang dilampirkan.</div>
            <div class="premium-pills">
                <span>AI Grounded</span><span>QA Validator</span><span>Mobile Ready</span><span>Teacher First</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="source-warning">
            <div class="source-warning-title">📌 PENTING!</div>
            Mohon Ustadzah untuk ketik di kolom <b>Materi Utama</b> dengan teks <code>materi dilampirkan</code>
            agar RoboMANTAP menggunakan file yang sudah di-drop sebagai sumber utama pembuatan soal dengan lebih akurat dan presisi.
        </div>
        """, unsafe_allow_html=True)

        st.markdown("#### 📚 Material Hub • File Drop Guru")
        st.caption("Satu paket materi dapat berisi PDF, PPTX, DOCX, PNG, JPG, atau WEBP. Materi yang sama dapat dipakai kembali untuk Quiz, LKPD, dan Media Ajar.")

        upload_col, status_col = st.columns([1.7, 1], gap="large")
        with upload_col:
            material_files = st.file_uploader(
                "Drag & drop materi guru di sini",
                type=["pdf", "pptx", "ppt", "docx", "png", "jpg", "jpeg", "webp"],
                accept_multiple_files=True,
                key="guru_material_drop",
                help="Dapat menambahkan beberapa file sekaligus menjadi satu File Drop.",
            )
            if material_files:
                file_rows = "".join(
                    f"<div class='file-row'><span>📄 {html.escape(f.name)}</span><span>{len(f.getvalue())/1024:.0f} KB</span></div>"
                    for f in material_files
                )
                st.markdown(f"<div class='file-list'>{file_rows}</div>", unsafe_allow_html=True)

        with status_col:
            current_code_html = (
                f"<div class='hub-code'><div class='hub-code-label'>FILE DROP AKTIF</div><div class='hub-code-value'>{html.escape(material_code)}</div><div class='hub-code-note'>{material_pack.get('file_count',0) if isinstance(material_pack, dict) else 0} file tersimpan untuk sesi ini.</div></div>"
                if material_code else
                "<div class='hub-empty'><div class='hub-code-label'>MATERIAL HUB</div><div class='hub-empty-title'>Belum ada materi aktif</div><div class='hub-code-note'>Drop file → simpan → gunakan kode yang sama di Quiz / LKPD / PPT.</div></div>"
            )
            st.markdown(current_code_html, unsafe_allow_html=True)

        save_material_col, recall_col = st.columns(2)
        with save_material_col:
            if st.button("💾 SIMPAN FILE DROP", type="primary", use_container_width=True, key="btn_save_material_hub"):
                if not material_files:
                    st.warning("Tambahkan minimal satu file terlebih dahulu.")
                else:
                    with st.spinner("RoboMANTAP membaca file, tabel, slide, gambar, dan membangun Source Knowledge Pack..."):
                        built_pack = build_material_knowledge_pack(material_files)
                    if not built_pack or not built_pack.get("files"):
                        st.error("File belum berhasil dibaca. Cek format atau coba upload ulang.")
                    else:
                        new_code = f"MD-{uuid.uuid4().hex[:6].upper()}"
                        meta_cfg = {
                            "source": "teacher_file_drop",
                            "file_count": built_pack.get("file_count", 0),
                            "created_by": "RoboMANTAP Streamlit",
                        }
                        db_ok = save_material_bundle_to_db(new_code, built_pack, meta_cfg)
                        st.session_state.material_bundle_code = new_code
                        st.session_state.material_bundle = built_pack | {"bundle_code": new_code, "config": meta_cfg}
                        if db_ok:
                            st.success(f"✅ Materi berhasil disimpan. File Drop: **{new_code}**")
                        else:
                            st.warning(f"✅ Materi berhasil dibaca untuk sesi ini. Kode aktif: **{new_code}** (penyimpanan database belum terhubung).")
                        st.rerun()
        with recall_col:
            recall_input = st.text_input("🔑 Ambil File Drop", value=material_code, placeholder="Contoh: MD-7K29FA", key="material_recall_code")
            if st.button("↻ MUAT FILE DROP", use_container_width=True, key="btn_recall_material_hub"):
                code = recall_input.strip().upper()
                recalled = get_material_bundle_from_db(code) if code else None
                if recalled:
                    st.session_state.material_bundle_code = code
                    st.session_state.material_bundle = recalled
                    st.success(f"✅ File Drop **{code}** aktif kembali.")
                    st.rerun()
                else:
                    st.error("Kode File Drop tidak ditemukan di Material Hub.")

        st.markdown("---")
        st.markdown("#### ⚙️ Konfigurasi Quiz Custom")

        with st.form("robomantap_quiz_custom_form", clear_on_submit=False):
            cqa, cqb = st.columns(2, gap="large")
            with cqa:
                custom_mapel = st.text_input(
                    "📚 Mata Pelajaran",
                    value=custom_cfg.get("mapel", "Matematika"),
                    placeholder="Contoh: Fisika, Bahasa Arab, Agama...",
                )
                custom_jenjang = st.selectbox(
                    "🏫 Jenjang",
                    ["MTs", "MA"],
                    index=["MTs", "MA"].index(custom_cfg.get("jenjang", "MA")),
                )
                custom_kelas = st.text_input(
                    "🎓 Kelas / Tingkat",
                    value=custom_cfg.get("kelas", "X MA"),
                    placeholder="Contoh: VIII MTs / XI MA",
                )
                custom_materi = st.text_input(
                    "📖 Materi Utama",
                    value=custom_cfg.get("materi", ""),
                    placeholder="Ketik materi topik, atau tepat: materi dilampirkan",
                    help="Gunakan 'materi dilampirkan' untuk menjadikan File Drop sebagai sumber utama.",
                )
                custom_submateri = st.text_input(
                    "🧠 Submateri (opsional)",
                    value=custom_cfg.get("submateri", ""),
                    placeholder="Contoh: Persamaan logaritma",
                )

            with cqb:
                custom_jumlah = st.number_input(
                    "🔢 Jumlah Soal (Max 50 Soal)",
                    min_value=1,
                    max_value=50,
                    value=int(custom_cfg.get("jumlah_soal", 25)),
                    step=1,
                )
                difficulty_options = ["Dasar", "Menengah", "Sulit", "HOTS", "Olimpiade"]
                custom_kesulitan = st.selectbox(
                    "🎯 Tingkat Kesulitan",
                    difficulty_options,
                    index=difficulty_options.index(custom_cfg.get("kesulitan", "HOTS")),
                )
                type_options = ["Pilihan Ganda", "HOTS", "Analitis", "Numerik", "Konseptual", "Campuran"]
                custom_tipe = st.selectbox(
                    "🧩 Gaya Soal",
                    type_options,
                    index=type_options.index(custom_cfg.get("tipe_soal", "Campuran")),
                )
                lang_options = ["Bahasa Indonesia", "Bahasa Arab", "Indonesia + Arab", "English"]
                custom_bahasa = st.selectbox(
                    "🌐 Bahasa",
                    lang_options,
                    index=lang_options.index(custom_cfg.get("bahasa", "Bahasa Indonesia")),
                )
                context_options = [
                    "Standar Sekolah", "Kehidupan Sehari-hari", "Keislaman", "Lingkungan", "Teknologi", "OMI / Olimpiade", "Campuran",
                ]
                custom_konteks = st.selectbox(
                    "🌍 Konteks",
                    context_options,
                    index=context_options.index(custom_cfg.get("konteks", "Standar Sekolah")),
                )

            option_rule = "A–D • 4 pilihan" if option_count_for_jenjang(custom_jenjang) == 4 else "A–E • 5 pilihan"
            st.info(f"🎯 **Aturan opsi {custom_jenjang}: {option_rule}.** RoboMANTAP akan memvalidasi jumlah opsi kembali sebelum kuis diterbitkan.")

            st.markdown("##### ⏱️ Durasi Pengerjaan Kuis")
            t1, t2, t3 = st.columns(3)
            with t1:
                timer_h = st.number_input("Jam", min_value=0, max_value=23, value=int(custom_cfg.get("timer_h", 0)))
            with t2:
                timer_m = st.number_input("Menit", min_value=0, max_value=59, value=int(custom_cfg.get("timer_m", 30)))
            with t3:
                timer_s = st.number_input("Detik", min_value=0, max_value=59, value=int(custom_cfg.get("timer_s", 0)))

            timer_total = int(timer_h) * 3600 + int(timer_m) * 60 + int(timer_s)
            timer_label = "Tanpa batas waktu" if timer_total <= 0 else str(timedelta(seconds=timer_total))
            st.caption(f"⏳ Durasi sesi: **{timer_label}**")

            st.markdown("##### 📅 Masa Aktif Kuis")
            st.caption("Atur jam buka dan jam tutup kuis dalam WIB.")
            now_wib_time = (datetime.utcnow() + timedelta(hours=7)).time()
            default_end_time = (datetime.utcnow() + timedelta(hours=9)).time()
            col_act1, col_act2 = st.columns(2)
            with col_act1:
                time_start = st.time_input("Jam Buka", value=custom_cfg.get("time_start_val", now_wib_time), key="input_time_start")
            with col_act2:
                time_end = st.time_input("Jam Tutup", value=custom_cfg.get("time_end_val", default_end_time), key="input_time_end")
            st.info(f"📌 **Masa Aktif:** {time_start.strftime('%H:%M')} → {time_end.strftime('%H:%M')} WIB")

            submitted = st.form_submit_button(
                "✨ GENERATE QUIZ CUSTOM • AI + SOURCE QA",
                type="primary",
                use_container_width=True,
            )

        if submitted:
            now_wib = datetime.utcnow() + timedelta(hours=7)
            dt_start = datetime.combine(now_wib.date(), time_start)
            dt_end = datetime.combine(now_wib.date(), time_end)
            if dt_end <= dt_start:
                dt_end += timedelta(days=1)

            material_triggered = normalize_material_trigger(custom_materi)
            source_pack_for_quiz = None
            if material_triggered:
                source_pack_for_quiz = st.session_state.get("material_bundle")
                source_code = st.session_state.get("material_bundle_code", "")
                if not source_pack_for_quiz and source_code:
                    source_pack_for_quiz = get_material_bundle_from_db(source_code)
                    if source_pack_for_quiz:
                        st.session_state.material_bundle = source_pack_for_quiz
                if not source_pack_for_quiz:
                    st.error("⚠️ Materi ditandai 'materi dilampirkan', tetapi belum ada File Drop aktif. Upload + Simpan materi terlebih dahulu.")

            if not custom_mapel.strip():
                st.error("⚠️ Mata pelajaran wajib diisi")
            elif not custom_materi.strip():
                st.error("⚠️ Materi utama wajib diisi")
            elif material_triggered and not source_pack_for_quiz:
                pass
            else:
                if timer_total == 0:
                    st.info("⏱️ Kuis dibuat tanpa batas waktu pengerjaan.")
                source_label = "File Drop aktif" if material_triggered else "Topik manual"
                with st.spinner(f"RoboMANTAP sedang merancang {custom_jumlah} soal • {source_label} • AI Validator aktif..."):
                    generated = generate_custom_quiz_ai(
                        mapel=custom_mapel.strip(),
                        jenjang=custom_jenjang,
                        kelas=custom_kelas.strip(),
                        materi=custom_materi.strip(),
                        submateri=custom_submateri.strip(),
                        jumlah_soal=int(custom_jumlah),
                        kesulitan=custom_kesulitan,
                        tipe_soal=custom_tipe,
                        bahasa=custom_bahasa,
                        konteks=custom_konteks,
                        timer_seconds=timer_total,
                        source_pack=source_pack_for_quiz,
                    )

                if generated:
                    st.session_state.custom_quiz_draft = generated
                    st.session_state.custom_quiz_config = {
                        "mapel": custom_mapel.strip(),
                        "jenjang": custom_jenjang,
                        "kelas": custom_kelas.strip(),
                        "materi": custom_materi.strip(),
                        "submateri": custom_submateri.strip(),
                        "jumlah_soal": int(custom_jumlah),
                        "kesulitan": custom_kesulitan,
                        "tipe_soal": custom_tipe,
                        "bahasa": custom_bahasa,
                        "konteks": custom_konteks,
                        "timer_h": int(timer_h),
                        "timer_m": int(timer_m),
                        "timer_s": int(timer_s),
                        "timer_seconds": timer_total,
                        "active_from": dt_start.isoformat(),
                        "active_until": dt_end.isoformat(),
                        "time_start_str": time_start.strftime('%H:%M'),
                        "time_end_str": time_end.strftime('%H:%M'),
                        "material_bundle_code": st.session_state.get("material_bundle_code", "") if material_triggered else "",
                        "source_mode": "teacher_material" if material_triggered else "manual_topic",
                        "option_count": option_count_for_jenjang(custom_jenjang),
                        "option_labels": list(option_labels_for_jenjang(custom_jenjang)),
                    }
                    custom_quiz = generated
                    custom_cfg = st.session_state.custom_quiz_config
                    st.success(f"✅ {len(generated)} soal siap. Draft sudah melewati lapisan validasi AI.")
                else:
                    st.error("❌ RoboMANTAP belum berhasil menghasilkan paket soal valid. Coba ulangi atau perjelas materi.")

        if custom_quiz:
            st.markdown("---")
            source_mode = custom_cfg.get("source_mode", "manual_topic")
            source_chip = (
                f"<span class='chip chip-green'>📚 Source Grounding • {html.escape(custom_cfg.get('material_bundle_code','-'))}</span>"
                if source_mode == "teacher_material" else
                "<span class='chip chip-blue'>🧠 Topic Architect • manual</span>"
            )
            st.markdown(f"""
            <div class="preview-hero">
                <div><div class="preview-label">QUIZ PREVIEW</div><div class="preview-title">{html.escape(custom_cfg.get('mapel','Kuis'))}</div></div>
                <div class="preview-meta">{source_chip}<span class='chip chip-purple'>{len(custom_quiz)} soal</span><span class='chip chip-blue'>Opsi {"A-D" if option_count_for_jenjang(custom_cfg.get("jenjang", "MTs")) == 4 else "A-E"}</span><span class='chip chip-gold'>{html.escape(custom_cfg.get('kesulitan','-'))}</span></div>
            </div>
            """, unsafe_allow_html=True)

            total_q = len(custom_quiz)
            for q_idx, cq in enumerate(custom_quiz, start=1):
                with st.expander(
                    f"{q_idx:02d} • {clean_preview_math_scientific(str(cq.get('question', 'Soal')))[:88]}",
                    expanded=(q_idx == 1)
                ):
                    st.markdown(f"**Soal {q_idx}**")
                    st.markdown(
                        clean_preview_math_scientific(
                            cq.get("question", "Soal")
                        )
                    )

                    # ============================================================
                    # OPSI JAWABAN — CLEANER MATEMATIKA / ILMIAH
                    # ============================================================
                    opt_cols = st.columns(2)
                    
                    for opt_idx, option in enumerate(cq.get("options", [])):
                    
                        # Ambil teks opsi
                        raw_option = str(option).strip()
                    
                        # Jika format AI: "A. jawaban..."
                        if "." in raw_option:
                            option_parts = raw_option.split(".", 1)
                            option_label = option_parts[0].strip()
                            option_text = option_parts[1].strip()
                        else:
                            option_label = chr(65 + opt_idx)
                            option_text = raw_option
                    
                        # --------------------------------------------------------
                        # CLEANER HARUS DILAKUKAN SEBELUM html.escape()
                        # --------------------------------------------------------
                        option_text = clean_preview_math_scientific(option_text)
                    
                        with opt_cols[opt_idx % 2]:
                            st.markdown(
                                f"""
                                <div class="answer-card">
                                    <b>{html.escape(option_label)}</b>
                                    {html.escape(option_text)}
                                </div>
                                """,
                                unsafe_allow_html=True
                            )


                            
                    st.success(f"Kunci terencana: **{cq.get('correct_answer','-')}**")
                    if cq.get("source_locator"):
                        st.caption(f"🔎 Grounded source: {cq.get('source_locator')}")
                    with st.expander("Lihat Solution Basis"):
                        solution_basis = cq.get(
                            "solution_basis",
                            "Belum tersedia."
                        )
                        
                        solution_basis = clean_solution_preview(solution_basis)
                        solution_basis = clean_preview_math_scientific(solution_basis)
                        
                        st.markdown(solution_basis)

            docx_data = generate_quiz_docx(custom_cfg, custom_quiz)
            clean_mapel_name = custom_cfg.get('mapel', 'Quiz').replace(' ', '_')
            st.download_button(
                label="📄 Download Paket Kuis (.docx)",
                data=docx_data,
                file_name=f"RoboMANTAP_Kuis_{clean_mapel_name}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                type="primary",
            )

            st.markdown("#### 🚀 Terbitkan Kuis ke Siswa")
            if "default_quiz_code" not in st.session_state:
                st.session_state.default_quiz_code = f"MNT-{uuid.uuid4().hex[:4].upper()}"
            col_pub1, col_pub2 = st.columns([2, 1])
            with col_pub1:
                st.text_input(
                    "🔑 Buat Kode Kuis Unik (opsional)",
                    value=st.session_state.default_quiz_code,
                    max_chars=15,
                    key="user_quiz_code",
                    help="Contoh: MTK-KLS10",
                )
            with col_pub2:
                st.write("")
                if st.button("🚀 TERBITKAN KUIS", type="primary", use_container_width=True):
                    clean_code = st.session_state.user_quiz_code.strip().upper()
                    if not clean_code:
                        st.warning("⚠️ Kode kuis tidak boleh kosong.")
                    else:
                        packages_5 = create_5_quiz_packages(custom_quiz)
                        custom_cfg["packages"] = packages_5
                        if publish_custom_quiz_to_db(clean_code, custom_cfg, custom_quiz):
                            st.session_state.last_published_code = clean_code
                            st.session_state.default_quiz_code = f"MNT-{uuid.uuid4().hex[:4].upper()}"
                            st.success(f"🎉 Kuis diterbitkan. 5 Paket Soal Acak siap digunakan. Kode: **{clean_code}**")
                        else:
                            st.error("❌ Gagal menerbitkan kuis. Periksa koneksi Database.")

        st.markdown("""
        <div class="premium-footer-card">
            <div class="footer-kicker">ROBO MANTAP • U.PROJECT NEXUS</div>
            <div class="footer-title">Satu sumber materi, banyak output pembelajaran.</div>
            <div class="footer-copy">Material Hub dapat dipakai kembali untuk Quiz Custom, LKPD, dan Media Ajar PPT tanpa upload ulang.</div>
        </div>
        """, unsafe_allow_html=True)

    with tab3:
        st.markdown("""
        <div class="premium-hero automation-hero">
            <div class="premium-kicker">UPN • AUTOMATION STUDIO</div>
            <div class="premium-title">⚡ RoboMANTAP <span>Automation</span></div>
            <div class="premium-subtitle">Bangun LKPD dan media presentasi dari topik manual atau File Drop yang sama.</div>
            <div class="premium-pills"><span>LKPD PDF</span><span>Media PPTX</span><span>Speaker Notes</span><span>Material Reuse</span></div>
        </div>
        """, unsafe_allow_html=True)

        shared_code = st.session_state.get("material_bundle_code", "")
        shared_pack = st.session_state.get("material_bundle", None)
        auto1, auto2, auto3 = st.tabs(["📄 LKPD Studio", "📊 Media Ajar PPT", "📦 Paket Pembelajaran"])

        with auto1:
            st.markdown("#### 📄 LKPD Studio")
            st.caption("LKPD generatif dengan layout premium, logo UPN, dan grounding materi yang sama dengan Quiz Custom.")
            lk_source_col, lk_code_col = st.columns([1.4, 1])
            with lk_source_col:
                topic_lkpd = st.text_input("Topik / Materi Pembelajaran", value="", placeholder="Contoh: Persamaan Kuadrat", key="lkpd_topic")
            with lk_code_col:
                lk_material_code = st.text_input("File Drop (opsional)", value=shared_code, placeholder="MD-XXXXXX", key="lkpd_material_code")
            col_lkpd1, col_lkpd2 = st.columns(2)
            with col_lkpd1:
                kelas_lkpd = st.selectbox("Kelas / Jenjang", ["VII MTs", "VIII MTs", "IX MTs", "X MA", "XI MA", "XII MA"], key="lkpd_kelas")
            with col_lkpd2:
                mapel_lkpd = st.selectbox("Mata Pelajaran", ["Matematika", "IPA", "IPS", "PAI & Bahasa Arab", "Fisika", "Biologi", "Kimia", "Bahasa Indonesia", "Bahasa Inggris"], key="lkpd_mapel")

            if st.button("✨ GENERATE LKPD PREMIUM", type="primary", use_container_width=True, key="generate_lkpd_premium"):
                source_for_lkpd = shared_pack if lk_material_code.strip().upper() == shared_code and shared_pack else None
                if lk_material_code.strip():
                    source_for_lkpd = get_material_bundle_from_db(lk_material_code.strip().upper()) or source_for_lkpd
                if not topic_lkpd.strip() and not source_for_lkpd:
                    st.warning("Isi topik atau masukkan File Drop yang sudah disimpan.")
                else:
                    effective_topic = topic_lkpd.strip() or "Materi terlampir"
                    with st.spinner("RoboMANTAP sedang menyusun LKPD • mengikat sumber • menata layout..."):
                        ai_content = generate_lkpd_content(mapel_lkpd, kelas_lkpd, effective_topic, source_pack=source_for_lkpd)
                    if not ai_content:
                        st.error("LKPD belum berhasil dibuat. Silakan coba ulangi.")
                    else:
                        pdf_buffer = create_lkpd_pdf_buffer(mapel_lkpd, kelas_lkpd, effective_topic, ai_content, logo_path=UPN_PRIMARY_LOGO)
                        st.session_state.lkpd_pdf_bytes = pdf_buffer.getvalue()
                        st.session_state.lkpd_filename = f"RoboMANTAP_LKPD_{mapel_lkpd}_{effective_topic.replace(' ', '_')}.pdf"
                        st.session_state.lkpd_source_code = lk_material_code.strip().upper()
                        st.success("✅ LKPD premium berhasil dibuat.")

            if st.session_state.get("lkpd_pdf_bytes"):
                st.markdown("<div class='result-card'><div class='result-card-title'>✅ LKPD READY</div><div class='result-card-copy'>Dokumen siap dicetak atau dibagikan ke guru/siswa.</div></div>", unsafe_allow_html=True)
                st.download_button(
                    label="📥 DOWNLOAD LKPD PDF",
                    type="primary",
                    data=st.session_state.lkpd_pdf_bytes,
                    file_name=st.session_state.get("lkpd_filename", "RoboMANTAP_LKPD.pdf"),
                    mime="application/pdf",
                    use_container_width=True,
                    key="download_lkpd_premium",
                )

        with auto2:
            st.markdown("#### 📊 Media Ajar Studio")
            st.caption("Storyboard → visual shape → speaker notes → PPTX 16:9 siap presentasi.")
            media_source_col, media_info_col = st.columns([1.5, 1])
            with media_source_col:
                media_topic = st.text_input("Topik Presentasi", value="", placeholder="Contoh: Sistem Persamaan Linear", key="media_topic")
                media_material_code = st.text_input("File Drop (opsional)", value=shared_code, placeholder="MD-XXXXXX", key="media_material_code")
            with media_info_col:
                media_slide_count = st.number_input("Jumlah Slide", min_value=6, max_value=30, value=12, step=1, key="media_slide_count")
                media_duration = st.number_input("Durasi Kelas (menit)", min_value=15, max_value=180, value=60, step=5, key="media_duration")
            m1, m2, m3 = st.columns(3)
            with m1:
                media_lang = st.selectbox("Bahasa", ["Bahasa Indonesia", "Indonesia + Arab", "English"], key="media_lang")
            with m2:
                media_style = st.selectbox("Gaya Visual", ["Premium UPN", "Academic Clean", "Modern Madrasah", "Minimal Executive"], key="media_style")
            with m3:
                media_mode = st.selectbox("Mode Presenter", ["Interactive", "Expository", "HOTS / Discussion"], key="media_mode")

            if st.button("🚀 BUILD MEDIA AJAR • PPTX", type="primary", use_container_width=True, key="generate_media_ppt"):
                source_for_media = shared_pack if media_material_code.strip().upper() == shared_code and shared_pack else None
                if media_material_code.strip():
                    source_for_media = get_material_bundle_from_db(media_material_code.strip().upper()) or source_for_media
                if not media_topic.strip() and not source_for_media:
                    st.warning("Isi topik presentasi atau masukkan File Drop.")
                else:
                    effective_media_topic = media_topic.strip() or "Materi terlampir"
                    with st.spinner(f"RoboMANTAP sedang membangun storyboard {media_slide_count} slide + speaker notes..."):
                        storyboard = generate_media_ajar_ai(
                            mapel=mapel_lkpd if 'mapel_lkpd' in locals() else "Umum",
                            jenjang=st.session_state.get("jenjang") or "MA",
                            kelas=kelas_lkpd if 'kelas_lkpd' in locals() else "X MA",
                            topik=effective_media_topic,
                            jumlah_slide=int(media_slide_count),
                            durasi_menit=int(media_duration),
                            bahasa=media_lang,
                            gaya=media_style,
                            mode_presentasi=media_mode,
                            source_pack=source_for_media,
                        )
                    if not storyboard:
                        st.error("Storyboard PPT belum berhasil dibuat. Coba ulangi.")
                    else:
                        ppt_bytes = build_media_ajar_pptx(
                            storyboard,
                            {
                                "mapel": mapel_lkpd if 'mapel_lkpd' in locals() else "Umum",
                                "kelas": kelas_lkpd if 'kelas_lkpd' in locals() else "X MA",
                            },
                            logo_path=UPN_MARK_LOGO,
                        )
                        st.session_state.media_ppt_bytes = ppt_bytes
                        st.session_state.media_ppt_filename = f"RoboMANTAP_Media_{re.sub(r'[^A-Za-z0-9_-]+','_',effective_media_topic)}.pptx"
                        st.session_state.media_storyboard = storyboard
                        st.success("✅ Media Ajar PPT siap digunakan di kelas.")

            if st.session_state.get("media_storyboard"):
                story = st.session_state.media_storyboard
                st.markdown(f"<div class='result-card'><div class='result-card-title'>{html.escape(story.get('deck_title','Media Ajar RoboMANTAP'))}</div><div class='result-card-copy'>{html.escape(story.get('deck_subtitle','PPTX siap presentasi • speaker notes terpasang'))}</div></div>", unsafe_allow_html=True)
                for slide in story.get("slides", [])[:12]:
                    st.markdown(f"<div class='story-card'><div class='story-number'>{slide.get('slide',0):02d}</div><div><b>{html.escape(slide.get('title',''))}</b><div class='story-meta'>{html.escape(slide.get('visual_type','concept'))} · {html.escape(slide.get('source_locator','') or 'source internal')}</div></div></div>", unsafe_allow_html=True)
                st.download_button(
                    label="📊 DOWNLOAD MEDIA AJAR PPTX",
                    type="primary",
                    data=st.session_state.media_ppt_bytes,
                    file_name=st.session_state.get("media_ppt_filename", "RoboMANTAP_Media_Ajar.pptx"),
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    use_container_width=True,
                    key="download_media_ppt",
                )

        with auto3:
            st.markdown("#### 📦 Paket Pembelajaran Terintegrasi")
            st.caption("Gunakan satu topik / satu File Drop untuk menghasilkan LKPD PDF dan Media Ajar PPT dalam satu alur kerja.")
            package_topic = st.text_input("Topik Paket", placeholder="Contoh: Fungsi Kuadrat", key="package_topic")
            package_code = st.text_input("File Drop Paket (opsional)", value=shared_code, placeholder="MD-XXXXXX", key="package_code")
            pc1, pc2, pc3 = st.columns(3)
            with pc1:
                package_mapel = st.text_input("Mapel", value="Matematika", key="package_mapel")
            with pc2:
                package_kelas = st.selectbox("Kelas", ["VII MTs", "VIII MTs", "IX MTs", "X MA", "XI MA", "XII MA"], key="package_kelas")
            with pc3:
                package_slides = st.number_input("Slide PPT", min_value=6, max_value=24, value=12, step=1, key="package_slides")

            if st.button("⚡ GENERATE PAKET LKPD + PPT", type="primary", use_container_width=True, key="generate_package"):
                pack_source = shared_pack if package_code.strip().upper() == shared_code and shared_pack else None
                if package_code.strip():
                    pack_source = get_material_bundle_from_db(package_code.strip().upper()) or pack_source
                if not package_topic.strip() and not pack_source:
                    st.warning("Isi topik paket atau pilih File Drop yang tersimpan.")
                else:
                    effective_package_topic = package_topic.strip() or "Materi terlampir"
                    with st.spinner("Membangun Paket Pembelajaran: LKPD + Storyboard + PPTX..."):
                        pack_lkpd = generate_lkpd_content(package_mapel, package_kelas, effective_package_topic, source_pack=pack_source)
                        pack_story = generate_media_ajar_ai(
                            mapel=package_mapel,
                            jenjang=package_kelas.split()[-1] if package_kelas else "MA",
                            kelas=package_kelas,
                            topik=effective_package_topic,
                            jumlah_slide=int(package_slides),
                            durasi_menit=60,
                            bahasa="Bahasa Indonesia",
                            gaya="Premium UPN",
                            mode_presentasi="Interactive",
                            source_pack=pack_source,
                        )
                    if not pack_lkpd or not pack_story:
                        st.error("Paket belum lengkap. Silakan ulangi sekali lagi.")
                    else:
                        pack_pdf = create_lkpd_pdf_buffer(package_mapel, package_kelas, effective_package_topic, pack_lkpd, logo_path=UPN_PRIMARY_LOGO).getvalue()
                        pack_ppt = build_media_ajar_pptx(pack_story, {"mapel": package_mapel, "kelas": package_kelas}, logo_path=UPN_MARK_LOGO)
                        st.session_state.package_lkpd_bytes = pack_pdf
                        st.session_state.package_ppt_bytes = pack_ppt
                        st.success("✅ Paket Pembelajaran selesai dibuat dari sumber yang sama.")

            if st.session_state.get("package_lkpd_bytes") and st.session_state.get("package_ppt_bytes"):
                pdl, pdp = st.columns(2)
                with pdl:
                    st.download_button("📄 DOWNLOAD LKPD", data=st.session_state.package_lkpd_bytes, file_name="RoboMANTAP_Paket_LKPD.pdf", mime="application/pdf", use_container_width=True, key="download_package_lkpd")
                with pdp:
                    st.download_button("📊 DOWNLOAD PPT", data=st.session_state.package_ppt_bytes, file_name="RoboMANTAP_Paket_Media.pptx", mime="application/vnd.openxmlformats-officedocument.presentationml.presentation", use_container_width=True, key="download_package_ppt")

        st.markdown("""
        <div class="premium-footer-card">
            <div class="footer-kicker">AUTOMATION STUDIO</div>
            <div class="footer-title">Satu Material Hub → Quiz + LKPD + Media Ajar.</div>
            <div class="footer-copy">Tujuannya bukan sekadar membuat file, tetapi menjaga sumber pembelajaran tetap konsisten antar-output.</div>
        </div>
        """, unsafe_allow_html=True)
# ==============================================================================
# 3. TAMPILAN PILIHAN MATA PELAJARAN OMI 2026 (SISWA)
# ==============================================================================
elif st.session_state.page == "select_mapel":
    st.markdown(f"### 📚 Pilih Bidang OMI 2026 -<br><span style='color: #059669; display: inline-block;'>{st.session_state.jenjang}</span>", unsafe_allow_html=True)
    if st.button("⬅️ Kembali Pilih Jenjang"):
        st.session_state.page = "landing"
        st.rerun()

    st.write("---")
    mapel_dict = KISI_KISI_OMI[st.session_state.jenjang]
    cols = st.columns(len(mapel_dict))

    for idx, (mapel_name, submateri_list) in enumerate(mapel_dict.items()):
        with cols[idx % len(cols)]:
            st.markdown(f"""
            <div class="mapel-card">
                <h4>{mapel_name}</h4>
                <p style="font-size: 12px; opacity: 0.7;">{len(submateri_list)} Submateri Operasional</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"Pilih {mapel_name}", key=f"btn_mapel_{idx}", type="primary", use_container_width=True):
                st.session_state.mapel = mapel_name
                st.session_state.page = "setup"
                st.rerun()

# ==============================================================================
# 4. SETUP CBT & BIODATA SISWA
# ==============================================================================
elif st.session_state.page == "setup":
    st.markdown(f"""
    <div style="font-size: 23px; font-weight: bold; line-height: 1.4; margin-bottom: 10px;">
        ⚙️ Persiapan CBT:<br>
        <span style="font-size: 17px; color: #059669; font-weight: 600;">
            {st.session_state.mapel} ({st.session_state.jenjang})
        </span>
    </div>
    """, unsafe_allow_html=True)
    if st.button("⬅️ Ganti Mata Pelajaran"):
        st.session_state.page = "select_mapel"
        st.rerun()

    st.write("---")
    st.markdown("#### 📝 Masukkan Data Diri Kamu")
    st.session_state.nama_siswa = st.text_input("Nama Lengkap:", value=st.session_state.nama_siswa, placeholder="Contoh: Fulanah binti Fulan")
    st.write("---")

    c1, c2 = st.columns([5, 7])

    with c1:
        st.subheader("1. Konfigurasi Ujian")
        st.session_state.stage = st.radio("Pilih Tahap Pembinaan:", ["Internal", "Kab/Kota", "Provinsi", "Nasional"])
        
        available_submateri = KISI_KISI_OMI[st.session_state.jenjang][st.session_state.mapel]
        st.session_state.selected_submateri = st.multiselect(
            "Pilih Submateri: (Click (Select all) untuk memilih semua Submateri)",
            available_submateri,
            default=[],
            placeholder="Pilih submateri di sini..."
        )

    with c2:
        st.subheader("2. Petunjuk CBT RoboMANTAP")
        st.markdown("""
        * **Jumlah Soal:** TEPAT 10 Soal Pilihan Ganda Terintegrasi per Sesi.
        * **Standar Pembinaan:** Mengacu Juknis OMI 2026 (Sains, Keislaman, & Literasi Data).
        * **Skoring:** Benar (+4), Salah (-1), Kosong (0).
        """)
        st.write("")
        if st.button("🚀 MARI MULAI SESI TEST SEKARANG!", type="primary", use_container_width=True):
            nama_input = st.session_state.nama_siswa.strip()
            jumlah_huruf = len([c for c in nama_input if c.isalpha()])
            
            if jumlah_huruf < 4:
                st.error("⚠️ Masukkan nama lengkap yang valid!")
            else:
                st.session_state.session_id = str(uuid.uuid4())
                with st.spinner(f"RoboMANTAP sedang merancang 10 soal {st.session_state.mapel} Kamu. Tunggu sebentar ya... (nggak lama kok, hanya butuh waktu sekitar 15 detik saja! 😊)"):
                    quiz = generate_quiz_batch(
                        st.session_state.jenjang,
                        st.session_state.mapel,
                        st.session_state.stage,
                        st.session_state.selected_submateri
                    )
                    if quiz and len(quiz) == 10:
                        st.session_state.quiz_data = quiz
                        st.session_state.user_answers = {}
                        st.session_state.current_index = 0
                        # Sinkronisasi awal ke DB
                        update_progress_siswa(
                            st.session_state.session_id, st.session_state.nama_siswa,
                            st.session_state.jenjang, st.session_state.mapel, 1, [], "BERJALAN"
                        )
                        st.session_state.page = "quiz"
                        st.rerun()
                    else:
                        st.error("Gagal membuat paket soal. Silakan klik tombol sekali lagi.")

# ==============================================================================
# 4b. SETUP KUIS CUSTOM & BIODATA SISWA (SAMPUL MASUK SISWA)
# ==============================================================================
elif st.session_state.page == "setup_custom":
    pkg = st.session_state.get("custom_pkg", {})
    cfg = normalize_custom_timer_config(pkg.get("config", {}) or {})
    
    st.markdown(f"""
    <div style="font-size: 23px; font-weight: bold; line-height: 1.4; margin-bottom: 10px;">
        ⚙️ Persiapan Kuis:<br>
        <span style="font-size: 17px; color: #059669; font-weight: 600;">
            {st.session_state.mapel} ({st.session_state.jenjang})
        </span>
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("⬅️ Batal & Kembali ke Beranda Utama"):
        st.session_state.page = "landing"
        st.session_state.is_custom_quiz = False
        st.rerun()

    st.write("---")
    st.markdown("#### 📝 Masukkan Data Diri Kamu")
    st.session_state.nama_siswa = st.text_input(
        "Nama Lengkap Siswa:", 
        value=st.session_state.nama_siswa, 
        placeholder="Masukkan Nama Lengkap Kamu disini..."
    )
    
    st.write("---")  
    timer_sec = cfg.get("timer_seconds", 0)
    timer_text = "Tanpa Batas Waktu" if timer_sec <= 0 else str(timedelta(seconds=timer_sec))
    
    st.subheader("📋 Informasi Kuis")
    st.markdown(f"""
    * **Mata Pelajaran:** {cfg.get('mapel', '-')}
    * **Materi:** {cfg.get('materi', '-')}
    * **Jumlah Soal:** {len(st.session_state.quiz_data)} Soal
    * **Tingkat Kesulitan:** {cfg.get('kesulitan', '-')}
    * **Batas Waktu Ujian:** {timer_text}
    """)
    
    st.write("")
    if st.button("🚀 MULAI KUIS SEKARANG!", type="primary", use_container_width=True):
        nama_input = st.session_state.nama_siswa.strip()
        jumlah_huruf = len([c for c in nama_input if c.isalpha()])
        
        if jumlah_huruf < 4:
            st.error("⚠️ Masukkan nama lengkap yang valid!")
        else:
            kode_kuis_aktif = st.session_state.get("custom_quiz_code", "").strip().upper()
            if not kode_kuis_aktif:
                st.error("⚠️ Kode kuis tidak ditemukan di sesi ini. Silakan kembali ke beranda dan masukkan kode kuis lagi.")
                st.stop()

            master_quiz = pkg.get("quiz", [])
            packages_5 = cfg.get("packages", [])

            # Memanggil helper resmi dari ai_engine.py
            existing_session = check_active_session_from_db(nama_input, st.session_state.mapel)
            
            if existing_session:
                # --------------------------------------------------------------
                # RECOVER SESI LAMA (PAKAI ID_SESI ASLI DARI DATABASE)
                # --------------------------------------------------------------
                st.session_state.session_id = existing_session["id_sesi"]

                # Ambil variasi paket acak yang sama berdasarkan session_id lama
                if packages_5:
                    pkg_idx = abs(hash(st.session_state.session_id)) % len(packages_5)
                    st.session_state.quiz_data = packages_5[pkg_idx]
                else:
                    ordered_quiz, order_error = get_or_create_student_quiz_order(
                        kode_kuis_aktif,
                        st.session_state.mapel,
                        master_quiz,
                        st.session_state.session_id,
                    )
                    if ordered_quiz is None:
                        st.error(f"⚠️ {order_error}")
                        st.stop()
                    st.session_state.quiz_data = ordered_quiz
                
                # Restore Waktu Ujian & Indeks Soal
                raw_created = existing_session["created_at"]
                if isinstance(raw_created, str):
                    start_dt = datetime.strptime(str(raw_created)[:19], "%Y-%m-%d %H:%M:%S")
                else:
                    start_dt = pd.to_datetime(raw_created).to_pydatetime()
                
                st.session_state.start_time_wib = start_dt
                st.session_state.custom_timer_seconds = timer_sec
                
                soal_terakhir = existing_session.get("soal_sekarang", 1)
                st.session_state.current_index = max(0, min(soal_terakhir - 1, len(st.session_state.quiz_data) - 1))
                st.session_state.user_answers = {}
                
                # Restore Penanda Pilihan Jawaban
                detail_saved = existing_session.get("detail_jawaban", [])
                if isinstance(detail_saved, list):
                    for idx, is_corr in enumerate(detail_saved):
                        if is_corr is not None and idx < len(st.session_state.quiz_data):
                            st.session_state.user_answers[idx] = st.session_state.quiz_data[idx]["options"][0]
                
                st.toast("🔄 Sesi pengerjaan sebelumnya berhasil dipulihkan!", icon="ℹ️")
            
            else:
                # --------------------------------------------------------------
                # INISIALISASI SESI BARU
                # --------------------------------------------------------------
                st.session_state.session_id = str(uuid.uuid4())

                if packages_5:
                    pkg_idx = abs(hash(st.session_state.session_id)) % len(packages_5)
                    st.session_state.quiz_data = packages_5[pkg_idx]
                else:
                    ordered_quiz, order_error = get_or_create_student_quiz_order(
                        kode_kuis_aktif,
                        st.session_state.mapel,
                        master_quiz,
                        st.session_state.session_id,
                    )
                    if ordered_quiz is None:
                        st.error(f"⚠️ {order_error}")
                        st.stop()
                    st.session_state.quiz_data = ordered_quiz

                st.session_state.user_answers = {}
                st.session_state.current_index = 0
                st.session_state.custom_timer_seconds = timer_sec
                st.session_state.start_time_wib = datetime.utcnow() + timedelta(hours=7)
                
                update_progress_siswa(
                    st.session_state.session_id, 
                    st.session_state.nama_siswa,
                    st.session_state.jenjang, 
                    st.session_state.mapel, 
                    1, 
                    [], 
                    "BERJALAN",
                    is_custom=True
                )
            
            st.session_state.page = "quiz"
            st.rerun()
    
# ==============================================================================
# 5. ENGINE TEST KUIS (OPTIMIZED WITH ST.FRAGMENT FOR ZERO LAG)
# ==============================================================================
# ==============================================================================
# ANTI-COPAS & DISABLE KLIK KANAN (PERLINDUNGAN HALAMAN KUIS)
# ==============================================================================
elif st.session_state.page == "quiz":
    quiz_data = st.session_state.get("quiz_data", [])
    
    if not quiz_data:
        st.error("⚠️ Data kuis tidak ditemukan. Silakan kembali ke beranda.")
        if st.button("🏠 Kembali ke Beranda"):
            st.session_state.page = "landing"
            st.rerun()
        st.stop()

    total_soal = len(quiz_data)
    
    # Pengaman indeks soal agar tidak out of bounds
    if st.session_state.current_index >= total_soal:
        st.session_state.current_index = total_soal - 1
    elif st.session_state.current_index < 0:
        st.session_state.current_index = 0

    curr_idx = st.session_state.current_index
    q = quiz_data[curr_idx]
    is_custom = st.session_state.get("is_custom_quiz", False)

    # Header Progress
    col_h1, col_h2 = st.columns([8, 4])
    with col_h1:
        if is_custom:
            st.subheader(f"Kuis By GuruMANTAP: {st.session_state.mapel}")
        else:
            stage_label = st.session_state.get("stage", "Internal")
            st.subheader(f"📝 CBT OMI: {st.session_state.mapel} ({stage_label})")
            
        st.caption(f"👤 Siswa: **{st.session_state.nama_siswa.strip()}**")
    with col_h2:
        st.progress((curr_idx + 1) / total_soal)
        st.caption(f"Soal **{curr_idx + 1}** dari **{total_soal}**")

    # Anti-Cheat & Live Timer WIB
    if "start_time_wib" not in st.session_state:
        st.session_state.start_time_wib = datetime.utcnow() + timedelta(hours=7)

    timer_seconds = st.session_state.get("custom_timer_seconds", 0)
    if is_custom and timer_seconds > 0:
        render_custom_timer(st.session_state.start_time_wib, timer_seconds)

 

    # Render Soal & Radio Pilihan Jawaban
    st.markdown(f"#### **Soal No. {curr_idx + 1}**")
    st.markdown(q["question"])
    st.write("")

    opts = q["options"]
    saved_ans = st.session_state.user_answers.get(curr_idx, None)
    default_opt_idx = opts.index(saved_ans) if saved_ans in opts else None

    selected_option = st.radio(
        "Pilih Jawaban Anda:", 
        opts, 
        index=default_opt_idx, 
        key=f"radio_q_{curr_idx}"
    )

    if selected_option:
        st.session_state.user_answers[curr_idx] = selected_option


    
    # Navigasi Utama (Berikutnya, Sebelumnya, Submit)

    # Helper Async Sync (Letakkan di dalam atau di luar blok quiz)
    def sync_to_db_async():
        # Salin variabel lokal untuk keamanan thread
        sess_id = st.session_state.session_id
        n_siswa = st.session_state.nama_siswa
        j_jang = st.session_state.jenjang
        m_pel = st.session_state.mapel
        c_idx = curr_idx + 1
        c_custom = is_custom
        
        detail = []
        for i in range(total_soal):
            u_ans = st.session_state.user_answers.get(i, None)
            if u_ans is None:
                detail.append(None)
            else:
                is_correct = (u_ans == quiz_data[i]["correct_answer"])
                detail.append(is_correct)
    
        def worker():
            try:
                update_progress_siswa(
                    sess_id, n_siswa, j_jang, m_pel,
                    c_idx, detail, "BERJALAN", is_custom=c_custom
                )
            except Exception:
                pass  # Jika DB sibuk, hindari membuat UI siswa crash
    
        # Eksekusi thread mandiri (bebas antrean)
        threading.Thread(target=worker, daemon=True).start()
    

    
    # Navigasi Utama
    col_nav1, col_nav2, col_nav3 = st.columns([3, 6, 3])
    
    with col_nav1:
        if curr_idx < total_soal - 1:
            if st.button("Berikutnya ➡️", type="primary", use_container_width=True, key=f"btn_next_{curr_idx}"):
                sync_to_db_async()  # Kirim ke DB di background (0 ms lag untuk siswa)
                st.session_state.current_index += 1
                st.rerun()
        else:
            if st.button("🏁 SUBMIT & SELESAIKAN", type="primary", use_container_width=True, key=f"btn_submit_{curr_idx}"):
                sync_to_db_async()  # Kirim status akhir
                st.session_state.page = "result"
                st.rerun()
                
    with col_nav3:
        if curr_idx > 0:
            if st.button("⬅️ Sebelumnya", use_container_width=True, key=f"btn_prev_{curr_idx}"):
                sync_to_db_async()
                st.session_state.current_index -= 1
                st.rerun()

    # Expander Hint AI Consultation
    with st.expander("Kamu bingung? Konsultasi di sini sama aku, RoboMANTAP! 🧕🏼"):
        st.caption("Fungsi kolom ini: Tulis ide awal atau rumus yang mau kamu coba, nanti RoboMANTAP bakal kasih petunjuk jalan keluarnya tanpa langsung bocorin jawaban!")
        
        attempt_input = st.text_input(
            "Gagasan / Ide Logika Kamu apa coba?:",
            placeholder="Contoh: Arti Bahasa Arab-nya apa?😟",
            key=f"hint_in_{curr_idx}"
        )
        
        hint_key = (
            st.session_state.mapel,
            curr_idx,
            q["question"],
            attempt_input.strip(),
        )

        if attempt_input.strip() and hint_key in st.session_state.ai_hint_cache:
            st.markdown("🧕🏼 **RoboMANTAP:**")
            st.markdown(st.session_state.ai_hint_cache[hint_key])

        if st.button("Diskusikan Yuk!", key=f"btn_hint_{curr_idx}"):
            if attempt_input.strip():
                if hint_key in st.session_state.ai_hint_cache:
                    st.markdown("🧕🏼 **RoboMANTAP:**")
                    st.markdown(st.session_state.ai_hint_cache[hint_key])
                else:
                    st.markdown("🧕🏼 **RoboMANTAP:**")
                    streamed_hint = st.write_stream(
                        get_ai_hint_stream(
                            q["question"],
                            attempt_input,
                            st.session_state.mapel,
                        ),
                    )

                    if streamed_hint and "⚠️" not in str(streamed_hint):
                        st.session_state.ai_hint_cache[hint_key] = str(streamed_hint)
            else:
                st.info("💡 Tolong ketik sedikit ide kamu dulu ya, biar RoboMANTAP bisa kasih petunjuk yang pas!")

# ==============================================================================
# 6. SCORECARD & EVALUASI SESI (OMI & KUIS CUSTOM)
# ==============================================================================
elif st.session_state.page == "result":
    quiz_data = st.session_state.quiz_data
    user_answers = st.session_state.user_answers
    total_soal = len(quiz_data)
    is_custom = st.session_state.get("is_custom_quiz", False)

    title_prefix = "Kuis Custom" if is_custom else "CBT OMI"
    st.subheader(f"📊 Evaluasi {title_prefix}: {st.session_state.mapel} ({st.session_state.jenjang})")

    if st.session_state.get("is_timeout", False):
        st.warning("⏱️ **Waktu Ujian Telah Habis!** Sesi kamu otomatis dihentikan dan seluruh jawaban yang sempat terisi telah dievaluasi oleh sistem. Tetap semangat dan tingkatkan manajemen waktu di ujian berikutnya ya!")
        st.session_state.is_timeout = False  # Reset flag

    benar, salah, kosong = 0, 0, 0
    detail = []
    for idx, q in enumerate(quiz_data):
        u_ans = user_answers.get(idx, None)
        if u_ans is None:
            kosong += 1
            detail.append(None)
        elif u_ans == q["correct_answer"]:
            benar += 1
            detail.append(True)
        else:
            salah += 1
            detail.append(False)

    # Perhitungan Skoring Otomatis
    if is_custom:
        total_skor = int(round((benar / total_soal) * 100)) if total_soal > 0 else 0
        max_skor = 100
        skor_display_str = f"{total_skor} / 100"
    else:
        total_skor = (benar * 4) - (salah * 1)
        max_skor = 40
        skor_display_str = f"{total_skor} / 40"

    # Sinkronisasi Status SELESAI ke Database Guru
    update_progress_siswa(
        st.session_state.session_id,
        st.session_state.nama_siswa,
        st.session_state.jenjang,
        st.session_state.mapel,
        total_soal,
        detail,
        "SELESAI",
        is_custom=st.session_state.get("is_custom_quiz", False)
    )

    # Ekstraksi Nama Panggilan Siswa
    nama_lengkap = st.session_state.get('nama_siswa', '').strip()
    nama_display = nama_lengkap.split()[0] if nama_lengkap else "Santri MANTAP"

    # Feedback Pesan RoboMANTAP berdasarkan Persentase Ketuntasan
    pct_success = (benar / total_soal) * 100 if total_soal > 0 else 0

    if pct_success >= 80:
        feedback_msg = f"🌟 **Luar Biasa! (Skor: {skor_display_str})**\n\nRoboMANTAP bangga banget sama kamu, **{nama_display}**! Pemahaman kamu di materi {st.session_state.mapel} sudah sangat tajam. Pertahankan terus fokus kamu! 🚀✨"
        feedback_type = "success"
    elif pct_success >= 40:
        feedback_msg = f"👍 **Kerja Bagus! (Skor: {skor_display_str})**\n\nUsaha yang mantap, **{nama_display}**! Kamu sudah paham sebagian besar konsepnya. Coba cek pembahasan di bawah untuk memperbaiki sedikit kekeliruan tadi ya! 💪😊"
        feedback_type = "info"
    else:
        feedback_msg = f"🌱 **Tetap Semangat, {nama_display}! (Skor: {skor_display_str})**\n\nJangan berkecil hati ya! Setiap kesalahan adalah proses belajar. Yuk pelajari pembahasan rinci di bawah bersama RoboMANTAP! 🧕🏼❤️"
        feedback_type = "warning"

    # Render Scorecard Modern Grid
    eval_css = """
    <style>
    .eval-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 10px;
        margin: 15px 0 20px 0;
    }
    @media (max-width: 640px) {
        .eval-grid {
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
        }
    }
    .eval-card {
        border-radius: 10px;
        padding: 10px 8px;
        text-align: center;
        box-shadow: 0 3px 10px rgba(0, 0, 0, 0.2);
    }
    .eval-title {
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.3px;
        margin-bottom: 3px;
        white-space: nowrap;
    }
    .eval-value {
        font-size: 20px;
        font-weight: 800;
        line-height: 1.2;
    }
    </style>
    """
    st.markdown(eval_css, unsafe_allow_html=True)

    benar_sub = " (+4)" if not is_custom else ""
    salah_sub = " (-1)" if not is_custom else ""

    eval_html = f"""<div class="eval-grid">
    <div class="eval-card" style="background: linear-gradient(135deg, rgba(120, 53, 15, 0.45) 0%, rgba(69, 26, 3, 0.75) 100%); border: 1px solid rgba(245, 158, 11, 0.5);">
        <div class="eval-title" style="color: #fde68a;">🏆 Total Skor</div>
        <div class="eval-value" style="color: #fbbf24;">{total_skor} <span style="font-size: 11px; color: #d1d5db;">/ {max_skor}</span></div>
    </div>
    <div class="eval-card" style="background: linear-gradient(135deg, rgba(6, 78, 59, 0.45) 0%, rgba(2, 44, 34, 0.75) 100%); border: 1px solid rgba(5, 150, 105, 0.45);">
        <div class="eval-title" style="color: #a7f3d0;">✅ Benar{benar_sub}</div>
        <div class="eval-value" style="color: #34d399;">{benar}</div>
    </div>
    <div class="eval-card" style="background: linear-gradient(135deg, rgba(127, 29, 29, 0.35) 0%, rgba(69, 10, 10, 0.65) 100%); border: 1px solid rgba(239, 68, 68, 0.4);">
        <div class="eval-title" style="color: #fca5a5;">❌ Salah{salah_sub}</div>
        <div class="eval-value" style="color: #f87171;">{salah}</div>
    </div>
    <div class="eval-card" style="background: linear-gradient(135deg, rgba(55, 65, 81, 0.35) 0%, rgba(31, 41, 55, 0.65) 100%); border: 1px solid rgba(156, 163, 175, 0.35);">
        <div class="eval-title" style="color: #d1d5db;">⚪ Kosong (0)</div>
        <div class="eval-value" style="color: #9ca3af;">{kosong}</div>
    </div>
</div>"""

    st.markdown(eval_html, unsafe_allow_html=True)

    if feedback_type == "success":
        st.success(f"🧕🏼 **Pesan dari RoboMANTAP:**\n\n{feedback_msg}")
    elif feedback_type == "info":
        st.info(f"🧕🏼 **Pesan dari RoboMANTAP:**\n\n{feedback_msg}")
    else:
        st.warning(f"🧕🏼 **Pesan dari RoboMANTAP:**\n\n{feedback_msg}")

    st.write("---")  
    if is_custom:
        # Tampilan Khusus Kuis Custom Guru (Satu Kali Pengerjaan)
        st.info("✅ **Kuis Selesai!** Hasil pengerjaanmu telah berhasil disimpan dan diteruskan ke GuruMANTAP. Man jadda wajada! Terus berjuang dan semangat belajarnya ya!🌟")
        if st.button("🏠 Kembali ke Beranda Utama", type="primary", use_container_width=True):
            st.session_state.page = "landing"
            st.session_state.is_custom_quiz = False
            st.rerun()
    else:
        # Tampilan Latihan OMI (Bebas Ulangi Sesi Soal Baru)
        col_act1, col_act2 = st.columns(2)
        with col_act1:
            if st.button("🔄 LATIHAN SOAL LAGI DONG! (SESI BARU)", type="primary", use_container_width=True):
                st.cache_data.clear()
                with st.spinner("Sabar ya, RoboMANTAP sedang menyiapkan soal baru Kamu.. (nggak lama kok, hanya butuh waktu sekitar 15 detik saja! 😊)"):
                    new_quiz = generate_quiz_batch(st.session_state.jenjang, st.session_state.mapel, st.session_state.stage, st.session_state.selected_submateri)
                    if new_quiz and len(new_quiz) == 10:
                        st.session_state.quiz_data = new_quiz
                        st.session_state.user_answers = {}
                        st.session_state.current_index = 0
                        st.session_state.ai_hint_cache = {}
                        st.session_state.ai_solution_cache = {}
                        st.session_state.session_id = str(uuid.uuid4())
                        update_progress_siswa(
                            st.session_state.session_id, st.session_state.nama_siswa,
                            st.session_state.jenjang, st.session_state.mapel, 1, [], "BERJALAN"
                        )
                        st.session_state.page = "quiz"
                        st.rerun()

        with col_act2:
            if st.button("🏠 Kembali ke Beranda Utama", use_container_width=True):
                st.session_state.page = "landing"
                st.session_state.is_custom_quiz = False
                st.rerun()

    st.write("---")
    st.markdown("### 📖 Pembahasan Rinci dari Pembina RoboMANTAP ")
    st.caption("💡 *Untuk meminta RoboMANTAP membahas nya, Klik pada masing-masing soal di bawah ini ya!* 😊")
    
    for idx, q in enumerate(quiz_data):
        u_ans = user_answers.get(idx, "Tidak Dijawab")
        is_correct = u_ans == q["correct_answer"]
        status_icon = "✅ BENAR" if is_correct else ("❌ SALAH" if u_ans != "Tidak Dijawab" else "⚪ KOSONG")
        
        with st.expander(f"Soal No. {idx + 1} [{status_icon}] - Jawaban Anda: {u_ans}"):
            st.markdown(f"**Soal:**\n{q['question']}")
            st.markdown(f"**Kunci Jawaban:** {q['correct_answer']}")
            
            # Jika Kuis Custom memiliki Solution Basis dari Guru, tampilkan langsung
            if is_custom and q.get("solution_basis"):
                st.info(f"💡 **Dasar Solusi Guru:**\n\n{q['solution_basis']}")

            st.write("---")
            
            solution_key = (
                st.session_state.mapel,
                idx,
                q["question"],
                q["correct_answer"],
            )

            if solution_key in st.session_state.ai_solution_cache:
                st.markdown("**🧕🏼 Pembahasan dari RoboMANTAP:**")
                st.markdown(st.session_state.ai_solution_cache[solution_key])

            if st.button(f"Tampilkan Pembahasannya dong! (Soal {idx + 1})", key=f"btn_sol_{idx}"):
                if solution_key in st.session_state.ai_solution_cache:
                    st.markdown("**🧕🏼 Pembahasan dari RoboMANTAP:**")
                    st.markdown(st.session_state.ai_solution_cache[solution_key])
                else:
                    st.markdown("**🧕🏼 Pembahasan dari RoboMANTAP:**")
                    streamed_solution = st.write_stream(
                        get_ai_solution_stream(
                            q["question"],
                            q["correct_answer"],
                            st.session_state.mapel,
                        ),
                    )

                    if streamed_solution and "⚠️" not in str(streamed_solution):
                        st.session_state.ai_solution_cache[solution_key] = str(streamed_solution)

