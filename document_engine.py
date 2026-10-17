"""Document and export engines for RoboMANTAP-Intelligence.

Contains the legacy DOCX/PDF layout helpers, isolated from the Streamlit page
router so page navigation does not make the main entrypoint even larger.
"""
import html
import io
import os
import re
import tempfile
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Pt, RGBColor, Inches
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, PageBreak, Image)
from ai_engine import option_count_for_jenjang, normalize_custom_timer_config
from ui_theme import now_wib

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
        r"\implies": "⇒",
        r"\impliedby": "⇐",
        r"\iff": "⇔",
        r"\Longleftrightarrow": "⇔",
        r"\longleftrightarrow": "↔",
        r"\Longleftarrow": "⇐",
        r"\Longrightarrow": "⇒",
        
        r"\approx": "≈",
        r"\equiv": "≡",
        r"\propto": "∝",
        
        r"\sum": "Σ",
        r"\prod": "Π",
        r"\int": "∫",
        r"\partial": "∂",
        r"\nabla": "∇",
        
        r"\Delta": "Δ",
        r"\Omega": "Ω",
        r"\Gamma": "Γ",
        r"\Lambda": "Λ",
        r"\Sigma": "Σ",
        r"\Phi": "Φ",
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
    generated_at_wib = now_wib()
    nama_bulan = [
        "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]
    tgl_presisi = f"{generated_at_wib.day} {nama_bulan[generated_at_wib.month]} {generated_at_wib.year}"
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
    generated_at_wib = now_wib()
    nama_bulan = [
        "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]
    tgl_presisi = f"{generated_at_wib.day} {nama_bulan[generated_at_wib.month]} {generated_at_wib.year}"
    
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
