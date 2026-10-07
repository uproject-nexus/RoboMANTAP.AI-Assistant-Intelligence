from __future__ import annotations

import io
import os
from datetime import datetime, timedelta

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Inches, Pt, RGBColor

from ai_engine import append_text_with_fractions, clean_math_string
from tka_engine import get_tka_image


IMAGE_WIDTH_IN = 7 / 2.54
IMAGE_HEIGHT_IN = 13 / 2.54


def _add_stimulus_image(doc: Document, image_data) -> None:
    if image_data is None:
        return
    if isinstance(image_data, memoryview):
        image_data = image_data.tobytes()
    elif isinstance(image_data, bytearray):
        image_data = bytes(image_data)
    if not isinstance(image_data, bytes):
        return
    try:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(6)
        p.add_run().add_picture(io.BytesIO(image_data), width=Inches(IMAGE_WIDTH_IN), height=Inches(IMAGE_HEIGHT_IN))
    except Exception:
        return


def build_tka_docx(config: dict, questions: list[dict]) -> bytes:
    """TKA DOCX renderer aligned to the existing Quiz Custom Word layout."""
    doc = Document()

    header_table = doc.add_table(rows=1, cols=2)
    header_table.autofit = False
    cells = header_table.rows[0].cells
    cells[0].width = Inches(1.6)
    cells[1].width = Inches(4.7)
    cells[0].vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    cells[1].vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    p_logo = cells[0].paragraphs[0]
    p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    logo_path = "logo.png"
    if os.path.exists(logo_path):
        p_logo.add_run().add_picture(logo_path, width=Inches(1.5))
    else:
        r_logo = p_logo.add_run("[LOGO MANTAP]")
        r_logo.bold = True
        r_logo.font.size = Pt(12)
        r_logo.font.color.rgb = RGBColor(6, 78, 59)

    p_title = cells[1].paragraphs[0]
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_after = Pt(2)
    r1 = p_title.add_run("LEMBAR TKA GuruMANTAP\n")
    r1.bold = True
    r1.font.size = Pt(13)
    r1.font.color.rgb = RGBColor(6, 78, 59)
    r2 = p_title.add_run("Madrasah Aliyah dan Tsanawiyah Al-Irsyad Al-Islamiyah Putri Bondowoso\n")
    r2.bold = True
    r2.font.size = Pt(10.5)
    now_wib = datetime.utcnow() + timedelta(hours=7)
    nama_bulan = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    r3 = p_title.add_run(f"Tanggal: {now_wib.day} {nama_bulan[now_wib.month]} {now_wib.year}")
    r3.italic = True
    r3.font.size = Pt(9.5)
    r3.font.color.rgb = RGBColor(100, 100, 100)

    p_div = doc.add_paragraph()
    p_div.paragraph_format.space_before = Pt(4)
    p_div.paragraph_format.space_after = Pt(10)
    p_bdr = parse_xml(
        r'<w:pBdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        r'<w:bottom w:val="single" w:sz="20" w:space="1" w:color="064E3B"/>'
        r'</w:pBdr>'
    )
    p_div._p.get_or_add_pPr().append(p_bdr)

    p_paket = doc.add_paragraph()
    p_paket.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_paket.paragraph_format.space_after = Pt(10)
    r_paket = p_paket.add_run(f"PAKET TKA {config.get('mapel', 'MATA UJI').upper()}")
    r_paket.bold = True
    r_paket.font.size = Pt(13)
    r_paket.font.color.rgb = RGBColor(6, 78, 59)

    duration = timedelta(seconds=int(config.get("timer_seconds") or 0))
    option_text = "A-D" if str(config.get("jenjang", "MTs")).upper() == "MTs" else "A-E"
    meta_items = [
        ("Jenjang", str(config.get("jenjang", "-"))),
        ("Mata Uji", str(config.get("mapel", "-"))),
        ("Jumlah Soal", f"{len(questions)} Soal | Opsi: {option_text} | Durasi: {duration}"),
        ("Masa Aktif TKA", f"{config.get('active_from', '--') or '--'} hingga {config.get('active_until', '--') or '--'} WIB"),
    ]

    meta_table = doc.add_table(rows=0, cols=3)
    meta_table.autofit = False
    for label, val in meta_items:
        row_cells = meta_table.add_row().cells
        p0 = row_cells[0].paragraphs[0]
        r0 = p0.add_run(label)
        r0.bold = True
        p0.paragraph_format.space_before = Pt(2)
        p0.paragraph_format.space_after = Pt(2)
        row_cells[0].width = Inches(1.5)
        p1 = row_cells[1].paragraphs[0]
        r1 = p1.add_run(":")
        r1.bold = True
        p1.paragraph_format.space_before = Pt(2)
        p1.paragraph_format.space_after = Pt(2)
        row_cells[1].width = Inches(0.2)
        p2 = row_cells[2].paragraphs[0]
        p2.add_run(val)
        p2.paragraph_format.space_before = Pt(2)
        p2.paragraph_format.space_after = Pt(2)
        row_cells[2].width = Inches(4.8)

    p_space = doc.add_paragraph()
    p_space.paragraph_format.space_before = Pt(12)
    p_space.paragraph_format.space_after = Pt(4)

    image_cache: dict[str, bytes] = {}

    for idx, item in enumerate(questions, start=1):
        p_q = doc.add_paragraph()
        p_q.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p_q.paragraph_format.space_before = Pt(8)
        p_q.paragraph_format.space_after = Pt(4)
        p_q.add_run(f"Soal {idx}. ").bold = True
        append_text_with_fractions(p_q, item.get("question", ""), is_bold=True)

        # Satu stimulus saja untuk setiap nomor soal; stimulus yang sama boleh direferensikan oleh beberapa nomor.
        image_data = item.get("image_data")
        if image_data is None and item.get("image_id"):
            image_key = str(item["image_id"])
            if image_key not in image_cache:
                record = get_tka_image(image_key)
                image_cache[image_key] = record.get("image_data") if record else None
            image_data = image_cache.get(image_key)
        if image_data is not None:
            _add_stimulus_image(doc, image_data)

        for opt in item.get("options", []):
            p_opt = doc.add_paragraph()
            p_opt.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p_opt.paragraph_format.left_indent = Inches(0.25)
            p_opt.paragraph_format.space_after = Pt(2)
            append_text_with_fractions(p_opt, opt)

        p_ans = doc.add_paragraph()
        p_ans.paragraph_format.left_indent = Inches(0.25)
        p_ans.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p_ans.add_run("Kunci Jawaban: ").bold = True
        append_text_with_fractions(p_ans, item.get("correct_answer", ""), is_bold=True, color_rgb=RGBColor(5, 150, 105))

        if item.get("solution_basis"):
            p_sol = doc.add_paragraph()
            p_sol.paragraph_format.left_indent = Inches(0.25)
            p_sol.paragraph_format.space_after = Pt(12)
            p_sol.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p_sol.add_run("Pembahasan: ").bold = True
            append_text_with_fractions(p_sol, item.get("solution_basis", ""))

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
