import os
import re
import uuid
import html
import json
import base64
import random
import urllib.parse
import hashlib
import threading
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy import text
# from-import python-docx untuk generate Word dan Pdf berlogo
from datetime import datetime, timedelta

from bank_soal_engine import (
    extract_blueprint_from_docx,
    blueprint_summary,
    generate_bank_soal,
    build_bank_soal_docx,
    extract_blueprint_preview_rows
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

from ui_theme import apply_intelligence_theme, now_wib, normalize_wib_datetime
from quiz_sessions import (
    _quiz_signature, _quiz_question_ids, build_stable_student_quiz_order,
    ensure_quiz_session_order_table, _get_saved_quiz_order,
    get_or_create_student_quiz_order,
)
from document_engine import (
    clean_math_string, clean_solution_preview, contains_arabic,
    apply_arabic_paragraph_style, apply_arabic_run_style,
    add_omml_fraction, add_omml_matrix, append_text_with_fractions,
    generate_quiz_docx, draw_cover_background, generate_frac_image,
    clean_pdf_text, create_lkpd_pdf_buffer,
)

st.set_page_config(
    page_title="RoboMANTAP-Intelligence",
    page_icon="logo.png",
    layout="wide",
    initial_sidebar_state="auto"
)


TKA_PORTAL_URL = os.getenv("TKA_PORTAL_URL", "https://robomantap-tka.onrender.com")

def _tka_review_answer_equal(question: dict, user_answer) -> bool:
    qtype = str(question.get("question_type") or "PG").upper()
    if qtype == "MCMA":
        expected = question.get("correct_answers") or question.get("correct_answer") or []
        actual = user_answer if isinstance(user_answer, list) else []
        return {str(x).strip().upper() for x in actual} == {str(x).strip().upper() for x in expected}
    if qtype == "KATEGORI":
        expected = question.get("correct_answers") or question.get("correct_answer") or []
        actual = user_answer if isinstance(user_answer, list) else []
        return isinstance(expected, list) and isinstance(actual, list) and expected == actual
    return str(user_answer or "").strip().upper() == str(question.get("correct_answer") or "").strip().upper()


def _tka_review_answer_label(question: dict, answer) -> str:
    qtype = str(question.get("question_type") or "PG").upper()
    if qtype == "MCMA":
        return ", ".join(str(x) for x in (answer or [])) if isinstance(answer, list) else str(answer or "Tidak Dijawab")
    if qtype == "KATEGORI":
        return " | ".join(str(x) for x in (answer or [])) if isinstance(answer, list) else str(answer or "Tidak Dijawab")
    return str(answer or "Tidak Dijawab")


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
            st.session_state.session_id = review_id
            st.session_state.is_custom_quiz = True
            st.session_state.is_tka_session = (review_data.get("activity_type") == "TKA")
            st.session_state.loaded_review_id = review_id


LOGO_PUBLIC_URL = "https://raw.githubusercontent.com/uproject-nexus/RoboMANTAP.AI-Assistant-Intelligence/main/logo.png"

# Script gabungan untuk menimpa Icon, Apple Touch Icon, dan Web App Manifest
components.html(
    f"""
    <script>
        const doc = window.parent.document;
        const head = doc.getElementsByTagName('head')[0];

        // 1. Update Apple Touch Icon & Favicon
        let appleIcon = doc.querySelector("link[rel='apple-touch-icon']");
        if (!appleIcon) {{
            appleIcon = doc.createElement('link');
            appleIcon.rel = 'apple-touch-icon';
            head.appendChild(appleIcon);
        }}
        appleIcon.href = '{LOGO_PUBLIC_URL}';

        let icon = doc.querySelector("link[rel='icon']");
        if (icon) {{
            icon.href = '{LOGO_PUBLIC_URL}';
        }}

        // 2. Timpa Manifest PWA (Mengubah Nama & Logo pada Pop-up Install App)
        const myManifest = {{
            "short_name": "RoboMANTAP",
            "name": "RoboMANTAP-Intelligence",
            "icons": [
                {{
                    "src": "{LOGO_PUBLIC_URL}",
                    "sizes": "192x192 512x512",
                    "type": "image/png",
                    "purpose": "any maskable"
                }}
            ],
            "start_url": ".",
            "display": "standalone",
            "background_color": "#FFF9F0",
            "theme_color": "#5B6CFF"
        }};

        const blob = new Blob([JSON.stringify(myManifest)], {{type: 'application/json'}});
        const manifestURL = URL.createObjectURL(blob);

        let manifestLink = doc.querySelector("link[rel='manifest']");
        if (manifestLink) {{
            manifestLink.href = manifestURL;
        }} else {{
            manifestLink = doc.createElement('link');
            manifestLink.rel = 'manifest';
            manifestLink.href = manifestURL;
            head.appendChild(manifestLink);
        }}
    </script>
    """,
    height=0,
    width=0
)

# -----------------------------------------------------------------------------
# ONE-TIME DATABASE INITIALIZATION
# Streamlit reruns the script frequently. DDL/table checks must NOT execute on
# every widget interaction. cache_resource keeps this initialization process-
# wide while preserving the existing database functions unchanged.
# -----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _initialize_database_once():
    # Initialize only the core CBT schema at startup. Feature-specific schemas are
    # initialized lazily when a student enters that workspace.
    create_table_if_not_exists()
    return True

@st.cache_resource(show_spinner=False)
def _initialize_tka_tables_once():
    from tka_engine import ensure_tka_tables
    return ensure_tka_tables()

if not st.session_state.get("_rm_startup_ready", False):
    with st.spinner("Menyiapkan RoboMANTAP-Intelligence dan memeriksa layanan inti..."):
        _initialize_database_once()
    st.session_state["_rm_startup_ready"] = True
else:
    _initialize_database_once()

@st.cache_data(ttl=30, show_spinner=False)
def _cached_dashboard_custom_mapels():
    conn = init_db_connection()
    if not conn:
        return []
    try:
        df = conn.query(
            """
            SELECT DISTINCT mapel
            FROM sesi_ujian
            WHERE (mapel LIKE '%(Quiz)%' OR mapel LIKE '%(TKA)%')
              AND status NOT IN ('ARCHIVED', 'TRIAL', 'DRAFT', 'HIDDEN')
            """,
            ttl=30,
        )
        return df['mapel'].dropna().astype(str).tolist() if not df.empty else []
    except Exception:
        return []
# Accessibility and performance: no global copy/selection blocking and no
# always-on screen wake lock. Exam timing is enforced by the server-side timer.

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
       ROBOMANTAP INTELLIGENCE LIVE TRACKING — MODERN MONITORING CARDS
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
@st.cache_data(show_spinner=False)
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

apply_intelligence_theme()

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
if "bank_blueprint" not in st.session_state: st.session_state.bank_blueprint = None
if "bank_questions" not in st.session_state: st.session_state.bank_questions = []
if "bank_report" not in st.session_state: st.session_state.bank_report = None
if "bank_docx_bytes" not in st.session_state: st.session_state.bank_docx_bytes = None
if "bank_docx_config_signature" not in st.session_state: st.session_state.bank_docx_config_signature = None
if "student_intelligence_name" not in st.session_state: st.session_state.student_intelligence_name = ""
if "student_intelligence_grade" not in st.session_state: st.session_state.student_intelligence_grade = "Semua Jenjang"
if "student_adaptive_focus" not in st.session_state: st.session_state.student_adaptive_focus = ""
if "student_adaptive_topics" not in st.session_state: st.session_state.student_adaptive_topics = []

# ------------------------------------------------------------------------------
# RANDOMISASI PRODUCTION: URUTAN SOAL UNIK PER SESI SISWA
# ------------------------------------------------------------------------------
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

# Header Utama — identitas produk dan timestamp operasional WIB
_rendered_at_wib = now_wib()
_day_names = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
_month_names = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
_rendered_date = f"{_day_names[_rendered_at_wib.weekday()]}, {_rendered_at_wib.day} { _month_names[_rendered_at_wib.month - 1] } {_rendered_at_wib.year}"
st.markdown(f"""
<div class="rm-topbar">
  <div class="rm-topbar-mark">{img_mantap_html}</div>
  <div class="rm-topbar-brand"><b>RoboMANTAP<span>-Intelligence</span></b><small>Learning that understands you</small></div>
  <div class="rm-topbar-spacer"></div>
  <div class="rm-topbar-date"><span class="rm-live-dot"></span><span>{_rendered_date}<br><b>{_rendered_at_wib.strftime('%H:%M')} WIB</b></span></div>
</div>
""", unsafe_allow_html=True)

# SIDEBAR BARU — navigasi berbasis tujuan, ringkas, cerah, dan adaptif per peran.
with st.sidebar:
    st.markdown(f"""
    <div class="rm-sidebar-brand">
      <div class="rm-sidebar-logo">🎓</div>
      <div class="rm-sidebar-name">RoboMANTAP<span> Intelligence</span></div>
      <div class="rm-sidebar-caption">Belajar lebih cerdas, setiap hari</div>
      <div class="rm-sidebar-status"><span></span> Learning system ready</div>
    </div>
    """, unsafe_allow_html=True)

    current_page = st.session_state.get("page", "landing")
    if current_page in ("landing", "student_intelligence", "guru_login", "guru_dashboard", "select_mapel"):
        st.markdown('<div class="rm-sidebar-section">RUANG UTAMA</div>', unsafe_allow_html=True)
        if st.button("🏡  Beranda", key="nav_home", use_container_width=True, disabled=current_page == "landing"):
            st.session_state.page = "landing"
            st.rerun()
        if st.button("🌈  Portal Santri", key="nav_student", use_container_width=True, disabled=current_page == "student_intelligence"):
            st.session_state.page = "student_intelligence"
            st.rerun()
        if st.button("🧑‍🏫  Ruang Guru", key="nav_teacher", use_container_width=True, disabled=current_page in ("guru_login", "guru_dashboard")):
            st.session_state.page = "guru_login"
            st.rerun()
        st.markdown('<div class="rm-sidebar-section">LATIHAN & UJIAN</div>', unsafe_allow_html=True)
        if st.button("🧩  Latihan OMI · MTs", key="nav_omi_mts", use_container_width=True):
            st.session_state.jenjang = "MTs (Sederajat SMP)"
            st.session_state.page = "select_mapel"
            st.rerun()
        if st.button("🚀  Latihan OMI · MA", key="nav_omi_ma", use_container_width=True):
            st.session_state.jenjang = "MA (Sederajat SMA)"
            st.session_state.page = "select_mapel"
            st.rerun()
        st.markdown('<div class="rm-sidebar-section">PORTAL TERHUBUNG</div>', unsafe_allow_html=True)
        st.markdown(f'<a class="rm-sidebar-link" href="{TKA_PORTAL_URL}" target="_blank">🎯 &nbsp; Portal TKA <span>↗</span></a>', unsafe_allow_html=True)
        st.markdown('<a class="rm-sidebar-link" href="https://robomantap-intelligence-cbt.onrender.com" target="_blank">📝 &nbsp; Kuis Guru <span>↗</span></a>', unsafe_allow_html=True)

    if current_page == "guru_dashboard":
        st.markdown('<div class="rm-sidebar-section">FILTER MONITORING</div>', unsafe_allow_html=True)
        with st.form("guru_dashboard_filter_form", clear_on_submit=False):
            st.radio("Rentang waktu", ["Hari Ini", "Kemarin", "3 Hari Terakhir"], key="filter_time")
            st.toggle("Sesi terbaru saja", value=True, key="filter_latest", help="Tampilkan sesi terbaru untuk setiap siswa.")
            selected_jenjang_input = st.selectbox("Jenjang", ["Semua Jenjang", "MTs (Sederajat SMP)", "MA (Sederajat SMA)"], key="filter_jenjang")
            quiz_custom_mapels = _cached_dashboard_custom_mapels()
            if selected_jenjang_input == "MTs (Sederajat SMP)":
                base_mapels = list(KISI_KISI_OMI["MTs (Sederajat SMP)"].keys())
            elif selected_jenjang_input == "MA (Sederajat SMA)":
                base_mapels = list(KISI_KISI_OMI["MA (Sederajat SMA)"].keys())
            else:
                base_mapels = list(KISI_KISI_OMI["MTs (Sederajat SMP)"].keys()) + list(KISI_KISI_OMI["MA (Sederajat SMA)"].keys())
            mapel_options = ["Semua Mapel"] + sorted(set(base_mapels + quiz_custom_mapels))
            st.selectbox("Mata pelajaran", mapel_options, key="filter_mapel")
            st.selectbox("Status", ["Semua Status", "BERJALAN", "SELESAI", "EXPIRED"], key="filter_status")
            st.form_submit_button("Terapkan filter", use_container_width=True, type="primary")

    if current_page not in ("landing", "quiz"):
        st.markdown('<div class="rm-sidebar-tip"><strong>✨ Tip RoboMANTAP</strong><br>Gunakan rekomendasi belajar dan hasil latihan untuk menentukan langkah berikutnya.</div>', unsafe_allow_html=True)
    sidebar_nexus_html = f'<img src="data:image/png;base64,{logo_nexus_b64}" alt="U.Project Nexus" style="width:100%;max-width:130px;max-height:42px;object-fit:contain;">' if logo_nexus_b64 else '<b>U.Project Nexus</b>'
    st.markdown(f'<div class="rm-sidebar-footer">{sidebar_nexus_html}<div>Made for better learning</div><small>© 2026 U.Project Nexus</small></div>', unsafe_allow_html=True)

#===========================================================
# GENERATOR DOCX. KUIS
#===========================================================
# PEMBERSIH
@st.fragment(run_every="1s")
def render_custom_timer(start_time_wib, timer_seconds):
    # Timer ujian memakai timestamp aware WIB; refresh per detik memang diperlukan
    # untuk akurasi countdown. Refresh 10 detik hanya dipakai untuk live monitoring.
    sekarang_wib = now_wib()
    start_time_wib = normalize_wib_datetime(start_time_wib)
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

# ==============================================================================
# 1. TAMPILAN AWAL (GERBANG SISWA & GURU)
# ==============================================================================
if st.session_state.page == "landing":
    st.markdown("""
    <section class="rm-welcome-hero">
      <div class="rm-welcome-copy">
        <div class="rm-eyebrow"><span class="rm-sparkle">✦</span> YOUR LEARNING, LEVELLED UP</div>
        <h1>Halo, pejuang ilmu!<br><span>Siap jadi makin MANTAP?</span></h1>
        <p>Satu tempat untuk berlatih, memahami materi, menyiapkan ujian, dan menemukan cara belajar yang paling cocok untukmu.</p>
        <div class="rm-hero-chips"><span>🧠 AI-assisted learning</span><span>🎯 Latihan terarah</span><span>🌱 Bertumbuh setiap hari</span></div>
      </div>
      <div class="rm-hero-art"><div class="rm-orbit rm-orbit-one"></div><div class="rm-orbit rm-orbit-two"></div><div class="rm-book-stack">📚</div><div class="rm-float-bubble rm-bubble-one">✨</div><div class="rm-float-bubble rm-bubble-two">💡</div><div class="rm-float-bubble rm-bubble-three">🚀</div></div>
    </section>
    <div class="rm-section-heading"><div><div class="rm-eyebrow rm-eyebrow-color">PILIH RUANGMU</div><h2>Mulai dari yang kamu butuhkan</h2><p>Semua jalur penting ada di depan—tanpa menu yang menumpuk.</p></div></div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3, gap="medium")
    with c1:
        st.markdown('<div class="rm-feature-card rm-card-lilac"><div class="rm-feature-icon">🎒</div><div class="rm-feature-tag">PERSONAL LEARNING</div><h3>Portal Santri</h3><p>Belajar dengan panduan AI, latihan pintar, rangkuman PDF, dan insight yang mengikuti perjalananmu.</p></div>', unsafe_allow_html=True)
        if st.button("Buka ruang belajarku ↗", key="home_student", type="primary", use_container_width=True):
            st.session_state.page = "student_intelligence"
            st.rerun()
    with c2:
        st.markdown('<div class="rm-feature-card rm-card-mint"><div class="rm-feature-icon">🧑‍🏫</div><div class="rm-feature-tag">TEACHING WORKSPACE</div><h3>Ruang Guru</h3><p>Kelola kuis, susun bank soal, buat bahan ajar dengan AI, dan pantau aktivitas siswa.</p></div>', unsafe_allow_html=True)
        if st.button("Masuk ruang guru ↗", key="home_teacher", use_container_width=True):
            st.session_state.page = "guru_login"
            st.rerun()
    with c3:
        st.markdown('<div class="rm-feature-card rm-card-peach"><div class="rm-feature-icon">🏆</div><div class="rm-feature-tag">OLIMPIADE & PRACTICE</div><h3>Latihan OMI</h3><p>Latihan bertahap untuk MTs dan MA dengan mata pelajaran sesuai jenjang.</p></div>', unsafe_allow_html=True)
        if st.button("Pilih jenjang latihan ↗", key="home_omi", use_container_width=True):
            st.session_state.page = "select_mapel"
            st.rerun()

    st.markdown('<div class="rm-section-heading rm-section-heading-compact"><div><div class="rm-eyebrow rm-eyebrow-color">LEBIH SIAP, LEBIH PERCAYA DIRI</div><h2>Peralatan belajar yang terhubung</h2><p>Portal khusus tetap tersedia saat kamu membutuhkannya.</p></div></div>', unsafe_allow_html=True)
    p1, p2 = st.columns(2, gap="medium")
    with p1:
        st.markdown(f'<a class="rm-portal-link rm-link-blue" href="{TKA_PORTAL_URL}" target="_blank"><span class="rm-portal-icon">🎯</span><span><b>Portal TKA 2026</b><small>Persiapkan diri dengan latihan TKA</small></span><strong>↗</strong></a>', unsafe_allow_html=True)
    with p2:
        st.markdown('<a class="rm-portal-link rm-link-yellow" href="https://robomantap-intelligence-cbt.onrender.com" target="_blank"><span class="rm-portal-icon">📝</span><span><b>Kuis GuruMANTAP</b><small>Kerjakan kuis yang dibagikan guru</small></span><strong>↗</strong></a>', unsafe_allow_html=True)

    with st.expander("💬 Registrasi / bantuan akses melalui WhatsApp", expanded=False):
        st.markdown('<div class="rm-registration-intro"><b>Mulai terhubung dengan RoboMANTAP</b><p>Siapkan data yang diperlukan, lalu lanjutkan percakapan di WhatsApp resmi.</p></div>', unsafe_allow_html=True)
        NO_WA_BOT = "6283141694735"
        wa_registration_role = st.radio("Saya adalah", ["👤 Siswa", "🧑‍🏫 Guru"], horizontal=True, key="wa_registration_role", label_visibility="collapsed")
        if wa_registration_role == "👤 Siswa":
            with st.form("form_wa_siswa"):
                s_nama = st.text_input("Nama lengkap", placeholder="Nama lengkap siswa")
                s_jenjang = st.selectbox("Jenjang", ["MTs", "MA"])
                d1, d2 = st.columns(2)
                with d1: s_kelas = st.text_input("Kelas", placeholder="9A / 12")
                with d2: s_absen = st.text_input("Nomor absen", placeholder="03")
                s_username = st.text_input("Username pilihan", placeholder="santri.aisyah", help="3–24 karakter: huruf kecil, angka, titik, atau garis bawah.")
                st.caption("Jaga username-mu dan jangan bagikan kepada teman.")
                btn_siswa = st.form_submit_button("Lanjutkan ke WhatsApp", type="primary", use_container_width=True)
            if btn_siswa:
                username_clean = str(s_username or "").strip().casefold()
                if not s_nama or not s_kelas or not s_absen or not username_clean:
                    st.error("Lengkapi semua data terlebih dahulu.")
                elif not re.fullmatch(r"[a-z0-9][a-z0-9._]{2,23}", username_clean):
                    st.error("Username harus 3–24 karakter, diawali huruf/angka, dan hanya memakai huruf kecil, angka, titik, atau garis bawah.")
                else:
                    pesan = f"Halo RoboMANTAP! Saya [SISWA] : {s_nama.strip()} - {s_jenjang} - {s_kelas.strip()} - {s_absen.strip()} - {username_clean}"
                    link = f"https://wa.me/{NO_WA_BOT}?text={urllib.parse.quote(pesan)}"
                    st.success("Data siap. Lanjutkan melalui tombol WhatsApp di bawah.")
                    st.markdown(f'<a class="rm-whatsapp-button" href="{link}" target="_blank">Buka WhatsApp RoboMANTAP ↗</a>', unsafe_allow_html=True)
        else:
            with st.form("form_wa_guru"):
                g_nama = st.text_input("Nama lengkap guru", placeholder="Nama lengkap")
                g_kode = st.text_input("PIN akses guru", type="password", help="Hubungi admin UPN jika membutuhkan kode akses.")
                btn_guru = st.form_submit_button("Verifikasi dan lanjutkan", type="primary", use_container_width=True)
            if btn_guru:
                if not g_nama or not g_kode:
                    st.error("Nama dan PIN akses wajib diisi.")
                elif g_kode != "MANTAP2026":
                    st.error("PIN akses tidak sesuai.")
                else:
                    pesan = f"Halo RoboMANTAP! Saya [GURU] : {g_nama} - VALIDATED"
                    link = f"https://wa.me/{NO_WA_BOT}?text={urllib.parse.quote(pesan)}"
                    st.success("Identitas terverifikasi. Lanjutkan melalui WhatsApp.")
                    st.markdown(f'<a class="rm-whatsapp-button" href="{link}" target="_blank">Buka WhatsApp RoboMANTAP ↗</a>', unsafe_allow_html=True)

    st.markdown('<div class="rm-bottom-note"><span>🌈</span><div><b>Setiap langkah kecil berarti.</b><small>Belajar bukan tentang siapa yang paling cepat, tapi siapa yang terus bertumbuh.</small></div></div>', unsafe_allow_html=True)

elif st.session_state.page == "student_intelligence":
    from student_intelligence import render_student_intelligence_dashboard
    render_student_intelligence_dashboard(
        st.session_state.get("student_intelligence_name", ""),
        st.session_state.get("student_intelligence_grade", "Semua Jenjang"),
    )
    st.write("---")
    if st.button("⬅️ Kembali ke Beranda", use_container_width=True):
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
        st.session_state.page = "landing"
        st.rerun()

# ==============================================================================
# 2. LOGIN GURU & DASHBOARD (NEW UPGRADE)
# ==============================================================================
elif st.session_state.page == "guru_login":
    st.subheader("🔒 Akses Portal GuruMANTAP")

    st.markdown("""
    <div style="background-color: rgba(28, 131, 225, 0.1); border-left: 4px solid #1c83e1; padding: 10px 12px; border-radius: 6px; font-size: 10px; color: var(--text-color); margin-bottom: 15px;">
        ⚠️ Fitur ini dilindungi PIN untuk menjaga kerahasiaan nilai siswa dan soal CBT
    </div>
    """, unsafe_allow_html=True)
    
    with st.form("guru_login_form", clear_on_submit=False):
        pin_input = st.text_input("Masukkan PIN Akses:", type="password", placeholder="Masukkan PIN GuruMANTAP...")
        login_submit = st.form_submit_button("Login", type="primary", use_container_width=True)
    if login_submit:
        if pin_input == "MANTAP2026":
            st.session_state.guru_auth = True
            st.session_state.page = "guru_dashboard"
            st.rerun()
        else:
            st.error("PIN Salah. Silakhan coba lagi!")
    st.write("---")
    if st.button("⬅️ Kembali ke Beranda", use_container_width=True):
        st.session_state.page = "landing"
        st.rerun()

elif st.session_state.page == "guru_dashboard":
    if not st.session_state.guru_auth:
        st.warning("Akses Ditolak.")
        st.stop()

    st.markdown("<p style='font-size: 27px; font-weight: bold; margin-bottom: 8px;'>🖥️ Dashboard GuruMANTAP</p>", unsafe_allow_html=True)
    guru_section = st.radio(
        "Ruang kerja GuruMANTAP",
        ["🔴 Live Monitoring", "✨ Quiz Custom", "⚡ Automation", "📚 Bank Soal", "🎓 TKA Studio"],
        horizontal=True, key="guru_workspace_section", label_visibility="collapsed"
    )
    if guru_section == "🔴 Live Monitoring":
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
                '<b>LIVE AKTIF!</b> · memperbarui data setiap 10 detik, matikan Live bila tidak diperlukan.'
                '</p>',
                unsafe_allow_html=True
            )
        else:
            st.caption(
                "⏸️ **Live Dimatikan** · tampilan stabil dan nyaman untuk membaca laporan RoboMANTAP."
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
                            waktu_mulai_dt = normalize_wib_datetime(datetime.strptime(
                                str(waktu_mulai_raw)[:19], "%Y-%m-%d %H:%M:%S"
                            ))
                        else:
                            waktu_mulai_dt = normalize_wib_datetime(pd.to_datetime(waktu_mulai_raw).to_pydatetime())

                        waktu_mulai_str = waktu_mulai_dt.strftime("%H:%M WIB")

                        if row["status_real"] == "BERJALAN":
                            waktu_sekarang_wib = now_wib()
                            selisih_detik = max(
                                0,
                                int((waktu_sekarang_wib - waktu_mulai_dt).total_seconds())
                            )
                        else:
                            waktu_selesai_raw = row["updated_at"]
                            if isinstance(waktu_selesai_raw, str):
                                waktu_selesai_dt = normalize_wib_datetime(datetime.strptime(
                                    str(waktu_selesai_raw)[:19], "%Y-%m-%d %H:%M:%S"
                                ))
                            else:
                                waktu_selesai_dt = normalize_wib_datetime(pd.to_datetime(waktu_selesai_raw).to_pydatetime())

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
            @st.fragment(run_every="10s")
            def active_live_view():
                render_monitoring_content()
            active_live_view()
        else:
            render_monitoring_content()


    if guru_section == "✨ Quiz Custom":
        custom_cfg = st.session_state.get("custom_quiz_config", {})
        custom_quiz = st.session_state.get("custom_quiz_draft", [])
        material_code = st.session_state.get("material_bundle_code", "")
        material_pack = st.session_state.get("material_bundle", None)

        st.markdown("""
        <div class="premium-hero">
            <div class="premium-kicker">ROBOMANTAP-INTELLIGENCE • QUIZ WORKSPACE</div>
            <div class="premium-title">🧩 RoboMANTAP <span>Quiz Custom</span></div>
            <div class="premium-subtitle">Buat soal secara manual atau dari materi yang dilampirkan.</div>
            <div class="premium-pills">
                <span>AI Grounded</span><span>QA Validator</span><span>Mobile Ready</span><span>Teacher First</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("#### 📚 Material Hub • File Drop Guru")
        st.caption("Paket materi serbaguna untuk Quiz, LKPD, dan Media Ajar!")

        upload_col = st.container()
        with upload_col:
            material_files = st.file_uploader(
                "Drag & drop materi GuruMANTAP di sini",
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
                        material_code = new_code
                        material_pack = st.session_state.material_bundle
                        if db_ok:
                            st.success(f"✅ Materi berhasil disimpan. File Drop: **{new_code}**")
                        else:
                            st.warning(f"✅ Materi berhasil dibaca untuk sesi ini. Kode aktif: **{new_code}** (penyimpanan database belum terhubung).")
        with recall_col:
            with st.form("material_recall_form", clear_on_submit=False):
                recall_input = st.text_input("🔑 Ambil File Drop", value=material_code, placeholder="Contoh: MD-7K29FA", key="material_recall_code")
                recall_submit = st.form_submit_button("↻ MUAT FILE DROP", use_container_width=True)
            if recall_submit:
                code = recall_input.strip().upper()
                recalled = get_material_bundle_from_db(code) if code else None
                if recalled:
                    st.session_state.material_bundle_code = code
                    st.session_state.material_bundle = recalled
                    material_code = code
                    material_pack = recalled
                    st.success(f"✅ File Drop **{code}** aktif kembali.")
                else:
                    st.error("Kode File Drop tidak ditemukan di Material Hub.")

        # Render status after save/recall handlers so the current run can display
        # the new state without forcing an additional full-app rerun.
        current_code_html = (
            f"<div class='hub-code'><div class='hub-code-label'>FILE DROP AKTIF</div><div class='hub-code-value'>{html.escape(material_code)}</div><div class='hub-code-note'>{material_pack.get('file_count',0) if isinstance(material_pack, dict) else 0} file tersimpan untuk sesi ini.</div></div>"
            if material_code else
            "<div class='hub-empty'><div class='hub-code-label'>MATERIAL HUB</div><div class='hub-empty-title'>Belum ada materi aktif</div><div class='hub-code-note'>Drop file → simpan → gunakan kode yang sama di Quiz / LKPD / PPT.</div></div>"
        )
        st.markdown(current_code_html, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("""
        <div class="source-warning">
            <div class="source-warning-title">📌 PENTING!</div>
            Mohon Ustadzah ketik <code>materi dilampirkan</code> di kolom <b>Materi Utama</b> bila ingin memuat soal sesuai dengan file yang di upload.
        </div>
        """, unsafe_allow_html=True)
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

            option_rule = (
                "A–D • 4 pilihan"
                if option_count_for_jenjang(custom_jenjang) == 4
                else "A–E • 5 pilihan"
            )
            
            st.markdown(
                f"""
                <div style="
                    background-color: #1e293b;
                    border-left: 4px solid #3b82f6;
                    padding: 10px 14px;
                    border-radius: 6px;
                    font-size: 12px;
                    color: #e2e8f0;
                    margin-bottom: 1rem;
                ">
                    🎯 <b>Aturan opsi {custom_jenjang}: {option_rule}.</b> RoboMANTAP akan memvalidasi jumlah opsi kembali sebelum kuis diterbitkan.
                </div>
            """,
                unsafe_allow_html=True,
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
            now_wib_time = now_wib().time()
            default_end_time = (now_wib() + timedelta(hours=2)).time()
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
            current_wib = now_wib()
            dt_start = datetime.combine(current_wib.date(), time_start)
            dt_end = datetime.combine(current_wib.date(), time_end)
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
            st.caption(
                f"{custom_cfg.get('mapel', '-')} • {custom_cfg.get('jenjang', '-')} • "
                f"{custom_cfg.get('kesulitan', '-')} • {len(custom_quiz)} soal • "
                f"Timer: {str(timedelta(seconds=int(custom_cfg.get('timer_seconds', 0)))) if custom_cfg.get('timer_seconds', 0) else 'Tanpa batas'}"
            )

            for q_idx, cq in enumerate(custom_quiz, start=1):
                with st.expander(f"Soal {q_idx}", expanded=(q_idx == 1)):
                    st.markdown(cq["question"])
                    for option in cq["options"]:
                        st.markdown(f"- {option}")
                    st.success(f"Kunci terencana: **{cq['correct_answer']}**")
                    with st.expander("Lihat Solution Basis"):
                        st.markdown(cq.get("solution_basis", "Belum tersedia."))

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
            with st.form("publish_quiz_form", clear_on_submit=False):
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
                    publish_quiz_submit = st.form_submit_button("🚀 TERBITKAN KUIS", type="primary", use_container_width=True)
            if publish_quiz_submit:
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

    if guru_section == "⚡ Automation":
        st.markdown("""
        <div class="premium-hero automation-hero">
            <div class="premium-kicker">ROBOMANTAP-INTELLIGENCE • AUTOMATION STUDIO</div>
            <div class="premium-title">⚡ RoboMANTAP <span>Automation</span></div>
            <div class="premium-subtitle">Buat Media ajar dari topik manual atau berkas yang terlampir.</div>
            <div class="premium-pills"><span>LKPD PDF</span><span>Media PPTX</span><span>Speaker Notes</span><span>Material Reuse</span></div>
        </div>
        """, unsafe_allow_html=True)

        shared_code = st.session_state.get("material_bundle_code", "")
        shared_pack = st.session_state.get("material_bundle", None)
        automation_section = st.radio(
            "Pilih studio", ["📄 LKPD Studio", "📊 Media Ajar PPT", "📦 Paket Pembelajaran"],
            horizontal=True, key="automation_studio_section", label_visibility="collapsed"
        )

        if automation_section == "📄 LKPD Studio":
            st.markdown("##### 📄 LKPD Studio")
            st.caption("LKPD generatif premium yang sesuai dengan Material Hub.")
            with st.form("lkpd_generation_form", clear_on_submit=False):
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
    
                if st.form_submit_button("✨ GENERATE LKPD PREMIUM", type="primary", use_container_width=True):
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
                            pdf_buffer = create_lkpd_pdf_buffer(mapel_lkpd, kelas_lkpd, effective_topic, ai_content, logo_mantap_b64)
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

        if automation_section == "📊 Media Ajar PPT":
            st.markdown("##### 📊 Media Ajar Studio")
            st.caption("Storyboard → visual shape → speaker notes → Siap presentasi!")
            with st.form("media_generation_form", clear_on_submit=False):
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
    
                if st.form_submit_button("🚀 BUILD MEDIA AJAR • PPTX", type="primary", use_container_width=True):
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
                                logo_mantap_b64,
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

        if automation_section == "📦 Paket Pembelajaran":
            st.markdown("##### 📦 Paket Pembelajaran Terintegrasi")
            st.caption("Gunakan satu topik / satu File Drop untuk menghasilkan LKPD PDF dan Media Ajar PPT dalam satu alur kerja.")
            with st.form("package_generation_form", clear_on_submit=False):
                package_topic = st.text_input("Topik Paket", placeholder="Contoh: Fungsi Kuadrat", key="package_topic")
                package_code = st.text_input("File Drop Paket (opsional)", value=shared_code, placeholder="MD-XXXXXX", key="package_code")
                pc1, pc2, pc3 = st.columns(3)
                with pc1:
                    package_mapel = st.text_input("Mapel", value="Matematika", key="package_mapel")
                with pc2:
                    package_kelas = st.selectbox("Kelas", ["VII MTs", "VIII MTs", "IX MTs", "X MA", "XI MA", "XII MA"], key="package_kelas")
                with pc3:
                    package_slides = st.number_input("Slide PPT", min_value=6, max_value=24, value=12, step=1, key="package_slides")
    
                if st.form_submit_button("⚡ GENERATE PAKET LKPD + PPT", type="primary", use_container_width=True):
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
                            pack_pdf = create_lkpd_pdf_buffer(package_mapel, package_kelas, effective_package_topic, pack_lkpd, logo_mantap_b64).getvalue()
                            pack_ppt = build_media_ajar_pptx(pack_story, {"mapel": package_mapel, "kelas": package_kelas}, logo_mantap_b64)
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

    if guru_section == "📚 Bank Soal":
        st.markdown("""
        <div class="premium-hero automation-hero">
            <div class="premium-kicker">ROBOMANTAP-INTELLIGENCE • ASSESSMENT INTELLIGENCE</div>
            <div class="premium-title">📚 RoboMANTAP <span>Bank Soal</span></div>
            <div class="premium-subtitle">Upload kisi-kisi → baca blueprint → buat variasi → validasi → export</div>
            <div class="premium-pills"><span>Blueprint First</span><span>Variant Engine</span><span>AI QA</span><span>Traceability</span><span>DOCX Ready</span></div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="source-warning">
            <div class="source-warning-title">🎯 Prinsip Bank Soal</div>
            <b>Kisi-kisi adalah acuan utama.</b> Filter guru hanya mengatur jenjang dan jumlah variasi.
        </div>
        """, unsafe_allow_html=True)

        bank_file = st.file_uploader(
            "📥 Upload Kisi-Kisi Ujian (.docx)",
            type=["docx"],
            key="bank_blueprint_upload",
            help="Gunakan DOCX dengan tabel NO • ATP • INDIKATOR SOAL • [Level Kognitif/C1–C6] • PG • Isian • Uraian. Level C1–C6 akan menjadi constraint generator dan QA bila tersedia.",
        )

        if bank_file is not None:
            raw_bank_bytes = bank_file.getvalue()
            current_hash = hashlib.sha256(raw_bank_bytes).hexdigest()
            if st.session_state.get("bank_blueprint_hash") != current_hash:
                with st.spinner("RoboMANTAP membaca struktur tabel kisi-kisi..."):
                    parsed_blueprint = extract_blueprint_from_docx(raw_bank_bytes)
                st.session_state.bank_blueprint = parsed_blueprint
                st.session_state.bank_blueprint_hash = current_hash
                st.session_state.bank_questions = []
                st.session_state.bank_report = None
                st.session_state.bank_docx_bytes = None
                st.session_state.bank_docx_config_signature = None

        blueprint = st.session_state.get("bank_blueprint")

        if blueprint:
            summary = blueprint_summary(blueprint)
            metadata = blueprint.get("metadata", {})

            st.markdown("#### 1. Blueprint berhasil dibaca")
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("Blueprint", summary["blueprint_count"])
            with c2: st.metric("Slot Kisi-Kisi", summary["base_slots"])
            with c3: st.metric("PG", summary["slots_by_form"].get("PG", 0))
            with c4: st.metric("Isian + Uraian", summary["slots_by_form"].get("Isian", 0) + summary["slots_by_form"].get("Uraian", 0))
            st.caption(
                f"📄 {bank_file.name if bank_file else 'Kisi-kisi tersimpan'} • "
                f"{metadata.get('assessment') or 'Asesmen'} • Tahun {metadata.get('school_year') or '-'}"
            )
            cognitive_counts = summary.get("cognitive_levels", {})
            if cognitive_counts:
                level_text = " • ".join(f"{level}: {count}" for level, count in cognitive_counts.items())
                st.info(f"🧠 Level kognitif terbaca: **{level_text}**. Level ini menjadi constraint generator dan QA.")

            if blueprint.get("warnings"):
                for warning in blueprint["warnings"]:
                    st.warning(warning)

            with st.expander("🔎 Lihat Blueprint yang Dibaca", expanded=True):
                rows = extract_blueprint_preview_rows(blueprint)
                if rows:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                st.caption("Ekstraksi menggunakan struktur tabel DOCX. Jika tersedia, Level Kognitif C1–C6 ikut menjadi constraint generator dan QA.")

            with st.form("bank_generation_form", clear_on_submit=False):
                st.markdown("#### 2. Konfigurasi Generator")
                c1, c2, c3 = st.columns(3)
                with c1:
                    bank_jenjang = st.selectbox("🏫 Jenjang", ["SD", "SMP", "SMA", "MTs", "MA"], key="bank_jenjang")
                with c2:
                    bank_mapel = st.text_input("📚 Mata Pelajaran", value=metadata.get("subject") or "Matematika", key="bank_mapel")
                with c3:
                    bank_kelas = st.text_input("🎓 Kelas / Tingkat", value=metadata.get("grade") or "", key="bank_kelas")
    
                c1, c2 = st.columns([1, 2])
                with c1:
                    bank_variants = st.number_input(
                        "🔁 Jumlah Variasi per Blueprint", min_value=1, max_value=10, value=3, step=1,
                        key="bank_variants",
                        help="3 berarti setiap blueprint dibuat menjadi 3 variasi berbeda dengan kompetensi yang sama.",
                    )
                with c2:
                    bank_language = st.selectbox("🌐 Bahasa Soal", ["Bahasa Indonesia", "Bahasa Arab", "Indonesia + Arab", "English"], key="bank_language")
    
                estimated = summary["base_slots"] * int(bank_variants)
                st.info(
                    f"📐 Estimasi: **{summary['base_slots']} slot dasar × {int(bank_variants)} variasi = {estimated} soal**. "
                    "Jika satu blueprint memiliki beberapa bentuk soal, semua bentuk tetap dipertahankan."
                )
    
                if st.form_submit_button("🚀 GENERATE BANK SOAL • BLUEPRINT QA", type="primary", use_container_width=True):
                    if not bank_mapel.strip():
                        st.error("Mata pelajaran wajib diisi.")
                    elif not blueprint.get("blueprints"):
                        st.error("Blueprint belum terbaca.")
                    else:
                        with st.spinner(f"RoboMANTAP membuat {estimated} soal dan menjalankan QA blueprint..."):
                            questions, report = generate_bank_soal(
                                blueprint, variants=int(bank_variants), jenjang=bank_jenjang,
                                mapel=bank_mapel.strip(), kelas=bank_kelas.strip(), language=bank_language,
                            )
                        st.session_state.bank_questions = questions
                        st.session_state.bank_report = report
                        st.session_state.bank_docx_bytes = None
                        st.session_state.bank_docx_config_signature = None
                        if report.get("deterministic_ok") and report.get("review_count", 0) == 0:
                            st.success(f"✅ Bank soal selesai: {len(questions)} soal.")
                        elif questions:
                            st.warning(f"⚠️ {len(questions)} soal tersedia; {report.get('review_count', 0)} berstatus REVIEW.")
                        else:
                            st.error("❌ Bank soal belum berhasil dibuat lengkap.")
    
            questions = st.session_state.get("bank_questions", [])
            report = st.session_state.get("bank_report") or {}
            if questions:
                st.markdown("---")
                st.markdown("#### 3. QA & Preview")
                c1, c2, c3, c4 = st.columns(4)
                with c1: st.metric("Generated", report.get("generated_total", len(questions)))
                with c2: st.metric("Expected", report.get("expected_total", estimated))
                with c3: st.metric("QA PASS", report.get("pass_count", 0))
                with c4: st.metric("Review", report.get("review_count", 0))

                qa = report.get("ai_qa") or {}
                if qa.get("notes"):
                    st.caption("QA: " + " • ".join(map(str, qa.get("notes", [])[:3])))

                bank_preview_type = st.radio(
                    "Bentuk soal", ["PG", "Isian", "Uraian"], horizontal=True,
                    key="bank_preview_type", label_visibility="collapsed"
                )
                form_questions = [q for q in questions if q.get("question_type") == bank_preview_type]
                if not form_questions:
                    st.info("Tidak ada soal dengan bentuk ini pada kisi-kisi.")
                for i, q in enumerate(form_questions, start=1):
                    icon = "✅" if q.get("_qa_status") == "pass" else "⚠️"
                    with st.expander(
                        f"{icon} {i:02d} • {q.get('blueprint_id')} • V{q.get('variant')} • No. {q.get('source_number')}",
                        expanded=(i == 1),
                    ):
                        st.caption(f"Blueprint {q.get('blueprint_id')} • Variasi {q.get('variant')} • Level {q.get('cognitive_level') or '—'} • Bentuk {q.get('question_type')}")
                        st.markdown(q.get("question", ""))
                        for opt in q.get("options", []):
                            st.markdown(f"- {opt}")
                        st.success(f"Jawaban: **{q.get('correct_answer', '')}**")
                        with st.expander("Lihat Pembahasan"):
                            st.markdown(q.get("solution_basis", "Belum tersedia."))

                st.markdown("#### 4. Download Word")
                with st.form("bank_docx_form", clear_on_submit=False):
                    include_key = st.checkbox(
                        "Sertakan kunci jawaban & pembahasan",
                        value=True,
                        key="bank_include_key",
                        help="Jika dicentang, bagian Kunci dan Pembahasan ikut dimasukkan ke DOCX.",
                    )
                    include_map = st.checkbox(
                        "Sertakan Peta Blueprint / Traceability",
                        value=True,
                        key="bank_include_map",
                        help="Jika dicentang, Peta Blueprint dan Lampiran Traceability ikut dimasukkan ke DOCX.",
                    )

                    # A DOCX is tied to the exact checkbox/configuration used when it
                    # was built. This prevents Streamlit reruns from offering an old
                    # file after the teacher changes a checkbox.
                current_docx_signature = (
                    bool(include_key),
                    bool(include_map),
                    int(bank_variants),
                    str(bank_jenjang),
                    str(bank_mapel.strip()),
                    str(bank_kelas.strip()),
                    len(questions),
                )
                built_signature = st.session_state.get("bank_docx_config_signature")
                if st.session_state.get("bank_docx_bytes") and built_signature != current_docx_signature:
                    st.session_state.bank_docx_bytes = None
                    st.session_state.bank_docx_config_signature = None
                    st.info("ℹ️ Pilihan download berubah. Klik **BUILD BANK SOAL (.DOCX)** kembali agar dokumen mengikuti centang terbaru.")

                build_bank_docx_submit = st.form_submit_button("📄 BUILD BANK SOAL (.DOCX)", type="primary", use_container_width=True)
                if build_bank_docx_submit:
                    with st.spinner("Menata Bank Soal ke Word..."):
                        st.session_state.bank_docx_bytes = build_bank_soal_docx(
                            blueprint, questions, jenjang=bank_jenjang, mapel=bank_mapel.strip(),
                            kelas=bank_kelas.strip(), variants=int(bank_variants),
                            include_answer_key=bool(include_key), include_blueprint_map=bool(include_map),
                            logo_path=(os.path.join(os.path.dirname(__file__), "logo.png") if os.path.exists(os.path.join(os.path.dirname(__file__), "logo.png")) else None),
                        )
                    st.session_state.bank_docx_config_signature = current_docx_signature
                    st.success(
                        "✅ Dokumen Bank Soal siap dengan konfigurasi: "
                        f"kunci/pembahasan={'YA' if include_key else 'TIDAK'} • "
                        f"peta/traceability={'YA' if include_map else 'TIDAK'}."
                    )

            if (
                st.session_state.get("bank_docx_bytes")
                and st.session_state.get("bank_docx_config_signature") == current_docx_signature
            ):
                safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", bank_mapel.strip() or "Bank_Soal")
                st.download_button(
                    "⬇️ DOWNLOAD BANK SOAL WORD",
                    data=st.session_state.bank_docx_bytes,
                    file_name=f"RoboMANTAP_Bank_Soal_{safe_name}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                    key="download_bank_docx",
                )

            st.markdown("""
            <div class="premium-footer-card">
                <div class="footer-kicker">ROBO MANTAP • U.PROJECT NEXUS</div>
                <div class="footer-title">Blueprint → Variants → QA → Exam-Ready Document.</div>
                <div class="footer-copy">Setiap soal dapat ditelusuri kembali ke blueprint, variasi, level kognitif, bentuk, dan nomor sumber.</div>
            </div>
            """, unsafe_allow_html=True)


# 3. TAMPILAN PILIHAN MATA PELAJARAN OMI 2026 (SISWA)
# ==============================================================================

    if guru_section == "🎓 TKA Studio":
        _initialize_tka_tables_once()
        from tka_studio import render_tka_studio
        render_tka_studio()

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
    # -------------------------------------------------------------------------
    # 1. HEADER PERSIAPAN & TOMBOL KEMBALI
    # -------------------------------------------------------------------------
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.markdown(f"""
        <div style="font-size: 25px; font-weight: 800; line-height: 1.3; color: #f8fafc;">
            ⚙️ Persiapan CBT<br>
            <span style="font-size: 15px; color: #34d399; font-weight: 600;">
                {st.session_state.mapel} &bull; {st.session_state.jenjang}
            </span>
        </div>
        """, unsafe_allow_html=True)
    with col_h2:
        st.write("")
        if st.button("⬅️ Kembali Ganti Bidang", use_container_width=True):
            st.session_state.page = "select_mapel"
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # 2. FORM UTAMA (MENCEGAH RERUN SETIAP KLIK/KETIK)
    # -------------------------------------------------------------------------
    with st.form(key="cbt_setup_form", clear_on_submit=False):
        
        # --- DATA DIRI ---
        st.markdown('<div style="font-size: 22px; font-weight: 700; color: #f8fafc; margin-bottom: 6px;">📝 Data Diri Siswa</div>', unsafe_allow_html=True)
        nama_input = st.text_input(
            "Nama Lengkap:", 
            value=st.session_state.get("nama_siswa", ""), 
            placeholder="Masukkan Nama Lengkap Kamu",
            label_visibility="collapsed"
        )

        st.markdown("<hr style='margin: 15px 0; border-color: rgba(255,255,255,0.08);'>", unsafe_allow_html=True)

        # --- GRID KONFIGURASI & PETUNJUK ---
        c1, c2 = st.columns([6, 6])

        with c1:
            st.markdown('<div style="font-size: 22px; font-weight: 700; color: #f8fafc; margin-bottom: 8px;">1. Konfigurasi Ujian</div>', unsafe_allow_html=True)
            
            # Opsi Radio Horizontal agar ringkas di HP
            stage_input = st.radio(
                "Pilih Tahap Pembinaan:", 
                ["Internal", "Kab/Kota", "Provinsi", "Nasional"],
                index=0,
                horizontal=True
            )
          
            # Kode multiselect Anda tetap sama
            available_submateri = KISI_KISI_OMI[st.session_state.jenjang][st.session_state.mapel]
            
            submateri_input = st.multiselect(
                "Pilih Submateri (Kosongkan jika memilih semua):",
                available_submateri,
                default=[],
                placeholder="Pilih submateri di sini..."
            )
            st.write("---")
        
        with c2:
            st.markdown('<div style="font-size: 22px; font-weight: 700; color: #f8fafc; margin-bottom: 8px;">2. Petunjuk CBT RoboMANTAP</div>', unsafe_allow_html=True)
            
            # Card Petunjuk Bergaya Glassmorphism Dark
            petunjuk_html = """
            <div style="background: rgba(30, 41, 59, 0.4); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 12px 14px; font-size: 12px; color: #cbd5e1; line-height: 1.6;">
                <div style="margin-bottom: 6px;">🎯 <b>Jumlah Soal:</b> TEPAT 10 Soal Pilihan Ganda</div>
                <div style="margin-bottom: 6px;">📜 <b>Standar Pembinaan:</b> Mengacu Juknis OMI 2026 (Sains, Keislaman, & Literasi Data)</div>
                <div>📊 <b>Skoring:</b> Benar (<span style="color:#34d399; font-weight:700;">+4</span>), Salah (<span style="color:#f87171; font-weight:700;">-1</span>), Kosong (0)</div>
            </div>
            """
            st.markdown(petunjuk_html, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        
        # --- TOMBOL SUBMIT (SATU-SATUNYA PEMICU RERUN) ---
        submitted = st.form_submit_button(
            "🚀 MARI MULAI SESI TEST SEKARANG!", 
            type="primary", 
            use_container_width=True
        )

    # -------------------------------------------------------------------------
    # 3. EKSEKUSI PEMBUATAN SOAL SETELAH TOMBOL DIKLIK
    # -------------------------------------------------------------------------
    if submitted:
        # Simpan nilai dari form ke session_state
        st.session_state.nama_siswa = nama_input
        st.session_state.stage = stage_input
        st.session_state.selected_submateri = submateri_input

        nama_clean = nama_input.strip()
        jumlah_huruf = len([c for c in nama_clean if c.isalpha()])
        
        if jumlah_huruf < 4:
            st.error("⚠️ Masukkan nama lengkap yang valid (minimal 4 huruf)!")
        else:
            st.session_state.session_id = str(uuid.uuid4())
            with st.spinner(f"RoboMANTAP sedang merancang 10 soal {st.session_state.mapel} Kamu. Tunggu sebentar ya... (sekitar 15 detik) 😊"):
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
                        st.session_state.session_id, 
                        st.session_state.nama_siswa,
                        st.session_state.jenjang, 
                        st.session_state.mapel, 
                        1, [], "BERJALAN"
                    )
                    st.session_state.page = "quiz"
                    st.rerun()
                else:
                    st.error("❌ Gagal membuat paket soal. Silakan klik tombol sekali lagi.")

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
    with st.form("custom_student_identity_form", clear_on_submit=False):
        nama_siswa_input = st.text_input(
            "Nama Lengkap Siswa:",
            value=st.session_state.nama_siswa,
            placeholder="Masukkan Nama Lengkap Kamu disini..."
        )
        save_identity = st.form_submit_button("💾 Simpan Nama", use_container_width=True)
    if save_identity:
        st.session_state.nama_siswa = nama_siswa_input.strip()
    
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
                    start_dt = normalize_wib_datetime(datetime.strptime(str(raw_created)[:19], "%Y-%m-%d %H:%M:%S"))
                else:
                    start_dt = normalize_wib_datetime(pd.to_datetime(raw_created).to_pydatetime())
                
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
                st.session_state.start_time_wib = now_wib()
                
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
        st.session_state.start_time_wib = now_wib()

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
                    c_idx, detail, "BERJALAN", is_custom=c_custom,
                    user_answers_dict=dict(st.session_state.user_answers),
                    quiz_data_list=list(quiz_data),
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
        
        with st.form(f"hint_form_{curr_idx}", clear_on_submit=False):
            attempt_input = st.text_input(
                "Gagasan / Ide Logika Kamu apa coba?:",
                placeholder="Contoh: Arti Bahasa Arab-nya apa?😟",
                key=f"hint_in_{curr_idx}"
            )
            discuss_hint = st.form_submit_button("Diskusikan Yuk!", use_container_width=True)
        
        hint_key = (
            st.session_state.mapel,
            curr_idx,
            q["question"],
            attempt_input.strip(),
        )

        if attempt_input.strip() and hint_key in st.session_state.ai_hint_cache:
            st.markdown("🧕🏼 **RoboMANTAP:**")
            st.markdown(st.session_state.ai_hint_cache[hint_key])

        if discuss_hint:
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
    is_tka = st.session_state.get("is_tka_session", False)

    title_prefix = "TKA" if is_tka else ("Kuis Custom" if is_custom else "CBT OMI")
    st.subheader(f"📊 Evaluasi {title_prefix}: {st.session_state.mapel} ({st.session_state.jenjang})")

    if st.session_state.get("is_timeout", False):
        st.warning("⏱️ **Waktu Ujian Telah Habis!** Sesi kamu otomatis dihentikan dan seluruh jawaban yang sempat terisi telah dievaluasi oleh sistem. Tetap semangat dan tingkatkan manajemen waktu di ujian berikutnya ya!")
        st.session_state.is_timeout = False  # Reset flag

    benar, salah, kosong = 0, 0, 0
    detail = []
    for idx, q in enumerate(quiz_data):
        u_ans = user_answers.get(idx, None)
        if u_ans is None or u_ans == [] or u_ans == "":
            kosong += 1
            detail.append(None)
        elif is_tka and _tka_review_answer_equal(q, u_ans):
            benar += 1
            detail.append(True)
        elif (not is_tka) and u_ans == q["correct_answer"]:
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

    # Sinkronisasi Status SELESAI ke Database Guru.
    # Review TKA harus tetap memakai marker (TKA), jangan ditulis ulang sebagai (Quiz).
    if is_tka:
        from tka_engine import update_tka_progress
        _initialize_tka_tables_once()
        update_tka_progress(
            session_id=st.session_state.session_id,
            nama=st.session_state.nama_siswa,
            jenjang=st.session_state.jenjang,
            mapel=st.session_state.mapel,
            soal_sekarang=total_soal,
            detail_jawaban=detail,
            status="SELESAI",
            user_answers=dict(user_answers),
            questions=list(quiz_data),
        )
    else:
        update_progress_siswa(
            st.session_state.session_id,
            st.session_state.nama_siswa,
            st.session_state.jenjang,
            st.session_state.mapel,
            total_soal,
            detail,
            "SELESAI",
            is_custom=st.session_state.get("is_custom_quiz", False),
            user_answers_dict=dict(user_answers),
            quiz_data_list=list(quiz_data),
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
                # Do not clear the entire Streamlit cache here. That would also
                # evict unrelated dashboard/image caches and make the next screen
                # needlessly slow. generate_quiz_batch already creates a fresh set
                # from the current inputs.
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
        if is_tka:
            is_correct = _tka_review_answer_equal(q, u_ans) if u_ans not in (None, "Tidak Dijawab", "", []) else False
            answer_display = _tka_review_answer_label(q, u_ans)
            correct_display = _tka_review_answer_label(q, q.get("correct_answers") or q.get("correct_answer"))
        else:
            is_correct = u_ans == q["correct_answer"]
            answer_display = str(u_ans)
            correct_display = str(q["correct_answer"])
        status_icon = "✅ BENAR" if is_correct else ("❌ SALAH" if answer_display != "Tidak Dijawab" else "⚪ KOSONG")
        
        with st.expander(f"Soal No. {idx + 1} [{status_icon}] - Jawaban Anda: {answer_display}"):
            st.markdown(f"**Soal:**\n{q['question']}")
            if is_tka and q.get("stimulus_text"):
                st.markdown(f"**Stimulus:**\n{q['stimulus_text']}")
            if is_tka and q.get("image_id"):
                st.caption("Stimulus gambar tersedia pada paket TKA.")
            st.markdown(f"**Kunci Jawaban:** {correct_display}")
            
            # Jika Kuis Custom memiliki Solution Basis dari Guru, tampilkan langsung
            if is_custom and q.get("solution_basis"):
                st.info(f"💡 **Dasar Solusi Guru:**\n\n{q['solution_basis']}")

            st.write("---")
            
            solution_answer = correct_display
            solution_key = (
                st.session_state.mapel,
                idx,
                q["question"],
                json.dumps(q.get("correct_answers") if is_tka else q.get("correct_answer"), ensure_ascii=False, sort_keys=True, default=str),
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
                            solution_answer,
                            st.session_state.mapel,
                        ),
                    )

                    if streamed_solution and "⚠️" not in str(streamed_solution):
                        st.session_state.ai_solution_cache[solution_key] = str(streamed_solution)
