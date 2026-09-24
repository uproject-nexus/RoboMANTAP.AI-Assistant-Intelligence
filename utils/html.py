"""HTML safety helpers for UI rendering."""
from __future__ import annotations
import html


def escape_html(value: str) -> str:
    return html.escape(str(value or ""), quote=True)
