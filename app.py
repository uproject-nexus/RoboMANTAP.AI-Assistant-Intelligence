import io
import os
import re
import uuid
import html
import json
import base64
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
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
    publish_custom_quiz_to_db, get_custom_quiz_from_db, check_active_session_from_db
)

st.set_page_config(
    page_title="RoboMANTAP-Intelligence",
    page_icon="logo.png",
    layout="wide",
    initial_sidebar_state="auto"
)

# Inisialisasi Tabel Database saat aplikasi pertama kali dimuat
create_table_if_not_exists()

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
    </style>
""", unsafe_allow_html=True)

# Helper Base64 Image
def get_image_base64(path):
    if os.path.exists(path):
        with open(path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    return None

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
        
        if selected_jenjang_filter == "MTs (Sederajat SMP)":
            mapel_options = ["Semua Mapel"] + list(KISI_KISI_OMI["MTs (Sederajat SMP)"].keys())
        elif selected_jenjang_filter == "MA (Sederajat SMA)":
            mapel_options = ["Semua Mapel"] + list(KISI_KISI_OMI["MA (Sederajat SMA)"].keys())
        else:
            all_mapels = list(KISI_KISI_OMI["MTs (Sederajat SMP)"].keys()) + list(KISI_KISI_OMI["MA (Sederajat SMA)"].keys())
            mapel_options = ["Semua Mapel"] + sorted(list(set(all_mapels)))
            
        selected_mapel_filter = st.selectbox("📚 Filter Mata Pelajaran:", mapel_options, key="filter_mapel")
        selected_status_filter = st.selectbox("📌 Filter Status:", ["Semua Status", "BERJALAN", "SELESAI", "EXPIRED"], key="filter_status")

    else:
        st.markdown("""
        <div style="background: var(--secondary-background-color); border: 1px solid rgba(5, 150, 105, 0.3); padding: 12px 14px; border-radius: 10px; margin-bottom: 15px;">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                <span style="font-size: 11px; font-weight: 600; opacity: 0.7;">ENGINE STATUS</span>
                <span style="font-size: 10px; background: #059669; color: white; padding: 2px 8px; border-radius: 12px; font-weight: 700;">LIVE 🟢</span>
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

    sidebar_nexus_html = f'<div style="background: #ffffff; padding: 6px 14px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.08); display: inline-block; margin-bottom: 8px; border: 1px solid rgba(0,0,0,0.05);"><img src="data:image/png;base64,{logo_nexus_b64}" style="height: 42px; max-width: 100%; display: block; margin: 0 auto;"></div>' if logo_nexus_b64 else ''
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
# HELPER MERAPIKAN OUTPUT KUIS
import html

# ============================================================
# HELPER RAPIKAN OUTPUT KUIS DOCX (ASLI TANPA DIUBAH)
# ============================================================

