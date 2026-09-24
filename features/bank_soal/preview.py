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

from .blueprint_parser import extract_blueprint_from_docx, extract_blueprint_from_source

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
