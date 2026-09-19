import io
import os
import json
import random
import uuid
from datetime import datetime, timezone, timedelta
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
ai_hint_cache = {}
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

def parse_wib_datetime(dt_str):
    """Helper untuk membaca format ISO dari Supabase dan mengonversinya ke datetime WIB."""
    if not dt_str:
        return None
    try:
        s = str(dt_str).strip().replace(" ", "T")
        dt_raw = datetime.fromisoformat(s.replace('Z', '+00:00'))
        if dt_raw.tzinfo is not None:
            return dt_raw.astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)
        return dt_raw
    except Exception as e:
        print(f"[DATE PARSE ERROR] Gagal parse tanggal '{dt_str}': {e}")
        return None

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
    
    # 1. Cek Keberadaan Token di Database Supabase
    if not quiz_package:
        return templates.TemplateResponse(
            request=request,
            name="student_login.html", 
            context={"error": "❌ Kode Kuis tidak ditemukan atau belum diterbitkan!"}
        )

    config = quiz_package.get("config", {})
    
    # 2. Waktu Saat Ini di WIB (UTC+7)
    now_wib = datetime.utcnow() + timedelta(hours=7)
    
    active_from_raw = config.get("active_from")
    active_until_raw = config.get("active_until")

    # 3. Validasi Masa Aktif Kuis (Strict WIB Comparison)
    if active_from_raw and active_until_raw:
        dt_from = parse_wib_datetime(active_from_raw)
        dt_until = parse_wib_datetime(active_until_raw)

        if dt_from and now_wib < dt_from:
            time_start = config.get("time_start_str", dt_from.strftime("%H:%M"))
            return templates.TemplateResponse(
                request=request,
                name="student_login.html",
                context={"error": f"⏰ Kuis Belum Dibuka! Kuis baru dapat diakses pada pukul {time_start} WIB."}
            )

        if dt_until and now_wib > dt_until:
            time_end = config.get("time_end_str", dt_until.strftime("%H:%M"))
            return templates.TemplateResponse(
                request=request,
                name="student_login.html",
                context={"error": f"❌ Kode Kuis Sudah Kedaluwarsa! Masa aktif kuis ini telah berakhir pada pukul {time_end} WIB."}
            )

    # 4. Ambil Soal dan Buat Sesi Ujian Siswa
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
        "current_index": 0,
        "start_time": datetime.utcnow()
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

    # 1. Catat Waktu Mulai Pertama Kali (Mencegah Reset Timer saat Relog)
    if "start_time" not in sess:
        sess["start_time"] = datetime.utcnow()

    # 2. Hitung Sisa Waktu Ujian Real-Time dari Server (dalam detik)
    duration_m = sess["config"].get("timer_m", 30)
    elapsed_s = (datetime.utcnow() - sess["start_time"]).total_seconds()
    remaining_s = max(0, int((duration_m * 60) - elapsed_s))

    return templates.TemplateResponse(
        request=request,
        name="student_exam.html", 
        context={
            "session_id": session_id,
            "sess": sess,
            "quiz_json": json.dumps(sess["quiz"]),
            "answers_json": json.dumps(sess.get("answers", {})), # <-- Kirim jawaban tersimpan
            "remaining_seconds": remaining_s                      # <-- Kirim sisa waktu presisi
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

@app.post("/api/hint", response_class=HTMLResponse)
async def handle_hint_request(
    curr_idx: int = Form(...),
    mapel: str = Form(""),
    question: str = Form(""),
    attempt_input: str = Form("")
):
    attempt_str = attempt_input.strip()

    # Validasi input kosong
    if not attempt_str:
        return """
        <div class="p-2.5 bg-blue-950/40 border border-blue-500/30 text-blue-300 rounded-lg text-xs mt-2">
            💡 Tolong ketik sedikit ide kamu dulu ya, biar RoboMANTAP bisa kasih petunjuk yang pas!
        </div>
        """

    # Cek cache lokal
    hint_key = (mapel, curr_idx, question, attempt_str)
    
    if hint_key in ai_hint_cache:
        hint_text = ai_hint_cache[hint_key]
    else:
        # Panggil AI Stream dari ai_engine.py
        hint_chunks = [chunk for chunk in get_ai_hint_stream(question, attempt_str, mapel)]
        hint_text = "".join(hint_chunks)
        
        # Simpan ke cache jika tidak error
        if hint_text and "⚠️" not in hint_text:
            ai_hint_cache[hint_key] = hint_text

    return f"""
    <div class="p-3 bg-slate-900 border border-slate-800 rounded-lg text-slate-200 text-xs leading-relaxed mt-2 animate-fade-in">
        <div class="font-bold text-emerald-400 mb-1">🧕🏼 RoboMANTAP:</div>
        <div>{hint_text}</div>
    </div>
    """
