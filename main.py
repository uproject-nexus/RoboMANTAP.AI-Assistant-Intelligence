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
    
    return RedirectResponse(
        url=f"/exam/{session_id}", 
        status_code=status.HTTP_303_SEE_OTHER
    )

# ==============================================================================
# ROUTE WORKSPACE EXAM (MENGGABUNGKAN GET & POST KE SINGLE-FILE STUDENT_EXAM.HTML)
# ==============================================================================
# ==============================================================================
# HELPER FUNCTION & ROUTE WORKSPACE EXAM (PENGGANTI /start-exam LAMA)
# ==============================================================================

async def render_exam_workspace(request: Request, session_id: str):
    sess = STUDENT_SESSIONS.get(session_id)
    if not sess:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    # 1. Catat Waktu Mulai Pertama Kali (Mencegah Reset Timer saat Refresh)
    if "start_time" not in sess:
        sess["start_time"] = datetime.now(timezone.utc)

    # 2. Hitung Sisa Waktu Ujian Real-Time dari Server
    duration_m = sess.get("config", {}).get("timer_m", 30)
    now_utc = datetime.now(timezone.utc)
    start_time = sess["start_time"]
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
        
    elapsed_s = (now_utc - start_time).total_seconds()
    remaining_s = max(0, int((duration_m * 60) - elapsed_s))

    # 3. Render Single-File student_exam.html
    return templates.TemplateResponse(
        request=request,
        name="student_exam.html", 
        context={
            "session_id": session_id,
            "sess": sess,
            "mapel": sess.get("config", {}).get("mapel", "Kuis RoboMANTAP"),
            "materi": sess.get("config", {}).get("materi", "Umum"),
            "nama": sess.get("nama", "Siswa"),
            "kelas": sess.get("kelas", "-"),
            "absen": sess.get("absen", "-"),
            "quiz_json": json.dumps(sess.get("quiz", [])),
            "answers_json": json.dumps(sess.get("answers", {})),
            "remaining_seconds": remaining_s
        }
    )

# Route 1: Menerima submit form POST dari Login
@app.post("/start-exam", response_class=HTMLResponse)
async def start_exam_post(request: Request, session_id: str = Form(...)):
    return await render_exam_workspace(request, session_id)

# Route 2: Menerima akses langsung via URL GET / refresh browser
@app.get("/exam/{session_id}", response_class=HTMLResponse)
async def start_exam_get(request: Request, session_id: str):
    return await render_exam_workspace(request, session_id)

# ==============================================================================
# 1. API SAVE ANSWER (MENYIMPAN JAWABAN REAL-TIME)
# ==============================================================================
@app.post("/api/save-answer")
async def save_answer(
    session_id: str = Form(...),
    q_index: int = Form(...),
    answer: str = Form(...)
):
    sess = STUDENT_SESSIONS.get(session_id)
    if sess:
        # Inisialisasi dictionary answers jika belum ada
        if "answers" not in sess:
            sess["answers"] = {}

        # Simpan dalam format integer dan string agar konsisten
        sess["answers"][q_index] = answer
        sess["answers"][str(q_index)] = answer

        detail_ans = []
        quiz = sess.get("quiz", [])

        for idx, item in enumerate(quiz):
            # Toleransi cek kunci tipe integer maupun string
            user_ans = sess["answers"].get(idx) or sess["answers"].get(str(idx))
            if user_ans is not None:
                correct_ans = item.get("correct_answer") or item.get("key")
                detail_ans.append(user_ans == correct_ans)
            else:
                detail_ans.append(None)

        # Update progress ke Supabase (dengan penangkap error agar tidak crash)
        try:
            update_progress_siswa(
                session_id=session_id,
                nama=sess.get("nama", "Siswa"),
                jenjang=sess.get("config", {}).get("jenjang", "Kuis"),
                mapel=sess.get("config", {}).get("mapel", "Kuis"),
                soal_sekarang=q_index + 1,
                detail_jawaban=detail_ans,
                status="BERJALAN",
                is_custom=True
            )
        except Exception as e:
            print(f"⚠️ Warning Sync Supabase (Save Answer): {e}")

    return HTMLResponse(content="", status_code=200)

# ==============================================================================
# 2. API SUBMIT EXAM (KALKULASI NILAI & Halaman student_result.html)
# ==============================================================================
@app.post("/submit-exam", response_class=HTMLResponse)
async def submit_exam(request: Request, session_id: str = Form(...)):
    sess = STUDENT_SESSIONS.get(session_id)
    if not sess:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    quiz = sess.get("quiz", [])
    answers = sess.get("answers", {})

    # Ekstraksi Nama Depan/Panggilan Siswa
    nama_lengkap = sess.get("nama", "").strip()
    nama_depan = nama_lengkap.split()[0] if nama_lengkap else "Santri MANTAP"

    benar = 0
    salah = 0
    kosong = 0
    detail_ans = []

    for idx, item in enumerate(quiz):
        # FIX: Toleransi pencarian kunci integer dan string
        user_ans = answers.get(idx) or answers.get(str(idx))
        correct_ans = item.get("correct_answer") or item.get("key")

        if not user_ans:
            kosong += 1
            detail_ans.append(False)
        elif user_ans == correct_ans:
            benar += 1
            detail_ans.append(True)
        else:
            salah += 1
            detail_ans.append(False)

    total_soal = len(quiz)
    skor = int(round((benar / total_soal) * 100)) if total_soal > 0 else 0

    # Simpan pengerjaan ke Supabase
    try:
        update_progress_siswa(
            session_id=session_id,
            nama=nama_lengkap,  # Di DB tetap tersimpan nama lengkap
            jenjang=sess.get("config", {}).get("jenjang", "MA"),
            mapel=sess.get("config", {}).get("mapel", "Matematika"),
            soal_sekarang=total_soal,
            detail_jawaban=detail_ans,
            status="SELESAI",
            is_custom=True,
            user_answers_dict=answers,
            quiz_data_list=quiz
        )
    except Exception as e:
        print(f"⚠️ Warning Sync Supabase (Submit Exam): {e}")

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


# ==============================================================================
# 3. API HINT AI (ROBOMANTAP CONSULTATION)
# ==============================================================================
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
        try:
            # Panggil AI Stream dari ai_engine.py
            hint_chunks = [chunk for chunk in get_ai_hint_stream(question, attempt_str, mapel)]
            hint_text = "".join(hint_chunks)

            # Simpan ke cache jika tidak error
            if hint_text and "⚠️" not in hint_text:
                ai_hint_cache[hint_key] = hint_text
        except Exception as e:
            hint_text = f"⚠️ Maaf, RoboMANTAP sedang sibuk sebentar. Coba tekan tombol diskusi lagi ya! ({e})"

    return f"""
    <div class="p-3 bg-slate-900 border border-slate-800 rounded-lg text-slate-200 text-xs leading-relaxed mt-2 animate-fade-in">
        <div class="font-bold text-emerald-400 mb-1">🧕🏼 RoboMANTAP:</div>
        <div>{hint_text}</div>
    </div>
    """
