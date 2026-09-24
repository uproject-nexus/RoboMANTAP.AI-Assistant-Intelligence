"""LKPD PDF renderer. Extracted from the stable legacy renderer without behavior redesign."""
from __future__ import annotations
import io, os, re
from datetime import datetime, timedelta, timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def draw_cover_background(canvas_obj, doc):
    canvas_obj.saveState()
    cover_path = "cover.png"
    if os.path.exists(cover_path):
        canvas_obj.drawImage(cover_path, 0, 0, width=A4[0], height=A4[1])
    canvas_obj.restoreState()

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

def create_lkpd_pdf_buffer(mapel, kelas, topik, ai_content, logo_path="logo.png"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=2.0 * cm, rightMargin=2.0 * cm,
        topMargin=2.0 * cm, bottomMargin=2.0 * cm
    )
    styles = getSampleStyleSheet()
    
    # Ambil Tanggal Presisi WIB saat PDF dibuat
    now_wib = datetime.now(timezone.utc) + timedelta(hours=7)
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

