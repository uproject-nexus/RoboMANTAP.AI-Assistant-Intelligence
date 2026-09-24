"""Public Student Intelligence application service."""
from .analytics import (
    STUDENT_INTELLIGENCE_VERSION, student_key, fetch_student_sessions,
    build_student_profile,
)
from infrastructure.database.student_intelligence import (
    ensure_student_intelligence_tables, save_profile, record_action,
)


def save_student_profile(nama_siswa: str, jenjang: str, profile: dict) -> bool:
    return save_profile(student_key(nama_siswa, jenjang), nama_siswa, jenjang, profile)


def record_student_action(nama_siswa: str, jenjang: str, action_type: str, title: str, payload=None) -> bool:
    return record_action(student_key(nama_siswa, jenjang), action_type, title, payload)


def render_student_intelligence_dashboard(nama_siswa: str = "", jenjang: str = "Semua Jenjang") -> None:
    # UI import remains lazy so analytics/service can be tested without Streamlit.
    from .domain import render_student_intelligence_dashboard as _render
    return _render(nama_siswa, jenjang)


def start_adaptive_practice(name: str, grade: str, profile: dict):
    from .domain import _start_adaptive_practice
    return _start_adaptive_practice(name, grade, profile)

__all__ = [
    "STUDENT_INTELLIGENCE_VERSION", "student_key", "fetch_student_sessions",
    "build_student_profile", "ensure_student_intelligence_tables",
    "save_student_profile", "record_student_action",
    "render_student_intelligence_dashboard", "start_adaptive_practice",
]
