"""FastAPI + HTMX routes for CBT OMI."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from features.omi.domain.config import KISI_KISI_OMI, STAGES, normalize_jenjang, subjects_for_jenjang, validate_subject
from features.omi.domain.service import result_for, solution_for, start_omi, hint_for
from features.omi.domain.session import anti_cheat, get_session, heartbeat, save_answer, public_quiz

router = APIRouter(prefix="/omi", tags=["OMI CBT"])
TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _setup_context(jenjang: str, mapel: str, nama: str = "", error: str | None = None):
    jenjang_norm = normalize_jenjang(jenjang)
    submateri = validate_subject(jenjang_norm, mapel)
    return {
        "jenjang": jenjang_norm,
        "mapel": mapel,
        "submateri": submateri,
        "stages": STAGES,
        "nama": nama,
        "error": error,
    }


@router.get("", response_class=HTMLResponse)
async def omi_root(request: Request):
    return templates.TemplateResponse(request=request, name="landing.html", context={"jenjangs": KISI_KISI_OMI.keys()})


@router.get("/setup", response_class=HTMLResponse)
async def omi_setup(request: Request, jenjang: str, mapel: str, nama: str = ""):
    try:
        context = _setup_context(jenjang, mapel, nama=nama)
    except ValueError as exc:
        try:
            fallback_jenjang = normalize_jenjang(jenjang)
            fallback_subjects = subjects_for_jenjang(fallback_jenjang)
        except ValueError:
            fallback_jenjang = jenjang
            fallback_subjects = {}
        return templates.TemplateResponse(request=request, name="subjects.html", context={"jenjang": fallback_jenjang, "subjects": fallback_subjects, "error": str(exc)})
    return templates.TemplateResponse(request=request, name="setup.html", context=context)


@router.post("/start", response_class=HTMLResponse)
async def omi_start(
    request: Request,
    nama: str = Form(...),
    jenjang: str = Form(...),
    mapel: str = Form(...),
    stage: str = Form("Internal"),
    selected_submateri: list[str] = Form(default=[]),
):
    sess, error = start_omi(nama, jenjang, mapel, stage, selected_submateri)
    if not sess:
        try:
            context = _setup_context(jenjang, mapel, nama=nama, error=error)
        except ValueError:
            context = {"jenjang": jenjang, "mapel": mapel, "submateri": [], "stages": STAGES, "nama": nama, "error": error}
        return templates.TemplateResponse(request=request, name="setup.html", context=context, status_code=422)
    return RedirectResponse(url=f"/omi/exam/{sess['session_id']}", status_code=303)


@router.get("/exam/{session_id}", response_class=HTMLResponse)
async def omi_exam(request: Request, session_id: str):
    sess = get_session(session_id)
    if not sess:
        return RedirectResponse(url="/omi", status_code=303)
    if sess.get("finished"):
        return RedirectResponse(url=f"/omi/result/{session_id}", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="exam.html",
        context={
            "session_id": session_id,
            "sess": sess,
            "quiz_json": public_quiz(sess),
            "answers_json": sess.get("answers", {}),
            "anti_cheat_json": sess.get("anti_cheat", {}),
            "jumlah_soal": len(sess.get("quiz", [])),
        },
    )


@router.post("/api/session/{session_id}/answer")
async def omi_answer(session_id: str, q_index: int = Form(...), answer: str = Form(...)):
    result = save_answer(session_id, q_index, answer)
    return HTMLResponse(content=result["message"], status_code=result["status"])


@router.post("/api/session/{session_id}/heartbeat")
async def omi_heartbeat(session_id: str):
    return HTMLResponse(content="", status_code=heartbeat(session_id))


@router.post("/api/session/{session_id}/anti-cheat")
async def omi_anti_cheat(session_id: str, violation_count: int = Form(0), reason: str = Form("Pindah tab")):
    result = anti_cheat(session_id, violation_count, reason)
    status = result.get("status", 200)
    if result.get("forced"):
        return HTMLResponse(content="STOP", status_code=status)
    return HTMLResponse(content=str(result.get("count", 0)), status_code=status)


@router.post("/api/session/{session_id}/hint", response_class=HTMLResponse)
async def omi_hint(session_id: str, q_index: int = Form(...), attempt_input: str = Form("")):
    text = hint_for(session_id, q_index, attempt_input)
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return HTMLResponse(
        content=f'<div class="p-3 bg-slate-900 border border-slate-800 rounded-lg text-slate-200 text-xs leading-relaxed mt-2 animate-fade-in"><div class="font-bold text-emerald-400 mb-1">🧕🏼 RoboMANTAP:</div><div id="hint-content">{safe}</div></div>'
    )


@router.post("/submit/{session_id}", response_class=HTMLResponse)
async def omi_submit(request: Request, session_id: str):
    result = result_for(session_id)
    if not result:
        return RedirectResponse(url="/omi", status_code=303)
    # Mark final only after the score has been computed from the server-side answers.
    from features.omi.domain.session import mark_finished
    mark_finished(session_id)
    return RedirectResponse(url=f"/omi/result/{session_id}", status_code=303)


@router.get("/result/{session_id}", response_class=HTMLResponse)
async def omi_result(request: Request, session_id: str):
    result = result_for(session_id)
    if not result:
        return RedirectResponse(url="/omi", status_code=303)
    if not result["sess"].get("finished"):
        return RedirectResponse(url=f"/omi/exam/{session_id}", status_code=303)
    sess = result["sess"]
    return templates.TemplateResponse(
        request=request,
        name="result.html",
        context={
            **result,
            "session_id": session_id,
            "quiz": sess.get("quiz", []),
            "answers": sess.get("answers", {}),
            "jenjang": sess.get("jenjang"),
            "mapel": sess.get("mapel"),
            "stage": sess.get("stage", "Internal"),
            "restart_url": f"/omi/setup?jenjang={quote(sess.get('jenjang', 'MA'))}&mapel={quote(sess.get('mapel', ''))}&nama={quote(sess.get('nama', ''))}",
        },
    )


@router.post("/api/session/{session_id}/solution/{q_index}", response_class=HTMLResponse)
async def omi_solution(session_id: str, q_index: int):
    text = solution_for(session_id, q_index)
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return HTMLResponse(content=f'<div class="mt-3 bg-slate-950 border border-emerald-500/20 rounded-xl p-4 text-xs text-slate-300 leading-relaxed"><div class="font-bold text-emerald-400 mb-2">🧕🏼 Pembahasan dari RoboMANTAP:</div><div>{safe}</div></div>')

@router.get("/{jenjang}", response_class=HTMLResponse)
async def omi_subjects(request: Request, jenjang: str):
    try:
        jenjang_norm = normalize_jenjang(jenjang)
        subjects = subjects_for_jenjang(jenjang_norm)
    except ValueError as exc:
        return templates.TemplateResponse(request=request, name="landing.html", context={"jenjangs": KISI_KISI_OMI.keys(), "error": str(exc)})
    return templates.TemplateResponse(
        request=request,
        name="subjects.html",
        context={"jenjang": jenjang_norm, "subjects": subjects},
    )


