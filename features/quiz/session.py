"""Quiz session utilities."""
from .session_store import STUDENT_SESSIONS, get_session, put_session, remove_session

# Stable question-order helpers remain compatibility hooks until their DB-backed
# repository is extracted in a later pass.
def build_stable_student_quiz_order(*args, **kwargs):
    from legacy.app import build_stable_student_quiz_order as fn
    return fn(*args, **kwargs)

def ensure_quiz_session_order_table(*args, **kwargs):
    from legacy.app import ensure_quiz_session_order_table as fn
    return fn(*args, **kwargs)

def get_or_create_student_quiz_order(*args, **kwargs):
    from legacy.app import get_or_create_student_quiz_order as fn
    return fn(*args, **kwargs)

__all__ = ["STUDENT_SESSIONS", "get_session", "put_session", "remove_session", "build_stable_student_quiz_order", "ensure_quiz_session_order_table", "get_or_create_student_quiz_order"]
