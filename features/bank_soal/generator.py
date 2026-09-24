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
from .blueprint_parser import blueprint_summary, _option_count, _option_labels, _slot_list

def _infer_diagram_type(*texts: Any) -> str | None:
    """Infer an explicit geometric shape deterministically from source text."""
    patterns = [
        ("gabungan_jajargenjang_segitiga", r"gabungan\s+(?:antara\s+)?jajar\s*genjang\s+(?:dan|dengan)\s+segitiga|jajar\s*genjang\s+dan\s+segitiga"),
        ("persegi_panjang", r"persegi\s*panjang|rectangle"),
        ("layang_layang", r"layang\s*-?\s*layang|kite"),
        ("belah_ketupat", r"belah\s+ketupat|rhombus"),
        ("jajargenjang", r"jajar\s*genjang|parallelogram"),
        ("trapesium", r"trapes(?:ium|oid)|trapezoid"),
        ("segitiga", r"segitiga|triangle"),
        ("lingkaran", r"lingkaran|circle"),
        ("persegi", r"\bpersegi\b|square"),
    ]
    # Prefer the indicator/ATP/chapter order supplied by the caller, rather
    # than accidentally matching an unrelated shape mentioned later.
    for value in texts:
        text = _clean(value).lower()
        if not text:
            continue
        for dtype, pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return dtype
    return None

def _generation_prompt(
    bp: dict,
    variants: int,
    jenjang: str,
    mapel: str,
    kelas: str,
    language: str,
    requested_keys: list[tuple[int, str, int]] | None = None,
) -> str:
    labels = _option_labels(jenjang)
    if requested_keys is None:
        slots = [
            {"variant": v, "question_type": slot["question_type"], "source_number": slot["source_number"]}
            for v in range(1, variants + 1)
            for slot in _slot_list(bp)
        ]
    else:
        slots = [
            {"variant": int(v), "question_type": form, "source_number": int(number)}
            for v, form, number in requested_keys
        ]
    slot_text = json.dumps(slots, ensure_ascii=False)
    total = len(slots)
    explicit_shape = _infer_diagram_type(bp.get("indicator", ""), bp.get("atp", ""), bp.get("chapter", ""))
    shape_rule = (
        f"BENTUK DIAGRAM YANG DIWAJIBKAN OLEH SUMBER: {explicit_shape}. "
        "Jika soal membutuhkan gambar, diagram.type WAJIB sama dengan bentuk ini."
        if explicit_shape else
        "Sumber tidak menyebut bentuk secara eksplisit. Jika soal memang membutuhkan diagram, pilih tipe yang benar-benar sesuai dengan konteks soal."
    )

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

SLOT:
Total target keluaran = {total} pertanyaan.
Buat TEPAT satu pertanyaan untuk setiap kombinasi variant/question_type/source_number
yang tercantum pada daftar SLOT TARGET. Jangan menghilangkan atau menambah kombinasi.

ATURAN TIPE:
- PG: tepat {_option_count(jenjang)} pilihan: {", ".join(labels)}. Hanya satu jawaban benar.
- Isian: tidak memiliki opsi. Jawaban benar harus singkat dan jelas.
- Uraian: tidak memiliki opsi. correct_answer berisi inti jawaban/model answer,
  sedangkan solution_basis berisi langkah/pedoman penskoran ringkas.

ATURAN PRESISI:
1. Indikator harus tercermin langsung pada stimulus dan tuntutan jawaban.
2. Bila indikator mengatakan "disajikan soal cerita", gunakan soal cerita.
3. Bila indikator mengatakan "disajikan gambar", buat stimulus yang dapat diwujudkan melalui diagram.
4. Jangan mengarang fakta yang tidak diperlukan.
5. Untuk Matematika, hitung ulang angka dan pastikan jawabannya benar.
6. Setiap variasi harus benar-benar berbeda, bukan sekadar mengganti nama.
7. Jangan mengubah bentuk soal yang ditentukan blueprint.
8. Bahasa harus natural dan sesuai tingkat {jenjang}.
9. Untuk materi Arab/religius, gunakan bahasa yang sesuai bidang dan jangan mengarang kutipan agama.
10. Jika menggunakan notasi matematika, gunakan Unicode/LaTeX yang valid.
11. Level kognitif blueprint adalah CONSTRAINT WAJIB.

