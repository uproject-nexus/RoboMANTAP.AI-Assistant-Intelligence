import os
import json
import re
import time
import pandas as pd
import streamlit as st
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Setup Matplotlib Headless untuk Server Cloud (Render/Streamlit)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Import Python-Docx & XML Parser untuk Word
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

from datetime import datetime, timezone, timedelta


try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
except ImportError:
    pass

load_dotenv()

# ==============================================================================
# PEMBACAAN API KEY AMAN (DUAL COMPATIBILITY: STREAMLIT & FASTAPI/RENDER)
# ==============================================================================
api_keys = []
raw_keys = os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY")

# Fallback ke st.secrets jika dipanggil di dalam lingkungan Streamlit
if not raw_keys:
    try:
        if hasattr(st, "secrets"):
            if "GEMINI_API_KEYS" in st.secrets:
                raw_keys = st.secrets["GEMINI_API_KEYS"]
            elif "GEMINI_API_KEY" in st.secrets:
                raw_keys = st.secrets["GEMINI_API_KEY"]
    except Exception:
        raw_keys = None

if raw_keys:
    if isinstance(raw_keys, list):
        api_keys = raw_keys
    else:
        raw_keys_str = str(raw_keys).strip()
        if raw_keys_str.startswith("["):
            try:
                api_keys = json.loads(raw_keys_str)
            except Exception:
                api_keys = [k.strip(' "\'') for k in raw_keys_str.strip("[]").split(",") if k.strip()]
        elif "," in raw_keys_str:
            api_keys = [k.strip(' "\'') for k in raw_keys_str.split(",") if k.strip()]
        else:
            api_keys = [raw_keys_str.strip(' "\'')]

# Helper untuk menampilkan error yang aman di kedua lingkungan (Streamlit & Render)
def show_error(msg: str):
    print(f"[AI ENGINE ERROR] {msg}")
    try:
        st.error(msg)
    except Exception:
        pass

# Model untuk pembuatan soal
QUIZ_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")

# Model khusus interaksi LIVE: prioritaskan latency rendah.
STREAM_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")

STREAM_HINT_MAX_TOKENS = 9000
STREAM_SOLUTION_MAX_TOKENS = 9000
STREAM_TIMEOUT_MS = 90_000

_clients_cache = None

def get_gemini_clients():
    """
    Reuse koneksi Gemini antar request.
    Menggunakan caching global yang kompatibel untuk Streamlit maupun Uvicorn FastAPI.
    """
    global _clients_cache
    if _clients_cache is not None:
        return _clients_cache

    clients = []
    for key in api_keys:
        try:
            clients.append(
                genai.Client(
                    api_key=key,
                    http_options=types.HttpOptions(
                        timeout=STREAM_TIMEOUT_MS,
                        retry_options=types.HttpRetryOptions(attempts=1),
                    ),
                )
            )
        except Exception:
            continue

    _clients_cache = clients
    return clients


def _stream_config(model_name: str, max_output_tokens: int):
    if model_name.startswith("gemini-3."):
        return types.GenerateContentConfig(
            max_output_tokens=max_output_tokens,
            thinking_config=types.ThinkingConfig(
                thinking_level="high"
            ),
        )

    return types.GenerateContentConfig(
        max_output_tokens=max_output_tokens,
        thinking_config=types.ThinkingConfig(
            thinking_budget=0,
            include_thoughts=False,
        ),
    )


def _buffer_stream_text(source, min_chars: int = 2, flush_seconds: float = 0.01):
    buffer = []
    size = 0
    last_flush = time.monotonic()

    for chunk in source:
        if not chunk:
            continue

        buffer.append(chunk)
        size += len(chunk)

        now = time.monotonic()
        if size >= min_chars or (now - last_flush) >= flush_seconds:
            yield "".join(buffer)
            buffer.clear()
            size = 0
            last_flush = now

    if buffer:
        yield "".join(buffer)


def _stream_from_clients(prompt: str, max_output_tokens: int):
    clients = get_gemini_clients()

    if not clients:
        yield "⚠️ Tidak ada koneksi yang aktif nih. Coba Kamu klik lagi.."
        return

    for client in clients:
        for model_name in STREAM_MODELS:
            try:
                response = client.models.generate_content_stream(
                    model=model_name,
                    contents=prompt,
                    config=_stream_config(model_name, max_output_tokens),
                )

                emitted = False

                def raw_stream():
                    for chunk in response:
                        chunk_text = getattr(chunk, "text", None)
                        if chunk_text:
                            yield chunk_text

                for piece in _buffer_stream_text(raw_stream()):
                    emitted = True
                    yield piece

                if emitted:
                    return

            except Exception:
                continue

    yield (
        "⚠️ Maaf ya, koneksi sedang bermasalah atau kuota sedang penuh nih. "
        "Silakan coba klik lagi ya!"
    )

def format_latex_options(options):
    formatted = []
    for opt in options:
        opt = str(opt).replace(r"\frac", r"\tfrac")
        if "\\" in opt and "$" not in opt:
            parts = opt.split(". ", 1)
            opt = f"{parts[0]}. ${parts[1]}$" if len(parts) == 2 else f"${opt}$"
        formatted.append(opt)
    return formatted

def clean_json_text(text: str) -> str:
    if not text:
        return ""
    
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    def replace_slash(match):
        g = match.group(0)
        if g in (r'\\', r'\"'):
            return g 
        return r'\\' 

    return re.sub(r'\\\\|\\"|\\', replace_slash, text)

def call_gemini_with_rotation(prompt: str, is_json: bool = False):
    clients = get_gemini_clients()
    if not clients:
        return None

    for client in clients:
        for model_name in QUIZ_MODELS:
            try:
                config_kwargs = {}

                if is_json:
                    config_kwargs["response_mime_type"] = "application/json"

                if model_name.startswith("gemini-3."):
                    config_kwargs["thinking_config"] = types.ThinkingConfig(
                        thinking_level="high"
                    )
                else:
                    config_kwargs["thinking_config"] = types.ThinkingConfig(
                        thinking_budget=0,
                        include_thoughts=False,
                    )

                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_kwargs),
                )

                if response and response.text:
                    return response.text

            except Exception:
                continue

    return None

def stream_ai_text(prompt: str, max_output_tokens: int = STREAM_HINT_MAX_TOKENS):
    yield from _stream_from_clients(
        prompt,
        max_output_tokens=max_output_tokens,
    )

