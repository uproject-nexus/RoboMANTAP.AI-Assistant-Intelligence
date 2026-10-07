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
    """Build a clean TKA Word document using the Quiz Custom visual conventions."""
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.55)
    section.bottom_margin = Inches(0.55)
    section.left_margin = Inches(0.65)
    section.right_margin = Inches(0.65)

    # Header: compact, centered and consistent with Quiz Custom.
    header_table = doc.add_table(rows=1, cols=2)
    header_table.autofit = False
    cells = header_table.rows[0].cells
    cells[0].width = Inches(1.35)
    cells[1].width = Inches(5.05)
    p_logo = cells[0].paragraphs[0]
    p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    logo_path = "logo.png"
    if os.path.exists(logo_path):
        p_logo.add_run().add_picture(logo_path, width=Inches(1.25))
    else:
        r_logo = p_logo.add_run("RoboMANTAP")
        r_logo.bold = True
        r_logo.font.size = Pt(11)
    p_title = cells[1].paragraphs[0]
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_after = Pt(1)
    r = p_title.add_run("LEMBAR TKA GuruMANTAP\n")
    r.bold = True; r.font.size = Pt(13); r.font.color.rgb = RGBColor(6, 78, 59)
    r = p_title.add_run("Madrasah Aliyah dan Tsanawiyah Al-Irsyad Al-Islamiyah Putri Bondowoso\n")
    r.bold = True; r.font.size = Pt(10)
    now_wib = datetime.utcnow() + timedelta(hours=7)
    nama_bulan = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    r = p_title.add_run(f"Tanggal: {now_wib.day} {nama_bulan[now_wib.month]} {now_wib.year}")
    r.italic = True; r.font.size = Pt(9); r.font.color.rgb = RGBColor(100, 100, 100)

    p_div = doc.add_paragraph()
    p_div.paragraph_format.space_before = Pt(2); p_div.paragraph_format.space_after = Pt(7)
    p_div._p.get_or_add_pPr().append(parse_xml(r'<w:pBdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:bottom w:val="single" w:sz="20" w:space="1" w:color="064E3B"/></w:pBdr>'))

    p_paket = doc.add_paragraph(); p_paket.alignment = WD_ALIGN_PARAGRAPH.CENTER; p_paket.paragraph_format.space_after = Pt(7)
    r = p_paket.add_run(f"PAKET TKA {config.get('mapel', 'MATA UJI').upper()}"); r.bold = True; r.font.size = Pt(13); r.font.color.rgb = RGBColor(6,78,59)

    duration_seconds = int(config.get("timer_seconds") or 0)
    duration_text = f"{duration_seconds // 3600} jam {(duration_seconds % 3600) // 60} menit" if duration_seconds >= 3600 else f"{duration_seconds // 60} menit"
    option_text = "A-D" if str(config.get("jenjang", "MTs")).upper() == "MTs" else "A-E"
    meta_items = [
        ("Jenjang", str(config.get("jenjang", "-"))),
        ("Mata Uji", str(config.get("mapel", "-"))),
        ("Jumlah Soal", f"{len(questions)} Soal | PG/MCMA: {option_text} | Durasi: {duration_text}"),
        ("Masa Aktif TKA", f"{config.get('active_from', '--') or '--'} hingga {config.get('active_until', '--') or '--'} WIB"),
    ]
    meta_table = doc.add_table(rows=0, cols=3); meta_table.autofit = False
    for label, val in meta_items:
        c = meta_table.add_row().cells
        c[0].width = Inches(1.45); c[1].width = Inches(0.2); c[2].width = Inches(4.75)
        p = c[0].paragraphs[0]; rr = p.add_run(label); rr.bold = True; p.paragraph_format.space_after = Pt(1)
        p = c[1].paragraphs[0]; p.add_run(":").bold = True
        p = c[2].paragraphs[0]; p.add_run(val); p.paragraph_format.space_after = Pt(1)

    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    image_cache: dict[str, bytes | None] = {}

    def add_justified(text: str, *, bold_prefix: str | None = None, left_indent: float = 0.0, after: float = 3.0):
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_after = Pt(after)
        if left_indent: p.paragraph_format.left_indent = Inches(left_indent)
        if bold_prefix and text.startswith(bold_prefix):
            p.add_run(bold_prefix).bold = True
            append_text_with_fractions(p, text[len(bold_prefix):])
        else:
            append_text_with_fractions(p, text)
        return p

    for idx, item in enumerate(questions, start=1):
        qtype = str(item.get("question_type") or "PG").upper()
        type_label = {"PG":"Pilihan Ganda", "MCMA":"Pilihan Ganda Kompleks (MCMA)", "KATEGORI":"Pilihan Ganda Kompleks (Kategori)"}.get(qtype, qtype)
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY; p.paragraph_format.space_before = Pt(8); p.paragraph_format.space_after = Pt(2)
        p.add_run(f"{idx}. ").bold = True
        r = p.add_run(f"[{type_label}] "); r.bold = True
        append_text_with_fractions(p, item.get("question", ""))

        stimulus_text = str(item.get("stimulus_text") or "").strip()
        if stimulus_text:
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY; p.paragraph_format.left_indent = Inches(0.18); p.paragraph_format.space_after = Pt(4)
            r = p.add_run("Stimulus: "); r.bold = True
            append_text_with_fractions(p, stimulus_text)

        image_data = item.get("image_data")
        if image_data is None and item.get("image_id"):
            image_key = str(item["image_id"])
            if image_key not in image_cache:
                record = get_tka_image(image_key)
                image_cache[image_key] = record.get("image_data") if record else None
            image_data = image_cache.get(image_key)
        if image_data is not None:
            _add_stimulus_image(doc, image_data)

        if qtype in {"PG", "MCMA"}:
            for opt in item.get("options", []):
                p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY; p.paragraph_format.left_indent = Inches(0.3); p.paragraph_format.space_after = Pt(1)
                append_text_with_fractions(p, str(opt))
            answers = item.get("correct_answers") or item.get("correct_answer") or []
            if isinstance(answers, list):
                answer_text = ", ".join(str(x) for x in answers)
            else:
                answer_text = str(answers)
            add_justified(f"Kunci Jawaban: {answer_text}", bold_prefix="Kunci Jawaban: ", left_indent=0.3, after=2)
        else:
            for pos, category in enumerate(item.get("category_items", []), 1):
                p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY; p.paragraph_format.left_indent = Inches(0.25); p.paragraph_format.space_after = Pt(1)
                p.add_run(f"{pos}. ").bold = True
                append_text_with_fractions(p, str(category.get("statement", "")))
                p2 = doc.add_paragraph(); p2.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY; p2.paragraph_format.left_indent = Inches(0.45); p2.paragraph_format.space_after = Pt(2)
                p2.add_run("Respons: ").bold = True
                append_text_with_fractions(p2, " / ".join(str(x) for x in (category.get("options") or [])))
            answers = item.get("correct_answers") or item.get("correct_answer") or []
            add_justified("Kunci Kategori: " + " | ".join(str(x) for x in (answers if isinstance(answers, list) else [answers])), left_indent=0.3, after=2)

        if item.get("solution_basis"):
            add_justified("Pembahasan: " + str(item.get("solution_basis")), bold_prefix="Pembahasan: ", left_indent=0.3, after=9)

    buffer = io.BytesIO(); doc.save(buffer); buffer.seek(0); return buffer.getvalue()
