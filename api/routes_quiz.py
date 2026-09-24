"""HTTP routes for the student CBT domain."""
from fastapi import APIRouter, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from features.quiz.cbt_service import verify_and_create_session, exam_context, save_answer, heartbeat, anti_cheat_event, submit_exam, hint, STREAMLIT_URL, initialize_database

router = APIRouter()
TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@router.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="student_login.html", context={"error": None})

@router.post("/verify-token", response_class=HTMLResponse)
async def verify_token(request: Request, nama: str = Form(...), kelas: str = Form(...), absen: str = Form(...), token: str = Form(...)):
    result = verify_and_create_session(nama, kelas, absen, token)
    if not result["ok"]:
        return templates.TemplateResponse(request=request, name="student_login.html", context={"error": result["error"]})
    return RedirectResponse(url=f"/exam/{result['session_id']}", status_code=status.HTTP_303_SEE_OTHER)

async def _render_exam(request: Request, session_id: str):
    sess, context = exam_context(session_id)
    if not sess:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    if context.get("redirect"):
        return RedirectResponse(url=context["redirect"], status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="student_exam.html", context=context)

@router.post("/start-exam", response_class=HTMLResponse)
async def start_exam_post(request: Request, session_id: str = Form(...)):
    return await _render_exam(request, session_id)

@router.get("/exam/{session_id}", response_class=HTMLResponse)
async def start_exam_get(request: Request, session_id: str):
    return await _render_exam(request, session_id)

@router.post("/api/save-answer")
async def save_answer_route(session_id: str = Form(...), q_index: int = Form(...), answer: str = Form(...)):
    code, body = save_answer(session_id, q_index, answer)
    return HTMLResponse(content=body, status_code=code)

@router.post("/api/session-heartbeat")
async def session_heartbeat(session_id: str = Form(...)):
    return HTMLResponse(content="", status_code=heartbeat(session_id))

@router.post("/api/anti-cheat")
async def anti_cheat_route(session_id: str = Form(...), violation_count: int = Form(0), reason: str = Form("Pindah tab")):
    code, body = anti_cheat_event(session_id, violation_count, reason)
    return HTMLResponse(content=body, status_code=code)

@router.post("/submit-exam", response_class=HTMLResponse)
async def submit_exam_route(request: Request, session_id: str = Form(...), anti_cheat_detected: str = Form("0"), anti_cheat_reason: str = Form(""), anti_cheat_count: int = Form(0)):
    result = submit_exam(session_id, anti_cheat_detected, anti_cheat_reason, anti_cheat_count)
    if result is None:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="student_result.html", context=result)

@router.post("/api/hint", response_class=HTMLResponse)
async def handle_hint_request(curr_idx: int = Form(...), mapel: str = Form(""), question: str = Form(""), attempt_input: str = Form("")):
    return HTMLResponse(content=hint(curr_idx, mapel, question, attempt_input), status_code=200)
