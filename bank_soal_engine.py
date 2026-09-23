"""
RoboMANTAP • Bank Soal / Blueprint Engine
------------------------------------------
Pipeline:
Kisi-kisi DOCX -> deterministic table extraction -> normalized blueprint
-> variant generation -> blueprint QA -> premium DOCX.
"""

from __future__ import annotations

import io
import os
import re
import json
import math
import html
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn, nsdecls
from xml.sax.saxutils import escape

from ai_engine import call_gemini_with_rotation, clean_json_text, _call_gemini_contents
from google.genai import types


FORM_ORDER = ("PG", "Isian", "Uraian")
COGNITIVE_LEVELS = ("C1", "C2", "C3", "C4", "C5", "C6")


def _normalize_cognitive_level(value: Any) -> str:
    """Normalize explicit Bloom/cognitive labels such as C4, C-4, C4 (Analisis).

    Multiple levels are preserved as a slash-separated value so the source
    blueprint is not silently rewritten.
    """
    text = _clean(value).upper()
    if not text:
        return ""
    found = []
    for n in re.findall(r"\bC\s*[-–]?\s*([1-6])\b", text):
        label = f"C{n}"
        if label not in found:
            found.append(label)
    return "/".join(found)


def _cognitive_levels(value: Any) -> list[str]:
    normalized = _normalize_cognitive_level(value)
    return [x for x in normalized.split("/") if x in COGNITIVE_LEVELS]


def _find_cognitive_column(rows: list[list[str]], search_upto: int) -> int | None:
    """Find an explicit cognitive-level column without guessing from content."""
    labels = (
        "LEVEL KOGNITIF", "TINGKAT KOGNITIF", "KOGNITIF",
        "TAKSONOMI BLOOM", "TAKSONOMI", "LEVEL KOGNISI", "LEVEL SOAL",
        "TINGKAT KESULITAN", "LEVEL KESULITAN", "LEVEL",
    )
    for row in rows[: max(1, search_upto + 1)]:
        for idx, cell in enumerate(row):
            value = _clean(cell).upper()
            if any(label in value for label in labels):
                return idx
    return None


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()

def clean_math_string(text: str) -> str:
    """Same math-cleaning logic used by the existing Quiz DOCX renderer.

    Bank Soal intentionally shares this renderer so fractions, matrices,
    inverses, composition symbols and escaped newlines behave the same way.
    """
    if not text:
        return ""
    text = str(text)

    # Literal and actual newlines must never leak into the Word document.
    text = text.replace("\\r\\n", " ").replace("\\n", " ").replace("\\r", " ")
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")

    replacements = {
        r"\rightarrow": "→", r"\to": "→", r"\Rightarrow": "⇒",
        r"\leftarrow": "←", r"\leftrightarrow": "↔",
        r"\Longleftrightarrow": "⇔", r"\longleftrightarrow": "↔",
        r"\Longleftarrow": "⇐", r"\Longrightarrow": "⇒",
        r"\implies": "⇒", r"\impliedby": "⇐", r"\iff": "⇔",
        r"\circ": "∘", r"\circl": "∘",
        r"\times": "×", r"\cdot": "·", r"\div": "÷", r"\neq": "≠",
        r"\leq": "≤", r"\geq": "≥", r"\le": "≤", r"\ge": "≥",
        r"\pm": "±", r"\mp": "∓", r"\infty": "∞", r"\pi": "π",
        r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
        r"\theta": "θ", r"\lambda": "λ", r"\mu": "μ", r"\sigma": "σ",
        r"\in": "∈", r"\notin": "∉", r"\forall": "∀", r"\exists": "∃",
        r"\emptyset": "∅", r"\angle": "∠", r"\perp": "⊥", r"\parallel": "∥",
        r"\approx": "≈", r"\equiv": "≡", r"\propto": "∝",
        r"\sum": "Σ", r"\prod": "Π", r"\int": "∫", r"\partial": "∂", r"\nabla": "∇",
        r"\Delta": "Δ", r"\Omega": "Ω", r"\Gamma": "Γ", r"\Lambda": "Λ",
        r"\Sigma": "Σ", r"\Phi": "Φ", r"\degree": "°",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"(?<![A-Za-z])circl(?![A-Za-z])", "∘", text)
    text = re.sub(r"\\left\b\s*[\(\[\{\.\|]?", "(", text)
    text = re.sub(r"\\right\b\s*[\)\]\}\.\|]?", ")", text)
    text = re.sub(r"\\(?:dots|cdots|ldots)", "…", text)
    text = re.sub(r"\\sqrt\{([^}]+)\}", r"√(\1)", text)
    text = re.sub(r"\\sqrt\s*([a-zA-Z0-9_]+)", r"√\1", text)
    sup_map = str.maketrans("0123456789+-=()nxyi", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿˣʸⁱ")
    sub_map = str.maketrans("0123456789+-=()nixy", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₙᵢₓᵧ")
    text = re.sub(r"\^\{([^}]+)\}|\^([\-0-9a-zA-Z])", lambda m: (m.group(1) or m.group(2)).translate(sup_map), text)
    text = re.sub(r"_\{([^}]+)\}|_([0-9a-zA-Z])", lambda m: (m.group(1) or m.group(2)).translate(sub_map), text)
    text = text.replace("$", "")
    text = text.replace("left(", "(").replace("right)", ")").replace("dots", "…")
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"\\([a-zA-Z]+)", r"\1", text).replace("\\", "")
    return re.sub(r"\s+", " ", text).strip()


def contains_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]", str(text or "")))


def apply_arabic_paragraph_style(paragraph):
    try:
        ppr = paragraph._p.get_or_add_pPr()
        bidi = parse_xml(r'<w:bidi xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" w:val="1"/>')
        ppr.append(bidi)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    except Exception:
        pass


def apply_arabic_run_style(run):
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
    num_clean = clean_math_string(num_text)
    den_clean = clean_math_string(den_text)
    omml_xml = (
        f'<m:oMath {nsdecls("m")}>'
        f'<m:f>'
        f'<m:num><m:r><m:t>{escape(num_clean)}</m:t></m:r></m:num>'
        f'<m:den><m:r><m:t>{escape(den_clean)}</m:t></m:r></m:den>'
        f'</m:f>'
        f'</m:oMath>'
    )
    paragraph._p.append(parse_xml(omml_xml))


def add_omml_matrix(paragraph, matrix_type: str, content: str):
    beg_chr, end_chr = "(", ")"
    if matrix_type == "bmatrix":
        beg_chr, end_chr = "[", "]"
    elif matrix_type in ["vmatrix", "Vmatrix"]:
        beg_chr, end_chr = "|", "|"
    elif matrix_type == "matrix":
        beg_chr, end_chr = "", ""
    rows = [r.strip() for r in re.split(r"\\\\|\\cr", content) if r.strip()]
    matrix_xml_rows = []
    for row in rows:
        cols = [c.strip() for c in row.split("&")]
        cols_xml = []
        for col in cols:
            cleaned = html.escape(clean_math_string(col))
            cols_xml.append(f'<m:e><m:r><m:t>{cleaned}</m:t></m:r></m:e>')
        matrix_xml_rows.append(f'<m:mr>{"".join(cols_xml)}</m:mr>')
    inner_matrix = f'<m:m>{"".join(matrix_xml_rows)}</m:m>'
    if beg_chr or end_chr:
        omml_xml = (
            f'<m:oMath {nsdecls("m")}><m:d><m:dPr>'
            f'<m:begChr m:val="{escape(beg_chr)}"/><m:endChr m:val="{escape(end_chr)}"/>'
            f'</m:dPr><m:e>{inner_matrix}</m:e></m:d></m:oMath>'
        )
    else:
        omml_xml = f'<m:oMath {nsdecls("m")}>{inner_matrix}</m:oMath>'
    paragraph._p.append(parse_xml(omml_xml))