def clean_math_string(text: str) -> str:
    """Pembersih simbol & notasi matematika dasar untuk teks biasa."""
    if not text:
        return ""
    
    # 1. Konversi Panah LaTeX SEBELUM memproses \left / \right
    text = re.sub(r'\\(?:rightarrow|to)\b', '→', text)
    text = re.sub(r'\\Rightarrow\b', '⇒', text)
    text = re.sub(r'\\leftarrow\b', '←', text)
    text = re.sub(r'\\leftrightarrow\b', '↔', text)

    # 2. Bersihkan \left dan \right (Gunakan \b agar \rightarrow tidak terpotong)
    text = re.sub(r'\\left\b\s*[\(\[\{\.\|]?', '(', text)
    text = re.sub(r'\\right\b\s*[\)\]\}\.\|]?', ')', text)
    text = re.sub(r'\\(?:dots|cdots|ldots)', '…', text)

    # 3. Konversi Akar \sqrt{x}
    text = re.sub(r'\\sqrt\{([^}]+)\}', r'√(\1)', text)
    text = re.sub(r'\\sqrt\s*([a-zA-Z0-9_]+)', r'√\1', text)

    # 4. Pangkat & Subscript Unicode
    sup_map = str.maketrans("0123456789+-=()nxyi", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿˣʸⁱ")
    sub_map = str.maketrans("0123456789+-=()nixy", "₀₁₂₃₄⁵₆₇₈₉₊₋₌₍₎ₙᵢₓᵧ")

    text = re.sub(r'\^\{([^}]+)\}|\^([\-0-9a-zA-Z])', lambda m: (m.group(1) or m.group(2)).translate(sup_map), text)
    text = re.sub(r'\_\{([^}]+)\}|\_([0-9a-zA-Z])', lambda m: (m.group(1) or m.group(2)).translate(sub_map), text)

    # 5. Simbol Matematika
    replacements = {
        r"\times": "×", r"\cdot": "·", r"\div": "÷", r"\neq": "≠",
        r"\leq": "≤", r"\geq": "≥", r"\pm": "±", r"\infty": "∞",
        r"\pi": "π", r"\alpha": "α", r"\beta": "β", r"\theta": "θ", "$": ""
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # 6. Sapu bersih ampas backslash
    text = text.replace("left(", "(").replace("right)", ")").replace("dots", "…")
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r'\\([a-zA-Z]+)', r'\1', text).replace("\\", "")
    return re.sub(r'\s+', ' ', text).strip()

clean_math_text = clean_math_string


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


# ============================================================
# PENAMBAHAN PARSER MATRIKS WORD EQUATION (OMML VALID)
# ============================================================

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
        ("Jumlah Soal", f"{len(quiz_list)} Soal | Durasi: {config.get('timer_h', 0)}j {config.get('timer_m', 0)}m"),
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
    st.markdown("#### 📝 Sesi Kuis GuruMANTAP")
    
    col_c1, col_c2 = st.columns([3, 1])
    with col_c1:
        kode_masuk_input = st.text_input("Masukkan Kode Kuis GuruMANTAP:", placeholder="Masukkan Kode Kuis disini...", label_visibility="collapsed")
    with col_c2:
        if st.button("Masuk Kuis ➔", key="btn_custom_enter", use_container_width=True, type="primary"):
            if not kode_masuk_input.strip():
                st.warning("⚠️ Masukkan kode kuisnya dulu ya!")
            else:
                pkg = get_custom_quiz_from_db(kode_masuk_input.strip())
                if pkg:
                    cfg = pkg.get('config', {})
                    
                    # Pengecekan Masa Aktif Waktu (WIB)
                    now_wib = datetime.utcnow() + timedelta(hours=7)
                    active_from_str = cfg.get('active_from')
                    active_until_str = cfg.get('active_until')
                    
                    is_valid = True
                    if active_from_str and active_until_str:
                        dt_from = datetime.fromisoformat(active_from_str)
                        dt_until = datetime.fromisoformat(active_until_str)
                        
                        if now_wib < dt_from:
                            st.error(f"⏳ **Kuis Belum Dibuka!**\n\nKuis baru dapat diakses pada pukul **{cfg.get('time_start_str', '--:--')} WIB**.")
                            is_valid = False
                        elif now_wib > dt_until:
                            st.error(f"❌ **Kode Kuis Sudah Kedaluwarsa!**\n\nMasa aktif kuis ini telah berakhir pada pukul **{cfg.get('time_end_str', '--:--')} WIB**.")
                            is_valid = False

                    if is_valid:
                        st.session_state.is_custom_quiz = True
                        st.session_state.custom_pkg = pkg
                        st.session_state.mapel = cfg.get('mapel', 'Custom Quiz')
                        st.session_state.jenjang = cfg.get('jenjang', 'Umum')
                        st.session_state.quiz_data = pkg['quiz']
                        st.session_state.page = "setup_custom"
                        st.rerun()
                else:
                    st.error("❌ Kode Kuis tidak ditemukan! Periksa kembali kodenya ya")

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
        st.markdown("<p style='font-size: 18px; font-weight: bold; margin-bottom: 10px;'>Monitoring & Evaluasi Pembinaan OMI</p>", unsafe_allow_html=True)

        time_filter = st.session_state.get("filter_time", "Hari Ini")
        selected_jenjang_filter = st.session_state.get("filter_jenjang", "Semua Jenjang")
        selected_mapel_filter = st.session_state.get("filter_mapel", "Semua Mapel")
        selected_status_filter = st.session_state.get("filter_status", "Semua Status")
 
        auto_refresh = st.toggle("🔄 Live Now!", value=False, help="Nyalakan untuk memantau siswa secara real-time. Matikan saat membaca laporan")

        # Indikator Status Auto-Refresh
        if auto_refresh:
            st.markdown('<p style="font-size: 12px; opacity: 0.8;"><span class="blinking-dot-green">🟢</span> <b>Status:</b> Live Aktif! memperbarui data setiap 5 detik</p>', unsafe_allow_html=True)
        else:
            st.caption("⏸️ **Status:** Live dimatikan (tampilan stabil, aman untuk membaca laporan RoboMANTAP)")

        # Kondisi Tanggal
        if time_filter == "Hari Ini":
            where_clauses = ["DATE(updated_at) = CURRENT_DATE"]
        elif time_filter == "Kemarin":
            where_clauses = ["DATE(updated_at) = CURRENT_DATE - INTERVAL '1 day'"]
        else:
            where_clauses = ["DATE(updated_at) >= CURRENT_DATE - INTERVAL '2 days'"]

        # Kondisi Jenjang
        if selected_jenjang_filter != "Semua Jenjang":
            where_clauses.append(f"jenjang = '{selected_jenjang_filter}'")

        # Kondisi Mapel
        if selected_mapel_filter != "Semua Mapel":
            where_clauses.append(f"mapel = '{selected_mapel_filter}'")

        where_sql = " AND ".join(where_clauses)

        # Function Progress Bar Visual
        def render_progress_bar_html(detail_list):
            if not isinstance(detail_list, list) or len(detail_list) == 0: 
                return ""
            
            total_soal = len(detail_list)
            html = '<div style="display: flex; gap: 3px; align-items: center;">'
            for i in range(total_soal): 
                val = detail_list[i]
                color = "#10b981" if val is True else ("#ef4444" if val is False else "#d1d5db")
                html += f'<div style="background-color:{color}; height:12px; flex:1; border-radius:2px;" title="Soal {i+1}"></div>'
            html += '</div>'
            return html

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

                # 4. DIAGNOSIS AI KONTEKSTUAL (IKUT FILTER)
                # =========================================================================
                # Judul Tombol Dinamis Mengikuti Filter
                label_target = f"{selected_mapel_filter}" if selected_mapel_filter != "Semua Mapel" else selected_jenjang_filter
                if st.button(f"🧕 Buat Laporan RoboMANTAP! ({label_target})", type="primary", use_container_width=True):
                    with st.spinner(f"RoboMANTAP sedang menganalisis data {label_target}..."):
                        total_siswa = len(df)
                        rata_rata = df['nilai_akhir'].mean()
                        tertinggi = df['nilai_akhir'].max()
                        terendah = df['nilai_akhir'].min()

                        kelompok_mahir = len(df[df['nilai_akhir'] >= 32])
                        kelompok_sedang = len(df[(df['nilai_akhir'] >= 16) & (df['nilai_akhir'] < 32)])
                        kelompok_butuh_bimbingan = len(df[df['nilai_akhir'] < 16])

                        prompt = f"""
                        Anda cukup buatkan Laporan Evaluasi Eksekutif Spesifik dengan kalimat padat dan ringkas berdasarkan data berikut:

                        SCOPE EVALUASI:
                        - Rentang Waktu: {time_filter}
                        - Target Jenjang: {selected_jenjang_filter}
                        - Target Mata Pelajaran: {selected_mapel_filter}
                        - Mode Sesi: {"Sesi Terbaru Saja (Deduplikasi)" if only_latest else "Seluruh Riwayat Sesi"}

                        STATISTIK KELAS:
                        - Total Siswa/Sesi: {total_siswa}
                        - Rata-Rata Nilai: {rata_rata:.1f} / 40
                        - Nilai Tertinggi: {tertinggi} / 40 | Nilai Terendah: {terendah} / 40
                        - Kelompok Sangat Mahir (Skor >= 32): {kelompok_mahir} santri
                        - Kelompok Berkembang (Skor 16 - 31): {kelompok_sedang} santri
                        - Kelompok Perlu Intervensi (Skor < 16): {kelompok_butuh_bimbingan} santri

                        INSTRUKSI STRUKTUR LAPORAN (Format Markdown Rapi & Tajam):
                        1. 📊 **EXECUTIVE SUMMARY & EVALUASI PERFORMA ({label_target})**
                           (Evaluasi ketuntasan materi secara mendalam dan tingkat kesenjangan nilai).
                        2. 👥 **PETA PEMBAGIAN KELOMPOK PEMBINAAN SISTER CLASS**
                           (Saran pengelompokan santri berdasarkan kesiapan materi).
                        3. 🚀 **ACTION PLAN STRATEGIS UNTUK GURU PEMBINA**
                           (3 langkah konkret yang harus dieksekusi guru pembina minggu ini).
                        """
                        report_result = stream_ai_text(prompt, max_output_tokens=3000)
                        st.session_state.cached_ai_report = "".join(list(report_result))

                # Display Cache Laporan AI
                if "cached_ai_report" in st.session_state and st.session_state.cached_ai_report:
                    st.markdown(f"### 📊 Laporan Evaluasi RoboMANTAP ({label_target})")
                    st.markdown(st.session_state.cached_ai_report)

                    col_rep1, col_rep2 = st.columns(2)
                    with col_rep1:
                        st.download_button(
                            label="📥 Unduh Teks Laporan (.txt)",
                            data=st.session_state.cached_ai_report,
                            file_name=f"Laporan_Diagnosis_AI_{label_target.replace(' ', '_')}_{time_filter.replace(' ', '_')}.txt",
                            mime="text/plain",
                            use_container_width=True
                        )
                    with col_rep2:
                        if st.button("🗑️ Hapus Laporan dari Layar", use_container_width=True):
                            st.session_state.cached_ai_report = ""
                            st.rerun()

                # =========================================================================
                # 5. LIVE TRACKING TABEL
                # =========================================================================
                st.write("---")
                st.markdown('#### <span class="blinking-dot-green">🟢</span> Live Tracking Pengerjaan', unsafe_allow_html=True)

                for index, row in df.iterrows():
                    with st.container():
                        col_nama, col_mapel, col_skor, col_bar, col_act = st.columns([2.5, 2.5, 1, 3.5, 1.5])

                        # Status Badge
                        if row['status_real'] == 'SELESAI':
                            status_badge = "✅"
                        elif row['status_real'] == 'EXPIRED':
                            status_badge = "⏸️ (Terputus)"
                        else:
                            status_badge = "🔄"

                        # Format Nama & Badge Percobaan
                        safe_nama = str(row['nama_siswa']).strip().replace("*", "")
                        percobaan_badge = f"<span style='font-size: 10px; background: rgba(5,150,105,0.15); color: #059669; padding: 2px 6px; border-radius: 4px; font-weight: 600;'>Percobaan ke-{row['total_percobaan']}</span>" if only_latest else ""

                        # Hitung Waktu Mulai & Durasi Berjalan (Presisi WIB & Server UTC)
                        try:
                            waktu_mulai_raw = row['created_at'] if ('created_at' in row and pd.notna(row['created_at'])) else row['updated_at']
                            
                            if isinstance(waktu_mulai_raw, str):
                                waktu_mulai_dt = datetime.strptime(str(waktu_mulai_raw)[:19], "%Y-%m-%d %H:%M:%S")
                            else:
                                waktu_mulai_dt = pd.to_datetime(waktu_mulai_raw).to_pydatetime()
                            
                            waktu_mulai_str = waktu_mulai_dt.strftime("%H:%M WIB")

                            if row['status_real'] == 'BERJALAN':
                                # Paksa waktu server UTC menjadi WIB (+7 jam)
                                waktu_sekarang_wib = datetime.utcnow() + timedelta(hours=7)
                                
                                selisih_detik = int((waktu_sekarang_wib - waktu_mulai_dt).total_seconds())
                                if selisih_detik < 0: 
                                    selisih_detik = 0
                                    
                                menit = selisih_detik // 60
                                detik = selisih_detik % 60
                                
                                if menit < 60:
                                    durasi_str = f"⏱️ {menit}m {detik:02d}s"
                                else:
                                    durasi_str = f"⏱️ {menit // 60}j {menit % 60}m"
                
                            elif row['status_real'] == 'EXPIRED':
                                # Khusus status Terputus/Inaktif
                                waktu_selesai_raw = row['updated_at']
                                if isinstance(waktu_selesai_raw, str):
                                    waktu_selesai_dt = datetime.strptime(str(waktu_selesai_raw)[:19], "%Y-%m-%d %H:%M:%S")
                                else:
                                    waktu_selesai_dt = pd.to_datetime(waktu_selesai_raw).to_pydatetime()
                                    
                                selisih_detik = int((waktu_selesai_dt - waktu_mulai_dt).total_seconds())
                                if selisih_detik < 0: 
                                    selisih_detik = 0
                                
                                menit = selisih_detik // 60
                                durasi_str = f"⏸️ Terputus ({menit}m)" if menit > 0 else "⏸️ Terputus (< 1m)"
                
                            else:
                                # Khusus status SELESAI (Siswa menamatkan 10 soal)
                                waktu_selesai_raw = row['updated_at']
                                if isinstance(waktu_selesai_raw, str):
                                    waktu_selesai_dt = datetime.strptime(str(waktu_selesai_raw)[:19], "%Y-%m-%d %H:%M:%S")
                                else:
                                    waktu_selesai_dt = pd.to_datetime(waktu_selesai_raw).to_pydatetime()
                                    
                                selisih_detik = int((waktu_selesai_dt - waktu_mulai_dt).total_seconds())
                                if selisih_detik < 0: 
                                    selisih_detik = 0
                                
                                menit = selisih_detik // 60
                                durasi_str = f"🏁 Selesai ({menit}m)" if menit > 0 else "🏁 Selesai (< 1m)"
                

                        except Exception as e:
                            waktu_mulai_str = "--:--"
                            durasi_str = "⏱️ -"

                        # Render Kolom Tampilan (Menggunakan {waktu_mulai_str})
                        col_nama.markdown(f"**{safe_nama}** {status_badge}<br/>{percobaan_badge}", unsafe_allow_html=True)
                        col_mapel.markdown(f"""
                        <div style="line-height: 1.3;">
                            <span style="font-weight: 600; font-size: 13px;">{row['mapel']}</span> <span style="font-size: 11px; opacity: 0.7;">({row['jenjang'][:3]})</span><br/>
                            <span style="font-size: 10px; color: #9ca3af;">🕒 {waktu_mulai_str} • <b style="color: #34d399;">{durasi_str}</b></span>
                        </div>
                        """, unsafe_allow_html=True)
                        col_skor.markdown(f"**Skor: {row['nilai_akhir']}**")

                        # Progress Bar & Micro Analytics
                        try:
                            detail_list = row['detail_jawaban']
                            if isinstance(detail_list, str):
                                import json
                                detail_list = json.loads(detail_list)
                            
                            col_bar.markdown(render_progress_bar_html(detail_list), unsafe_allow_html=True)

                            with col_act:
                                with st.popover("📊 Analisis"):
                                    safe_nama = str(row['nama_siswa']).strip().replace("*", "")
                                    st.markdown(f"**Analisis Siswa:** {safe_nama}")
                                    st.caption(f"Mapel: {row['mapel']} | Sesi Ke-{row['total_percobaan']}")

                                    if isinstance(detail_list, list) and len(detail_list) > 0:
                                        total_soal_sis = len(detail_list)
                                        b_cnt = sum(1 for x in detail_list if x is True)
                                        s_cnt = sum(1 for x in detail_list if x is False)
                                        k_cnt = sum(1 for x in detail_list if x is None)
                                        
                                        # Deteksi Jenis Kuis untuk Perhitungan Persentase Presisi
                                        is_custom_row = check_is_custom(row)
                                        
                                        if is_custom_row:
                                            # Kuis Custom: Rasio Benar dari Total N Soal
                                            pct = (b_cnt / total_soal_sis) * 100 if total_soal_sis > 0 else 0
                                        else:
                                            # CBT OMI: Rasio Skor Riil OMI terhadap Skor Maksimal (40 Poin)
                                            skor_omi = (b_cnt * 4) - (s_cnt * 1)
                                            pct = max(0, (skor_omi / 40) * 100) # Konversi proporsional OMI

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

                                        # Kategori Kesiapan Pedagogis
                                        if pct >= 80:
                                            st.success(f"🌟 **Kategori: Siap Kompetisi ({pct:.0f}%)**")
                                            st.markdown("**💡 Rekomendasi Pembinaan:**\n- Tingkatkan ke materi pengayaan HOTS\n- Siswa direkomendasikan masuk skuat utama")
                                        elif pct >= 40:
                                            st.warning(f"⚠️ **Kategori: Berkembang ({pct:.0f}%)**")
                                            st.markdown("**💡 Rekomendasi Pembinaan:**\n- Lakukan pembahasan khusus pada butir soal yang salah/kosong\n- Penguatan pemahaman konsep dasar masih perlu pematangan")
                                        else:
                                            st.error(f"🌱 **Kategori: Perlu Intervensi ({pct:.0f}%)**")
                                            st.markdown("**💡 Rekomendasi Pembinaan:**\n- Jadwalkan bimbingan intensif\n- Pelajari ulang modul pembahasan sebelum latihan berikutnya")
                                    else:
                                        st.info("Pengerjaan belum dimulai!") 
                                
                        except:
                            col_bar.write("-")
                        st.divider()

            except Exception as e:
                st.error(f"Gagal mengambil data dari database: {e}")

        # Fragment Execution Logic
        if auto_refresh:
            @st.fragment(run_every="5s")
            def active_live_view():
                render_monitoring_content()
            active_live_view()
        else:
            render_monitoring_content()


    with tab2:
        custom_cfg = st.session_state.get("custom_quiz_config", {})
        custom_quiz = st.session_state.get("custom_quiz_draft", [])

        with st.form("robomantap_quiz_custom_form", clear_on_submit=False):
            st.markdown("#### 🧩 Konfigurasi Quiz Custom")

            cqa, cqb = st.columns(2)
            with cqa:
                custom_mapel = st.text_input(
                    "📚 Mata Pelajaran",
                    value=custom_cfg.get("mapel", "Matematika"),
                    placeholder="Contoh: Matematika, Fisika, Bahasa Arab...",
                )
                custom_jenjang = st.selectbox(
                    "🏫 Jenjang",
                    [                
                        "MTs",                      
                        "MA",            
                    ],
                    index=[
                        "MTs", "MA"
                    ].index(custom_cfg.get("jenjang", "MA")),
                )
                custom_kelas = st.text_input(
                    "🎓 Kelas / Tingkat",
                    value=custom_cfg.get("kelas", "X MA"),
                    placeholder="Contoh: VIII MTs / XI MA",
                )
                custom_materi = st.text_input(
                    "📖 Materi Utama",
                    value=custom_cfg.get("materi", ""),
                    placeholder="Contoh: Logaritma",
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
                    "Standar Sekolah",
                    "Kehidupan Sehari-hari",
                    "Keislaman",
                    "Lingkungan",
                    "Teknologi",
                    "OMI / Olimpiade",
                    "Campuran",
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
            
            st.markdown("##### 📅 Masa Aktif Kuis (Rentang Waktu 1x24 Jam)")
            st.caption("Set jam kuis mulai dibuka hingga otomatis ditutup:")
            
            now_wib_time = (datetime.utcnow() + timedelta(hours=7)).time()
            default_end_time = (datetime.utcnow() + timedelta(hours=9)).time() # Default aktif 2 jam

            col_act1, col_act2 = st.columns(2)
            with col_act1:
                time_start = st.time_input(
                    "Jam Buka:", 
                    value=custom_cfg.get("time_start_val", now_wib_time),
                    key="input_time_start"
                )
            with col_act2:
                time_end = st.time_input(
                    "Jam Tutup:", 
                    value=custom_cfg.get("time_end_val", default_end_time),
                    key="input_time_end"
                )

            st.info(f"📌 **Masa Aktif Kuis:** ( {time_start.strftime('%H:%M')} hingga {time_end.strftime('%H:%M')} WIB )")
            
            submitted = st.form_submit_button(
                "🧕🏼 GENERATE RoboMANTAP QUIZ CUSTOM",
                type="primary",
                use_container_width=True,
            )

        if submitted:
            now_wib = datetime.utcnow() + timedelta(hours=7)
            dt_start = datetime.combine(now_wib.date(), time_start)
            dt_end = datetime.combine(now_wib.date(), time_end)
            # Jika jam tutup lebih kecil dari jam buka, anggap kuis selesai di hari berikutnya
            if dt_end <= dt_start:
                dt_end += timedelta(days=1)

            if not custom_mapel.strip():
                st.error("⚠️ Mata pelajaran wajib diisi")
            elif not custom_materi.strip():
                st.error("⚠️ Materi utama wajib diisi agar RoboMANTAP dapat merancang soal secara spesifik")
            else:
                # Tampilkan info jika tanpa batas waktu (timer 0), tapi proses pembuatan soal tetap berjalan
                if timer_total == 0:
                    st.info("⏱️ Kuis dibuat tanpa batas waktu pengerjaan.")

                with st.spinner(
                    f"RoboMANTAP sedang merancang {custom_jumlah} soal {custom_mapel} dengan tingkat {custom_kesulitan}..."
                ):
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
                        # --- PENAMBAHAN MASA AKTIF KUIS (WAJIB ADA) ---
                        "active_from": dt_start.isoformat(),
                        "active_until": dt_end.isoformat(),
                        "time_start_str": time_start.strftime('%H:%M'),
                        "time_end_str": time_end.strftime('%H:%M'),
                    }
                    custom_quiz = generated
                    custom_cfg = st.session_state.custom_quiz_config
                    st.success(f"✅ {len(generated)} soal berhasil dibuat dan disimpan sebagai draft.")
                else:
                    st.error(
                        "❌ RoboMANTAP belum berhasil menghasilkan paket yang valid. "
                        "Coba ulangi atau sederhanakan materi/konteks."
                    )

        if custom_quiz:
            st.write("---")
            st.markdown("#### 🔎 Preview Quiz Custom")
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

            # Generate dokumen Word (.docx) berformat rapi
            docx_data = generate_quiz_docx(custom_cfg, custom_quiz)
            clean_mapel_name = custom_cfg.get('mapel', 'Quiz').replace(' ', '_')

            st.download_button(
                label="📄 Download Paket Kuis (.docx)",
                data=docx_data,
                file_name=f"RoboMANTAP_Kuis_{clean_mapel_name}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                type="primary"
            )

            st.markdown("#### 🚀 Terbitkan Kuis ke Siswa")

            # 1. Inisialisasi kode default sekali saja agar tidak berubah saat rerun
            if "default_quiz_code" not in st.session_state:
                st.session_state.default_quiz_code = f"MNT-{uuid.uuid4().hex[:4].upper()}"

            col_pub1, col_pub2 = st.columns([2, 1])
            with col_pub1:
                # 2. Gunakan key="user_quiz_code" agar Streamlit mengunci input dari guru
                st.text_input(
                    "🔑 Buat Kode Kuis Unik (opsional):", 
                    value=st.session_state.default_quiz_code, 
                    max_chars=15,
                    key="user_quiz_code",
                    help="Ubah teks ini jika ingin membuat kode khusus (misal: MTK-KLS10)"
                )
            with col_pub2:
                st.write("")
                if st.button("🚀 TERBITKAN KUIS CUSTOM", type="primary", use_container_width=True):
                    # 3. Ambil nilai presisi dari input guru di session_state
                    clean_code = st.session_state.user_quiz_code.strip().upper()
                    
                    if not clean_code:
                        st.warning("⚠️ Kode kuis tidak boleh kosong!")
                    elif publish_custom_quiz_to_db(clean_code, custom_cfg, custom_quiz):
                        # Simpan status sukses dan perbarui default code untuk generasi kuis berikutnya
                        st.session_state.last_published_code = clean_code
                        st.session_state.default_quiz_code = f"MNT-{uuid.uuid4().hex[:4].upper()}"
                        st.success(f"🎉 Kuis Berhasil Diterbitkan! Bagikan Kode ini ke Siswa: **{clean_code}**")
                    else:
                        st.error("❌ Gagal menerbitkan kuis. Periksa koneksi Database.")
                        
        st.write("---")
        st.markdown("""
        <div style="background: rgba(16, 185, 129, 0.08); border-left: 4px solid #10b981; padding: 12px 16px; border-radius: 6px; margin-bottom: 15px;">
            <div style="font-size: 13px; font-weight: 700; color: #34d399; margin-bottom: 4px;">
                🧕 RoboMANTAP QUIZ CUSTOM 
            </div>
            <ul style="margin: 6px 0 0 0; padding-left: 18px;">
                <li><b>✨ Buat kuis sesuai kebutuhan Anda!</b></li>
                <li><b>⚡ Atur → Klik → Siap Digunakan!</b></li>
            </ul>
            <div style="font-size: 13px; font-weight: 700; color: #34d399; margin-bottom: 4px;">
                Ingin sistem seperti ini diterapkan secara resmi di sekolah Anda? U.Project Nexus menyediakan implementasi dan kustomisasi sistem sesuai kebutuhan institusi.
            </div>
        </div>
        """, unsafe_allow_html=True)

    with tab3:
        # GENERATOR LKPD EKSKLUSIF BERLOGO
        st.markdown("""
        <div style="background: linear-gradient(135deg, #064e3b 0%, #022c22 100%); padding: 12px; border-radius: 10px; border: 1px solid #059669; color: white; margin-bottom: 12px;">
            <div style="font-size: 14px; font-weight: 700;">📄 Generator LKPD</div>
            <div style="font-size: 11px; opacity: 0.85; margin-top: 2px;">Terintegrasi AI By U.Project Nexus dengan format menyesuaikan sekolah</div>
        </div>
        """, unsafe_allow_html=True)

        topic_lkpd = st.text_input("Topik / Materi Pembelajaran:", placeholder="Contoh: Persamaan Kuadrat / Tajwid Hukum Nun Mati", key="lkpd_topic")
        
        col_lkpd1, col_lkpd2 = st.columns(2)
        with col_lkpd1:
            kelas_lkpd = st.selectbox("Kelas / Jenjang:", ["VII MTs", "VIII MTs", "IX MTs", "X MA", "XI MA", "XII MA"], key="lkpd_kelas")
        with col_lkpd2:
            mapel_lkpd = st.selectbox("Mata Pelajaran:", ["Matematika", "IPA", "IPS", "PAI & Bahasa Arab", "Fisika", "Biologi", "Kimia"], key="lkpd_mapel")

        st.caption("💡*Modul cetak PDF ini adalah versi demo. Tampilan cover, logo, dan struktur LKPD dapat ditingkatkan atau disesuaikan penuh berdasarkan permintaan pihak sekolah*")
        if st.button("📄 Generate LKPD (.pdf)", type="primary", use_container_width=True):
            if not topic_lkpd.strip():
                st.warning("⚠️ Ketik topik/materi pembelajarannya dulu ya!")
            else:
                with st.spinner("RoboMANTAP sedang merancang LKPD Anda..."):
                    ai_content = generate_lkpd_content(mapel_lkpd, kelas_lkpd, topic_lkpd)
                    if not ai_content:
                        st.error("Gagal menyusun LKPD. Silakan coba klik tombol sekali lagi.")
                    else:
                        pdf_buffer = create_lkpd_pdf_buffer(mapel_lkpd, kelas_lkpd, topic_lkpd, ai_content)
                        # Simpan hasil PDF & nama file ke session_state agar permanen
                        st.session_state.lkpd_pdf_bytes = pdf_buffer.getvalue()
                        st.session_state.lkpd_filename = f"LKPD_{mapel_lkpd}_{topic_lkpd.replace(' ', '_')}_GuruMANTAP.pdf"
        # TAMPILKAN TOMBOL DOWNLOAD PERMANEN
        if st.session_state.get("lkpd_pdf_bytes"):
            st.success("✅ Dokumen LKPD Berhasil Dibuat!")
            st.download_button(
                label="📥 Download LKPD",
                type="primary",
                data=st.session_state.lkpd_pdf_bytes,
                file_name=st.session_state.get("lkpd_filename", "LKPD_RoboMANTAP.pdf"),
                mime="application/pdf",
                use_container_width=True
            )
                        
        st.write("---")
        st.markdown("""
        <div style="background: rgba(16, 185, 129, 0.08); border-left: 4px solid #10b981; padding: 12px 16px; border-radius: 6px; margin-bottom: 15px;">
            <div style="font-size: 13px; font-weight: 700; color: #34d399; margin-bottom: 4px;">
                ⚡ RoboMANTAP AUTOMATION
            </div>
            <ul style="margin: 6px 0 0 0; padding-left: 18px;">
                <li><b>📄 Atur format → klik → LKPD siap!</b></li>
                <li><b>📲 WhatsApp Automation!</b></li>
                <li><b>🧕🏼 RoboMANTAP AI Tutor 24/7!</b></li>
            </ul>
            <div style="font-size: 13px; font-weight: 700; color: #34d399; margin-bottom: 4px;">
                Ingin sistem seperti ini diterapkan secara resmi di sekolah Anda? U.Project Nexus menyediakan implementasi dan kustomisasi sistem sesuai kebutuhan institusi.
            </div>
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
    cfg = pkg.get("config", {})
    
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
    # Ringkasan Parameter Kuis dari Guru
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
            # Cek apakah siswa sudah pernah masuk sesi ini sebelumnya (Auto-Resume)
            existing_session = check_active_session_from_db(nama_input, st.session_state.mapel)
            
            if existing_session:
                # RECOVER SESI LAMA
                st.session_state.session_id = existing_session["id_sesi"]
                
                # Format ulang waktu mulai dari DB ke format datetime WIB
                raw_created = existing_session["created_at"]
                if isinstance(raw_created, str):
                    start_dt = datetime.strptime(str(raw_created)[:19], "%Y-%m-%d %H:%M:%S")
                else:
                    start_dt = pd.to_datetime(raw_created).to_pydatetime()
                
                st.session_state.start_time_wib = start_dt
                st.session_state.custom_timer_seconds = timer_sec
                st.session_state.current_index = 0
                st.session_state.user_answers = {}
                
                # Load kembali jawaban yang pernah diisi
                detail_saved = existing_session["detail_jawaban"]
                for idx, is_corr in enumerate(detail_saved):
                    if is_corr is not None:
                        # Tandai bahwa soal indeks ini sudah ada isinya
                        st.session_state.user_answers[idx] = st.session_state.quiz_data[idx]["options"][0] # placeholder restore
                
                st.toast("🔄 Sesi pengerjaan sebelumnya berhasil dipulihkan!", icon="ℹ️")
            else:
                # INSIALISASI SESI BARU
                st.session_state.session_id = str(uuid.uuid4())
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

# 5. ENGINE TEST KUIS
# ==============================================================================
elif st.session_state.page == "quiz":
    quiz_data = st.session_state.quiz_data
    curr_idx = st.session_state.current_index
    total_soal = len(quiz_data)
    q = quiz_data[curr_idx]

    is_custom = st.session_state.get("is_custom_quiz", False)

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

    # Anti-Cheat & Live Timer WIB Smooth
    if "start_time_wib" not in st.session_state:
        st.session_state.start_time_wib = datetime.utcnow() + timedelta(hours=7)

    timer_seconds = st.session_state.get("custom_timer_seconds", 0)
    if is_custom and timer_seconds > 0:
        render_custom_timer(st.session_state.start_time_wib, timer_seconds)

    st.write("---")
    st.markdown(f"#### **Soal No. {curr_idx + 1}**")
    st.markdown(q["question"])
    st.write("")

    opts = q["options"]
    saved_ans = st.session_state.user_answers.get(curr_idx, None)
    default_opt_idx = opts.index(saved_ans) if saved_ans in opts else None

    selected_option = st.radio("Pilih Jawaban Anda:", opts, index=default_opt_idx, key=f"radio_q_{curr_idx}")

    # Trigger sinkronisasi real-time ke Database jika jawaban berubah
    if selected_option and selected_option != saved_ans:
        st.session_state.user_answers[curr_idx] = selected_option
        
        detail = []
        for i in range(total_soal):
            u_ans = st.session_state.user_answers.get(i, None)
            if u_ans is None:
                detail.append(None)
            else:
                is_correct = (u_ans == quiz_data[i]["correct_answer"])
                detail.append(is_correct)
                
        update_progress_siswa(
            st.session_state.session_id,
            st.session_state.nama_siswa,
            st.session_state.jenjang,
            st.session_state.mapel,
            curr_idx + 1,
            detail,
            "BERJALAN",
            is_custom=is_custom
        )

    st.write("---")
    
    col_nav1, col_nav2, col_nav3 = st.columns([3, 6, 3])
    with col_nav1:
        if curr_idx < total_soal - 1:
            if st.button("Berikutnya ➡️", type="primary", use_container_width=True):
                st.session_state.current_index += 1
                st.rerun()
        else:
            if st.button("🏁 SUBMIT & SELESAIKAN", type="primary", use_container_width=True):
                st.session_state.page = "result"
                st.rerun()
    with col_nav3:
        if curr_idx > 0:
            if st.button("⬅️ Sebelumnya", use_container_width=True):
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
