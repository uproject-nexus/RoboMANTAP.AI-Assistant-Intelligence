import io
import os
import uuid
import base64
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# Import python-docx untuk generate Word berlogo (ReportLab PDF)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
)

from ai_engine import (
    generate_quiz_batch, get_ai_hint_stream, get_ai_solution_stream,
    create_table_if_not_exists, update_progress_siswa, init_db_connection,
    generate_lkpd_content, stream_ai_text
)

st.set_page_config(
    page_title="RoboMANTAP-AI (Assistant Intelligence)",
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
    /* Class Grid Kustom Evaluasi (2x2 di Mobile, 4-Kolom di Desktop) */
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
        <span style="color: #6ee7b7; font-weight: 600;">Powered by RoboMANTAP-AI (Assistant Intelligence)</span>
    </div>
</div>
""", unsafe_allow_html=True)

# Sidebar Control
with st.sidebar:
    st.markdown("""
    <div style="background: linear-gradient(135deg, #064e3b 0%, #022c22 100%); padding: 16px; border-radius: 12px; border: 1px solid #059669; text-align: center; margin-bottom: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
        <div style="font-size: 26px; margin-bottom: 4px;">🧕🏼</div>
        <div style="color: #ffffff; font-weight: 700; font-size: 16px; letter-spacing: 0.5px;">RoboMANTAP-AI</div>
        <div style="color: #6ee7b7; font-size: 11px; font-weight: 500; margin-bottom: 6px;">Assistant Intelligence System</div>
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


    
# Helper LKPD PDF
def draw_cover_background(canvas_obj, doc):
    canvas_obj.saveState()
    cover_path = "cover.png"
    if os.path.exists(cover_path):
        canvas_obj.drawImage(cover_path, 0, 0, width=A4[0], height=A4[1])
    canvas_obj.restoreState()

def create_lkpd_pdf_buffer(mapel, kelas, topik, ai_content, logo_path="logo.png"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=2.0 * cm, rightMargin=2.0 * cm,
        topMargin=2.2 * cm, bottomMargin=2.2 * cm
    )
    styles = getSampleStyleSheet()
    
    style_cover_school = ParagraphStyle('CoverSchool', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, leading=14, textColor=colors.HexColor('#064E3B'), alignment=1)
    style_cover_title = ParagraphStyle('CoverTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=18, leading=22, textColor=colors.HexColor('#059669'), alignment=1)
    style_cover_sub = ParagraphStyle('CoverSub', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=13, textColor=colors.HexColor('#374151'), alignment=1)
    style_section_heading = ParagraphStyle('SecHeading', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, leading=14, textColor=colors.white)
    style_body = ParagraphStyle('BodyTextCustom', parent=styles['Normal'], fontName='Helvetica', fontSize=9.5, leading=13, textColor=colors.HexColor('#1F2937'))

    story = []
    story.append(Spacer(1, 2.2 * cm))

    if os.path.exists(logo_path):
        img_logo = Image(logo_path, width=3.8 * cm, height=2.2 * cm)
        img_logo.hAlign = 'CENTER'
        story.append(img_logo)
        story.append(Spacer(1, 0.4 * cm))

    school_html = "Madrasah Aliyah dan Tsanawiyah<br/><b>Al-Irsyad Al-Islamiyah Putri Bondowoso</b>"
    story.append(Paragraph(school_html, style_cover_school))
    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph("LEMBAR KERJA PESERTA DIDIK", style_cover_title))
    story.append(Paragraph("(LKPD)", style_cover_title))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("Model Pembelajaran HOTS & Integrasi Nilai Keislaman", style_cover_sub))
    story.append(Spacer(1, 1.0 * cm))

    meta_text = f"<b>Mata Pelajaran:</b> {mapel}<br/><b>Kelas / Jenjang:</b> {kelas}<br/><b>Topik Utama:</b> {topik}<br/><br/><b>Nama / Kelompok:</b> ............................../............................."
    p_meta = Paragraph(meta_text, style_body)
    
    table_meta = Table([[p_meta]], colWidths=[14 * cm])
    table_meta.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#ECFDF5')),
        ('BOX', (0,0), (-1,-1), 1.5, colors.HexColor('#059669')),
        ('PADDING', (0,0), (-1,-1), 12), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
    ]))
    table_meta.hAlign = 'CENTER'
    story.append(table_meta)
    story.append(Spacer(1, 2.5 * cm))
    story.append(Paragraph("<i>Tahun Ajaran:......../........</i>", style_cover_sub))
    story.append(PageBreak())

    # Halaman 2
    head_a = Paragraph("🎯 [A] TUJUAN PEMBELAJARAN (HOTS)", style_section_heading)
    t_head_a = Table([[head_a]], colWidths=[16.5 * cm])
    t_head_a.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#059669')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(t_head_a)
    story.append(Spacer(1, 0.2 * cm))

    tujuan_list = ai_content.get("tujuan", [])
    tujuan_text = "<br/>".join([f"{i+1}. {t}" for i, t in enumerate(tujuan_list)])
    story.append(Paragraph(tujuan_text, style_body))
    story.append(Spacer(1, 0.5 * cm))

    head_b = Paragraph("📖 [B] APERSEPSI & EKSPLORASI KONSEP", style_section_heading)
    t_head_b = Table([[head_b]], colWidths=[16.5 * cm])
    t_head_b.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#059669')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(t_head_b)
    story.append(Spacer(1, 0.2 * cm))

    p_ringkasan = Paragraph(ai_content.get("ringkasan", ""), style_body)
    t_box_b = Table([[p_ringkasan]], colWidths=[16.5 * cm])
    t_box_b.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F0F9FF')), ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#BAE6FD')), ('PADDING', (0,0), (-1,-1), 8)]))
    story.append(t_box_b)
    story.append(Spacer(1, 0.5 * cm))

    head_c = Paragraph("✍️ [C] TUGAS EKSPLORASI MANDIRI", style_section_heading)
    t_head_c = Table([[head_c]], colWidths=[16.5 * cm])
    t_head_c.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#059669')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(t_head_c)
    story.append(Spacer(1, 0.3 * cm))

    for i in range(1, 3):
        story.append(Paragraph(f"<b>Soal {i}:</b> {ai_content.get(f'soal_{i}', '')}", style_body))
        story.append(Spacer(1, 0.1 * cm))
        p_ans = Paragraph("<font color='#9CA3AF'><i>Lembar Jawaban:</i></font><br/><br/><br/><br/>", style_body)
        t_ans = Table([[p_ans]], colWidths=[16.5 * cm])
        t_ans.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F9FAFB')), ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#E5E7EB')), ('PADDING', (0,0), (-1,-1), 6)]))
        story.append(t_ans)
        story.append(Spacer(1, 0.4 * cm))

    head_d = Paragraph("🌿 [D] REFLEKSI KEISLAMAN & HIKMAH", style_section_heading)
    t_head_d = Table([[head_d]], colWidths=[16.5 * cm])
    t_head_d.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#D97706')), ('PADDING', (0,0), (-1,-1), 6)]))
    story.append(t_head_d)
    story.append(Spacer(1, 0.2 * cm))

    p_refleksi = Paragraph(f'<i>"{ai_content.get("refleksi", "")}"</i>', style_body)
    t_box_d = Table([[p_refleksi]], colWidths=[16.5 * cm])
    t_box_d.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#FEF3C7')), ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#FDE68A')), ('PADDING', (0,0), (-1,-1), 8)]))
    story.append(t_box_d)

    doc.build(story, onFirstPage=draw_cover_background, onLaterPages=draw_cover_background)
    buffer.seek(0)
    return buffer


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
    tab1, tab2, tab3 = st.tabs(["🔴 Live Monitoring", "🧕Bank Soal", "📲 WA Automation"])
    with tab1:
        st.markdown("<p style='font-size: 18px; font-weight: bold; margin-bottom: 10px;'>Monitoring & Evaluasi Pembinaan OMI</p>", unsafe_allow_html=True)

        time_filter = st.session_state.get("filter_time", "Hari Ini")
        selected_jenjang_filter = st.session_state.get("filter_jenjang", "Semua Jenjang")
        selected_mapel_filter = st.session_state.get("filter_mapel", "Semua Mapel")
        selected_status_filter = st.session_state.get("filter_status", "Semua Status")
 
        auto_refresh = st.toggle("🔄 Live Now!", value=False, help="Nyalakan untuk memantau siswa secara real-time. Matikan saat membaca laporan")

        # Indikator Status Auto-Refresh
        if auto_refresh:
            st.markdown('<p style="font-size: 12px; opacity: 0.8;"><span class="blinking-dot-green">🟢</span> <b>Status:</b> Live Aktif! memperbarui data setiap 3 detik</p>', unsafe_allow_html=True)
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
            if not isinstance(detail_list, list): return ""
            html = '<div style="display: flex; gap: 4px; align-items: center;">'
            for i in range(10): 
                if i < len(detail_list):
                    val = detail_list[i]
                    color = "#10b981" if val is True else ("#ef4444" if val is False else "#d1d5db")
                else:
                    color = "#f3f4f6"
                html += f'<div style="background-color:{color}; height:14px; flex:1; border-radius:3px;"></div>'
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
                        id_sesi, nama_siswa, jenjang, mapel, soal_sekarang, detail_jawaban, nilai_akhir, updated_at,
                        CASE 
                            WHEN status = 'BERJALAN' AND updated_at < NOW() - INTERVAL '15 minutes' THEN 'EXPIRED'
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
                        id_sesi, nama_siswa, jenjang, mapel, soal_sekarang, detail_jawaban, nilai_akhir, updated_at,
                        CASE 
                            WHEN status = 'BERJALAN' AND updated_at < NOW() - INTERVAL '15 minutes' THEN 'EXPIRED'
                            ELSE status
                        END as status_real,
                        1 as total_percobaan
                    FROM sesi_ujian
                    WHERE {where_sql}
                    ORDER BY updated_at DESC
                    """

                df = conn.query(query, ttl=0)

                # Filter Status di sisi Pandas jika user memilih status tertentu
                if not df.empty and selected_status_filter != "Semua Status":
                    df = df[df['status_real'] == selected_status_filter]

                if df.empty:
                    st.info(f"🚫 Tidak ada data pengerjaan siswa yang sesuai! Silahkan seting Kontrol Panel & Filter di Sidebar (click pojok kiri atas)")
                    return

                # =========================================================================
                # MINI KPI CARDS ELEGAN (GRID 2x2 DI HP, 4 KOLOM DI DESKTOP)
                # =========================================================================
                val_total = len(df['nama_siswa'].unique()) if only_latest else len(df)
                val_aktif = len(df[df['status_real'] == 'BERJALAN'])
                val_selesai = len(df[df['status_real'] == 'SELESAI'])
                val_rata = f"{df['nilai_akhir'].mean():.1f}" if not df.empty else "0.0"

                st.markdown(f"""
                <style>
                .kpi-grid {{
                    display: grid;
                    grid-template-columns: repeat(4, 1fr);
                    gap: 10px;
                    margin-bottom: 15px;
                }}
                @media (max-width: 640px) {{
                    .kpi-grid {{
                        grid-template-columns: repeat(2, 1fr); /* 2x2 Grid Seimbang di Layar HP */
                        gap: 8px;
                    }}
                }}
                .kpi-card {{
                    background: linear-gradient(135deg, rgba(6, 78, 59, 0.4) 0%, rgba(2, 44, 34, 0.7) 100%);
                    border: 1px solid rgba(5, 150, 105, 0.35);
                    border-radius: 10px;
                    padding: 8px 10px;
                    text-align: center;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.15);
                }}
                .kpi-title {{
                    font-size: 10px;
                    color: #a7f3d0;
                    font-weight: 600;
                    text-transform: uppercase;
                    letter-spacing: 0.3px;
                    margin-bottom: 2px;
                    white-space: nowrap;
                }}
                .kpi-value {{
                    font-size: 18px;
                    font-weight: 800;
                    color: #ffffff;
                    line-height: 1.2;
                }}
                </style>

                <div class="kpi-grid">
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
                    <div class="kpi-card">
                        <div class="kpi-title">🎯 Rata-Rata Nilai</div>
                        <div class="kpi-value" style="color: #f59e0b;">{val_rata} <span style="font-size: 11px; color: #9ca3af;">/ 40</span></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # =========================================================================
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
                        
                        col_nama.markdown(f"**{safe_nama}** {status_badge}<br/>{percobaan_badge}", unsafe_allow_html=True)
                        col_mapel.caption(f"{row['mapel']}<br/><b>{row['jenjang'][:3]}</b>", unsafe_allow_html=True)
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

                                    if isinstance(detail_list, list) and len(detail_list) == 10:
                                        b_cnt = sum(1 for x in detail_list if x is True)
                                        s_cnt = sum(1 for x in detail_list if x is False)
                                        k_cnt = sum(1 for x in detail_list if x is None)
                                        pct = (b_cnt / 10) * 100

                                        # Kartu Mikro Ringkas (Sejajar Horizontal di HP)
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

                                        # Kategori Kesiapan & Rekomendasi Pedagogis
                                        if pct >= 80:
                                            st.success(f"🌟 **Kategori: Siap Kompetisi ({pct:.0f}%)**")
                                            st.markdown("**💡 Rekomendasi Pembinaan:**")
                                            st.markdown("- Tingkatkan ke materi pengayaan HOTS tingkat Provinsi/Nasional\n- Siswa direkomendasikan masuk skuat utama pembinaan OMI")
                                        elif pct >= 40:
                                            st.warning(f"⚠️ **Kategori: Berkembang ({pct:.0f}%)**")
                                            st.markdown("**💡 Rekomendasi Pembinaan:**")
                                            st.markdown("- Lakukan pembahasan (*review*) khusus pada butir soal yang salah/kosong\n- Penguatan pemahaman konsep dasar masih perlu pematangan")
                                        else:
                                            st.error(f"🌱 **Kategori: Perlu Intervensi ({pct:.0f}%)**")
                                            st.markdown("**💡 Rekomendasi Pembinaan:**")
                                            st.markdown("- Jadwalkan bimbingan intensif\n- Pelajari ulang modul pembahasan sebelum melakukan latihan berikutnya")
                                    else:
                                        st.info("Pengerjaan belum selesai!")
                                
                                
                        except:
                            col_bar.write("-")
                        st.divider()

            except Exception as e:
                st.error(f"Gagal mengambil data dari database: {e}")

        # Fragment Execution Logic
        if auto_refresh:
            @st.fragment(run_every="3s")
            def active_live_view():
                render_monitoring_content()
            active_live_view()
        else:
            render_monitoring_content()


    with tab2:
        st.markdown("<p style='font-size: 15px; font-weight: bold; margin-bottom: 6px;'>🧕🏼 AI Quiz Generator & Analisis</p>", unsafe_allow_html=True)
        st.markdown("""
        <div style="background-color: #eff6ff; border-left: 4px solid #3b82f6; padding: 10px 12px; border-radius: 8px; font-size: 12px; line-height: 1.5; color: #1e3a8a; margin-bottom: 15px;">
            <b style="font-size: 13px;">🚀 Fitur Mendatang (U.Project Nexus Intelligence v3.6):</b>
            <ul style="margin: 6px 0 0 0; padding-left: 18px;">
                <li><b>Server Eksklusif:</b> Engine khusus pemrosesan soal tingkat lanjut</li>
                <li><b>Generator Massal:</b> Buat puluhan/ratusan paket soal HOTS & tematik secara instan</li>
                <li><b>Export Cetak & PDF:</b> Siap cetak ber-template eksklusif sekolah</li>
                <li><b>Analisis Butir Soal:</b> Evaluasi daya pembeda & tingkat kesukaran</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

    with tab3:
        st.markdown("<p style='font-size: 15px; font-weight: bold; margin-bottom: 6px;'>📲 WhatsApp Integration Engine</p>", unsafe_allow_html=True)
        st.markdown("""
        <div style="background-color: #eff6ff; border-left: 4px solid #3b82f6; padding: 10px 12px; border-radius: 8px; font-size: 12px; line-height: 1.5; color: #1e3a8a; margin-bottom: 15px;">
            <b style="font-size: 13px;">⚡ One-Click Automation U.Project Nexus:</b>
            <ul style="margin: 6px 0 0 0; padding-left: 18px;">
                <li><b>Broadcast Hasil Ujian:</b> Laporan nilai otomatis ke WA orang tua & siswa</li>
                <li><b>ChatBot RoboMANTAP 24/7:</b> Asisten tutor pribadi siswa di rumah</li>
                <li><b>Auto-LKPD Guru:</b> Buat LKPD otomatis sesuai template khas sekolah</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # GENERATOR LKPD WORD (.DOCX) EKSKLUSIF BERLOGO
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
                        st.success("✅ Dokumen LKPD Berhasil Dibuat!")
                        
                        st.download_button(
                            label="📥 Download LKPD",
                            data=pdf_buffer,
                            file_name=f"LKPD_{mapel_lkpd}_{topic_lkpd.replace(' ', '_')}_RoboMANTAP.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )

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
            if not st.session_state.nama_siswa.strip():
                st.error("⚠️ Isi nama lengkap kamu dulu ya sebelum mulai!")
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
# 5. ENGINE TEST INTERAKTIF (10 SOAL CBT) + LIVE SYNC DATABASE
# ==============================================================================
elif st.session_state.page == "quiz":
    quiz_data = st.session_state.quiz_data
    curr_idx = st.session_state.current_index
    q = quiz_data[curr_idx]

    col_h1, col_h2 = st.columns([8, 4])
    with col_h1:
        st.subheader(f"📝 CBT OMI: {st.session_state.mapel} ({st.session_state.stage})")
        st.caption(f"👤 Siswa: **{st.session_state.nama_siswa.strip()}**")
    with col_h2:
        st.progress((curr_idx + 1) / 10)
        st.caption(f"Soal **{curr_idx + 1}** dari **10**")

    st.write("---")
    st.markdown(f"#### **Soal No. {curr_idx + 1}**")
    st.markdown(q["question"])
    st.write("")

    opts = q["options"]
    saved_ans = st.session_state.user_answers.get(curr_idx, None)
    default_opt_idx = opts.index(saved_ans) if saved_ans in opts else None

    selected_option = st.radio("Pilih Jawaban Anda:", opts, index=default_opt_idx, key=f"radio_q_{curr_idx}")
    
    # Trigger sinkronisasi jika ada pilihan jawaban yang berubah
    if selected_option and selected_option != saved_ans:
        st.session_state.user_answers[curr_idx] = selected_option
        
        detail = []
        for i in range(10):
            u_ans = st.session_state.user_answers.get(i, None)
            if u_ans is None:
                detail.append(None)
            else:
                is_correct = (u_ans == quiz_data[i]["correct_answer"])
                detail.append(is_correct)
                
        update_progress_siswa(
            st.session_state.session_id, st.session_state.nama_siswa,
            st.session_state.jenjang, st.session_state.mapel, curr_idx + 1, detail, "BERJALAN"
        )

    st.write("---")
    
    col_nav1, col_nav2, col_nav3 = st.columns([3, 6, 3])
    with col_nav1:
        if curr_idx < 9:
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

    # Expander Hint dengan Live Streaming Text
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
# 6. SCORECARD & EVALUASI SESI
# ==============================================================================
elif st.session_state.page == "result":
    st.subheader(f"📊 Evaluasi CBT: {st.session_state.mapel} ({st.session_state.jenjang})")
    quiz_data = st.session_state.quiz_data
    user_answers = st.session_state.user_answers

    benar, salah, kosong, total_skor = 0, 0, 0, 0
    detail = []
    for idx, q in enumerate(quiz_data):
        u_ans = user_answers.get(idx, None)
        if u_ans is None:
            kosong += 1
            detail.append(None)
        elif u_ans == q["correct_answer"]:
            benar += 1
            total_skor += 4
            detail.append(True)
        else:
            salah += 1
            total_skor -= 1
            detail.append(False)

    # Sinkronisasi Final Status SELESAI ke DB Guru
    update_progress_siswa(
        st.session_state.session_id,
        st.session_state.nama_siswa,
        st.session_state.jenjang,
        st.session_state.mapel,
        10,
        detail,
        "SELESAI"
    )

    # Ekstraksi Nama Panggilan
    nama_lengkap = st.session_state.get('nama_siswa', '').strip()
    if nama_lengkap:
        nama_display = nama_lengkap.split()[0]
    else:
        nama_display = "Santri MANTAP"

    if total_skor >= 32:
        feedback_msg = f"🌟 **Luar Biasa! (Skor: {total_skor}/40)**\n\nRoboMANTAP bangga banget sama kamu, **{nama_display}**! Pemahaman kamu di materi {st.session_state.mapel} sudah sangat tajam. Pertahankan fokus kamu untuk Persiapan OMI 2026 ya! 🚀✨"
        feedback_type = "success"
    elif total_skor >= 16:
        feedback_msg = f"👍 **Kerja Bagus! (Skor: {total_skor}/40)**\n\nUsaha yang mantap, **{nama_display}**! Kamu sudah paham sebagian besar konsepnya. Coba cek pembahasan di bawah untuk memperbaiki sedikit kekeliruan tadi ya! 💪😊"
        feedback_type = "info"
    else:
        feedback_msg = f"🌱 **Tetap Semangat, {nama_display}! (Skor: {total_skor}/40)**\n\nJangan berkecil hati ya! Setiap kesalahan adalah proses belajar. Yuk pelajari pembahasan rinci di bawah dan coba latihan 10 soal lagi bersama RoboMANTAP! 🧕🏼❤️"
        feedback_type = "warning"

    # Render Scorecard Modern Grid 2x2
    st.markdown(f"""
    <div class="eval-grid">
        <!-- Kartu Total Skor -->
        <div class="eval-card" style="background: linear-gradient(135deg, rgba(120, 53, 15, 0.45) 0%, rgba(69, 26, 3, 0.75) 100%); border: 1px solid rgba(245, 158, 11, 0.5);">
            <div class="eval-title" style="color: #fde68a;">🏆 Total Skor</div>
            <div class="eval-value" style="color: #fbbf24;">{total_skor} <span style="font-size: 11px; color: #d1d5db;">/ 40</span></div>
        </div>

        <!-- Kartu Benar -->
        <div class="eval-card" style="background: linear-gradient(135deg, rgba(6, 78, 59, 0.45) 0%, rgba(2, 44, 34, 0.75) 100%); border: 1px solid rgba(5, 150, 105, 0.45);">
            <div class="eval-title" style="color: #a7f3d0;">✅ Benar (+4)</div>
            <div class="eval-value" style="color: #34d399;">{benar}</div>
        </div>

        <!-- Kartu Salah -->
        <div class="eval-card" style="background: linear-gradient(135deg, rgba(127, 29, 29, 0.35) 0%, rgba(69, 10, 10, 0.65) 100%); border: 1px solid rgba(239, 68, 68, 0.4);">
            <div class="eval-title" style="color: #fca5a5;">❌ Salah (-1)</div>
            <div class="eval-value" style="color: #f87171;">{salah}</div>
        </div>

        <!-- Kartu Kosong -->
        <div class="eval-card" style="background: linear-gradient(135deg, rgba(55, 65, 81, 0.35) 0%, rgba(31, 41, 55, 0.65) 100%); border: 1px solid rgba(156, 163, 175, 0.35);">
            <div class="eval-title" style="color: #d1d5db;">⚪ Kosong (0)</div>
            <div class="eval-value" style="color: #9ca3af;">{kosong}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if feedback_type == "success":
        st.success(f"🧕🏼 **Pesan dari RoboMANTAP:**\n\n{feedback_msg}")
    elif feedback_type == "info":
        st.info(f"🧕🏼 **Pesan dari RoboMANTAP:**\n\n{feedback_msg}")
    else:
        st.warning(f"🧕🏼 **Pesan dari RoboMANTAP:**\n\n{feedback_msg}")
    st.write("---")
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
        if st.button("⚙️ Pilih Mata Pelajaran Lain", use_container_width=True):
            st.session_state.page = "select_mapel"
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