def append_text_with_fractions(paragraph, text: str, is_bold: bool = False, color_rgb: RGBColor = None):
    """Shared Quiz DOCX math renderer: plain text + vertical fractions + matrices."""
    if not text:
        return
    text = str(text)
    math_pattern = re.compile(
        r"\\begin\{(?P<mtype>[pbvV]?matrix)\}(?P<mcontent>.*?)\\end\{(?P=mtype)\}|\\(?:f|tf)rac\{(?P<num>[^}]+)\}\{(?P<den>[^}]+)\}",
        re.DOTALL,
    )
    last_idx = 0
    for match in math_pattern.finditer(text):
        start, end = match.span()
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
        if match.group("mtype"):
            add_omml_matrix(paragraph, match.group("mtype"), match.group("mcontent"))
        elif match.group("num"):
            add_omml_fraction(paragraph, match.group("num"), match.group("den"))
        run_space = paragraph.add_run(" ")
        run_space.bold = is_bold
        last_idx = end
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


def _cell_clean(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ")
    # Merged cells in Word can expose duplicated line fragments.
    parts = [_clean(p) for p in text.splitlines() if _clean(p)]
    if not parts:
        return ""
    return parts[0] if all(p == parts[0] for p in parts) else " ".join(parts)


def _parse_question_numbers(value: str) -> list[int]:
    """Parse 1, 1–2, 1-3 and similar blueprint numbering."""
    raw = _clean(value).replace("—", "-").replace("–", "-")
    if not raw:
        return []
    numbers: list[int] = []
    for chunk in re.split(r"[,;/]+", raw):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", chunk)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            if end >= start and end - start <= 200:
                numbers.extend(range(start, end + 1))
            continue
        for n in re.findall(r"\d+", chunk):
            numbers.append(int(n))
    return list(dict.fromkeys(numbers))


def _is_chapter_row(cells: list[str]) -> bool:
    first = _clean(cells[0]) if cells else ""
    if not first.upper().startswith("BAB "):
        return False
    nonempty = [_clean(x).upper() for x in cells[:3] if _clean(x)]
    return len(nonempty) >= 2 and len(set(nonempty)) == 1


def _looks_like_header(cells: list[str]) -> bool:
    joined = " ".join(_clean(x).upper() for x in cells)
    return "ATP" in joined and "INDIKATOR" in joined


def _looks_like_form_header(cells: list[str]) -> bool:
    return any(_clean(x).upper() in FORM_ORDER for x in cells)


def extract_blueprint_from_docx(file_bytes: bytes) -> dict:
    """
    Extract the blueprint from the actual DOCX table structure.
    This intentionally uses table cells rather than flattened paragraph text,
    because merged/header cells are meaningful in a school blueprint.
    """
    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [_clean(p.text) for p in doc.paragraphs if _clean(p.text)]

    title = " ".join(paragraphs[:4])
    grade_match = re.search(r"(?:KELAS|TINGKAT)\s+([IVXLC0-9]+)", title, re.I)
    year_match = re.search(r"(20\d{2}\s*[-–]\s*20\d{2})", title)
    subject_match = re.search(r"KISI\s*[–-]\s*KISI\s+([A-ZÀ-ÖØ-Ýa-zà-öø-ÿ ]+?)(?:\s+KELAS|\s*$)", title, re.I)
    assessment_match = re.search(
        r"(SUMATIF.*?)(?:\s+TAHUN|\s*$)", title, re.I
    )

    metadata = {
        "subject": _clean(subject_match.group(1)) if subject_match else "",
        "grade": grade_match.group(1) if grade_match else "",
        "assessment": _clean(assessment_match.group(1)) if assessment_match else "",
        "school_year": year_match.group(1).replace("–", "-").replace(" ", "") if year_match else "",
        "title": title,
    }

    table = doc.tables[0] if doc.tables else None
    if table is None:
        return {
            "metadata": metadata,
            "blueprints": [],
            "warnings": ["Tidak ditemukan tabel kisi-kisi di dalam DOCX."],
            "source_type": "docx",
        }

    # Locate the two header rows.
    header_idx = None
    form_idx = None
    for idx, row in enumerate(table.rows[:6]):
        cells = [_cell_clean(c.text) for c in row.cells]
        if _looks_like_header(cells):
            header_idx = idx
        if _looks_like_form_header(cells):
            form_idx = idx

    if header_idx is None:
        header_idx = 0
    if form_idx is None:
        form_idx = min(header_idx + 1, len(table.rows) - 1)

    header_rows = [
        [_cell_clean(c.text) for c in table.rows[idx].cells]
        for idx in range(min(len(table.rows), max(6, form_idx + 1)))
    ]
    cognitive_col = _find_cognitive_column(header_rows, form_idx)

    header_cells = [_cell_clean(c.text).upper() for c in table.rows[form_idx].cells]
    form_columns: dict[int, str] = {}
    for col, value in enumerate(header_cells):
        normalized = value.strip().upper()
        if normalized == "PG":
            form_columns[col] = "PG"
        elif normalized == "ISIAN":
            form_columns[col] = "Isian"
        elif normalized == "URAIAN":
            form_columns[col] = "Uraian"

    if not form_columns:
        # Fallback based on the known conventional layout: NO, ATP, INDIKATOR, PG, Isian, Uraian
        form_columns = {3: "PG", 4: "Isian", 5: "Uraian"}

    current_chapter = ""
    current_cognitive_level = ""
    blueprints: list[dict] = []
    bp_counter = 0

    for row_idx, row in enumerate(table.rows):
        if row_idx <= form_idx:
            continue
        cells = [_cell_clean(c.text) for c in row.cells]
        if not any(cells):
            continue

        if _is_chapter_row(cells):
            current_chapter = _clean(cells[0])
            continue

        # Ignore any accidental repeated header rows.
        if _looks_like_header(cells) or _looks_like_form_header(cells):
            continue

        no = _clean(cells[0]) if len(cells) > 0 else ""
        atp = _clean(cells[1]) if len(cells) > 1 else ""
        indicator = _clean(cells[2]) if len(cells) > 2 else ""

        cognitive_level = ""
        if cognitive_col is not None and cognitive_col < len(cells):
            cognitive_level = _normalize_cognitive_level(cells[cognitive_col])
            if cognitive_level:
                current_cognitive_level = cognitive_level
            elif current_cognitive_level:
                # Supports vertically merged Word cells represented as blank
                # values on continuation rows. This is only used when an
                # explicit cognitive-level column was detected.
                cognitive_level = current_cognitive_level

        if not indicator and not atp:
            continue

        # A Word merge can duplicate the chapter number as "1 1 1".
        # The actual indicator/ATP are the authoritative fields.
        forms: dict[str, list[int]] = {f: [] for f in FORM_ORDER}
        for col, form in form_columns.items():
            if col < len(cells):
                forms[form] = _parse_question_numbers(cells[col])

        if not any(forms.values()):
            # A row without question numbers is not a generation target.
            continue

        bp_counter += 1
        blueprints.append({
            "id": f"BP-{bp_counter:03d}",
            "chapter": current_chapter,
            "source_row": row_idx + 1,
            "no": no,
            "atp": atp,
            "indicator": indicator,
            "cognitive_level": cognitive_level,
            "cognitive_level_source": _clean(cells[cognitive_col]) if cognitive_col is not None and cognitive_col < len(cells) else "",
            "forms": forms,
            "raw_cells": cells,
        })

    # Infer subject/grade from table text when title extraction is weak.
    if not metadata["subject"]:
        for p in paragraphs:
            m = re.search(r"KISI\s*[–-]\s*KISI\s+(.+?)\s+KELAS", p, re.I)
            if m:
                metadata["subject"] = _clean(m.group(1))
                break

    total_slots = sum(
        len(bp["forms"].get(form, []))
        for bp in blueprints
        for form in FORM_ORDER
    )

    warnings = []
    if cognitive_col is not None:
        missing_levels = [bp["id"] for bp in blueprints if not bp.get("cognitive_level")]
        if missing_levels:
            warnings.append(
                "Kolom level kognitif terdeteksi, tetapi belum ada level C1–C6 pada: "
                + ", ".join(missing_levels[:12])
            )

    return {
        "metadata": metadata,
        "blueprints": blueprints,
        "total_slots": total_slots,
        "blueprint_count": len(blueprints),
        "cognitive_level_column": cognitive_col,
        "warnings": warnings,
        "source_type": "docx_table",
    }


def _vision_blueprint_from_parts(parts: list[Any], source_label: str) -> dict:
    prompt = f"""
Anda adalah Blueprint Reader RoboMANTAP. Sumber: {source_label}.
Baca seluruh isi visual dengan teliti. Tujuan utama adalah mengambil KISI-KISI, bukan membuat soal.
Pertahankan hubungan baris/kolom antara NO, BAB, ATP, INDIKATOR SOAL, LEVEL KOGNITIF, PG, ISIAN, URAIAN.
Jika tabel berlanjut ke halaman berikutnya, gabungkan barisnya. Jangan mengarang nilai yang tidak terlihat.
Level kognitif C1-C6 harus dipertahankan bila terlihat. Nomor seperti 1-2 harus menjadi [1,2].
Kembalikan JSON murni dengan schema:
{{
  "metadata": {{"subject":"","grade":"","assessment":"","school_year":"","title":""}},
  "blueprints": [
    {{"chapter":"","no":"","atp":"","indicator":"","cognitive_level":"C4","forms":{{"PG":[1,2],"Isian":[1],"Uraian":[]}}}}
  ],
  "warnings": []
}}
Jika kolom Level Kognitif tidak ada, gunakan "". Jangan menebak level dari indikator.
"""
    raw = _call_gemini_contents([prompt, *parts], is_json=True, max_output_tokens=16000)
    data = _parse_ai_json(raw)
    if not isinstance(data, dict) or not isinstance(data.get("blueprints"), list):
        raise ValueError("Vision AI tidak mengembalikan struktur blueprint yang valid.")
    normalized = []
    for idx, bp in enumerate(data.get("blueprints", []), start=1):
        if not isinstance(bp, dict):
            continue
        forms = bp.get("forms") if isinstance(bp.get("forms"), dict) else {}
        form_map = {form: _parse_question_numbers(",".join(map(str, forms.get(form, []) if isinstance(forms.get(form, []), list) else [forms.get(form, "")]))) for form in FORM_ORDER}
        if not _clean(bp.get("indicator")) and not _clean(bp.get("atp")):
            continue
        normalized.append({
            "id": f"BP-{idx:03d}", "chapter": _clean(bp.get("chapter")), "source_row": idx,
            "no": _clean(bp.get("no")), "atp": _clean(bp.get("atp")),
            "indicator": _clean(bp.get("indicator")),
            "cognitive_level": _normalize_cognitive_level(bp.get("cognitive_level")),
            "cognitive_level_source": _clean(bp.get("cognitive_level")),
            "forms": form_map, "raw_cells": [],
        })
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    total_slots = sum(len(bp["forms"].get(form, [])) for bp in normalized for form in FORM_ORDER)
    return {
        "metadata": {k: _clean(metadata.get(k)) for k in ["subject","grade","assessment","school_year","title"]},
        "blueprints": normalized, "total_slots": total_slots,
        "blueprint_count": len(normalized), "cognitive_level_column": None,
        "warnings": data.get("warnings", []) or [], "source_type": "vision",
    }


def _merge_vision_blueprints(results: list[dict]) -> dict:
    """Merge page/chunk Vision results without losing form-number information."""
    if not results:
        raise ValueError("Tidak ada hasil Vision yang dapat digabungkan.")
    metadata = {}
    merged = []
    warnings = []
    for result in results:
        if not isinstance(result, dict):
            continue
        for key, value in (result.get("metadata") or {}).items():
            if _clean(value) and not _clean(metadata.get(key)):
                metadata[key] = _clean(value)
        warnings.extend(result.get("warnings") or [])
        for bp in result.get("blueprints", []):
            if not isinstance(bp, dict):
                continue
            chapter = _clean(bp.get("chapter"))
            atp = _clean(bp.get("atp"))
            indicator = _clean(bp.get("indicator"))
            key = (chapter.lower(), atp.lower(), indicator.lower(), _clean(bp.get("no")).lower())
            existing = next((x for x in merged if (x.get("chapter","").lower(), x.get("atp","").lower(), x.get("indicator","").lower(), _clean(x.get("no")).lower()) == key), None)
            if existing is None:
                existing = {
                    "id": "", "chapter": chapter, "source_row": 0, "no": _clean(bp.get("no")),
                    "atp": atp, "indicator": indicator,
                    "cognitive_level": _normalize_cognitive_level(bp.get("cognitive_level")),
                    "cognitive_level_source": _clean(bp.get("cognitive_level_source") or bp.get("cognitive_level")),
                    "forms": {form: [] for form in FORM_ORDER}, "raw_cells": [],
                }
                merged.append(existing)
            elif not existing.get("cognitive_level") and bp.get("cognitive_level"):
                existing["cognitive_level"] = _normalize_cognitive_level(bp.get("cognitive_level"))
            for form in FORM_ORDER:
                existing["forms"][form] = sorted(set(existing["forms"].get(form, []) + bp.get("forms", {}).get(form, [])))
    for idx, bp in enumerate(merged, start=1):
        bp["id"] = f"BP-{idx:03d}"
        bp["source_row"] = idx
    total_slots = sum(len(bp["forms"].get(form, [])) for bp in merged for form in FORM_ORDER)
    return {
        "metadata": {k: _clean(metadata.get(k)) for k in ["subject","grade","assessment","school_year","title"]},
        "blueprints": merged, "total_slots": total_slots,
        "blueprint_count": len(merged), "cognitive_level_column": None,
        "warnings": list(dict.fromkeys(warnings)), "source_type": "vision",
    }


def extract_blueprint_from_source(file_bytes: bytes, filename: str) -> dict:
    """Read DOCX deterministically; PDF/image via Vision while preserving table semantics."""
    name = str(filename or "source").lower()
    ext = os.path.splitext(name)[1]
    if ext == ".docx":
        return extract_blueprint_from_docx(file_bytes)
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}:
        mime = {
            ".jpg":"image/jpeg", ".jpeg":"image/jpeg", ".png":"image/png", ".webp":"image/webp",
            ".gif":"image/gif", ".bmp":"image/bmp", ".tif":"image/tiff", ".tiff":"image/tiff",
        }[ext]
        part = types.Part.from_bytes(data=file_bytes, mime_type=mime)
        return _vision_blueprint_from_parts([part], filename)
    if ext == ".pdf":
        import fitz
        pdf = fitz.open(stream=file_bytes, filetype="pdf")
        if len(pdf) == 0:
            raise ValueError("PDF kosong.")
        chunk_size = 5
        overlap = 1
        results = []
        starts = list(range(0, len(pdf), chunk_size - overlap))
        for chunk_no, start_page in enumerate(starts, start=1):
            end_page = min(len(pdf), start_page + chunk_size)
            parts = []
            text_blocks = []
            for page_no in range(start_page, end_page):
                page = pdf[page_no]
                txt = page.get_text("text").strip()
                if txt:
                    text_blocks.append(f"[HALAMAN {page_no+1}]\n{txt[:9000]}")
                pix = page.get_pixmap(matrix=fitz.Matrix(1.35, 1.35), alpha=False)
                parts.append(types.Part.from_bytes(data=pix.tobytes("png"), mime_type="image/png"))
            if text_blocks:
                parts.insert(0, "\n\n".join(text_blocks))
            result = _vision_blueprint_from_parts(parts, f"{filename} • halaman {start_page+1}-{end_page} • chunk {chunk_no}")
            results.append(result)
        merged = _merge_vision_blueprints(results)
        if len(pdf) > chunk_size:
            merged.setdefault("warnings", []).append(
                f"PDF dibaca lengkap dalam {len(results)} kelompok halaman dengan overlap 1 halaman untuk menjaga kesinambungan tabel."
            )
        return merged
    raise ValueError(f"Format {ext or '(tanpa ekstensi)'} belum didukung.")


