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
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from ai_engine import call_gemini_with_rotation, clean_json_text


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
      "solution_basis": "..."
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
    prompt = _generation_prompt(bp, variants, jenjang, mapel, kelas, language)
    for _ in range(max(1, attempts)):
        raw = call_gemini_with_rotation(prompt, is_json=True)
        data = _parse_ai_json(raw)
        if not data or not isinstance(data.get("questions"), list):
            continue
        normalized = []
        for item in data["questions"]:
            q = _normalize_generated_question(item, jenjang)
            if q:
                q["blueprint_id"] = bp["id"]
                normalized.append(q)
        issues = _deterministic_alignment_issues(normalized, bp, variants, jenjang)
        if not issues:
            return normalized
    return []


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
- atau secara substantif tidak memenuhi level kognitif C1–C6 yang ditetapkan blueprint.

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
    variant_values = sorted({
        int(q.get("variant", 0))
        for q in questions
        if q.get("variant") is not None
    })

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
            for variant in variant_values
            for form in FORM_ORDER
        }
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
                r2 = p.add_run(q.get("question", ""))
                r2.font.size = Pt(10)

                if form == "PG":
                    for opt in q.get("options", []):
                        po = doc.add_paragraph()
                        po.paragraph_format.left_indent = Inches(0.22)
                        po.paragraph_format.space_after = Pt(1)
                        ro = po.add_run(opt)
                        ro.font.size = Pt(9.5)

                if include_answer_key:
                    pa = doc.add_paragraph()
                    pa.paragraph_format.left_indent = Inches(0.22)
                    ra = pa.add_run("Kunci: ")
                    ra.bold = True
                    ra.font.size = Pt(8.5)
                    rb = pa.add_run(q.get("correct_answer", ""))
                    rb.font.size = Pt(8.5)
                    rb.font.color.rgb = RGBColor(5, 150, 105)

                    ps = doc.add_paragraph()
                    ps.paragraph_format.left_indent = Inches(0.22)
                    rs = ps.add_run("Pembahasan: ")
                    rs.bold = True
                    rs.font.size = Pt(8.5)
                    rt = ps.add_run(q.get("solution_basis", ""))
                    rt.font.size = Pt(8.5)
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
