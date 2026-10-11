from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from ai_engine import get_ai_hint_stream
from tka_engine import (
    TKA_DEFAULT_DURATION_SECONDS,
    TKA_TOTAL_QUESTIONS,
    ensure_tka_tables,
    get_tka_from_db,
    get_tka_image,
    generate_tka_30,
    normalize_tka_jenjang,
    touch_tka_heartbeat,
    update_tka_progress,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates-tka")
STREAMLIT_URL = os.getenv("STREAMLIT_URL", "https://robomantap-intelligence.streamlit.app/")

app = FastAPI(title="RoboMANTAP TKA Portal")
templates = Jinja2Templates(directory=TEMPLATES_DIR)
STUDENT_SESSIONS: dict[str, dict[str, Any]] = {}
ai_hint_cache: dict[tuple, str] = {}

TKA_MTS_MAPELS = {"Bahasa Indonesia", "Matematika"}
TKA_MA_MAPELS = {
    "Bahasa Indonesia", "Matematika", "Bahasa Inggris",
    "Matematika Lanjutan", "Bahasa Indonesia Lanjutan", "Bahasa Inggris Lanjutan",
    "Fisika", "Kimia", "Biologi", "Ekonomi", "Sosiologi", "Geografi", "Sejarah",
    "Antropologi", "PPKn/Pendidikan Pancasila", "Bahasa Arab", "Bahasa Jerman",
    "Bahasa Prancis", "Bahasa Jepang", "Bahasa Korea", "Bahasa Mandarin",
    "Produk/Projek Kreatif dan Kewirausahaan",
}

try:
    ensure_tka_tables()
except Exception as exc:
    print(f"[TKA INIT WARN] {exc}")

def now_wib() -> datetime:
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)

def parse_wib_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        raw = str(value).strip().replace(" ", "T")
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo:
            return dt.astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)
        return dt
    except Exception:
        return None

def normalized_anti_cheat(sess: dict) -> dict:
    current = sess.get("anti_cheat") if isinstance(sess, dict) else None
    if not isinstance(current, dict):
        current = {}
    return {
        "detected": bool(current.get("detected", False)),
        "reason": str(current.get("reason", "") or ""),
        "violation_count": max(0, int(current.get("violation_count", 0) or 0)),
        "max_violations": 3,
    }

def _parse_answer_value(value: Any):
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed
    except Exception:
        return raw

def _answer_is_correct(item: dict, user_value: Any) -> bool:
    if user_value is None or user_value == "":
        return False
    qtype = str(item.get("question_type") or "PG").upper()
    if qtype == "MCMA":
        expected = item.get("correct_answers") or item.get("correct_answer") or []
        if not isinstance(expected, list):
            expected = [expected]
        actual = user_value if isinstance(user_value, list) else _parse_answer_value(user_value)
        if not isinstance(actual, list):
            actual = [actual]
        return {str(x).strip().upper() for x in actual} == {str(x).strip().upper() for x in expected}
    if qtype == "KATEGORI":
        expected = item.get("correct_answers") or item.get("correct_answer") or []
        actual = user_value if isinstance(user_value, list) else _parse_answer_value(user_value)
        if not isinstance(expected, list) or not isinstance(actual, list) or len(expected) != len(actual):
            return False
        return all(str(a).strip() == str(e).strip() for a, e in zip(actual, expected))
    expected = str(item.get("correct_answer") or "").strip().upper()
    actual = user_value if not isinstance(user_value, list) else (user_value[0] if user_value else "")
    return str(actual).strip().upper() == expected

def build_detail_answers(sess: dict) -> list[bool | None]:
    questions = sess.get("quiz", []) or []
    answers = sess.get("answers", {}) or {}
    detail = []
    for idx, item in enumerate(questions):
        user = answers.get(idx) if idx in answers else answers.get(str(idx))
        if user is None or user == "":
            detail.append(None)
        else:
            detail.append(_answer_is_correct(item, user))
    return detail

def duration_label(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} jam {m} menit" + (f" {s} detik" if s else "")
    return f"{m} menit" + (f" {s} detik" if s else "") if m else f"{s} detik"

def validate_active_window(config: dict) -> str | None:
    now = now_wib()
    start = parse_wib_datetime(config.get("active_from"))
    end = parse_wib_datetime(config.get("active_until"))
    if start and now < start:
        return f"⏰ TKA belum dibuka. Mulai {start.strftime('%d-%m-%Y %H:%M')} WIB."
    if end and now > end:
        return f"❌ Kode TKA sudah kedaluwarsa pada {end.strftime('%d-%m-%Y %H:%M')} WIB."
    return None

@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    mode = request.query_params.get("mode", "choice")
    if mode not in {"choice", "guru"}:
        mode = "choice"
    return templates.TemplateResponse(request=request, name="student_login.html", context={"error": None, "mode": mode})

