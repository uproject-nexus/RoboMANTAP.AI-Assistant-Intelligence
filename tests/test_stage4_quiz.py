import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

def test_stage4_quiz_modules_import():
    from features.quiz import cbt_service, session_store
    from api import routes_quiz, application
    assert application.app is not None
    assert routes_quiz.router is not None
    assert isinstance(session_store.STUDENT_SESSIONS, dict)

def test_stage4_route_contracts():
    from api.application import app
    paths = {r.path for r in app.routes}
    required = {"/", "/verify-token", "/exam/{session_id}", "/api/save-answer", "/api/session-heartbeat", "/api/anti-cheat", "/submit-exam", "/api/hint"}
    assert required.issubset(paths)