def generate_quiz_batch(jenjang: str, mapel: str, stage: str, selected_submateri: list):
    submateri_text = ", ".join(selected_submateri) if selected_submateri else "Semua Submateri Terintegrasi"

    stage_descriptions = {
        "Internal": "Internal: Fokus pada diagnostik, pemetaan bidang, dan penguatan konsep dasar.",
        "Kab/Kota": "Kab/Kota: Fokus pada pilihan ganda terstandar CBT, HOTS, dan analisis data.",
        "Provinsi": "Provinsi: Fokus pada analisis lintas konsep, pilihan ganda kompleks, serta keterkaitan sains, teknologi, dan nilai keislaman.",
        "Nasional": "Nasional: Fokus pada tingkat lanjutan (High-Level HOTS), eksplorasi problem solving, analisis eksperimen, dan penalaran ilmiah mendalam."
    }
    stage_description = stage_descriptions.get(stage, "Fokus pada penguatan konsep OMI.")

    system_prompt = f"""
    Anda adalah Pelatih Utama Bina Prestasi OMI 2026 (Olimpiade Sains & Matematika Al Irsyad) untuk tingkat {jenjang}.
    Rancanglah 1 paket latihan CBT berisi TEPAT 10 SOAL PILIHAN GANDA yang orisinal, presisi, dan tematik OMI.

    Spesifikasi Soal OMI 2026:
    - Jenjang: {jenjang}
    - Bidang / Mata Pelajaran: {mapel}
    - Tahap Pembinaan: {stage} ({stage_description})
    - Cakupan Submateri: {submateri_text}

    INTEGRASI TEMATIK & BAHASA ARAB OMI (BIARKAN PANJANG DAN NATURAL):
    1. Konteks Tematik: Wajib mengintegrasikan materi dengan tema Lingkungan, Teknologi, Kehidupan Sehari-hari, atau Nilai-Nilai Keislaman (seperti Zakat, Waktu Shalat, Penanggalan Hijriyah, Arah Kiblat, Waris, atau Sejarah Islam).
    2. Aturan Porsi & Variasi Bahasa (SANGAT PENTING):
    - Jika submateri berisi "Semua Submateri" (ALL) atau secara acak: UTAMAKAN karakteristik khusus OMI!
    - Dari total 10 soal yang dibuat, 7 soal WAJIB menggunakan Full Bahasa Indonesia berkonteks Keislaman, Lingkungan, Teknologi atau Umum.
    - HANYA MAKSIMAL 3 SOAL SAJA yang diperbolehkan menggunakan Variasi Bahasa Arab.
    - WAJIB AKSARA ARAB ASLI: Semua teks Bahasa Arab WAJIB ditulis menggunakan Aksara Arab asli (contoh: "خمسونا"). DILARANG menggunakan transliterasi/Ejaan Arab Latin (SEPERTI: "khamsuna mitran", "miatun", "uqtiridhat", dll).
    - Variasi Bahasa Arab yang diperbolehkan: Teks Soal ditulis dalam Aksara Arab asli tanpa harakat (atau harakat minimal), sedangkan Pilihan Jawaban A, B, C, D dalam Bahasa Indonesia (atau sebaliknya).
    - Jangan pernah membuat Teks Soal ditulis dalam Bahasa Arab dan Pilihan Jawaban ditulis dalam Bahasa Arab juga.
    - Jangan pernah membuat lebih dari 3 soal berbahasa Arab dalam satu paket kuis.

    ATURAN KHUSUS FORMATTING & KECEPATAN (SANGAT PENTING):
    - JANGAN sertakan field `hint` atau `solution` di sini. Fokus saja merancang 10 teks soal cerita dan jawaban agar proses AI kencang.
    - Angka biasa, nominal uang (Contoh: "Rp 60.000.000"), satuan (Contoh: "14 meter", "12 detik", "50 kg"), dan jam (Contoh: "19.00 WIB") WAJIB ditulis sebagai TEKS BIASA TANPA simbol '$' dan TANPA backslash '\'.
    - DILARANG KERAS membuat perintah LaTeX ilegal seperti '\60.000.000' atau '\14'.
    - Gunakan format LaTeX $...$ HANYA untuk rumus matematika asli, pecahan, akar, dan variabel (Contoh: "$\\pi = \\tfrac{{22}}{{7}}$", "$\\sqrt{{3}}$", "$x^2 = 16$").
    - DILARANG KERAS memasukkan kata/kalimat Bahasa Indonesia ke dalam format $...$.

    Format keluaran WAJIB berupa objek JSON murni:
    {{
        "quiz": [
            {{
                "id": 1,
                "question": "Teks soal cerita nomor 1 lengkap dan mendalam",
                "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
                "correct_answer": "Pilihan jawaban tepat (harus persis sama dengan salah satu opsi)"
            }}
        ]
    }}
    """

    raw_response = call_gemini_with_rotation(system_prompt, is_json=True)

    if not raw_response:
        show_error("⚠️ Waduh kuota sedang penuh nih. Silakan coba klik lagi ya...")
        return []

    try:
        cleaned_response = clean_json_text(raw_response)
        data = json.loads(cleaned_response, strict=False)
        quiz_list = data.get("quiz", [])
        for q in quiz_list:
            if "options" in q:
                q["options"] = format_latex_options(q["options"])
            if "correct_answer" in q:
                for opt in q["options"]:
                    if opt.startswith(q["correct_answer"][:2]):
                        q["correct_answer"] = opt
                        break
        return quiz_list
    except Exception as e:
        show_error(f"Gagal memproses format soal: {e}")
        return []

def get_ai_hint_stream(question: str, user_attempt: str, mapel: str = "Umum"):
    prompt = f"""
    Kamu adalah 'RoboMANTAP', teman belajar dan asisten AI yang ramah, santai, ceria, dan sangat suportif dari MTs & MA Al Irsyad Putri Bondowoso (MANTAP).
    Gunakan gaya bahasa memberi sapaan 'aku' dan 'kamu' yang bersahabat namun tetap edukatif.

    Mata Pelajaran: {mapel}
    Soal OMI: {question}
    Ide Pengerjaan Siswa: {user_attempt}

    Instruksi:
    - Jangan berikan salam pembuka yang berlebihan.
    - Berikan petunjuk atau bimbingan logika interaktif yang menyemangati dan memuji usaha siswa.
    - Bantu siswa menemukan celah penyelesaian soal bidang {mapel} ini secara natural, runtut, dan analitis step-by-step tanpa membocorkan jawaban akhir.
    - Gunakan format LaTeX $...$ HANYA jika terdapat notasi matematika/sains.
    """
    return stream_ai_text(prompt, max_output_tokens=STREAM_HINT_MAX_TOKENS)

def get_ai_solution_stream(question: str, correct_answer: str, mapel: str = "Umum"):
    prompt = f"""
    Kamu adalah Pembina OMI 2026. Berikan pembahasan komprehensif, runtut, dan analitis step-by-step untuk soal berikut.

    Bidang: {mapel}
    Soal:
    {question}

    Kunci Jawaban yang Benar: {correct_answer}

    Instruksi Pembahasan:
    - Jangan berikan salam pembuka yang berlebihan.
    - Jelaskan secara natural, tajam, dan edukatif mengapa jawaban tersebut benar.
    - Jika ada unsur Bahasa Arab, terjemahkan dan kupas secara runtut.
    - Jika ada hitungan, tunjukkan proses rumusnya dengan jelas.
    - WAJIB gunakan format LaTeX $...$ untuk semua notasi matematika/simbol fisika-kimia.
    """
    return stream_ai_text(prompt, max_output_tokens=STREAM_SOLUTION_MAX_TOKENS)