@app.get("/mandiri", response_class=HTMLResponse)
async def mandiri_page(request: Request):
    return templates.TemplateResponse(request=request, name="student_login.html", context={"error": None, "mode": "mandiri"})

@app.post("/mandiri/start", response_class=HTMLResponse)
async def mandiri_start(
    request: Request,
    nama: str = Form(...),
    kelas: str = Form(...),
    absen: str = Form(...),
    jenjang: str = Form(...),
    mapel: str = Form(...),
):
    jenjang = normalize_tka_jenjang(jenjang)
    allowed_mapels = TKA_MTS_MAPELS if jenjang == "MTs" else TKA_MA_MAPELS
    mapel = str(mapel or "").strip()
    if mapel not in allowed_mapels:
        return templates.TemplateResponse(request=request, name="student_login.html", context={
            "error": f"❌ Mata uji {mapel or '-'} tidak tersedia untuk jenjang {jenjang}.",
            "mode": "mandiri",
        })
    target_kelas = "9" if jenjang == "MTs" else "12"
    kelas = target_kelas
    
    # Mode mandiri tetap default menggunakan 30 soal simulasi
    questions = generate_tka_30(jenjang=jenjang, mapel=mapel, auto_select_images=True)
    if len(questions) != TKA_TOTAL_QUESTIONS:
        return templates.TemplateResponse(request=request, name="student_login.html", context={
            "error": "⚠️ RoboMANTAP belum berhasil menyiapkan paket simulasi TKA. Pastikan Library Gambar TKA sudah memiliki stimulus dan coba lagi.",
            "mode": "mandiri",
        })
    session_id = str(uuid.uuid4())[:8]
    config = {
        "jenis": "TKA",
        "mode": "MANDIRI",
        "jenjang": jenjang,
        "kelas": kelas.strip(),
        "mapel": mapel.strip(),
        "timer_seconds": TKA_DEFAULT_DURATION_SECONDS,
        "total_soal": TKA_TOTAL_QUESTIONS,
    }
    STUDENT_SESSIONS[session_id] = {
        "nama": nama.strip(), "kelas": kelas.strip(), "absen": absen.strip(),
        "config": config, "quiz": questions, "answers": {}, "current_index": 0,
        "start_time": datetime.now(timezone.utc),
        "anti_cheat": {"detected": False, "reason": "", "violation_count": 0, "max_violations": 3},
        "finished": False,
    }
    update_tka_progress(
        session_id=session_id, nama=nama.strip(), jenjang=jenjang, mapel=mapel.strip(),
        soal_sekarang=1, detail_jawaban=[None] * TKA_TOTAL_QUESTIONS,
        questions=questions, status="BERJALAN",
    )
    return await render_exam(request, session_id)

@app.post("/verify-token", response_class=HTMLResponse)
async def verify_token(
    request: Request,
    nama: str = Form(...),
    kelas: str = Form(...),
    absen: str = Form(...),
    token: str = Form(...),
):
    code = token.strip().upper()
    package = get_tka_from_db(code)
    if not package:
        return templates.TemplateResponse(request=request, name="student_login.html", context={
            "error": "❌ Kode TKA tidak ditemukan atau belum diterbitkan.", "mode": "guru"
        })
    config = package.get("config") or {}
    error = validate_active_window(config)
    if error:
        return templates.TemplateResponse(request=request, name="student_login.html", context={"error": error, "mode": "guru"})
    
    questions = package.get("tka") or []
    total_soal_dinamis = config.get("total_soal", len(questions))
    
    if len(questions) == 0:
        return templates.TemplateResponse(request=request, name="student_login.html", context={
            "error": "❌ Paket TKA ini kosong atau tidak valid.", "mode": "guru"
        })
        
    session_id = str(uuid.uuid4())[:8]
    anti = {"detected": False, "reason": "", "violation_count": 0, "max_violations": 3}
    STUDENT_SESSIONS[session_id] = {
        "nama": nama.strip(), "kelas": kelas.strip(), "absen": absen.strip(), "token": code,
        "config": config, "quiz": questions, "answers": {}, "current_index": 0,
        "start_time": datetime.now(timezone.utc), "anti_cheat": anti, "finished": False,
    }
    
    update_tka_progress(
        session_id=session_id, nama=nama.strip(), jenjang=config.get("jenjang", "MTs"),
        mapel=config.get("mapel", "Matematika"), soal_sekarang=1,
        detail_jawaban=[None] * total_soal_dinamis, questions=questions, anti_cheat=anti,
    )
    return await render_exam(request, session_id)

