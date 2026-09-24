"""Shared mathematical text normalization.

The OMML document renderer remains in infrastructure/documents/math.py for a
later document-migration stage. This utility keeps only normalization logic.
"""
from __future__ import annotations
import re


def clean_math_string(text: str) -> str:
    if not text:
        return ""
    text = str(text)
    replacements = {
        r"\rightarrow": "→", r"\to": "→", r"\Rightarrow": "⇒",
        r"\leftarrow": "←", r"\leftrightarrow": "↔", r"\circ": "∘",
        r"\circl": "∘", r"\times": "×", r"\cdot": "·", r"\div": "÷",
        r"\neq": "≠", r"\leq": "≤", r"\geq": "≥", r"\le": "≤", r"\ge": "≥",
        r"\pm": "±", r"\mp": "∓", r"\infty": "∞", r"\pi": "π",
        r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
        r"\theta": "θ", r"\lambda": "λ", r"\mu": "μ", r"\sigma": "σ",
        r"\subset": "⊂", r"\subseteq": "⊆", r"\supset": "⊃", r"\supseteq": "⊇",
        r"\in": "∈", r"\notin": "∉", r"\forall": "∀", r"\exists": "∃",
        r"\emptyset": "∅", r"\angle": "∠", r"\perp": "⊥", r"\parallel": "∥",
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
    text = re.sub(r"\_\{([^}]+)\}|\_([0-9a-zA-Z])", lambda m: (m.group(1) or m.group(2)).translate(sub_map), text)
    text = text.replace("$", "").replace("left(", "(").replace("right)", ")").replace("dots", "…")
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"\\([a-zA-Z]+)", r"\1", text).replace("\\", "")
    return re.sub(r"\s+", " ", text).strip()

clean_math_text = clean_math_string
