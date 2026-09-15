import io
import os
import json
import random
import uuid
from typing import Dict, Any

from fastapi import FastAPI, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ai_engine import (
    create_table_if_not_exists,
    get_custom_quiz_from_db,
    update_progress_siswa,
    get_ai_hint_stream
)

app = FastAPI(title="RoboMANTAP CBT Engine")

# Path absolut agar folder templates selalu terdeteksi di Linux Render
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Inisialisasi Tabel DB
try:
    create_table_if_not_exists()
except Exception as e:
    print(f"[DB INIT WARN] {e}")

# In-Memory Session Storage
STUDENT_SESSIONS: Dict[str, Dict[str, Any]] = {}

STREAMLIT_URL = "https://robomantap-intelligence.streamlit.app/" # Sesuaikan dengan URL Streamlit app.py kamu

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="student_login.html", 
        context={"error": None}
    )

@app.post("/verify-token", response_class=HTMLResponse)
async def verify_token(
    request: Request,
    nama: str = Form(...),
    kelas: str = Form(...),
    absen: str = Form(...),
    token: str = Form(...)
):
    clean_token = token.strip().upper()
    quiz_package = get_custom_quiz_from_db(clean_token)
    
    if not quiz_package:
        return templates.TemplateResponse(
            request=request,
            name="student_login.html", 
            context={"error": "Kode Kuis / Token tidak ditemukan atau belum diterbitkan!"}
        )

    config = quiz_package.get("config", {})
    master_quiz = quiz_package.get("quiz", [])
    packages = config.get("packages", [master_quiz])
    
    selected_quiz = random.choice(packages) if packages else master_quiz
    
    session_id = str(uuid.uuid4())[:8]
    STUDENT_SESSIONS[session_id] = {
        "nama": nama.strip(),
        "kelas": kelas.strip(),
        "absen": absen.strip(),
        "token": clean_token,
        "config": config,
        "quiz": selected_quiz,
        "answers": {},
        "current_index": 0
    }
    
    return templates.TemplateResponse(
        request=request,
        name="student_lobby.html", 
        context={
            "session_id": session_id,
            "nama": nama,
            "kelas": kelas,
            "absen": absen,
            "mapel": config.get("mapel", "Kuis"),
            "materi": config.get("materi", "-"),
            "jumlah_soal": len(selected_quiz),
            "durasi_menit": config.get("timer_m", 30)
        }
    )

@app.post("/start-exam", response_class=HTMLResponse)
async def start_exam(request: Request, session_id: str = Form(...)):
    sess = STUDENT_SESSIONS.get(session_id)
    if not sess:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="student_exam.html", 
        context={
            "session_id": session_id,
            "sess": sess,
            "quiz_json": json.dumps(sess["quiz"])
        }
    )

@app.post("/api/save-answer")
async def save_answer(
    session_id: str = Form(...),
    q_index: int = Form(...),
    answer: str = Form(...)
):
    sess = STUDENT_SESSIONS.get(session_id)
    if sess:
        sess["answers"][q_index] = answer
        
        detail_ans = []
        for idx, item in enumerate(sess["quiz"]):
            user_ans = sess["answers"].get(idx)
            if user_ans:
                detail_ans.append(user_ans == item.get("correct_answer"))
            else:
                detail_ans.append(None)
                
        update_progress_siswa(
            session_id=session_id,
            nama=sess["nama"],
            jenjang=sess["config"].get("jenjang", "Kuis"),
            mapel=sess["config"].get("mapel", "Kuis"),
            soal_sekarang=q_index + 1,
            detail_jawaban=detail_ans,
            status="BERJALAN",
            is_custom=True
        )
    return HTMLResponse(status_code=200)

@app.post("/submit-exam", response_class=HTMLResponse)
async def submit_exam(request: Request, session_id: str = Form(...)):
    sess = STUDENT_SESSIONS.get(session_id)
    if not sess:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    quiz = sess["quiz"]
    answers = sess["answers"]
    
    # Ekstraksi Nama Depan/Panggilan Siswa
    nama_lengkap = sess.get("nama", "").strip()
    nama_depan = nama_lengkap.split()[0] if nama_lengkap else "Santri MANTAP"

    benar = 0
    salah = 0
    kosong = 0
    detail_ans = []

    for idx, item in enumerate(quiz):
        user_ans = answers.get(idx)
        if not user_ans:
            kosong += 1
            detail_ans.append(False)
        elif user_ans == item.get("correct_answer"):
            benar += 1
            detail_ans.append(True)
        else:
            salah += 1
            detail_ans.append(False)

    total_soal = len(quiz)
    skor = int(round((benar / total_soal) * 100)) if total_soal > 0 else 0

    # Simpan pengerjaan ke Supabase
    update_progress_siswa(
        session_id=session_id,
        nama=nama_lengkap, # Di DB tetap tersimpan nama lengkap
        jenjang=sess["config"].get("jenjang", "MA"),
        mapel=sess["config"].get("mapel", "Matematika"),
        soal_sekarang=total_soal,
        detail_jawaban=detail_ans,
        status="SELESAI",
        is_custom=True,
        user_answers_dict=answers,
        quiz_data_list=quiz
    )

    base_url = STREAMLIT_URL.rstrip('/')
    target_streamlit_url = f"{base_url}/?review_session={session_id}"

    return templates.TemplateResponse(
        request=request,
        name="student_result.html", 
        context={
            "nama": nama_depan,  # <-- Dikirim nama depan saja untuk sapaan akrab
            "skor": skor,
            "benar": benar,
            "salah": salah,
            "kosong": kosong,
            "total": total_soal,
            "streamlit_url": target_streamlit_url
        }
    )