async def render_exam(request: Request, session_id: str):
    sess = STUDENT_SESSIONS.get(session_id)
    if not sess:
        return RedirectResponse(url="/", status_code=303)
    if sess.get("finished") or normalized_anti_cheat(sess)["detected"]:
        return RedirectResponse(url=f"{STREAMLIT_URL.rstrip('/')}/?review_session={session_id}", status_code=303)
        
    config = sess.get("config", {})
    questions = sess.get("quiz", [])
    total_soal = config.get("total_soal", len(questions))
    duration = int(config.get("timer_seconds") or TKA_DEFAULT_DURATION_SECONDS)
    
    start = sess.get("start_time")
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    remaining = max(0, int(duration - (datetime.now(timezone.utc) - start).total_seconds()))
    
    return templates.TemplateResponse(request=request, name="student_exam.html", context={
        "session_id": session_id, "sess": sess, "mapel": config.get("mapel", "TKA"),
        "materi": "Latihan TKA", "nama": sess.get("nama", "Siswa"), "kelas": sess.get("kelas", "-"),
        "absen": sess.get("absen", "-"), "jumlah_soal": total_soal,
        "duration_seconds": duration, "durasi_label": duration_label(duration),
        "quiz_json": json.dumps(questions, ensure_ascii=False),
        "answers_json": json.dumps(sess.get("answers", {}), ensure_ascii=False),
        "remaining_seconds": remaining, "anti_cheat_json": json.dumps(normalized_anti_cheat(sess)),
        "mode_label": "Latihan Mandiri" if config.get("mode") == "MANDIRI" else "By GuruMANTAP",
    })

@app.get("/exam/{session_id}", response_class=HTMLResponse)
async def exam_get(request: Request, session_id: str):
    return await render_exam(request, session_id)

@app.get("/api/image/{image_id}")
async def image_api(image_id: str):
    record = get_tka_image(image_id)
    if not record:
        return Response(status_code=404)
    return Response(content=record["image_data"], media_type=record["mime_type"], headers={"Cache-Control": "public, max-age=86400"})

@app.post("/api/save-answer")
async def save_answer(session_id: str = Form(...), q_index: int = Form(...), answer: str = Form(...)):
    sess = STUDENT_SESSIONS.get(session_id)
    if not sess or sess.get("finished"):
        return Response(status_code=409)
    config = sess.get("config", {})
    duration = int(config.get("timer_seconds") or TKA_DEFAULT_DURATION_SECONDS)
    start = sess.get("start_time")
    if start and (datetime.now(timezone.utc) - start).total_seconds() >= duration:
        return Response(content="TIMEOUT", status_code=409)
    quiz = sess.get("quiz", [])
    if q_index < 0 or q_index >= len(quiz):
        return Response(status_code=400)
    clean = _parse_answer_value(answer)
    if clean is None:
        return Response(status_code=400)
    item = quiz[q_index] or {}
    qtype = str(item.get("question_type") or "PG").upper()
    if qtype == "MCMA":
        if not isinstance(clean, list) or any(str(x).strip().upper() not in {str(o).split(".", 1)[0].strip().upper() for o in item.get("options", [])} for x in clean):
            return Response(status_code=400)
        clean = list(dict.fromkeys(str(x).strip().upper() for x in clean))
    elif qtype == "KATEGORI":
        categories = item.get("category_items") or []
        if not isinstance(clean, list) or len(clean) != len(categories):
            return Response(status_code=400)
        for value, category in zip(clean, categories):
            if str(value) not in [str(x) for x in (category.get("options") or [])]:
                return Response(status_code=400)
        clean = [str(x) for x in clean]
    else:
        clean = str(clean).strip().upper()
        allowed = {str(o).split(".", 1)[0].strip().upper() for o in item.get("options", [])}
        if clean not in allowed:
            return Response(status_code=400)
    sess.setdefault("answers", {})[str(q_index)] = clean
    sess["current_index"] = q_index
    update_tka_progress(
        session_id=session_id, nama=sess.get("nama", "Siswa"), jenjang=config.get("jenjang", "MTs"),
        mapel=config.get("mapel", "Matematika"), soal_sekarang=q_index + 1,
        detail_jawaban=build_detail_answers(sess), status="BERJALAN", questions=quiz,
        user_answers=sess.get("answers", {}), anti_cheat=normalized_anti_cheat(sess),
    )
    return Response(status_code=204)

@app.post("/api/session-heartbeat")
async def heartbeat(session_id: str = Form(...)):
    if session_id not in STUDENT_SESSIONS:
        return Response(status_code=404)
    if not STUDENT_SESSIONS[session_id].get("finished"):
        touch_tka_heartbeat(session_id)
    return Response(status_code=204)