ATURAN DIAGRAM — SANGAT KETAT:
{shape_rule}
Jika indikator/question tidak membutuhkan gambar, diagram = null.
Jika membutuhkan gambar, diagram WAJIB berupa objek dengan:
- required: true
- type: salah satu tipe yang BENAR-BENAR sesuai dengan bentuk soal
- measurements: hanya angka yang memang disebut/digunakan dalam soal
- unit: satuan ukuran, misalnya "cm"; jangan mengubah satuan soal
- labels: label ukuran yang tampil pada gambar
- caption: singkat atau kosong

TIPE YANG DIDUKUNG DAN DATA WAJIB:
- persegi: sisi
- persegi_panjang: panjang + lebar
- segitiga: alas + tinggi
- lingkaran: radius (r) atau diameter (d)
- jajargenjang: alas + tinggi; sisi boleh ditambahkan jika memang dipakai soal
- trapesium: sisi_atas + sisi_bawah + tinggi
- belah_ketupat: d1 + d2
- layang_layang: d1 + d2
- gabungan_jajargenjang_segitiga: alas + tinggi_jajargenjang + tinggi_segitiga

JANGAN menggunakan diagram layang-layang hanya karena contoh. Jangan mengganti persegi,
persegi panjang, segitiga, trapesium, jajargenjang, atau belah ketupat menjadi layang-layang.
Untuk setiap diagram, angka pada measurements harus muncul sebagai data numerik yang sama
pada soal/stimulus, dan unit harus sama.

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
      "diagram": {{
        "required": true,
        "type": "persegi",
        "measurements": {{"sisi": 12}},
        "unit": "cm",
        "labels": {{"side": "12 cm"}},
        "caption": ""
      }}
    }}
  ]
}}