def blueprint_summary(blueprint: dict) -> dict:
    counts = {
        form: sum(len(bp.get("forms", {}).get(form, [])) for bp in blueprint.get("blueprints", []))
        for form in FORM_ORDER
    }
    variants = int(blueprint.get("variants_per_blueprint", 1) or 1)
    cognitive_counts = Counter(
        bp.get("cognitive_level") for bp in blueprint.get("blueprints", [])
        if bp.get("cognitive_level")
    )
    return {
        "blueprint_count": len(blueprint.get("blueprints", [])),
        "base_slots": sum(counts.values()),
        "slots_by_form": counts,
        "cognitive_levels": dict(cognitive_counts),
        "estimated_questions": sum(counts.values()) * variants,
    }


def _option_count(jenjang: str) -> int:
    value = _clean(jenjang).lower()
    if value in {"sd", "mi"} or "sd" in value:
        return 3
    if value in {"smp", "mts"} or "smp" in value or "mts" in value:
        return 4
    return 5


def _option_labels(jenjang: str) -> list[str]:
    return [chr(65 + i) for i in range(_option_count(jenjang))]


def _slot_list(bp: dict) -> list[dict]:
    slots = []
    for form in FORM_ORDER:
        for number in bp.get("forms", {}).get(form, []):
            slots.append({"question_type": form, "source_number": int(number)})
    return slots