@app.post("/api/anti-cheat")
async def anti_cheat(session_id: str = Form(...), violation_count: int = Form(0), reason: str = Form("Pindah tab")):
    sess = STUDENT_SESSIONS.get(session_id)
    if not sess:
        return Response(status_code=404)
    meta = normalized_anti_cheat(sess)
    meta["violation_count"] = min(3, max(meta["violation_count"], int(violation_count or 0)))
    if meta["violation_count"]:
        meta["reason"] = str(reason or "Pindah tab")[:100]
    meta["detected"] = meta["violation_count"] >= 3
    sess["anti_cheat"] = meta
    forced = meta["detected"]
    update_tka_progress(
        session_id=session_id, nama=sess.get("nama", "Siswa"), jenjang=sess.get("config", {}).get("jenjang", "MTs"),
        mapel=sess.get("config", {}).get("mapel", "Matematika"), soal_sekarang=max(1, int(sess.get("current_index", 0)) + 1),
        detail_jawaban=build_detail_answers(sess), status="SELESAI" if forced else "BERJALAN",
        questions=sess.get("quiz", []), user_answers=sess.get("answers", {}) if forced else None,
        anti_cheat=meta,
    )
    if forced:
        sess["finished"] = True
        return Response(content="STOP")
    return Response(content="WARN")

@app.post("/submit-exam", response_class=HTMLResponse)
async def submit_exam(
    request: Request,
    session_id: str = Form(...),
    anti_cheat_detected: str = Form("0"),
    anti_cheat_reason: str = Form(""),
    anti_cheat_count: int = Form(0),
):
    sess = STUDENT_SESSIONS.get(session_id)
    if not sess:
        return RedirectResponse(url="/", status_code=303)
    quiz = sess.get("quiz", []) or []
    answers = sess.get("answers", {}) or {}
    total_soal = sess.get("config", {}).get("total_soal", len(quiz))
    
    benar = salah = kosong = 0
    detail = []
    for idx, item in enumerate(quiz):
        user = answers.get(idx) if idx in answers else answers.get(str(idx))
        if user is None or user == "" or user == []:
            kosong += 1
            detail.append(None)
        elif _answer_is_correct(item, user):
            benar += 1
            detail.append(True)
        else:
            salah += 1
            detail.append(False)
            
    meta = normalized_anti_cheat(sess)
    if str(anti_cheat_detected).lower() in {"1", "true", "yes", "on"} or int(anti_cheat_count or 0) > 0:
        meta["violation_count"] = min(3, max(meta["violation_count"], int(anti_cheat_count or 0)))
        meta["reason"] = str(anti_cheat_reason or meta["reason"] or "Pindah tab")[:100]
        meta["detected"] = meta["violation_count"] >= 3 or str(anti_cheat_detected).lower() in {"1", "true", "yes", "on"}
    sess["anti_cheat"] = meta
    
    update_tka_progress(
        session_id=session_id, nama=sess.get("nama", "Siswa"), jenjang=sess.get("config", {}).get("jenjang", "MTs"),
        mapel=sess.get("config", {}).get("mapel", "Matematika"), soal_sekarang=total_soal,
        detail_jawaban=detail, status="SELESAI", questions=quiz, user_answers=answers, anti_cheat=meta,
    )
    sess["finished"] = True
    
    # Kalkulasi nilai dinamis menyesuaikan total soal aktual
    score = int(round(benar / total_soal * 100)) if total_soal > 0 else 0
    review_url = f"{STREAMLIT_URL.rstrip('/')}/?review_session={session_id}"
    
    return templates.TemplateResponse(request=request, name="student_result.html", context={
        "nama": (sess.get("nama") or "Siswa").split()[0], "skor": score, "benar": benar,
        "salah": salah, "kosong": kosong, "total": total_soal,
        "streamlit_url": review_url, "mode_label": "Latihan Mandiri" if sess.get("config", {}).get("mode") == "MANDIRI" else "By GuruMANTAP",
    })

@app.post("/api/hint", response_class=HTMLResponse)
async def hint(curr_idx: int = Form(...), mapel: str = Form(""), question: str = Form(""), attempt_input: str = Form("")):
    attempt = attempt_input.strip()
    if not attempt:
        return '<div class="p-2.5 bg-blue-950/40 border border-blue-500/30 text-blue-300 rounded-lg text-xs mt-2">💡 Tulis dulu ide atau langkahmu supaya RoboMANTAP bisa memberi petunjuk.</div>'
    key = (mapel, curr_idx, question, attempt)
    if key not in ai_hint_cache:
        try:
            ai_hint_cache[key] = "".join(get_ai_hint_stream(question, attempt, mapel))
        except Exception:
            ai_hint_cache[key] = "⚠️ RoboMANTAP sedang sibuk. Silakan coba lagi."
    return f'<div class="p-3 bg-slate-900 border border-slate-800 rounded-lg text-slate-200 text-xs leading-relaxed mt-2"><div class="font-bold text-emerald-400 mb-1">🧕🏼 RoboMANTAP:</div><div>{ai_hint_cache[key]}</div></div>'
