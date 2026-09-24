"""In-memory CBT session store.

This preserves the current deployment model: the FastAPI process owns active
student sessions in memory. Persistent progress remains in the database layer.
"""
from typing import Any, Dict

STUDENT_SESSIONS: Dict[str, Dict[str, Any]] = {}


def get_session(session_id: str):
    return STUDENT_SESSIONS.get(session_id)


def put_session(session_id: str, session: Dict[str, Any]) -> None:
    STUDENT_SESSIONS[session_id] = session


def remove_session(session_id: str) -> None:
    STUDENT_SESSIONS.pop(session_id, None)