def _generation_prompt(
    bp: dict,
    variants: int,
    jenjang: str,
    mapel: str,
    kelas: str,
    language: str,
) -> str:
    labels = _option_labels(jenjang)
    slots = _slot_list(bp)
    slot_text = json.dumps(slots, ensure_ascii=False)
    total = len(slots) * variants

    return f"""
Anda adalah Blueprint Question Architect RoboMANTAP.
Tugas Anda adalah membuat BANK SOAL UJIAN yang TERIKAT pada satu baris kisi-kisi.
Jangan memperluas kompetensi di luar indikator.

IDENTITAS:
- Mata pelajaran: {mapel}
- Jenjang: {jenjang}
- Kelas: {kelas or '-'}
- Bahasa: {language}

KISI-KISI SUMBER KEBENARAN:
- Chapter/Bab: {bp.get('chapter','')}
- ATP: {bp.get('atp','')}
- Indikator soal: {bp.get('indicator','')}
- Level kognitif: {bp.get('cognitive_level') or 'Tidak dicantumkan'}
- Nomor/form yang diwajibkan: {slot_text}

JUMLAH VARIASI:
{variants} variasi per blueprint.
Setiap variasi harus berbeda konteks, angka, tokoh, atau stimulus jika memungkinkan,
tetapi mengukur kompetensi/indikator yang SAMA.
Jangan membuat variasi yang sebenarnya menguji materi lain.

SLOT:
Total target keluaran = {total} pertanyaan.
Untuk SETIAP variasi, buat tepat satu pertanyaan untuk setiap slot di daftar.
Jangan menghilangkan slot dan jangan menambah slot.

ATURAN TIPE:
- PG: tepat {_option_count(jenjang)} pilihan: {", ".join(labels)}. Hanya satu jawaban benar.
- Isian: tidak memiliki opsi. Jawaban benar harus singkat dan jelas.
- Uraian: tidak memiliki opsi. correct_answer berisi inti jawaban/model answer,
  sedangkan solution_basis berisi langkah/pedoman penskoran ringkas.

ATURAN PRESISI:
1. Indikator harus tercermin langsung pada stimulus dan tuntutan jawaban.
2. Bila indikator mengatakan "disajikan soal cerita", gunakan soal cerita.
3. Bila indikator mengatakan "disajikan gambar", buat stimulus yang dapat diwujudkan
   melalui deskripsi teks yang jelas; jangan mengklaim gambar tersedia bila tidak ada.
4. Jangan mengarang fakta yang tidak diperlukan.
5. Untuk Matematika, hitung ulang angka dan pastikan jawabannya benar.
6. Setiap variasi harus benar-benar berbeda, bukan sekadar mengganti nama.
7. Jangan mengubah bentuk soal yang ditentukan blueprint.
8. Bahasa harus natural dan sesuai tingkat {jenjang}.
9. Untuk materi Arab/religius, gunakan bahasa yang sesuai bidang dan jangan mengarang kutipan agama.
10. Jika menggunakan notasi matematika, gunakan Unicode/LaTeX yang valid.
11. Jika Level Kognitif dicantumkan pada blueprint, level tersebut adalah CONSTRAINT WAJIB.
    Soal harus menuntut proses berpikir sesuai level target, bukan hanya menggunakan
    materi yang lebih sulit. C4 = menganalisis, C5 = mengevaluasi, C6 = mencipta.
12. Jangan menurunkan tuntutan kognitif target. Jika target C5, soal hafalan/perhitungan
    rutin tidak boleh diklaim sebagai C5.

JIKA INDIKATOR ATAU SOAL MEMBUTUHKAN GAMBAR/DIAGRAM, field `diagram` WAJIB diisi.
Gunakan hanya tipe: layang_layang, persegi, persegi_panjang, segitiga, lingkaran, jajargenjang, trapesium, belah_ketupat, gabungan_jajargenjang_segitiga.
`measurements` harus berisi angka yang sama persis dengan data soal. Jangan mengarang ukuran. Jika tidak membutuhkan gambar, set `diagram` menjadi null.
Format contoh: required=true; type=layang_layang; measurements d1=30, d2=20; labels vertical=30 cm, horizontal=20 cm; caption kosong.

OUTPUT JSON MURNI:
{{
  "questions": [
    {{
      "blueprint_id": "{bp.get('id')}",
      "variant": 1,
      "question_type": "PG",
      "cognitive_level": "{bp.get('cognitive_level','')}",
      "source_number": 1,
      "question": "...",
      "options": ["A. ...", "B. ...", "C. ...", "D. ...", "E. ..."],
      "correct_answer": "A. ...",
      "solution_basis": "...",
      "diagram": null
    }}
  ]
}}

Keluaran HARUS berisi tepat {total} objek.
Gunakan variant 1..{variants}.
Gunakan question_type dan source_number PERSIS sesuai slot.
"""


def _parse_ai_json(raw: str) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(clean_json_text(raw), strict=False)
    except Exception:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0), strict=False)
            except Exception:
                return None
    return None


SUPPORTED_DIAGRAM_TYPES = {
    "layang_layang", "persegi", "persegi_panjang", "segitiga", "lingkaran",
    "jajargenjang", "trapesium", "belah_ketupat", "gabungan_jajargenjang_segitiga",
}


def _diagram_type_normalize(value: Any) -> str:
    text = _clean(value).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "layanglayang": "layang_layang", "kite": "layang_layang",
        "square": "persegi", "rectangle": "persegi_panjang",
        "triangle": "segitiga", "parallelogram": "jajargenjang",
        "trapezoid": "trapesium", "rhombus": "belah_ketupat", "circle": "lingkaran", "circle_shape": "lingkaran",
        "gabungan": "gabungan_jajargenjang_segitiga",
    }
    return aliases.get(text, text)