# ==============================================================================
# INTEGRASI DATABASE SUPABASE POSTGRESQL (STREAMLIT & RENDER READY)
# ==============================================================================
class DBWrapper:
    """Wrapper kompatibel untuk SQLAlchemy agar memiliki interface .session"""
    def __init__(self, engine):
        self.engine = engine
        self.SessionMaker = sessionmaker(bind=self.engine)

    @property
    def session(self):
        return self.SessionMaker()

    def query(self, sql_query: str, ttl: int = 0):
        with self.engine.connect() as connection:
            return pd.read_sql(text(sql_query), connection)

_db_conn_cache = None

def init_db_connection():
    global _db_conn_cache
    if _db_conn_cache is not None:
        return _db_conn_cache

    # 1. Cek Environment Variables (Render.com / .env)
    db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")

    # 2. Fallback ke Streamlit Secrets
    if not db_url:
        try:
            if hasattr(st, "secrets") and "DATABASE_URL" in st.secrets:
                db_url = st.secrets["DATABASE_URL"]
        except Exception:
            pass

    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        try:
            engine = create_engine(db_url, pool_pre_ping=True)
            _db_conn_cache = DBWrapper(engine)
            return _db_conn_cache
        except Exception as e:
            print(f"Gagal koneksi SQLAlchemy: {e}")

    # 3. Fallback Native Streamlit Connection (Jika dijalankan di Streamlit Cloud)
    try:
        conn = st.connection("postgresql", type="sql")
        _db_conn_cache = conn
        return _db_conn_cache
    except Exception:
        pass

    return None

