from __future__ import annotations

import io, os, re, json, math, html, tempfile
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
from infrastructure.ai.service import call_gemini_with_rotation, clean_json_text
from infrastructure.ai.material import _call_gemini_contents
try:
    from google.genai import types
except Exception:
    types = None

FORM_ORDER = ("PG", "Isian", "Uraian")
COGNITIVE_LEVELS = ("C1", "C2", "C3", "C4", "C5", "C6")

from .common import _normalize_cognitive_level, _cognitive_levels, _find_cognitive_column, _clean, clean_math_string, contains_arabic, apply_arabic_paragraph_style, apply_arabic_run_style, add_omml_fraction, add_omml_matrix, append_text_with_fractions, _cell_clean, _parse_question_numbers, _is_chapter_row, _looks_like_header, _looks_like_form_header

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
