from __future__ import annotations

import io
import os
import re
from datetime import datetime, timedelta

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Inches, Pt, RGBColor

from ai_engine import append_text_with_fractions, clean_math_string
from tka_engine import get_tka_image


def _format_date_wib(iso_str: str | None) -> str:
    """Mengubah string ISO date menjadi format tanggal WIB yang rapi."""
    if not iso_str or str(iso_str).strip() in {"--", "None", ""}:
        return "--"
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        nama_bulan = [
            "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember"
        ]
        return f"{dt.day} {nama_bulan[dt.month]} {dt.year}, {dt.strftime('%H:%M')} WIB"
    except Exception:
        return str(iso_str)


def _clean_docx_text(val: str | None) -> str:
    """Membersihkan literal escape sequence dan artefak LaTeX buatan AI."""
    if not val:
        return ""
    s = str(val).replace("\\n", "\n").replace("\r\n", "\n")

    # Bersihkan artefak LaTeX / text command
    s = re.sub(r"\\text\{([^}]+)\}", r"\1", s)
    s = re.sub(r"tte?ₓ?st?([a-zA-Z]+)", r"\1", s)
    s = re.sub(r"\btext\s+([a-zA-Z0-9³²]+)", r"\1", s)
    s = re.sub(r"\\approx", "≈", s)
    s = re.sub(r"\bapprox\b", "≈", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _clean_solution_basis(val: str | None) -> str:
    """Membersihkan pembahasan dari coretan trial-and-error / self-correction AI."""
    s = _clean_docx_text(val)
    if not s:
        return ""
    lines = s.split("\n")
    cleaned = []
    for line in lines:
        l_str = line.strip().lower()
        if any(
            l_str.startswith(p)
            for p in [
                "koreksi opsi",
                "mari periksa kembali",
                "mari cek ulang",
                "terdapat ketidaksesuaian",
                "salah, harusnya",
                "koreksi:",
            ]
        ):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _add_stimulus_image(
    doc: Document,
    image_data: bytes | memoryview | bytearray | None,
    caption: str | None = None,
) -> None:
    """Menambahkan gambar stimulus ke dokumen Word dengan aspek rasio yang proporsional."""
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
        p.paragraph_format.space_after = Pt(2 if caption else 6)

        run = p.add_run()
        # Mengunci lebar 3.5 inci tanpa memaksa tinggi agar aspek rasio terjaga sempurna
        run.add_picture(io.BytesIO(image_data), width=Inches(3.5))

        if caption:
            p_cap = doc.add_paragraph()
            p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_cap.paragraph_format.space_before = Pt(1)
            p_cap.paragraph_format.space_after = Pt(6)
            r_cap = p_cap.add_run(caption)
            r_cap.italic = True
            r_cap.font.size = Pt(8.5)
            r_cap.font.color.rgb = RGBColor(100, 100, 100)
    except Exception as exc:
        print(f"[DOCX IMAGE ADD ERROR] {exc}")


def build_tka_docx(config: dict, questions: list[dict]) -> bytes:
    """Membangun dokumen Word TKA yang rapi, presisi, dan sesuai standar resmi."""
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.55)
    section.bottom_margin = Inches(0.55)
    section.left_margin = Inches(0.65)
    section.right_margin = Inches(0.65)

    # Header Dokumen & Logo
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
    r.bold = True
    r.font.size = Pt(13)
    r.font.color.rgb = RGBColor(6, 78, 59)

    r = p_title.add_run("Madrasah Aliyah dan Tsanawiyah Al-Irsyad Al-Islamiyah Putri Bondowoso\n")
    r.bold = True
    r.font.size = Pt(10)

    now_wib = datetime.utcnow() + timedelta(hours=7)
    nama_bulan = [
        "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]
    r = p_title.add_run(f"Tanggal: {now_wib.day} {nama_bulan[now_wib.month]} {now_wib.year}")
    r.italic = True
    r.font.size = Pt(9)
    r.font.color.rgb = RGBColor(100, 100, 100)

    # Garis Pembatas Header
    p_div = doc.add_paragraph()
    p_div.paragraph_format.space_before = Pt(2)
    p_div.paragraph_format.space_after = Pt(7)
    p_div._p.get_or_add_pPr().append(
        parse_xml(
            r'<w:pBdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            r'<w:bottom w:val="single" w:sz="20" w:space="1" w:color="064E3B"/>'
            r'</w:pBdr>'
        )
    )

    # Judul Paket TKA
    p_paket = doc.add_paragraph()
    p_paket.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_paket.paragraph_format.space_after = Pt(7)
    r = p_paket.add_run(f"PAKET TKA {config.get('mapel', 'MATA UJI').upper()}")
    r.bold = True
    r.font.size = Pt(13)
    r.font.color.rgb = RGBColor(6, 78, 59)

    duration_seconds = int(config.get("timer_seconds") or 0)
    duration_text = (
        f"{duration_seconds // 3600} jam {(duration_seconds % 3600) // 60} menit"
        if duration_seconds >= 3600
        else f"{duration_seconds // 60} menit"
    )
    option_text = "A-D" if str(config.get("jenjang", "MTs")).upper() == "MTs" else "A-E"

    active_from_formatted = _format_date_wib(config.get("active_from"))
    active_until_formatted = _format_date_wib(config.get("active_until"))
    active_range_text = (
        f"{active_from_formatted} hingga {active_until_formatted}"
        if active_from_formatted != "--"
        else "Ditentukan Saat Diterbitkan"
    )

    meta_items = [
        ("Jenjang", str(config.get("jenjang", "-"))),
        ("Mata Uji", str(config.get("mapel", "-"))),
        ("Jumlah Soal", f"{len(questions)} Soal | PG/MCMA: {option_text} | Durasi: {duration_text}"),
        ("Masa Aktif TKA", active_range_text),
    ]

    meta_table = doc.add_table(rows=0, cols=3)
    meta_table.autofit = False
    for label, val in meta_items:
        c = meta_table.add_row().cells
        c[0].width = Inches(1.45)
        c[1].width = Inches(0.2)
        c[2].width = Inches(4.75)

        p = c[0].paragraphs[0]
        rr = p.add_run(label)
        rr.bold = True
        p.paragraph_format.space_after = Pt(1)

        p = c[1].paragraphs[0]
        p.add_run(":").bold = True

        p = c[2].paragraphs[0]
        p.add_run(val)
        p.paragraph_format.space_after = Pt(1)

    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    image_cache: dict[str, bytes | None] = {}

    def add_justified(
        text: str,
        *,
        bold_prefix: str | None = None,
        left_indent: float = 0.0,
        after: float = 3.0,
    ):
        cleaned_text = _clean_docx_text(text)
        if not cleaned_text:
            return

        paragraphs = cleaned_text.split("\n")
        for i, p_text in enumerate(paragraphs):
            p_text = p_text.strip()
            if not p_text:
                continue

            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.space_after = Pt(
                after if i == len(paragraphs) - 1 else 1.5
            )
            if left_indent:
                p.paragraph_format.left_indent = Inches(left_indent)

            if i == 0 and bold_prefix and p_text.startswith(bold_prefix):
                p.add_run(bold_prefix).bold = True
                append_text_with_fractions(p, p_text[len(bold_prefix) :])
            else:
                append_text_with_fractions(p, p_text)

    # Render Butir Soal
    for idx, item in enumerate(questions, start=1):
        qtype = str(item.get("question_type") or "PG").upper()
        type_label = {
            "PG": "Pilihan Ganda",
            "MCMA": "Pilihan Ganda Kompleks (MCMA)",
            "KATEGORI": "Pilihan Ganda Kompleks (Kategori)",
        }.get(qtype, qtype)

        question_text = _clean_docx_text(item.get("question"))
        stimulus_text = _clean_docx_text(item.get("stimulus_text"))

        # Deduplikasi jika stimulus_text sudah tercantum di dalam question
        if stimulus_text and (
            stimulus_text in question_text or question_text.startswith(stimulus_text)
        ):
            stimulus_text = ""

        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(2)
        p.add_run(f"{idx}. ").bold = True
        r = p.add_run(f"[{type_label}] ")
        r.bold = True
        append_text_with_fractions(p, question_text)

        if stimulus_text:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.left_indent = Inches(0.18)
            p.paragraph_format.space_after = Pt(4)
            r = p.add_run("Stimulus: ")
            r.bold = True
            append_text_with_fractions(p, stimulus_text)

        # Penanganan Gambar Presisi (Single vs Multi-Image)
        single_id = item.get("image_id")
        raw_image_ids = item.get("image_ids") or []
        images_to_render: list[tuple[bytes, str]] = []

        if (
            single_id
            and str(single_id).strip()
            and str(single_id).lower() not in {"null", "none"}
        ):
            s_id = str(single_id).strip()
            if s_id not in image_cache:
                rec = get_tka_image(s_id)
                image_cache[s_id] = rec.get("image_data") if rec else None
            img_bytes = image_cache.get(s_id)
            if img_bytes:
                no_str = "Gambar Stimulus"
                if isinstance(raw_image_ids, list):
                    for elem in raw_image_ids:
                        if isinstance(elem, dict) and str(elem.get("id")) == s_id:
                            if elem.get("no"):
                                no_str = f"Gambar {elem.get('no')}"
                            break
                images_to_render.append((img_bytes, no_str))

        elif raw_image_ids and isinstance(raw_image_ids, list):
            for idx_img, elem in enumerate(raw_image_ids, 1):
                img_id = str(
                    elem.get("id") if isinstance(elem, dict) else elem
                ).strip()
                no_num = elem.get("no") if isinstance(elem, dict) else idx_img
                if img_id and img_id.lower() not in {"null", "none"}:
                    if img_id not in image_cache:
                        rec = get_tka_image(img_id)
                        image_cache[img_id] = rec.get("image_data") if rec else None
                    img_bytes = image_cache.get(img_id)
                    if img_bytes:
                        images_to_render.append((img_bytes, f"Gambar {no_num}"))

        elif item.get("image_data"):
            images_to_render.append((item.get("image_data"), "Gambar Stimulus"))

        for img_bytes, cap_text in images_to_render:
            _add_stimulus_image(doc, img_bytes, caption=cap_text)

        # Opsi & Kunci Jawaban
        if qtype in {"PG", "MCMA"}:
            for opt in item.get("options", []):
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                p.paragraph_format.left_indent = Inches(0.3)
                p.paragraph_format.space_after = Pt(1)
                append_text_with_fractions(p, _clean_docx_text(str(opt)))

            answers = item.get("correct_answers") or item.get("correct_answer") or []
            if isinstance(answers, list):
                answer_text = ", ".join(str(x) for x in sorted(answers))
            else:
                answer_text = str(answers)

            add_justified(
                f"Kunci Jawaban: {answer_text}",
                bold_prefix="Kunci Jawaban: ",
                left_indent=0.3,
                after=2,
            )
        else:
            for pos, category in enumerate(item.get("category_items", []), 1):
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                p.paragraph_format.left_indent = Inches(0.25)
                p.paragraph_format.space_after = Pt(1)
                p.add_run(f"{pos}. ").bold = True
                append_text_with_fractions(
                    p, _clean_docx_text(str(category.get("statement", "")))
                )

                p2 = doc.add_paragraph()
                p2.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                p2.paragraph_format.left_indent = Inches(0.45)
                p2.paragraph_format.space_after = Pt(2)
                p2.add_run("Respons: ").bold = True
                append_text_with_fractions(
                    p2,
                    " / ".join(
                        str(x) for x in (category.get("options") or [])
                    ),
                )

            answers = item.get("correct_answers") or item.get("correct_answer") or []
            add_justified(
                "Kunci Kategori: "
                + " | ".join(
                    str(x)
                    for x in (answers if isinstance(answers, list) else [answers])
                ),
                bold_prefix="Kunci Kategori: ",
                left_indent=0.3,
                after=2,
            )

        # Pembahasan Bersih
        sol_text = _clean_solution_basis(item.get("solution_basis"))
        if sol_text:
            add_justified(
                "Pembahasan: " + sol_text,
                bold_prefix="Pembahasan: ",
                left_indent=0.3,
                after=9,
            )

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