def create_table_if_not_exists():
    conn = init_db_connection()
    if not conn: 
        return
    
    query = """
    CREATE TABLE IF NOT EXISTS sesi_ujian (
        id_sesi VARCHAR(100) PRIMARY KEY,
        nama_siswa VARCHAR(100) NOT NULL,
        jenjang VARCHAR(50),
        mapel VARCHAR(50),
        soal_sekarang INT DEFAULT 1,
        detail_jawaban JSONB DEFAULT '[]'::jsonb,
        jumlah_benar INT DEFAULT 0,
        jumlah_salah INT DEFAULT 0,
        nilai_akhir INT DEFAULT 0,
        status VARCHAR(20) DEFAULT 'BERJALAN',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS kuis_custom (
        kode_kuis VARCHAR(20) PRIMARY KEY,
        config JSONB NOT NULL,
        quiz_data JSONB NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    try:
        with conn.session as s:
            s.execute(text(query))
            s.commit()
    except Exception as e:
        print(f"Error create_table_if_not_exists: {e}")

def publish_custom_quiz_to_db(kode_kuis: str, config: dict, quiz_data: list) -> bool:
    conn = init_db_connection()
    if not conn: 
        return False

    query = """
    INSERT INTO kuis_custom (kode_kuis, config, quiz_data, created_at)
    VALUES (:kode, :cfg, :quiz, NOW() AT TIME ZONE 'Asia/Jakarta')
    ON CONFLICT (kode_kuis) DO UPDATE SET
        config = EXCLUDED.config,
        quiz_data = EXCLUDED.quiz_data;
    """
    try:
        with conn.session as s:
            s.execute(text(query), {
                "kode": kode_kuis.strip().upper(),
                "cfg": json.dumps(config, default=str),
                "quiz": json.dumps(quiz_data, default=str)
            })
            s.commit()
            return True
    except Exception as e:
        print(f"Error publish_custom_quiz_to_db: {e}")
        return False

def get_custom_quiz_from_db(kode_kuis: str):
    conn = init_db_connection()
    if not conn: 
        return None

    query = "SELECT config, quiz_data FROM kuis_custom WHERE UPPER(kode_kuis) = UPPER(:kode)"
    try:
        with conn.session as s:
            result = s.execute(text(query), {"kode": kode_kuis.strip()}).fetchone()
            if result:
                cfg = result[0] if isinstance(result[0], dict) else json.loads(result[0])
                quiz = result[1] if isinstance(result[1], list) else json.loads(result[1])
                return {"config": cfg, "quiz": quiz}
    except Exception as e:
        print(f"Error get_custom_quiz_from_db: {e}")
    return None

def update_progress_siswa(
    session_id: str,
    nama: str,
    jenjang: str,
    mapel: str,
    soal_sekarang: int,
    detail_jawaban: list,
    status: str = "BERJALAN",
    is_custom: bool = False,
    user_answers_dict: dict = None,
    quiz_data_list: list = None
):
    conn = init_db_connection()
    if not conn:
        return

    mapel_db = f"{mapel} (Quiz)" if (is_custom and "(Quiz)" not in mapel) else mapel

    total_soal = len(detail_jawaban) if len(detail_jawaban) > 0 else 10
    jumlah_benar = sum(1 for x in detail_jawaban if x is True)
    jumlah_salah = sum(1 for x in detail_jawaban if x is False)

    if is_custom:
        nilai_akhir = int(round((jumlah_benar / total_soal) * 100)) if total_soal > 0 else 0
    else:
        nilai_akhir = (jumlah_benar * 4) - (jumlah_salah * 1)

    # Jika membawa data soal & jawaban lengkap (saat submit dari CBT Render),
    # kemas dalam struktur dictionary agar bisa dibaca komplit oleh Streamlit.
    if user_answers_dict is not None or quiz_data_list is not None:
        payload = {
            "detail_boolean": detail_jawaban,
            "user_answers": user_answers_dict or {},
            "quiz_data": quiz_data_list or []
        }
        detail_json = json.dumps(payload, default=str)
    else:
        # Backward compatibility untuk pemanggilan standar
        detail_json = json.dumps(detail_jawaban)

    query = """
    INSERT INTO sesi_ujian (
        id_sesi, nama_siswa, jenjang, mapel, soal_sekarang, detail_jawaban, 
        jumlah_benar, jumlah_salah, nilai_akhir, status, created_at, updated_at
    )
    VALUES (
        :id_sesi, :nama, :jenjang, :mapel, :soal, :detail, 
        :benar, :salah, :nilai, :status, 
        NOW() AT TIME ZONE 'Asia/Jakarta', 
        NOW() AT TIME ZONE 'Asia/Jakarta'
    )
    ON CONFLICT (id_sesi) DO UPDATE SET
        soal_sekarang = EXCLUDED.soal_sekarang,
        detail_jawaban = EXCLUDED.detail_jawaban,
        jumlah_benar = EXCLUDED.jumlah_benar,
        jumlah_salah = EXCLUDED.jumlah_salah,
        nilai_akhir = EXCLUDED.nilai_akhir,
        status = EXCLUDED.status,
        updated_at = NOW() AT TIME ZONE 'Asia/Jakarta';
    """

    try:
        with conn.session as s:
            s.execute(
                text(query),
                {
                    "id_sesi": session_id,
                    "nama": nama,
                    "jenjang": jenjang,
                    "mapel": mapel_db,
                    "soal": soal_sekarang,
                    "detail": detail_json,
                    "benar": jumlah_benar,
                    "salah": jumlah_salah,
                    "nilai": nilai_akhir,
                    "status": status,
                },
            )
            s.commit()
    except Exception as e:
        print(f"Error update_progress_siswa: {e}")

def generate_lkpd_content(mapel: str, kelas: str, topik: str):
    prompt = f"""
    Anda adalah Tim Ahli Kurikulum Lembaga Pendidikan Al-Irsyad Al-Islamiyah Putri Bondowoso.
    Rancanglah isi Lembar Kerja Peserta Didik (LKPD) berbasis HOTS dan Terintegrasi Keislaman.

    Spesifikasi LKPD:
    - Mata Pelajaran: {mapel}
    - Kelas / Jenjang: {kelas}
    - Topik / Materi Utama: {topik}

    ATURAN NOTASI MATEMATIKA, FISIKA, KIMIA & LATEX (SANGAT PENTING):
    1. DILARANG KERAS menggunakan simbol dollar ($) atau backslash (\\) untuk rumus/variabel!
    2. Untuk angka pangkat atau indeks, HANYA gunakan simbol Unicode atau HTML sederhana:
       - Pangkat/Eksponen: Gunakan Unicode (x², x³, t²) atau <sup>2</sup>, <sup>3</sup>.
       - Indeks/Bawah: Gunakan Unicode (H₂O, CO₂) atau <sub>2</sub>.
       - Simbol Matematika: Gunakan simbol langsung seperti '≠', 'π', '√', '±', '≤', '≥', '°C'.
    3. Contoh Penulisan Rumus yang Benar di dalam teks:
       - "ax² + bx + c = 0 dengan a ≠ 0"
       - "h(t) = -5t² + 40t"
       - "Luas kolam adalah x² meter dan panjangnya x + 6 meter"
    4. UNTUK PECAHAN (SANGAT PENTING):
       - WAJIB gunakan simbol Unicode Pecahan Tegak untuk semua pecahan umum.
       - DILARANG KERAS menulis pecahan biasa dengan garis miring seperti '1/4', '3/8', atau '1/2'!
    5. Untuk matriks/array, WAJIB gunakan blok $$...$$
       - Jangan menulis environment matriks tanpa delimiter matematika.
    
    Instruksi Penyusunan Konten:
    1. Tujuan Pembelajaran: Buatkan 3 poin tujuan berbasis indikator HOTS.
    2. Apersepsi & Ringkasan Konsep: Sajikan materi singkat, tajam, dan korelasikan dengan nilai-nilai Keislaman/Tadabbur Sains.
    3. Tugas Eksplorasi Mandiri: Buat 5 soal studi kasus/problem solving HOTS yang melatih logika nalar santri/siswi.
    4. Refleksi Keislaman: Tuliskan 1 kalimat hikmah/perenungan dari mempelajari materi {topik}.

    Format keluaran WAJIB objek JSON murni:
    {{
        "tujuan": ["Poin tujuan 1", "Poin tujuan 2", "Poin tujuan 3"],
        "ringkasan": "Teks ringkasan konsep dan keislaman...",
        "soal_1": "Pertanyaan eksplorasi HOTS nomor 1",
        "soal_2": "Pertanyaan eksplorasi HOTS nomor 2",
        "soal_3": "Pertanyaan eksplorasi HOTS nomor 3",
        "soal_4": "Pertanyaan eksplorasi HOTS nomor 4",
        "soal_5": "Pertanyaan eksplorasi HOTS nomor 5",
        "refleksi": "Kalimat hikmah/refleksi..."
    }}
    """

    raw_response = call_gemini_with_rotation(prompt, is_json=True)
    if not raw_response:
        return None

    try:
        cleaned_response = clean_json_text(raw_response)
        data = json.loads(cleaned_response, strict=False)
        return data
    except Exception:
        return None

def generate_custom_quiz_ai(
    *,
    mapel: str,
    jenjang: str,
    kelas: str,
    materi: str,
    submateri: str,
    jumlah_soal: int,
    kesulitan: str,
    tipe_soal: str,
    bahasa: str,
    konteks: str,
    timer_seconds: int,
):
    prompt = f"""
    Anda adalah Question Architect RoboMANTAP untuk guru.
    Buat tepat {jumlah_soal} soal pilihan ganda berkualitas tinggi untuk pembelajaran.
    
    KONFIGURASI:
    - Mata Pelajaran: {mapel}
    - Jenjang: {jenjang}
    - Kelas: {kelas}
    - Materi: {materi}
    - Submateri: {submateri or 'Tidak ditentukan / semua yang relevan'}
    - Tingkat Kesulitan: {kesulitan}
    - Tipe Soal: {tipe_soal}
    - Bahasa: {bahasa}
    - Konteks: {konteks}
    - Batas Waktu Sesi: {timer_seconds} detik
    
    ATURAN KUALITAS:
    1. Tepat {jumlah_soal} soal, jangan kurang dan jangan lebih.
    2. Setiap soal memiliki tepat 4 opsi: A, B, C, D.
    3. Hanya satu opsi yang benar.
    4. correct_answer harus persis sama dengan salah satu opsi lengkap.
    5. Hindari ambiguitas, data yang kurang, dan asumsi yang tidak disebutkan.
    6. Untuk soal numerik, solution_basis harus memuat proses hitungan inti dan hasil akhir.
    7. Untuk HOTS/olimpiade, gunakan penalaran yang benar-benar relevan dengan level.
    8. Jangan memasukkan jawaban atau pembahasan yang saling bertentangan.
    9. Jika menggunakan LaTeX, gunakan $...$ dan escape backslash secara valid untuk JSON.
    10. JANGAN menambahkan markdown atau teks pembuka di luar JSON.
    11. Untuk matriks/array, WAJIB gunakan blok $$...$$
    12. Jangan menulis environment matriks tanpa delimiter matematika.
    
    OUTPUT JSON MURNI:
    {{
      "quiz": [
        {{
          "id": 1,
          "question": "...",
          "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
          "correct_answer": "C. ...",
          "solution_basis": "..."
        }}
      ],
      "config": {{
        "duration_seconds": {timer_seconds}
      }}
    }}
    """

    raw_response = call_gemini_with_rotation(prompt, is_json=True)
    if not raw_response:
        return []

    try:
        cleaned = clean_json_text(raw_response)
        data = json.loads(cleaned, strict=False)
    except Exception:
        match = re.search(r"\{.*\}", raw_response, flags=re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0), strict=False)
        except Exception:
            return []

    quiz = data.get("quiz", [])
    if not isinstance(quiz, list) or len(quiz) != jumlah_soal:
        return []

    normalized = []
    expected_prefixes = ("A.", "B.", "C.", "D.")

    for idx, item in enumerate(quiz, start=1):
        if not isinstance(item, dict):
            return []

        question = str(item.get("question", "")).strip()
        options = item.get("options", [])
        answer = str(item.get("correct_answer", "")).strip()
        solution_basis = str(item.get("solution_basis", "")).strip()

        if not question or not isinstance(options, list) or len(options) != 4:
            return []
        if not solution_basis:
            return []

        options = format_latex_options([str(x).strip() for x in options])
        if any(not x for x in options):
            return []
        if not all(any(x.startswith(prefix) for prefix in expected_prefixes) for x in options):
            return []
        if answer not in options:
            matching = [x for x in options if x[:1].upper() == answer[:1].upper()]
            if len(matching) == 1:
                answer = matching[0]
            else:
                return []

        normalized.append({
            "id": idx,
            "question": question,
            "options": options,
            "correct_answer": answer,
            "solution_basis": solution_basis,
        })

    return normalized

def check_active_session_from_db(nama_siswa: str, mapel: str):
    conn = init_db_connection()
    if not conn: 
        return None

    query = """
    SELECT id_sesi, detail_jawaban, created_at, soal_sekarang
    FROM sesi_ujian
    WHERE LOWER(TRIM(nama_siswa)) = LOWER(TRIM(:nama))
      AND (
          LOWER(TRIM(mapel)) = LOWER(TRIM(:mapel))
          OR LOWER(mapel) LIKE LOWER(:mapel_like)
      )
      AND status = 'BERJALAN'
    ORDER BY created_at DESC LIMIT 1;
    """
    try:
        with conn.session as s:
            res = s.execute(text(query), {
                "nama": nama_siswa.strip(), 
                "mapel": mapel.strip(),
                "mapel_like": f"%{mapel.strip()}%"
            }).fetchone()
            
            if res:
                detail_ans = res[1]
                if isinstance(detail_ans, str):
                    try:
                        detail_ans = json.loads(detail_ans)
                    except Exception:
                        detail_ans = []

                return {
                    "id_sesi": res[0],
                    "detail_jawaban": detail_ans if isinstance(detail_ans, list) else [],
                    "created_at": res[2],
                    "soal_sekarang": res[3] if len(res) > 3 and res[3] is not None else 1
                }
    except Exception as e:
        print(f"Error check_active_session_from_db: {e}")
    return None

def load_session_review_from_db(session_id: str):
    """Membaca data sesi ujian dari Supabase untuk ditampilkan di Streamlit."""
    conn = init_db_connection()
    if not conn:
        return None

    query = "SELECT nama_siswa, jenjang, mapel, detail_jawaban, nilai_akhir FROM sesi_ujian WHERE id_sesi = :id"
    try:
        with conn.session as s:
            res = s.execute(text(query), {"id": session_id.strip()}).fetchone()
            if res:
                nama, jenjang, mapel, detail_raw, nilai = res
                
                # Parsing detail_jawaban (apakah berupa dict payload baru atau list boolean lama)
                if isinstance(detail_raw, dict):
                    payload = detail_raw
                elif isinstance(detail_raw, str):
                    try:
                        payload = json.loads(detail_raw)
                    except Exception:
                        payload = {}
                else:
                    payload = {}

                if isinstance(payload, dict):
                    raw_user_answers = payload.get("user_answers", {})
                    quiz_data = payload.get("quiz_data", [])
                else:
                    raw_user_answers = {}
                    quiz_data = []

                # Format ulang key dictionary ke integer agar cocok dengan state Streamlit
                formatted_user_answers = {}
                for k, v in raw_user_answers.items():
                    try:
                        formatted_user_answers[int(k)] = v
                    except ValueError:
                        formatted_user_answers[k] = v

                return {
                    "nama": nama,
                    "jenjang": jenjang or "MA",
                    "mapel": mapel.replace(" (Quiz)", "") if mapel else "Kuis",
                    "quiz_data": quiz_data,
                    "user_answers": formatted_user_answers,
                    "nilai": nilai
                }
    except Exception as e:
        print(f"Error load_session_review_from_db: {e}")
    return None

# ==============================================================================
# HELPER PARSER MATHEMATICA & OMML WORD EQUATION
# ==============================================================================
def clean_math_string(text: str) -> str:
    """Pembersih simbol & notasi matematika dasar untuk teks biasa."""
    if not text:
        return ""
    
    text = re.sub(r'\\(?:rightarrow|to)\b', '→', text)
    text = re.sub(r'\\Rightarrow\b', '⇒', text)
    text = re.sub(r'\\leftarrow\b', '←', text)
    text = re.sub(r'\\leftrightarrow\b', '↔', text)

    text = re.sub(r'\\left\b\s*[\(\[\{\.\|]?', '(', text)
    text = re.sub(r'\\right\b\s*[\)\]\}\.\|]?', ')', text)
    text = re.sub(r'\\(?:dots|cdots|ldots)', '…', text)

    text = re.sub(r'\\sqrt\{([^}]+)\}', r'√(\1)', text)
    text = re.sub(r'\\sqrt\s*([a-zA-Z0-9_]+)', r'√\1', text)

    sup_map = str.maketrans("0123456789+-=()nxyi", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿˣʸⁱ")
    sub_map = str.maketrans("0123456789+-=()nixy", "₀₁₂₃₄⁵₆₇₈₉₊₋₌₍₎ₙᵢₓᵧ")

    text = re.sub(r'\^\{([^}]+)\}|\^([\-0-9a-zA-Z])', lambda m: (m.group(1) or m.group(2)).translate(sup_map), text)
    text = re.sub(r'\_\{([^}]+)\}|\_([0-9a-zA-Z])', lambda m: (m.group(1) or m.group(2)).translate(sub_map), text)

    replacements = {
        r"\times": "×", r"\cdot": "·", r"\div": "÷", r"\neq": "≠",
        r"\leq": "≤", r"\geq": "≥", r"\pm": "±", r"\infty": "∞",
        r"\pi": "π", r"\alpha": "α", r"\beta": "β", r"\theta": "θ", "$": ""
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    text = text.replace("left(", "(").replace("right)", ")").replace("dots", "…")
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r'\\([a-zA-Z]+)', r'\1', text).replace("\\", "")
    return re.sub(r'\s+', ' ', text).strip()

clean_math_text = clean_math_string

def add_omml_fraction(paragraph, num_text: str, den_text: str):
    """Menyisipkan struktur Pecahan Tegak Resmi Microsoft Word (Equation)."""
    num_clean = clean_math_string(num_text)
    den_clean = clean_math_string(den_text)
    
    omml_xml = (
        f'<m:oMath {nsdecls("m")}>'
        f'  <m:f>'
        f'    <m:num><m:r><m:t>{num_clean}</m:t></m:r></m:num>'
        f'    <m:den><m:r><m:t>{den_clean}</m:t></m:r></m:den>'
        f'  </m:f>'
        f'</m:oMath>'
    )
    paragraph._p.append(parse_xml(omml_xml))

def add_omml_matrix(paragraph, matrix_type: str, content: str):
    """Menyisipkan struktur Matriks 2D Bertingkat Resmi Microsoft Word (Equation)."""
    beg_chr, end_chr = "(", ")"
    if matrix_type == "bmatrix":
        beg_chr, end_chr = "[", "]"
    elif matrix_type in ["vmatrix", "Vmatrix"]:
        beg_chr, end_chr = "|", "|"
    elif matrix_type == "matrix":
        beg_chr, end_chr = "", ""

    rows = [r.strip() for r in re.split(r'\\\\|\\cr', content) if r.strip()]
    matrix_xml_rows = []
    for r in rows:
        cols = [c.strip() for c in r.split('&')]
        cols_xml = []
        for c in cols:
            cleaned_c = html.escape(clean_math_string(c))
            cols_xml.append(f'<m:e><m:r><m:t>{cleaned_c}</m:t></m:r></m:e>')
        matrix_xml_rows.append(f'<m:mr>{"".join(cols_xml)}</m:mr>')

    inner_matrix = f'<m:m>{"".join(matrix_xml_rows)}</m:m>'
    if beg_chr or end_chr:
        omml_xml = (
            f'<m:oMath {nsdecls("m")}>'
            f'  <m:d>'
            f'    <m:dPr>'
            f'      <m:begChr m:val="{beg_chr}"/>'
            f'      <m:endChr m:val="{end_chr}"/>'
            f'    </m:dPr>'
            f'    <m:e>{inner_matrix}</m:e>'
            f'  </m:d>'
            f'</m:oMath>'
        )
    else:
        omml_xml = f'<m:oMath {nsdecls("m")}>{inner_matrix}</m:oMath>'

    paragraph._p.append(parse_xml(omml_xml))

def append_text_with_fractions(paragraph, text: str, is_bold: bool = False, color_rgb: RGBColor = None):
    """Membagi paragraf: teks biasa, pecahan \\frac, dan matriks \\begin{...matrix}."""
    if not text:
        return

    math_pattern = re.compile(
        r'\\begin\{(?P<mtype>[pbvV]?matrix)\}(?P<mcontent>.*?)\\end\{(?P=mtype)\}|\\(?:f|tf)rac\{(?P<num>[^}]+)\}\{(?P<den>[^}]+)\}',
        re.DOTALL
    )
    last_idx = 0

    for match in math_pattern.finditer(text):
        start, end = match.span()
        if start > last_idx:
            plain_part = clean_math_string(text[last_idx:start])
            if plain_part:
                run = paragraph.add_run(plain_part + " ")
                run.bold = is_bold
                if color_rgb:
                    run.font.color.rgb = color_rgb

        if match.group('mtype'):
            add_omml_matrix(paragraph, match.group('mtype'), match.group('mcontent'))
        elif match.group('num'):
            add_omml_fraction(paragraph, match.group('num'), match.group('den'))
        
        run_space = paragraph.add_run(" ")
        run_space.bold = is_bold
        last_idx = end

    if last_idx < len(text):
        plain_part = clean_math_string(text[last_idx:])
        if plain_part:
            run = paragraph.add_run(plain_part)
            run.bold = is_bold
            if color_rgb:
                run.font.color.rgb = color_rgb
# ==============================================================================
# HELPER PARSER MARKDOWN & OMML UNTUK DOKUMEN KEDINASAN
# ==============================================================================
def append_markdown_formatted_text(doc, md_text: str):
    """
    Mengurai teks Markdown AI (### header, **bold**, bullet -) 
    menjadi paragraf Word berstandar kedinasan yang rapi dan elegan.
    """
    if not md_text:
        return

    lines = md_text.split('\n')
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        # 1. Sub-Header (###)
        if line_str.startswith('###'):
            p_h = doc.add_paragraph()
            p_h.paragraph_format.space_before = Pt(8)
            p_h.paragraph_format.space_after = Pt(3)
            h_text = line_str.lstrip('#').strip()
            run_h = p_h.add_run(h_text)
            run_h.bold = True
            run_h.font.size = Pt(11)
            run_h.font.color.rgb = RGBColor(6, 78, 59) # Emerald Kedinasan

        # 2. Poin Bullet (- atau *)
        elif line_str.startswith(('-', '*')):
            p_b = doc.add_paragraph()
            p_b.paragraph_format.left_indent = Inches(0.25)
            p_b.paragraph_format.space_after = Pt(2)
            
            content = line_str.lstrip('-*').strip()
            parts = re.split(r'(\*\*.*?\*\*)', content)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    clean_part = part[2:-2]
                    append_text_with_fractions(p_b, clean_part, is_bold=True, color_rgb=RGBColor(6, 78, 59))
                else:
                    append_text_with_fractions(p_b, part, is_bold=False)

        # 3. Paragraf Biasa
        else:
            p_gen = doc.add_paragraph()
            p_gen.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p_gen.paragraph_format.space_after = Pt(4)
            
            parts = re.split(r'(\*\*.*?\*\*)', line_str)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    clean_part = part[2:-2]
                    append_text_with_fractions(p_gen, clean_part, is_bold=True)
                else:
                    append_text_with_fractions(p_gen, part, is_bold=False)

# ==============================================================================
# GENERATOR GRAFIK VISUAL MATPLOTLIB (IN-MEMORY BUFFER)
# ==============================================================================
def generate_class_visual_charts(data_siswa: list):
    """Menghasilkan 2 gambar grafik statistik (Donut Chart & Horizontal Bar Chart)."""
    if not data_siswa:
        return None, None

    df = pd.DataFrame(data_siswa)
    
    # 1. Klasifikasi Kognitif Kelas
    mahir = len(df[df['nilai_akhir'] >= 80])
    berkembang = len(df[(df['nilai_akhir'] >= 50) & (df['nilai_akhir'] < 80)])
    intervensi = len(df[df['nilai_akhir'] < 50])

    # --- GRAFIK 1: DONUT CHART KATEGORI PENGUASAAN ---
    fig1, ax1 = plt.subplots(figsize=(5, 3.5), dpi=200)
    labels = ['Sangat Mahir (≥80)', 'Berkembang (50-79)', 'Perlu Intervensi (<50)']
    sizes = [mahir, berkembang, intervensi]
    colors = ['#10B981', '#F59E0B', '#EF4444']
    
    # Filter kategori bernilai > 0
    active_labels = [l for l, s in zip(labels, sizes) if s > 0]
    active_sizes = [s for s in sizes if s > 0]
    active_colors = [c for c, s in zip(colors, sizes) if s > 0]

    wedges, texts, autotexts = ax1.pie(
        active_sizes, labels=active_labels, colors=active_colors,
        autopct='%1.1f%%', startangle=140, pctdistance=0.75,
        textprops=dict(color="#1E293B", fontsize=8, weight="bold")
    )
    
    # Lubang Donut Tengah
    centre_circle = plt.Circle((0, 0), 0.50, fc='white')
    fig1.gca().add_artist(centre_circle)
    ax1.set_title("Distribusi Tingkat Penguasaan Kognitif Santri", fontsize=10, fontweight='bold', pad=12, color='#064E3B')
    plt.tight_layout()

    buf1 = io.BytesIO()
    plt.savefig(buf1, format='png', bbox_inches='tight')
    plt.close(fig1)
    buf1.seek(0)

    # --- GRAFIK 2: BAR CHART NILAI PER-SISWA ---
    fig2, ax2 = plt.subplots(figsize=(6, max(3, len(df) * 0.4)), dpi=200)
    df_sorted = df.sort_values(by='nilai_akhir', ascending=True)

    names = [n[:18] + '...' if len(n) > 18 else n for n in df_sorted['nama_siswa']]
    scores = df_sorted['nilai_akhir']
    bar_colors = ['#10B981' if s >= 80 else ('#F59E0B' if s >= 50 else '#EF4444') for s in scores]

    bars = ax2.barh(names, scores, color=bar_colors, height=0.6)
    ax2.set_xlim(0, 100)
    ax2.set_xlabel("Skor Akhir Ujian", fontsize=8, fontweight='bold', color='#475569')
    ax2.set_title("Peringkat & Performa Skor Santri", fontsize=10, fontweight='bold', pad=12, color='#064E3B')
    
    # Label Nilai di Ujung Bar
    for bar in bars:
        width = bar.get_width()
        ax2.text(width + 1.5, bar.get_y() + bar.get_height()/2, f'{int(width)}',
                 va='center', ha='left', fontsize=8, fontweight='bold', color='#1E293B')

    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)
    ax2.grid(axis='x', linestyle='--', alpha=0.5)
    plt.tight_layout()

    buf2 = io.BytesIO()
    plt.savefig(buf2, format='png', bbox_inches='tight')
    plt.close(fig2)
    buf2.seek(0)

    return buf1, buf2

# ==============================================================================
# MAIN DOCX REPORT GENERATOR (STANDAR RESMI KEDINASAN & VISUAL ANALYTICS)
# ==============================================================================
def generate_corporate_executive_docx_report(config: dict, data_siswa: list, collective_ai_summary: str = None) -> bytes:
    """
    Menghasilkan Dokumen Word (.docx) Laporan Rekapitulasi Ujian & Diagnostik Eksekutif
    Presisi Kedinasan: Kop Instansi, Garis XML Solid, Tabel Metadata 3-Kolom, Chart Visual, & Diagnosis Individu.
    """
    doc = Document()

    # Set Margin Halaman Standard 1 Inci
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    # --- 1. KOP INSTITUSI RESMI (PERSIS FORMAT ASLI) ---
    header_table = doc.add_table(rows=1, cols=2)
    header_table.autofit = False
    
    cells = header_table.rows[0].cells
    cells[0].width = Inches(1.6)
    cells[1].width = Inches(4.7)
    cells[0].vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    cells[1].vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    # Logo Instansi
    p_logo = cells[0].paragraphs[0]
    p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    logo_path = "logo.png"
    if os.path.exists(logo_path):
        p_logo.add_run().add_picture(logo_path, width=Inches(1.5))
    else:
        r_logo = p_logo.add_run("[LOGO MANTAP]")
        r_logo.bold = True
        r_logo.font.size = Pt(12)
        r_logo.font.color.rgb = RGBColor(6, 78, 59)

    # Teks Kop Instansi
    p_title = cells[1].paragraphs[0]
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_after = Pt(2)
    
    r1 = p_title.add_run("LAPORAN REKAPITULASI & DIAGNOSIS CBT\n")
    r1.bold = True
    r1.font.size = Pt(13)
    r1.font.color.rgb = RGBColor(6, 78, 59) # Warna Hijau Edukasi Kedinasan
    
    r2 = p_title.add_run("Madrasah Aliyah dan Tsanawiyah Al-Irsyad Al-Islamiyah Putri Bondowoso\n")
    r2.bold = True
    r2.font.size = Pt(10.5)
    
    # Tanggal Presisi WIB dengan Nama Bulan Bahasa Indonesia
    now_wib = datetime.utcnow() + timedelta(hours=7)
    nama_bulan = [
        "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]
    tgl_presisi = f"{now_wib.day} {nama_bulan[now_wib.month]} {now_wib.year}"
    
    r3 = p_title.add_run(f"Tanggal Penerbitan: {tgl_presisi} WIB")
    r3.italic = True
    r3.font.size = Pt(9.5)
    r3.font.color.rgb = RGBColor(100, 100, 100)

    # --- 2. GARIS PEMBATAS HIJAU SOLID (XML EMBED) ---
    p_div = doc.add_paragraph()
    p_div.paragraph_format.space_before = Pt(4)
    p_div.paragraph_format.space_after = Pt(10)
    pBdr = parse_xml(
        r'<w:pBdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        r'<w:bottom w:val="single" w:sz="20" w:space="1" w:color="064E3B"/>'
        r'</w:pBdr>'
    )
    p_div._p.get_or_add_pPr().append(pBdr)

    # --- 3. JUDUL EXECUTIVE REPORT ---
    p_paket = doc.add_paragraph()
    p_paket.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_paket.paragraph_format.space_after = Pt(10)
    r_paket = p_paket.add_run(f"EVALUASI UJIAN {config.get('mapel', 'Mata Pelajaran').upper()}")
    r_paket.bold = True
    r_paket.font.size = Pt(13)
    r_paket.font.color.rgb = RGBColor(6, 78, 59)

    # --- 4. METADATA KUIS (TABEL 3 KOLOM PRESISI & LURUS SEJAJAR) ---
    meta_items = [
        ("Jenjang / Kelas", f"{config.get('jenjang', '-')} ({config.get('kelas', 'Semua Kelas')})"),
        ("Materi Utama", f"{clean_math_string(config.get('materi', 'Ujian Terintegrasi'))}"),
        ("Total Peserta Ujian", f"{len(data_siswa)} Santri Terdaftar")
    ]

    meta_table = doc.add_table(rows=0, cols=3)
    meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_table.autofit = False

    for label, val in meta_items:
        row_cells = meta_table.add_row().cells
        
        # Kolom 1: Label
        p0 = row_cells[0].paragraphs[0]
        r0 = p0.add_run(label)
        r0.bold = True
        p0.paragraph_format.space_before = Pt(2)
        p0.paragraph_format.space_after = Pt(2)
        row_cells[0].width = Inches(1.5)
        
        # Kolom 2: Titik Dua
        p1 = row_cells[1].paragraphs[0]
        r1 = p1.add_run(":")
        r1.bold = True
        p1.paragraph_format.space_before = Pt(2)
        p1.paragraph_format.space_after = Pt(2)
        row_cells[1].width = Inches(0.2)
        
        # Kolom 3: Nilai
        p2 = row_cells[2].paragraphs[0]
        p2.add_run(val)
        p2.paragraph_format.space_before = Pt(2)
        p2.paragraph_format.space_after = Pt(2)
        row_cells[2].width = Inches(4.8)

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # --- 5. RINGKASAN KPI KELAS ---
    total = len(data_siswa)
    if total > 0:
        scores = [s.get("nilai_akhir", 0) for s in data_siswa]
        avg_score = sum(scores) / total
        max_score = max(scores)
        min_score = min(scores)
    else:
        avg_score = max_score = min_score = 0

    kpi_table = doc.add_table(rows=2, cols=4)
    kpi_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    kpi_table.style = 'Table Grid'
    
    headers = ["Total Santri", "Rata-Rata Kelas", "Skor Tertinggi", "Skor Terendah"]
    values = [str(total), f"{avg_score:.1f}", str(max_score), str(min_score)]

    for i, h in enumerate(headers):
        cell = kpi_table.cell(0, i)
        cell.text = h
        cell.paragraphs[0].runs[0].font.bold = True
        cell.paragraphs[0].runs[0].font.size = Pt(9.5)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    for i, v in enumerate(values):
        cell = kpi_table.cell(1, i)
        cell.text = v
        cell.paragraphs[0].runs[0].font.bold = True
        cell.paragraphs[0].runs[0].font.size = Pt(12.5)
        cell.paragraphs[0].runs[0].font.color.rgb = RGBColor(6, 78, 59)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph().paragraph_format.space_after = Pt(14)

    # --- 6. VISUAL ANALYTICS (MATPLOTLIB IN-DOCX CHART) ---
    chart1_buf, chart2_buf = generate_class_visual_charts(data_siswa)
    if chart1_buf and chart2_buf:
        doc.add_heading("1. Analisis Visual Performa Kelas", level=2)
        p_charts = doc.add_paragraph()
        p_charts.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        p_charts.add_run().add_picture(chart1_buf, width=Inches(3.1))
        p_charts.add_run("   ")
        p_charts.add_run().add_picture(chart2_buf, width=Inches(3.3))
        
        doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # --- 7. DIAGNOSIS KOLEKTIF KELAS ---
    doc.add_heading("2. Diagnosis Pedagogis Kolektif (AI Engine)", level=2)
    summary_text = collective_ai_summary or "Berdasarkan evaluasi kuis, tingkat penguasaan konsep santri berada pada kategori baik."
    append_markdown_formatted_text(doc, summary_text)
    doc.add_paragraph().paragraph_format.space_after = Pt(14)

    # --- 8. TABEL REKAPITULASI DETAIL SISWA ---
    doc.add_heading("3. Tabel Rekapitulasi Nilai Seluruh Santri", level=2)
    
    table = doc.add_table(rows=1, cols=6)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = 'Table Grid'

    hdr_cells = table.rows[0].cells
    headers_text = ["No", "Nama Santri", "Kelas", "Benar", "Salah", "Nilai Akhir"]
    for i, text in enumerate(headers_text):
        hdr_cells[i].text = text
        hdr_cells[i].paragraphs[0].runs[0].font.bold = True
        hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    for idx, s in enumerate(data_siswa, start=1):
        row_cells = table.add_row().cells
        row_cells[0].text = str(idx)
        row_cells[1].text = str(s.get("nama_siswa", "-"))
        row_cells[2].text = str(s.get("jenjang", "-"))
        row_cells[3].text = str(s.get("jumlah_benar", 0))
        row_cells[4].text = str(s.get("jumlah_salah", 0))
        row_cells[5].text = str(s.get("nilai_akhir", 0))
        
        row_cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        row_cells[3].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        row_cells[4].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        row_cells[5].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        row_cells[5].paragraphs[0].runs[0].font.bold = True

    doc.add_paragraph().paragraph_format.space_after = Pt(20)

    # --- 9. LAMPIRAN DIAGNOSIS PRESKRIPTIF PER-SANTRI ---
    doc.add_page_break()
    
    p_lamp = doc.add_paragraph()
    p_lamp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_lamp = p_lamp.add_run("LAMPIRAN: DIAGNOSIS PRESKRIPTIF INDIVIDU SANTRI")
    r_lamp.bold = True
    r_lamp.font.size = Pt(13)
    r_lamp.font.color.rgb = RGBColor(6, 78, 59)
    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    for idx, s in enumerate(data_siswa, start=1):
        p_indiv = doc.add_paragraph()
        r_indiv = p_indiv.add_run(f"Santri #{idx}: {s.get('nama_siswa', '-')} (Skor Akhir: {s.get('nilai_akhir', 0)})")
        r_indiv.bold = True
        r_indiv.font.size = Pt(11)
        r_indiv.font.color.rgb = RGBColor(6, 78, 59)

        detail_raw = s.get("detail_jawaban", [])
        quiz_data = None
        user_answers = None
        if isinstance(detail_raw, dict):
            detail_boolean = detail_raw.get("detail_boolean", [])
            user_answers = detail_raw.get("user_answers", {})
            quiz_data = detail_raw.get("quiz_data", [])
        elif isinstance(detail_raw, list):
            detail_boolean = detail_raw
        else:
            detail_boolean = []

        # Diagnosis AI Tanpa Nomor Soal
        indiv_report_text = generate_individual_analysis_ai(
            nama_siswa=s.get("nama_siswa", "-"),
            mapel=config.get("mapel", "Kuis"),
            jenjang=s.get("jenjang", "MA"),
            nilai=s.get("nilai_akhir", 0),
            detail_jawaban_list=detail_boolean,
            quiz_data=quiz_data,
            user_answers=user_answers
        )

        # Render Teks Markdown AI ke Paragraf Kedinasan
        append_markdown_formatted_text(doc, indiv_report_text)
        doc.add_paragraph().paragraph_format.space_after = Pt(14)

    # Simpan ke BytesIO Buffer
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