def _normalize_diagram_spec(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    dtype = _diagram_type_normalize(raw.get("type"))
    if dtype not in SUPPORTED_DIAGRAM_TYPES:
        return None
    measurements = raw.get("measurements") if isinstance(raw.get("measurements"), dict) else {}
    clean_measurements = {}
    for key, value in measurements.items():
        try:
            if isinstance(value, str):
                m = re.search(r"-?\d+(?:[.,]\d+)?", value)
                if m:
                    clean_measurements[str(key)] = float(m.group(0).replace(",", "."))
            elif isinstance(value, (int, float)):
                clean_measurements[str(key)] = float(value)
        except Exception:
            continue
    labels = raw.get("labels") if isinstance(raw.get("labels"), dict) else {}
    return {
        "required": bool(raw.get("required", True)),
        "type": dtype,
        "measurements": clean_measurements,
        "labels": {str(k): _clean(v) for k, v in labels.items() if _clean(v)},
        "caption": _clean(raw.get("caption")),
    }


def _needs_diagram(indicator: str, question: str) -> bool:
    text = f"{indicator} {question}".lower()
    return bool(re.search(r"disajikan\s+(?:sebuah\s+)?gambar|perhatikan\s+gambar|dari\s+gambar|berdasarkan\s+gambar", text))


def render_math_diagram(spec: dict) -> bytes | None:
    """Create a clean deterministic PNG diagram from validated numeric data."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        from matplotlib.patches import Polygon
    except Exception:
        return None

    dtype = spec.get("type")
    m = spec.get("measurements", {})
    fig, ax = plt.subplots(figsize=(5.8, 3.2), dpi=180)
    ax.set_aspect("equal")
    ax.axis("off")

    def label(x, y, text, **kwargs):
        ax.text(x, y, text, fontsize=9, ha="center", va="center", **kwargs)

    def dim(a, b, text, offset=(0, 0.18)):
        ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle="<->", lw=1.1))
        mx, my = (a[0]+b[0])/2, (a[1]+b[1])/2
        label(mx+offset[0], my+offset[1], text)

    if dtype == "layang_layang":
        d1, d2 = m.get("d1", m.get("diagonal_vertical")), m.get("d2", m.get("diagonal_horizontal"))
        if not d1 or not d2: return None
        w, h = d2/2, d1/2
        pts = np.array([[0,h], [w,0], [0,-h], [-w,0]])
        ax.add_patch(Polygon(pts, closed=True, fill=False, linewidth=1.8))
        ax.plot([-w,w],[0,0],linewidth=1.0,linestyle="--")
        ax.plot([0,0],[-h,h],linewidth=1.0,linestyle="--")
        dim((0,-h),(0,h), f"{d1:g} cm", offset=(0.38,0))
        dim((-w,0),(w,0), f"{d2:g} cm", offset=(0,-0.28))
    elif dtype == "persegi":
        s=m.get("sisi",m.get("side"));
        if not s: return None
        pts=np.array([[0,0],[s,0],[s,s],[0,s]])
        ax.add_patch(Polygon(pts,closed=True,fill=False,linewidth=1.8)); dim((0,0),(s,0),f"{s:g} cm",(0,-0.22)); dim((s,0),(s,s),f"{s:g} cm",(0.28,0))
    elif dtype == "persegi_panjang":
        p=m.get("panjang",m.get("length")); l=m.get("lebar",m.get("width"));
        if not p or not l: return None
        pts=np.array([[0,0],[p,0],[p,l],[0,l]])
        ax.add_patch(Polygon(pts,closed=True,fill=False,linewidth=1.8)); dim((0,0),(p,0),f"{p:g} cm",(0,-0.22)); dim((p,0),(p,l),f"{l:g} cm",(0.3,0))
    elif dtype == "segitiga":
        b=m.get("alas",m.get("base")); h=m.get("tinggi",m.get("height"));
        if not b or not h: return None
        x0=-b/2; pts=np.array([[x0,0],[x0+b,0],[0,h]])
        ax.add_patch(Polygon(pts,closed=True,fill=False,linewidth=1.8)); ax.plot([0,0],[0,h],linestyle="--",linewidth=1); dim((x0,0),(x0+b,0),f"{b:g} cm",(0,-0.22)); dim((0,0),(0,h),f"{h:g} cm",(0.3,0))
    elif dtype == "lingkaran":
        radius=m.get("r",m.get("radius")); diameter=m.get("d",m.get("diameter"))
        if not radius and diameter: radius=diameter/2
        if not radius: return None
        theta=np.linspace(0,2*np.pi,200); ax.plot(radius*np.cos(theta), radius*np.sin(theta), linewidth=1.8); ax.plot([0,radius],[0,0],linestyle="--",linewidth=1); label(radius/2,0.22,f"r = {radius:g} cm");
    elif dtype == "jajargenjang":
        b=m.get("alas",m.get("base")); h=m.get("tinggi",m.get("height")); s=m.get("sisi",m.get("side",h))
        if not b or not h: return None
        skew=min(max(float(s)*0.35,0.2), b*0.45); pts=np.array([[0,0],[b,0],[b+skew,h],[skew,h]])
        ax.add_patch(Polygon(pts,closed=True,fill=False,linewidth=1.8)); ax.plot([skew,skew],[0,h],linestyle="--",linewidth=1); dim((0,0),(b,0),f"{b:g} cm",(0,-0.22)); dim((skew,0),(skew,h),f"{h:g} cm",(0.35,0))
    elif dtype == "trapesium":
        a=m.get("sisi_atas",m.get("atas",m.get("a"))); b=m.get("sisi_bawah",m.get("bawah",m.get("b"))); h=m.get("tinggi",m.get("height"));
        if not a or not b or not h: return None
        x=(b-a)/2; pts=np.array([[0,0],[b,0],[b-x,h],[x,h]])
        ax.add_patch(Polygon(pts,closed=True,fill=False,linewidth=1.8)); ax.plot([x,x],[0,h],linestyle="--",linewidth=1); dim((0,0),(b,0),f"{b:g} cm",(0,-0.22)); dim((x,0),(x,h),f"{h:g} cm",(0.3,0)); label(b/2,h+0.2,f"{a:g} cm")
    elif dtype == "belah_ketupat":
        d1=m.get("d1",m.get("diagonal_vertical")); d2=m.get("d2",m.get("diagonal_horizontal"));
        if not d1 or not d2: return None
        w,h=d2/2,d1/2; pts=np.array([[0,h],[w,0],[0,-h],[-w,0]])
        ax.add_patch(Polygon(pts,closed=True,fill=False,linewidth=1.8)); ax.plot([-w,w],[0,0],linestyle="--",linewidth=1); ax.plot([0,0],[-h,h],linestyle="--",linewidth=1); dim((0,-h),(0,h),f"{d1:g} cm",(0.38,0)); dim((-w,0),(w,0),f"{d2:g} cm",(0,-0.28))
    elif dtype == "gabungan_jajargenjang_segitiga":
        b=m.get("alas",m.get("base")); h=m.get("tinggi_jajargenjang",m.get("height_parallelogram")); ht=m.get("tinggi_segitiga",m.get("height_triangle"));
        if not b or not h or not ht: return None
        skew=min(max(b*0.12,0.4),b*0.3); poly1=np.array([[0,0],[b,0],[b+skew,h],[skew,h]]); poly2=np.array([[skew,h],[b+skew,h],[b/2+skew,h+ht]])
        ax.add_patch(Polygon(poly1,closed=True,fill=False,linewidth=1.8)); ax.add_patch(Polygon(poly2,closed=True,fill=False,linewidth=1.8)); ax.plot([skew,skew],[0,h],linestyle="--",linewidth=1); ax.plot([b/2+skew,b/2+skew],[h,h+ht],linestyle="--",linewidth=1); dim((0,0),(b,0),f"{b:g} cm",(0,-0.22)); dim((skew,0),(skew,h),f"{h:g} cm",(0.35,0)); dim((b/2+skew,h),(b/2+skew,h+ht),f"{ht:g} cm",(0.35,0))
    else:
        plt.close(fig); return None

    fig.tight_layout(pad=0.8)
    output=io.BytesIO(); fig.savefig(output,format="png",bbox_inches="tight",transparent=False); plt.close(fig); return output.getvalue()


def _normalize_generated_question(item: dict, jenjang: str) -> dict | None:
    if not isinstance(item, dict):
        return None
    qtype = _clean(item.get("question_type")).title()
    if qtype.lower() == "pg":
        qtype = "PG"
    elif qtype.lower() == "isian":
        qtype = "Isian"
    elif qtype.lower() == "uraian":
        qtype = "Uraian"
    else:
        return None

    question = _clean(item.get("question"))
    answer = _clean(item.get("correct_answer"))
    solution = _clean(item.get("solution_basis"))
    cognitive_level = _normalize_cognitive_level(item.get("cognitive_level"))
    try:
        variant = int(item.get("variant"))
        source_number = int(item.get("source_number"))
    except Exception:
        return None
    if not question or not answer or not solution:
        return None

    if qtype == "PG":
        raw_options = item.get("options", [])
        if not isinstance(raw_options, list):
            return None
        options = []
        for idx, raw in enumerate(raw_options):
            body = re.sub(r"^\s*[A-Ea-e]\s*[\.\)\:\-]\s*", "", _clean(raw))
            options.append(f"{chr(65+idx)}. {body}" if body else f"{chr(65+idx)}.")
        expected = _option_labels(jenjang)
        if len(options) != len(expected):
            return None
        label_match = re.match(r"^\s*([A-Ea-e])\s*[\.\)\:\-]", answer)
        if label_match:
            answer_label = label_match.group(1).upper()
            answer_idx = expected.index(answer_label) if answer_label in expected else -1
            if answer_idx >= 0:
                answer = options[answer_idx]
        elif answer not in options:
            # Allow an answer body, but convert it to the exact option.
            answer_idx = next(
                (i for i, opt in enumerate(options)
                 if re.sub(r"^[A-E]\.\s*", "", opt).strip() == answer),
                -1
            )
            if answer_idx < 0:
                return None
            answer = options[answer_idx]
    else:
        options = []

    diagram = _normalize_diagram_spec(item.get("diagram"))
    return {
        "blueprint_id": _clean(item.get("blueprint_id")),
        "variant": variant,
        "question_type": qtype,
        "cognitive_level": cognitive_level,
        "source_number": source_number,
        "question": question,
        "options": options,
        "correct_answer": answer,
        "solution_basis": solution,
        "diagram": diagram,
    }


def _expected_keys(bp: dict, variants: int) -> set[tuple[int, str, int]]:
    return {
        (v, slot["question_type"], slot["source_number"])
        for v in range(1, variants + 1)
        for slot in _slot_list(bp)
    }


def _deterministic_alignment_issues(questions: list[dict], bp: dict, variants: int, jenjang: str) -> list[str]:
    expected = _expected_keys(bp, variants)
    actual = {
        (int(q.get("variant", 0)), q.get("question_type"), int(q.get("source_number", -1)))
        for q in questions
    }
    issues = []
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing:
            issues.append(f"missing={missing[:8]}")
        if extra:
            issues.append(f"extra={extra[:8]}")

    expected_count = _option_count(jenjang)
    target_levels = _cognitive_levels(bp.get("cognitive_level"))
    for q in questions:
        if q.get("question_type") == "PG" and len(q.get("options", [])) != expected_count:
            issues.append(f"invalid_options={q.get('variant')}/{q.get('source_number')}")
        if target_levels:
            generated_level = _normalize_cognitive_level(q.get("cognitive_level"))
            generated_levels = _cognitive_levels(generated_level)
            if not generated_levels or not any(level in target_levels for level in generated_levels):
                issues.append(
                    f"invalid_cognitive_level={q.get('variant')}/{q.get('question_type')}/"
                    f"{q.get('source_number')} expected={target_levels} got={generated_level or '-'}"
                )
    return issues


def _generate_blueprint_batch(
    bp: dict,
    variants: int,
    jenjang: str,
    mapel: str,
    kelas: str,
    language: str,
    attempts: int = 2,
) -> list[dict]:
    """Generate each variant as an independent batch.

    The previous implementation asked one AI response to produce all variants
    at once. That made the requested Variant identity dependent on the model
    faithfully repeating variant=1..N in every object. Here each variant is a
    separate generation/validation unit, so the variant identity is explicit
    and cannot collapse into one package.
    """
    combined: list[dict] = []

    for variant_number in range(1, variants + 1):
        variant_ok = False
        for _ in range(max(1, attempts)):
            prompt = _generation_prompt(bp, 1, jenjang, mapel, kelas, language)
            prompt += f"\n\nVARIANT WAJIB UNTUK BATCH INI: {variant_number}\n"
            prompt += (
                "Keluaran batch ini HANYA untuk variant tersebut. "
                f"Semua objek harus memiliki \"variant\": {variant_number}. "
                "Jangan menghasilkan variant lain."
            )

            raw = call_gemini_with_rotation(prompt, is_json=True)
            data = _parse_ai_json(raw)
            if not data or not isinstance(data.get("questions"), list):
                continue

            normalized = []
            for item in data["questions"]:
                q = _normalize_generated_question(item, jenjang)
                if q:
                    # The batch identity is authoritative; do not trust a
                    # malformed/missing variant value returned by the model.
                    q["variant"] = variant_number
                    q["blueprint_id"] = bp["id"]
                    normalized.append(q)

            # Validate against exactly one variant's slots.
            expected = {
                (variant_number, slot["question_type"], slot["source_number"])
                for slot in _slot_list(bp)
            }
            actual = {
                (int(q.get("variant", 0)), q.get("question_type"), int(q.get("source_number", -1)))
                for q in normalized
            }
            if actual != expected:
                continue

            issues = _deterministic_alignment_issues(normalized, bp, variants, jenjang)
            # The full-variants validator expects all variants, so validate
            # this batch's structural properties directly and cognitive level
            # explicitly here.
            target_levels = _cognitive_levels(bp.get("cognitive_level"))
            if target_levels:
                bad_level = False
                for q in normalized:
                    generated_levels = _cognitive_levels(q.get("cognitive_level"))
                    if not generated_levels or not any(level in target_levels for level in generated_levels):
                        bad_level = True
                        break
                if bad_level:
                    continue

            expected_count = _option_count(jenjang)
            if any(q.get("question_type") == "PG" and len(q.get("options", [])) != expected_count for q in normalized):
                continue
            diagram_invalid = False
            for q in normalized:
                needs_diagram = _needs_diagram(bp.get("indicator", ""), q.get("question", ""))
                if needs_diagram and not q.get("diagram"):
                    diagram_invalid = True
                    break
                if q.get("diagram"):
                    qtext = str(q.get("question", ""))
                    for measurement in q["diagram"].get("measurements", {}).values():
                        token = str(measurement).rstrip("0").rstrip(".") if isinstance(measurement, float) else str(measurement)
                        if token and token not in qtext:
                            diagram_invalid = True
                            break
                    if diagram_invalid:
                        break
            if diagram_invalid:
                continue

            combined.extend(normalized)
            variant_ok = True
            break

        if not variant_ok:
            # One failed variant makes this blueprint incomplete; the caller
            # can report it instead of silently producing a mixed/partial bank.
            return []

    return combined


def _ai_validate_alignment(questions: list[dict], blueprint: dict, jenjang: str) -> dict:
    """
    Small-output QA: AI reports only invalid question keys, rather than rewriting
    the whole bank. This keeps token usage reasonable even for large banks.
    """
    if not questions:
        return {"valid": False, "invalid": [], "notes": ["Bank kosong."]}

    compact_blueprint = []
    for bp in blueprint.get("blueprints", []):
        compact_blueprint.append({
            "id": bp["id"],
            "chapter": bp.get("chapter", ""),
            "atp": bp.get("atp", ""),
            "indicator": bp.get("indicator", ""),
            "cognitive_level": bp.get("cognitive_level", ""),
            "forms": bp.get("forms", {}),
        })

    compact_questions = [
        {
            "key": f"{q.get('blueprint_id')}|V{q.get('variant')}|{q.get('question_type')}|N{q.get('source_number')}",
            "question": q.get("question", ""),
            "cognitive_level": q.get("cognitive_level", ""),
            "options": q.get("options", []),
            "correct_answer": q.get("correct_answer", ""),
            "diagram": q.get("diagram"),
        }
        for q in questions
    ]

    prompt = f"""
Anda adalah QA Validator Bank Soal RoboMANTAP.
Bandingkan pertanyaan dengan kisi-kisi yang menjadi sumber kebenaran.

JENJANG: {jenjang}

BLUEPRINT:
{json.dumps(compact_blueprint, ensure_ascii=False)}

QUESTIONS:
{json.dumps(compact_questions, ensure_ascii=False)}

Tandai hanya pertanyaan yang:
- menguji kompetensi berbeda dari ATP/indikator,
- memakai bentuk soal berbeda dari blueprint,
- salah nomor/form/variant,
- memiliki jawaban benar yang tidak konsisten,
- memiliki opsi PG yang tidak sesuai,
- atau secara substantif tidak memenuhi level kognitif C1–C6 yang ditetapkan blueprint,
- atau memiliki diagram yang ukuran/jenisnya tidak konsisten dengan soal.

Jika blueprint menetapkan C4, soal harus benar-benar menuntut analisis; C5 menuntut evaluasi;
C6 menuntut penciptaan/perancangan. Jangan menerima soal rutin hanya karena diberi label C4/C5/C6.

Jangan menandai hanya karena redaksi/konteks berbeda. Variasi memang WAJIB berbeda konteks
selama kompetensi tetap sama.

OUTPUT JSON MURNI:
{{
  "valid": true,
  "invalid": [
    {{
      "key": "BP-001|V1|PG|N1",
      "reason": "..."
    }}
  ],
  "notes": ["..."]
}}
"""
    raw = call_gemini_with_rotation(prompt, is_json=True)
    data = _parse_ai_json(raw)
    if not isinstance(data, dict):
        return {"valid": False, "invalid": [], "notes": ["QA AI tidak mengembalikan JSON valid."]}
    return data


def generate_bank_soal(
    blueprint: dict,
    *,
    variants: int,
    jenjang: str,
    mapel: str,
    kelas: str = "",
    language: str = "Bahasa Indonesia",
) -> tuple[list[dict], dict]:
    """
    Generate the complete bank. Each blueprint row is the unit of variation.
    All form/number slots inside that row are preserved.
    """
    variants = max(1, min(int(variants), 10))
    blueprint = dict(blueprint)
    blueprint["variants_per_blueprint"] = variants

    all_questions: list[dict] = []
    row_reports = []

    for bp in blueprint.get("blueprints", []):
        batch = _generate_blueprint_batch(
            bp, variants, jenjang, mapel, kelas, language, attempts=2
        )
        if not batch:
            row_reports.append({
                "blueprint_id": bp["id"],
                "status": "failed",
                "reason": "AI belum menghasilkan seluruh slot sesuai blueprint.",
            })
            continue
        all_questions.extend(batch)
        row_reports.append({
            "blueprint_id": bp["id"],
            "status": "generated",
            "count": len(batch),
        })

    # Deterministic QA is always applied.
    expected_total = sum(
        len(_slot_list(bp)) * variants for bp in blueprint.get("blueprints", [])
    )
    deterministic_ok = len(all_questions) == expected_total

    ai_qa = {"valid": True, "invalid": [], "notes": []}
    if all_questions and deterministic_ok:
        ai_qa = _ai_validate_alignment(all_questions, blueprint, jenjang)

    invalid_keys = {
        str(item.get("key"))
        for item in ai_qa.get("invalid", [])
        if isinstance(item, dict) and item.get("key")
    }

    for q in all_questions:
        q["_qa_status"] = "review" if (
            f"{q.get('blueprint_id')}|V{q.get('variant')}|{q.get('question_type')}|N{q.get('source_number')}"
            in invalid_keys
        ) else "pass"

    # Stable order: blueprint -> variant -> form -> source number.
    form_rank = {form: idx for idx, form in enumerate(FORM_ORDER)}
    all_questions.sort(
        key=lambda q: (
            q.get("blueprint_id", ""),
            int(q.get("variant", 0)),
            form_rank.get(q.get("question_type"), 99),
            int(q.get("source_number", 0)),
        )
    )

    report = {
        "expected_total": expected_total,
        "generated_total": len(all_questions),
        "deterministic_ok": deterministic_ok,
        "ai_qa": ai_qa,
        "row_reports": row_reports,
        "pass_count": sum(q.get("_qa_status") == "pass" for q in all_questions),
        "review_count": sum(q.get("_qa_status") == "review" for q in all_questions),
    }
    return all_questions, report


def _set_cell_shading(cell, fill: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def _set_cell_border(cell, **kwargs):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = tcPr.first_child_found_in("w:tcBorders")
    if tcBorders is None:
        tcBorders = OxmlElement("w:tcBorders")
        tcPr.append(tcBorders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        if edge in kwargs:
            edge_data = kwargs.get(edge)
            tag = "w:{}".format(edge)
            element = tcBorders.find(qn(tag))
            if element is None:
                element = OxmlElement(tag)
                tcBorders.append(element)
            for key in ["val", "sz", "space", "color"]:
                if key in edge_data:
                    element.set(qn("w:{}".format(key)), str(edge_data[key]))


def _add_heading(doc, text: str, level: int = 1):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10 if level == 1 else 6)
    p.paragraph_format.space_after = Pt(5)
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(14 if level == 1 else 11)
    r.font.color.rgb = RGBColor(6, 78, 59)
    return p


def build_bank_soal_docx(
    blueprint: dict,
    questions: list[dict],
    *,
    jenjang: str,
    mapel: str,
    kelas: str = "",
    variants: int = 1,
    include_answer_key: bool = True,
    include_blueprint_map: bool = True,
    logo_path: str | None = None,
) -> bytes:
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.55)
    section.bottom_margin = Inches(0.55)
    section.left_margin = Inches(0.65)
    section.right_margin = Inches(0.65)

    # Header / identity.
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.columns[0].width = Inches(1.25)
    table.columns[1].width = Inches(5.9)
    c0, c1 = table.rows[0].cells
    c0.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    c1.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

    if logo_path and os.path.exists(logo_path):
        c0.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        c0.paragraphs[0].add_run().add_picture(logo_path, width=Inches(0.9))
    else:
        r = c0.paragraphs[0].add_run("UPN")
        r.bold = True
        r.font.size = Pt(18)
        r.font.color.rgb = RGBColor(6, 78, 59)

    p = c1.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("ROBO MANTAP • BANK SOAL UJIAN\n")
    r.bold = True
    r.font.size = Pt(15)
    r.font.color.rgb = RGBColor(6, 78, 59)
    r2 = p.add_run(f"{mapel or 'Mata Pelajaran'} • {jenjang} {kelas}".strip())
    r2.bold = True
    r2.font.size = Pt(10)

    meta = doc.add_table(rows=0, cols=2)
    meta.autofit = False
    metadata = blueprint.get("metadata", {})
    meta_rows = [
        ("Asesmen", metadata.get("assessment") or "-"),
        ("Tahun Pelajaran", metadata.get("school_year") or "-"),
        ("Blueprint", f"{len(blueprint.get('blueprints', []))} item"),
        ("Variasi / Blueprint", str(variants)),
        ("Total Soal", str(len(questions))),
    ]
    for label, value in meta_rows:
        cells = meta.add_row().cells
        cells[0].width = Inches(1.65)
        cells[1].width = Inches(5.35)
        cells[0].paragraphs[0].add_run(label).bold = True
        cells[1].paragraphs[0].add_run(str(value))
        _set_cell_shading(cells[0], "EAF7F1")
        for c in cells:
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            _set_cell_border(
                c,
                top={"val": "single", "sz": 4, "color": "D1D5DB"},
                bottom={"val": "single", "sz": 4, "color": "D1D5DB"},
                left={"val": "single", "sz": 4, "color": "D1D5DB"},
                right={"val": "single", "sz": 4, "color": "D1D5DB"},
            )

    if include_blueprint_map:
        _add_heading(doc, "Peta Blueprint", 1)
        t = doc.add_table(rows=1, cols=6)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        headers = ["ID", "Bab", "ATP", "Indikator", "Level", "Bentuk / Nomor"]
        for i, h in enumerate(headers):
            cell = t.rows[0].cells[i]
            cell.text = h
            _set_cell_shading(cell, "064E3B")
            for run in cell.paragraphs[0].runs:
                run.bold = True
                run.font.color.rgb = RGBColor(255, 255, 255)
                run.font.size = Pt(8)
        for bp in blueprint.get("blueprints", []):
            forms_text = " • ".join(
                f"{form}: {', '.join(map(str, bp.get('forms', {}).get(form, [])))}"
                for form in FORM_ORDER if bp.get("forms", {}).get(form)
            )
            cells = t.add_row().cells
            vals = [
                bp["id"], bp.get("chapter", ""), bp.get("atp", ""),
                bp.get("indicator", ""), bp.get("cognitive_level") or "—", forms_text
            ]
            for i, val in enumerate(vals):
                cells[i].text = str(val)
                for run in cells[i].paragraphs[0].runs:
                    run.font.size = Pt(7.5)
        doc.add_page_break()

    # ------------------------------------------------------------------
    # Final document layout: one complete package per Variant.
    # IMPORTANT: never mix questions from different variants on the same
    # package/page. Each variant is rendered as:
    #   VARIAN N
    #   A. PILIHAN GANDA
    #   B. ISIAN SINGKAT
    #   C. URAIAN
    # followed by a page break before the next variant.
    # ------------------------------------------------------------------
    # Render the configured number of packages explicitly. This prevents a
    # missing/empty variant from being silently merged into another variant.
    requested_variants = max(1, int(variants or blueprint.get("variants_per_blueprint", 1) or 1))
    variant_values = list(range(1, requested_variants + 1))

    form_titles = {
        "PG": "A. PILIHAN GANDA",
        "Isian": "B. ISIAN SINGKAT",
        "Uraian": "C. URAIAN",
    }

    # Build explicit buckets first. This avoids relying on the incoming
    # question order and guarantees V1 is completed before V2 starts.
    variant_buckets = {
        variant: {
            form: [
                q for q in questions
                if int(q.get("variant", 0)) == variant
                and q.get("question_type") == form
            ]
            for form in FORM_ORDER
        }
        for variant in variant_values
    }

    for variant_index, variant in enumerate(variant_values):
        # Every variant starts on a fresh page. This makes each variant a
        # genuinely separate package when the DOCX is printed or distributed.
        if variant_index > 0:
            doc.add_page_break()

        # Variant banner.
        banner = doc.add_table(rows=1, cols=1)
        banner.alignment = WD_TABLE_ALIGNMENT.CENTER
        banner.autofit = False
        banner.columns[0].width = Inches(6.9)
        bc = banner.cell(0, 0)
        bc.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        _set_cell_shading(bc, "064E3B")
        _set_cell_border(
            bc,
            top={"val": "single", "sz": 8, "color": "064E3B"},
            bottom={"val": "single", "sz": 8, "color": "064E3B"},
            left={"val": "single", "sz": 8, "color": "064E3B"},
            right={"val": "single", "sz": 8, "color": "064E3B"},
        )
        bp = bc.paragraphs[0]
        bp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        bp.paragraph_format.space_before = Pt(7)
        bp.paragraph_format.space_after = Pt(7)
        br = bp.add_run(f"VARIAN {variant}")
        br.bold = True
        br.font.size = Pt(16)
        br.font.color.rgb = RGBColor(255, 255, 255)

        # Small package label makes the purpose unambiguous in print/preview.
        cp = doc.add_paragraph()
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cp.paragraph_format.space_before = Pt(3)
        cp.paragraph_format.space_after = Pt(10)
        cr = cp.add_run("PAKET SOAL • SEMUA BENTUK SOAL DALAM VARIAN INI")
        cr.bold = True
        cr.font.size = Pt(7.5)
        cr.font.color.rgb = RGBColor(107, 114, 128)

        for form in FORM_ORDER:
            form_questions = variant_buckets.get(variant, {}).get(form, [])

            # Always keep the three planned section labels in the same order.
            # If a blueprint has no slot for a form, show a compact note rather
            # than silently merging the next form into the current section.
            _add_heading(doc, form_titles[form], 1)

            if not form_questions:
                empty = doc.add_paragraph()
                empty.paragraph_format.left_indent = Inches(0.18)
                empty.paragraph_format.space_after = Pt(7)
                er = empty.add_run("Tidak ada soal untuk bentuk ini pada varian ini.")
                er.italic = True
                er.font.size = Pt(8.5)
                er.font.color.rgb = RGBColor(107, 114, 128)
                continue

            for idx, q in enumerate(form_questions, start=1):
                # The printed number is local to Variant + Bentuk.
                # Traceability stores the same number together with V/form.
                q["_document_number"] = idx

                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(5)
                p.paragraph_format.space_after = Pt(3)
                r = p.add_run(f"{idx}. ")
                r.bold = True
                r.font.size = Pt(10)

                append_text_with_fractions(p, q.get("question", ""))

                diagram_bytes = render_math_diagram(q.get("diagram")) if q.get("diagram") else None
                if diagram_bytes:
                    dp = doc.add_paragraph()
                    dp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    dp.paragraph_format.space_before = Pt(3)
                    dp.paragraph_format.space_after = Pt(5)
                    dp.add_run().add_picture(io.BytesIO(diagram_bytes), width=Inches(4.9))
                    if q.get("diagram", {}).get("caption"):
                        cp = doc.add_paragraph()
                        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        cr = cp.add_run(q["diagram"]["caption"])
                        cr.italic = True
                        cr.font.size = Pt(8)
                        cr.font.color.rgb = RGBColor(107, 114, 128)

                if form == "PG":
                    for opt in q.get("options", []):
                        po = doc.add_paragraph()
                        po.paragraph_format.left_indent = Inches(0.22)
                        po.paragraph_format.space_after = Pt(1)
                        append_text_with_fractions(po, opt)

                if include_answer_key:
                    pa = doc.add_paragraph()
                    pa.paragraph_format.left_indent = Inches(0.22)
                    ra = pa.add_run("Kunci: ")
                    ra.bold = True
                    ra.font.size = Pt(8.5)
 
                    append_text_with_fractions(pa, q.get("correct_answer", ""), color_rgb=RGBColor(5, 150, 105))

                    ps = doc.add_paragraph()
                    ps.paragraph_format.left_indent = Inches(0.22)
                    rs = ps.add_run("Pembahasan: ")
                    rs.bold = True
                    rs.font.size = Pt(8.5)

                    append_text_with_fractions(ps, q.get("solution_basis", ""))
                    ps.paragraph_format.space_after = Pt(7)

    # ------------------------------------------------------------------
    # Blueprint traceability appendix. The rows deliberately follow the same
    # human-readable order as the document: V1 PG -> Isian -> Uraian, then V2...
    # ------------------------------------------------------------------
    if include_blueprint_map:
        doc.add_page_break()
        _add_heading(doc, "Lampiran • Traceability Bank Soal", 1)
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(7)
        r = p.add_run("Cara membaca: ")
        r.bold = True
        r.font.size = Pt(8.5)
        p.add_run(
            "No. Soal mengikuti nomor pada bagian Variant dan Bentuk. "
            "Variant membedakan paket soal, sedangkan Blueprint dan No. Kisi "
            "menunjukkan sumber kisi-kisi yang menjadi dasar soal."
        ).font.size = Pt(8.5)

        trace = doc.add_table(rows=1, cols=8)
        trace.alignment = WD_TABLE_ALIGNMENT.CENTER
        trace.autofit = False
        headers = ["Varian", "No. Soal", "Blueprint", "Level", "Bentuk", "No. Kisi", "QA", "Kode"]
        widths = [0.58, 0.62, 0.72, 0.55, 0.68, 0.62, 0.52, 1.28]
        for i, h in enumerate(headers):
            cell = trace.rows[0].cells[i]
            cell.width = Inches(widths[i])
            cell.text = h
            _set_cell_shading(cell, "064E3B")
            for run in cell.paragraphs[0].runs:
                run.bold = True
                run.font.color.rgb = RGBColor(255, 255, 255)
                run.font.size = Pt(7.5)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

        form_rank = {form: idx for idx, form in enumerate(FORM_ORDER)}
        trace_questions = sorted(
            questions,
            key=lambda q: (
                int(q.get("variant", 0)),
                form_rank.get(q.get("question_type"), 99),
                int(q.get("_document_number", 0)),
                q.get("blueprint_id", ""),
                int(q.get("source_number", 0)),
            ),
        )
        for q in trace_questions:
            cells = trace.add_row().cells
            variant = int(q.get("variant", 0))
            form = q.get("question_type", "")
            no_soal = q.get("_document_number", "")
            bp_id = q.get("blueprint_id", "")
            source_no = q.get("source_number", "")
            form_code = {"PG": "PG", "Isian": "IS", "Uraian": "UR"}.get(form, re.sub(r"[^A-Za-z0-9]+", "", str(form)).upper()[:3])
            code = f"{bp_id}-V{variant}-{form_code}-{no_soal:02d}" if isinstance(no_soal, int) else f"{bp_id}-V{variant}-{form_code}-{no_soal}"
            bp_lookup = next((bp for bp in blueprint.get("blueprints", []) if bp.get("id") == bp_id), {})
            vals = [
                f"V{variant}", no_soal, bp_id, bp_lookup.get("cognitive_level") or "—", form, source_no,
                "PASS" if q.get("_qa_status") == "pass" else "REVIEW",
                code,
            ]
            for i, val in enumerate(vals):
                cells[i].width = Inches(widths[i])
                cells[i].text = str(val)
                cells[i].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                for run in cells[i].paragraphs[0].runs:
                    run.font.size = Pt(7)
                if i == 5:
                    for run in cells[i].paragraphs[0].runs:
                        run.bold = True
                        run.font.color.rgb = (RGBColor(5, 150, 105) if q.get("_qa_status") == "pass" else RGBColor(180, 83, 9))

    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


def extract_blueprint_preview_rows(blueprint: dict) -> list[dict]:
    rows = []
    for bp in blueprint.get("blueprints", []):
        forms = bp.get("forms", {})
        rows.append({
            "ID": bp.get("id"),
            "Bab": bp.get("chapter"),
            "ATP": bp.get("atp"),
            "Indikator Soal": bp.get("indicator"),
            "Level Kognitif": bp.get("cognitive_level") or "—",
            "PG": ", ".join(map(str, forms.get("PG", []))) or "—",
            "Isian": ", ".join(map(str, forms.get("Isian", []))) or "—",
            "Uraian": ", ".join(map(str, forms.get("Uraian", []))) or "—",
        })
    return rows