Keluaran HARUS berisi tepat {total} objek.
Gunakan variant, question_type, dan source_number PERSIS sesuai SLOT TARGET.
"""

def _parse_ai_json(raw: str) -> dict | list | None:
    """Parse Gemini JSON while tolerating either the documented object shape
    or a bare list of question objects returned by some model responses.
    """
    if not raw:
        return None
    cleaned = clean_json_text(raw)
    try:
        return json.loads(cleaned, strict=False)
    except Exception:
        pass

    # Fallback: first try a JSON object, then a JSON array.
    for pattern in (r"\{.*\}", r"\[.*\]"):
        match = re.search(pattern, raw, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0), strict=False)
            except Exception:
                continue
    return None

def _diagram_type_normalize(value: Any) -> str:
    text = _clean(value).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "layanglayang": "layang_layang", "layang_layang": "layang_layang", "kite": "layang_layang",
        "square": "persegi", "persegi": "persegi",
        "rectangle": "persegi_panjang", "persegi_panjang": "persegi_panjang",
        "triangle": "segitiga", "segitiga": "segitiga",
        "parallelogram": "jajargenjang", "jajargenjang": "jajargenjang", "jajar_genjang": "jajargenjang",
        "trapezoid": "trapesium", "trapesium": "trapesium",
        "rhombus": "belah_ketupat", "belah_ketupat": "belah_ketupat",
        "circle": "lingkaran", "circle_shape": "lingkaran", "lingkaran": "lingkaran",
        "gabungan": "gabungan_jajargenjang_segitiga",
        "gabungan_jajargenjang_segitiga": "gabungan_jajargenjang_segitiga",
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
                    clean_measurements[str(key).strip().lower()] = float(m.group(0).replace(",", "."))
            elif isinstance(value, (int, float)):
                clean_measurements[str(key).strip().lower()] = float(value)
        except Exception:
            continue
    labels = raw.get("labels") if isinstance(raw.get("labels"), dict) else {}
    unit = _clean(raw.get("unit"))
    if not unit:
        # Preserve a unit if the model put it in one of its labels.
        for value in labels.values():
            match = re.search(r"\d+(?:[.,]\d+)?\s*(mm|cm|m|km)\b", _clean(value), re.I)
            if match:
                unit = match.group(1).lower()
                break
    unit = unit or "cm"
    return {
        "required": bool(raw.get("required", True)),
        "type": dtype,
        "measurements": clean_measurements,
        "unit": unit,
        "labels": {str(k): _clean(v) for k, v in labels.items() if _clean(v)},
        "caption": _clean(raw.get("caption")),
    }

def _needs_diagram(indicator: str, question: str) -> bool:
    text = f"{indicator} {question}".lower()
    return bool(re.search(
        r"disajikan\s+(?:sebuah\s+)?gambar|perhatikan\s+gambar|dari\s+gambar|berdasarkan\s+gambar|lihat\s+gambar|pada\s+gambar",
        text,
    ))

def _extract_units(text: str) -> set[str]:
    return {u.lower() for u in re.findall(r"\b(?:mm|cm|m|km)\b", str(text or ""), flags=re.I)}

def _measurement_present_in_text(value: float, text: str) -> bool:
    """Check the numeric value without relying on exact decimal formatting."""
    normalized = str(text).replace(",", ".")
    candidates = {f"{float(value):g}", f"{float(value):.10g}"}
    for candidate in candidates:
        if re.search(rf"(?<!\d){re.escape(candidate)}(?!\d)", normalized):
            return True
    # Accept integer representation for a mathematically integral float.
    if float(value).is_integer():
        iv = str(int(value))
        return bool(re.search(rf"(?<!\d){re.escape(iv)}(?!\d)", normalized))
    return False

def _diagram_validation_error(q: dict, bp: dict) -> str | None:
    indicator = bp.get("indicator", "")
    question = q.get("question", "")
    needs = _needs_diagram(indicator, question)
    diagram = q.get("diagram")

    # Jika soal butuh gambar tapi AI tidak memberikan objek diagram sama sekali
    if needs and not isinstance(diagram, dict):
        return "diagram_missing"

    if isinstance(diagram, dict):
        dtype = _diagram_type_normalize(diagram.get("type"))
        if not dtype or dtype not in SUPPORTED_DIAGRAM_TYPES:
            return f"diagram_type_invalid={dtype}"
            
    return None

    expected = _infer_diagram_type(indicator, question, bp.get("atp", ""), bp.get("chapter", ""))
    dtype = _diagram_type_normalize(diagram.get("type"))
    if expected and dtype != expected:
        return f"diagram_type_mismatch expected={expected} got={dtype}"

    measurements = diagram.get("measurements") or {}
    if not isinstance(measurements, dict):
        return "diagram_measurements_invalid"

    # Normalize common aliases to the canonical renderer keys.
    aliases = {
        "side": "sisi", "length": "panjang", "width": "lebar", "base": "alas", "height": "tinggi",
        "top": "sisi_atas", "top_base": "sisi_atas", "bottom": "sisi_bawah", "bottom_base": "sisi_bawah",
        "vertical_diagonal": "d1", "diagonal_vertical": "d1", "horizontal_diagonal": "d2", "diagonal_horizontal": "d2",
        "radius": "r", "jari_jari": "r", "diameter": "d",
        "height_parallelogram": "tinggi_jajargenjang", "height_triangle": "tinggi_segitiga",
    }
    canonical = {}
    for key, value in measurements.items():
        canonical[aliases.get(str(key).lower(), str(key).lower())] = value

    required_groups = DIAGRAM_REQUIREMENTS.get(dtype, ())
    for group in required_groups:
        if not any(k in canonical and isinstance(canonical[k], (int, float)) and float(canonical[k]) > 0 for k in group):
            return f"diagram_measurement_missing type={dtype} requires={group}"

    source_text = f"{indicator} {question}"
    for value in canonical.values():
        try:
            if not _measurement_present_in_text(float(value), source_text):
                return f"diagram_measurement_not_in_question value={value}"
        except Exception:
            return "diagram_measurement_invalid_value"

    unit = _clean(diagram.get("unit")) or "cm"
    if not re.fullmatch(r"(?:mm|cm|m|km)", unit, flags=re.I):
        return f"diagram_unit_invalid={unit}"
    source_units = _extract_units(source_text)
    if source_units and unit.lower() not in source_units:
        return f"diagram_unit_mismatch expected={sorted(source_units)} got={unit}"
    return None

def render_math_diagram(spec: dict) -> bytes | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        from matplotlib.patches import Polygon
    except Exception:
        return None

    dtype = spec.get("type")
    m = spec.get("measurements", {}) or {}
    unit = _clean(spec.get("unit")) or "cm"

    # 1. Canvas mini (1.5 x 1.2 inci) agar kualitas garis menyesuaikan ukuran sangat kecil
    fig, ax = plt.subplots(figsize=(1.5, 1.2), dpi=250)
    ax.set_aspect("equal")
    ax.axis("off")

    def _fmt(value):
        try:
            return f"{float(value):g}"
        except Exception:
            return str(value)

    # 2. Font dibesarkan relatif terhadap ukuran gambar yang kecil
    def label(x, y, text, fontsize=9.5):
        ax.text(
            x, y, text,
            fontsize=fontsize, ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none", alpha=0.9),
            zorder=8,
        )

    def dim(a, b, text, text_xy=None):
        ax.annotate(
            "", xy=b, xytext=a,
            arrowprops=dict(arrowstyle="<->", lw=0.6, shrinkA=0, shrinkB=0),
            zorder=5,
        )
        if text_xy is None:
            text_xy = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        label(text_xy[0], text_xy[1], text)

    def add_right_angle(pt, dx, dy, size):
        ax.plot([pt[0]+dx*size, pt[0]+dx*size], [pt[1], pt[1]+dy*size], color='black', lw=0.6)
        ax.plot([pt[0], pt[0]+dx*size], [pt[1]+dy*size, pt[1]+dy*size], color='black', lw=0.6)

    def num(*keys):
        for key in keys:
            if m.get(key) is not None:
                try:
                    v = float(m.get(key))
                    if v > 0: return v
                except Exception: pass
        return None

    # 3. Fault-Tolerant Rendering: Jika AI lupa ukuran, gambar tidak crash (pakai default proporsi visual)
    if dtype == "layang_layang":
        d1 = num("d1", "tinggi", "height") or 10
        d2 = num("d2", "lebar", "width") or 6
        w = d2 / 2
        top, bottom = d1 * 0.3, d1 * 0.7
        pts = np.array([[0, top], [w, 0], [0, -bottom], [-w, 0]])
        ax.add_patch(Polygon(pts, closed=True, fill=False, linewidth=1.0))
        ax.plot([-w, w], [0, 0], linewidth=0.5, linestyle="--")
        ax.plot([0, 0], [-bottom, top], linewidth=0.5, linestyle="--")
        
        gap = max(w, d1) * 0.15
        if num("d1", "tinggi", "height"):
            dim((w + gap, -bottom), (w + gap, top), f"{_fmt(d1)} {unit}", (w + gap*1.5, -bottom/2 + top/2))
        if num("d2", "lebar", "width"):
            dim((-w, -bottom-gap), (w, -bottom-gap), f"{_fmt(d2)} {unit}", (0, -bottom-gap*1.5))

    elif dtype == "persegi":
        s = num("sisi", "side", "panjang", "length") or 5
        pts = np.array([[0, 0], [s, 0], [s, s], [0, s]])
        ax.add_patch(Polygon(pts, closed=True, fill=False, linewidth=1.0))
        gap = s * 0.15
        if num("sisi", "side", "panjang", "length"):
            dim((0, -gap), (s, -gap), f"{_fmt(s)} {unit}", (s/2, -gap*2.2))
            dim((s+gap, 0), (s+gap, s), f"{_fmt(s)} {unit}", (s+gap*2.2, s/2))

    elif dtype == "persegi_panjang":
        p = num("panjang", "length", "p", "base", "alas") or 8
        l = num("lebar", "width", "l", "height", "tinggi") or 4
        pts = np.array([[0, 0], [p, 0], [p, l], [0, l]])
        ax.add_patch(Polygon(pts, closed=True, fill=False, linewidth=1.0))
        gap = max(p, l) * 0.15
        if num("panjang", "length", "p", "base", "alas"):
            dim((0, -gap), (p, -gap), f"{_fmt(p)} {unit}", (p/2, -gap*2.2))
        if num("lebar", "width", "l", "height", "tinggi"):
            dim((p+gap, 0), (p+gap, l), f"{_fmt(l)} {unit}", (p+gap*2.2, l/2))

    elif dtype in ("segitiga", "segitiga_siku_siku"):
        b = num("alas", "base", "b") or 6
        h = num("tinggi", "height", "h") or 5
        gap = max(b, h) * 0.15
        if dtype == "segitiga_siku_siku":
            pts = np.array([[0, 0], [b, 0], [0, h]])
            ax.add_patch(Polygon(pts, closed=True, fill=False, linewidth=1.0))
            add_right_angle([0,0], 1, 1, min(b, h)*0.1)
            
            if num("alas", "base", "b"):
                dim((0, -gap), (b, -gap), f"{_fmt(b)} {unit}", (b/2, -gap*2))
            if num("tinggi", "height", "h"):
                dim((-gap, 0), (-gap, h), f"{_fmt(h)} {unit}", (-gap*2, h/2))
        else:
            x0 = -b / 2
            pts = np.array([[x0, 0], [x0+b, 0], [0, h]])
            ax.add_patch(Polygon(pts, closed=True, fill=False, linewidth=1.0))
            ax.plot([0, 0], [0, h], linestyle="--", linewidth=0.5)
            if num("alas", "base", "b"):
                dim((x0, -gap), (x0+b, -gap), f"{_fmt(b)} {unit}", (0, -gap*2.2))
            if num("tinggi", "height", "h"):
                dim((x0+b+gap, 0), (x0+b+gap, h), f"{_fmt(h)} {unit}", (x0+b+gap*2.2, h/2))

    elif dtype == "lingkaran":
        radius = num("r", "radius", "jari_jari")
        if not radius:
            d = num("d", "diameter")
            radius = (d / 2) if d else 5
        theta = np.linspace(0, 2*np.pi, 120)
        ax.plot(radius*np.cos(theta), radius*np.sin(theta), linewidth=1.0)
        ax.plot([0, radius], [0, 0], linestyle="--", linewidth=0.5)
        if num("r", "radius", "jari_jari") or num("d", "diameter"):
            label(radius/2, radius*0.25, f"r = {_fmt(radius)} {unit}")

    elif dtype == "jajargenjang":
        b = num("alas", "base", "panjang") or 8
        h = num("tinggi", "height", "h") or 4
        sisi = num("sisi", "side", "lebar")
        skew = np.sqrt(sisi**2 - h**2) if (sisi and sisi > h) else (b * 0.25)
        
        pts = np.array([[0, 0], [b, 0], [b+skew, h], [skew, h]])
        ax.add_patch(Polygon(pts, closed=True, fill=False, linewidth=1.0))
        ax.plot([skew, skew], [0, h], linestyle="--", linewidth=0.5)
        gap = max(b, h) * 0.15
        if num("alas", "base", "panjang"):
            dim((0, -gap), (b, -gap), f"{_fmt(b)} {unit}", (b/2, -gap*2.2))
        if num("tinggi", "height", "h"):
            xdim = b + skew + gap
            dim((xdim, 0), (xdim, h), f"{_fmt(h)} {unit}", (xdim + gap, h/2))

    elif dtype in ("trapesium", "trapesium_siku_siku"):
        a = num("sisi_atas", "atas", "a") or 4
        b = num("sisi_bawah", "bawah", "b") or 8
        h = num("tinggi", "height", "h") or 4
        gap = max(b, h) * 0.15
        
        if dtype == "trapesium_siku_siku":
            pts = np.array([[0, 0], [b, 0], [a, h], [0, h]])
            ax.add_patch(Polygon(pts, closed=True, fill=False, linewidth=1.0))
            add_right_angle([0,0], 1, 1, min(a,b,h)*0.1)
            add_right_angle([0,h], 1, -1, min(a,b,h)*0.1)
            
            if num("sisi_bawah", "bawah", "b"):
                dim((0, -gap), (b, -gap), f"{_fmt(b)} {unit}", (b/2, -gap*2))
            if num("tinggi", "height", "h"):
                dim((-gap, 0), (-gap, h), f"{_fmt(h)} {unit}", (-gap*2, h/2))
            if num("sisi_atas", "atas", "a"):
                label(a/2, h + gap*1.2, f"{_fmt(a)} {unit}")
        else:
            x = (b-a) / 2
            pts = np.array([[0, 0], [b, 0], [b-x, h], [x, h]])
            ax.add_patch(Polygon(pts, closed=True, fill=False, linewidth=1.0))
            ax.plot([x, x], [0, h], linestyle="--", linewidth=0.5)
            if num("sisi_bawah", "bawah", "b"):
                dim((0, -gap), (b, -gap), f"{_fmt(b)} {unit}", (b/2, -gap*2.2))
            if num("tinggi", "height", "h"):
                dim((b+gap, 0), (b+gap, h), f"{_fmt(h)} {unit}", (b+gap*2.2, h/2))
            if num("sisi_atas", "atas", "a"):
                label(b/2, h + gap*1.2, f"{_fmt(a)} {unit}")

    elif dtype == "belah_ketupat":
        d1 = num("d1", "tinggi") or 8
        d2 = num("d2", "lebar") or 6
        w, h = d2/2, d1/2
        pts = np.array([[0, h], [w, 0], [0, -h], [-w, 0]])
        ax.add_patch(Polygon(pts, closed=True, fill=False, linewidth=1.0))
        ax.plot([-w, w], [0, 0], linestyle="--", linewidth=0.5)
        ax.plot([0, 0], [-h, h], linestyle="--", linewidth=0.5)
        gap = max(w, h) * 0.15
        if num("d1", "tinggi"):
            dim((w+gap, -h), (w+gap, h), f"{_fmt(d1)} {unit}", (w+gap*2, 0))
        if num("d2", "lebar"):
            dim((-w, -h-gap), (w, -h-gap), f"{_fmt(d2)} {unit}", (0, -h-gap*2.2))

    elif dtype == "gabungan_jajargenjang_segitiga":
        b = num("alas") or 8
        h = num("tinggi_jajargenjang") or 4
        ht = num("tinggi_segitiga") or 3
        skew = b*0.2
        poly1 = np.array([[0,0],[b,0],[b+skew,h],[skew,h]])
        poly2 = np.array([[skew,h],[b+skew,h],[b/2+skew,h+ht]])
        ax.add_patch(Polygon(poly1, closed=True, fill=False, linewidth=1.0))
        ax.add_patch(Polygon(poly2, closed=True, fill=False, linewidth=1.0))
        ax.plot([skew,skew],[0,h],linestyle="--",linewidth=0.5)
        gap = max(b,h,ht)*0.15
        if num("alas"):
            dim((0,-gap),(b,-gap),f"{_fmt(b)} {unit}",(b/2,-gap*2.2))
        if num("tinggi_jajargenjang"):
            dim((skew-gap,0),(skew-gap,h),f"{_fmt(h)} {unit}",(skew-gap*2.2,h/2))
        if num("tinggi_segitiga"):
            dim((b/2+skew+gap,h),(b/2+skew+gap,h+ht),f"{_fmt(ht)} {unit}",(b/2+skew+gap*2,h+ht/2))
    else:
        plt.close(fig)
        return None

    # Padding ekstrem agar teks ukuran yang membesar tidak terpotong tepi gambar
    ax.margins(x=0.45, y=0.45)
    fig.tight_layout(pad=0.15)
    
    output = io.BytesIO()
    fig.savefig(output, format="png", bbox_inches="tight", pad_inches=0.1, facecolor="white")
    plt.close(fig)
    return output.getvalue()

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
    """Generate one blueprint with fast full-batch generation and targeted repair.

    First call requests every expected key. If Gemini returns a partial set,
    only the missing variant/form/number keys are requested on the repair call.
    This avoids regenerating a successful blueprint and keeps latency bounded.
    """
    expected = _expected_keys(bp, variants)
    pending = set(expected)
    accepted: dict[tuple[int, str, int], dict] = {}
    max_attempts = max(1, min(int(attempts), 2))

    for attempt_no in range(1, max_attempts + 1):
        target_keys = sorted(pending)
        if not target_keys:
            break
        prompt = _generation_prompt(
            bp, variants, jenjang, mapel, kelas, language,
            requested_keys=target_keys,
        )
        prompt += (
            "\n\nVARIANT ID WAJIB:\n"
            "Gunakan variant/form/source_number PERSIS sesuai SLOT TARGET. "
            "Jangan mengembalikan slot yang tidak diminta."
        )

        raw = call_gemini_with_rotation(
            prompt,
            is_json=True,
            thinking_level="low",
            max_output_tokens=16000,
        )
        data = _parse_ai_json(raw)
        if isinstance(data, list):
            data = {"questions": data}
        if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
            continue

        normalized = []
        for item in data["questions"]:
            q = _normalize_generated_question(item, jenjang)
            if q:
                q["blueprint_id"] = bp["id"]
                normalized.append(q)

        # Accept only returned keys that were actually requested. Duplicates
        # are ignored so one malformed duplicate cannot overwrite a valid key.
        for q in normalized:
            key = (int(q.get("variant", 0)), q.get("question_type"), int(q.get("source_number", -1)))
            if key not in pending:
                continue
            if _diagram_validation_error(q, bp):
                continue
            accepted[key] = q

        pending = expected - set(accepted.keys())

        if not pending:
            result = list(accepted.values())
            issues = _deterministic_alignment_issues(result, bp, variants, jenjang)
            if not issues:
                return result
            return []

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
    raw = call_gemini_with_rotation(
        prompt, is_json=True, thinking_level="low", max_output_tokens=8000
    )
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

    missing_total = max(0, expected_total - len(all_questions))
    report = {
        "expected_total": expected_total,
        "generated_total": len(all_questions),
        "missing_total": missing_total,
        "deterministic_ok": deterministic_ok,
        "ai_qa": ai_qa,
        "row_reports": row_reports,
        "pass_count": sum(q.get("_qa_status") == "pass" for q in all_questions),
        "review_count": sum(q.get("_qa_status") == "review" for q in all_questions),
    }
    return all_questions, report
