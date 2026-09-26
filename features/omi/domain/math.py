"""Result-only math/text sanitizer shared with the proven Quiz Custom cleaner.

This module is intentionally used only by the OMI result/pembahasan display.
The stored question/answer data is never mutated.
"""
from __future__ import annotations

import html
import re


def clean_math_string(text: str) -> str:
    if text is None:
        return ""
    text = str(text)
    replacements = {
        r"\rightarrow": "→", r"\to": "→", r"\Rightarrow": "⇒",
        r"\leftarrow": "←", r"\leftrightarrow": "↔",
        r"\circ": "∘", r"\circl": "∘",
        r"\times": "×", r"\cdot": "·", r"\div": "÷", r"\neq": "≠",
        r"\leq": "≤", r"\geq": "≥", r"\le": "≤", r"\ge": "≥",
        r"\pm": "±", r"\mp": "∓", r"\infty": "∞", r"\pi": "π",
        r"\alpha": "α", r"\beta": "β", r"\theta": "θ", r"\lambda": "λ",
        r"\in": "∈", r"\notin": "∉", r"\forall": "∀", r"\exists": "∃",
        r"\emptyset": "∅", r"\angle": "∠", r"\perp": "⊥", r"\parallel": "∥",
        r"\implies": "⇒", r"\impliedby": "⇐", r"\iff": "⇔",
        r"\Longleftrightarrow": "⇔", r"\longleftrightarrow": "↔",
        r"\Longleftarrow": "⇐", r"\Longrightarrow": "⇒",
        r"\approx": "≈", r"\equiv": "≡", r"\propto": "∝",
        r"\sum": "Σ", r"\prod": "Π", r"\int": "∫", r"\partial": "∂",
        r"\nabla": "∇", r"\Delta": "Δ", r"\Omega": "Ω",
        r"\Gamma": "Γ", r"\Lambda": "Λ", r"\Sigma": "Σ", r"\Phi": "Φ",
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
    sub_map = str.maketrans("0123456789+-=()nixy", "₀₁₂₃₄⁵₆₇₈₉₊₋₌₍₎ₙᵢₓᵧ")
    text = re.sub(r"\^\{([^}]+)\}|\^([\-0-9a-zA-Z])", lambda m: (m.group(1) or m.group(2)).translate(sup_map), text)
    text = re.sub(r"\_\{([^}]+)\}|\_([0-9a-zA-Z])", lambda m: (m.group(1) or m.group(2)).translate(sub_map), text)
    text = text.replace("$", "")
    text = text.replace("left(", "(").replace("right)", ")").replace("dots", "…")
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"\\([a-zA-Z]+)", r"\1", text).replace("\\", "")
    return re.sub(r"\s+", " ", text).strip()


def clean_solution_preview(text: str) -> str:
    """Exact result-oriented behavior of the proven Quiz Custom cleaner."""
    if not text:
        return ""
    value = str(text).strip()
    value = re.sub(r"(?<![A-Za-z])circl(?![A-Za-z])", lambda _: r"\circ", value)
    simple_math = {
        r"\longrightarrow": "→", r"\rightarrow": "→", r"\to": "→",
        r"\Longrightarrow": "⇒", r"\Rightarrow": "⇒",
        r"\leftarrow": "←", r"\leftrightarrow": "↔",
        r"\times": "×", r"\cdot": "·", r"\div": "÷",
        r"\neq": "≠", r"\leq": "≤", r"\le": "≤",
        r"\geq": "≥", r"\ge": "≥", r"\pm": "±",
        r"\infty": "∞", r"\circ": "∘", r"\perp": "⊥",
        r"\parallel": "∥", r"\angle": "∠", r"\in": "∈",
        r"\notin": "∉", r"\forall": "∀", r"\exists": "∃",
        r"\emptyset": "∅", r"\pi": "π", r"\alpha": "α",
        r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
        r"\theta": "θ", r"\lambda": "λ", r"\mu": "μ",
        r"\approx": "≈", r"\equiv": "≡", r"\propto": "∝",
        r"\sum": "Σ", r"\int": "∫", r"\partial": "∂",
        r"\Delta": "Δ", r"\Omega": "Ω", r"\degree": "°",
    }
    for old, new in simple_math.items():
        value = value.replace(old, new)
    value = value.replace(" -> ", " → ").replace(" => ", " ⇒ ")
    value = value.replace("->", "→").replace("=>", "⇒")
    value = re.sub(r"\\left\s*([\(\[\{])", r"\1", value)
    value = re.sub(r"\\right\s*([\)\]\}])", r"\1", value)
    value = re.sub(r"\\(?:mathrm|text|mathbf|operatorname)\{([^{}]+)\}", r"\1", value)
    value = re.sub(r"\\ce\{([^{}]+)\}", r"\1", value)

    # Keep fractions/roots as KaTeX instead of flattening them to plain text.
    value = re.sub(r"\\frac\{[^{}]+\}\{[^{}]+\}", lambda m: f"${m.group(0)}$", value)
    value = re.sub(r"\\sqrt(?:\{[^{}]+\}|[A-Za-z0-9]+)", lambda m: f"${m.group(0)}$", value)

    sup_map = str.maketrans("0123456789+-=()nxyi", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿˣʸⁱ")
    sub_map = str.maketrans("0123456789+-=()nixy", "₀₁₂₃₄⁵₆₇₈₉₊₋₌₍₎ₙᵢₓᵧ")
    value = re.sub(r"\^\{([^}]+)\}|\^([A-Za-z0-9])", lambda m: (m.group(1) or m.group(2)).translate(sup_map), value)
    value = re.sub(r"_\{([^}]+)\}|_([A-Za-z0-9])", lambda m: (m.group(1) or m.group(2)).translate(sub_map), value)
    value = value.replace("$$$$", "")
    value = re.sub(r"\$\s*\$", "", value)
    return value.strip()


def display_math_html(text: str) -> str:
    """Sanitize for HTML while preserving $...$ delimiters for KaTeX."""
    cleaned = clean_solution_preview(text)
    return html.escape(cleaned).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
