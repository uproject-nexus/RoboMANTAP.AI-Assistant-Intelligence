import os
import json
import re
import streamlit as st
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Tambahan untuk Database Real-Time (Dari Kode Upgrade)
try:
    from sqlalchemy import text
except ImportError:
    pass

load_dotenv()

# Ambil daftar API Keys dari Streamlit Secrets atau .env
api_keys = []
if "GEMINI_API_KEYS" in st.secrets:
    api_keys = list(st.secrets["GEMINI_API_KEYS"])
elif os.getenv("GEMINI_API_KEY"):
    api_keys = [os.getenv("GEMINI_API_KEY")]

if not api_keys:
    raise ValueError("GEMINI_API_KEYS tidak ditemukan. Pastikan Secrets sudah dikonfigurasi.")

# Fokus ke model paling kencang agar tidak ada jeda retry yang bikin lemot
# Model untuk pembuatan soal
QUIZ_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")

# Model khusus interaksi LIVE: prioritaskan latency rendah.
STREAM_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")

STREAM_HINT_MAX_TOKENS = 9000
STREAM_SOLUTION_MAX_TOKENS = 9000
STREAM_TIMEOUT_MS = 90_000


@st.cache_resource(show_spinner=False)
def get_gemini_clients():
    """
    Reuse koneksi Gemini antar rerun Streamlit.
    Client tidak dibuat ulang setiap kali tombol AI diklik.
    """
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

    return clients


def _stream_config(model_name: str, max_output_tokens: int):
    """
    Konfigurasi live untuk meminimalkan time-to-first-token.
    Gemini 3.x: thinking minimal.
    Gemini 2.5 Flash-Lite: thinking dimatikan.
    """
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
    """
    Menggabungkan chunk API yang sangat kecil sebelum dikirim ke Streamlit.
    Tujuannya mengurangi frekuensi update UI, bukan mengubah token API.
    """
    import time

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
    """
    Streaming:
    - client reuse
    - retry internal SDK = 1 attempt
    - fallback hanya saat request/model benar-benar gagal
    - chunk dibuffer agar rendering lebih smooth
    """
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
        opt = opt.replace(r"\frac", r"\tfrac")
        formatted.append(opt)
    return formatted

def clean_json_text(text: str) -> str:
    """Membersihkan string JSON murni dari pemungkus markdown."""
    if not text:
        return ""
    
    text = text.strip()
    # Hapus pemungkus markdown ```json jika ada
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    # Fungsi pengganti otomatis untuk menjaga validitas JSON
    def replace_slash(match):
        g = match.group(0)
        if g in (r'\\', r'\"'):
            return g  # Biarkan \\ dan \" yang sudah valid
        return r'\\'  # Ubah \ tunggal menjadi \\

    # Amankan backslash tanpa merusak struktur JSON
    return re.sub(r'\\\\|\\"|\\', replace_slash, text)

def call_gemini_with_rotation(prompt: str, is_json: bool = False):
    """
    Non-stream request dengan client yang sudah di-cache.
    Retry internal dimatikan supaya fallback tidak menambah jeda tersembunyi.
    """
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

                if response.text:
                    return response.text

            except Exception:
                continue

    return None

def stream_ai_text(prompt: str, max_output_tokens: int = STREAM_HINT_MAX_TOKENS):
    """Generator sinkron yang kompatibel langsung dengan st.write_stream()."""
    yield from _stream_from_clients(
        prompt,
        max_output_tokens=max_output_tokens,
    )

def generate_quiz_batch(jenjang: str, mapel: str, stage: str, selected_submateri: list):
    """
    Menghasilkan 1 paket latihan CBT 10 soal berkualitas tinggi dan natural.
    Output HANYA soal dan opsi (tanpa pembahasan) agar generasi sangat cepat.
    """
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
        st.error("⚠️ Waduh kuota sedang penuh nih. Silakan coba klik lagi ya...")
        return []

    try:
        cleaned_response = clean_json_text(raw_response)
        # WAJIB strict=False untuk keamanan maksimal dari karakter escape
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
        st.error(f"Gagal memproses format soal: {e}")
        return []

def get_ai_hint_stream(question: str, user_attempt: str, mapel: str = "Umum"):
    """
    Menyusun prompt petunjuk dan langsung melemparnya ke generator stream.
    """
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
    """
    Menyusun prompt pembahasan rinci dan langsung melemparnya ke generator stream.
    """
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
# INTEGRASI DATABASE REAL-TIME UNTUK DASHBOARD GURU (U.PROJECT NEXUS)
# ==============================================================================

def init_db_connection():
    """Menginisialisasi koneksi ke PostgreSQL menggunakan fitur native Streamlit."""
    try:
        # Membutuhkan konfigurasi [connections.postgresql] di file .streamlit/secrets.toml
        return st.connection("postgresql", type="sql")
    except Exception as e:
        # Gagal silent agar tidak mengganggu aplikasi siswa jika DB belum disetup
        return None

# ------------------------------------------------------------------------------
# UPDATE CREATETABLE: TAMBAHKAN TABEL KUIS CUSTOM
# ------------------------------------------------------------------------------
def create_table_if_not_exists():
    conn = init_db_connection()
    if not conn: return
    
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
    except Exception:
        pass


# ------------------------------------------------------------------------------
# FUNGSI PUBLISH & GET KUIS CUSTOM KE DATABASE
# ------------------------------------------------------------------------------
def publish_custom_quiz_to_db(kode_kuis: str, config: dict, quiz_data: list) -> bool:
    """Menyimpan paket Kuis Custom yang diterbitkan guru ke database Supabase."""
    conn = init_db_connection()
    if not conn: return False

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
                "kode": kode_kuis,
                "cfg": json.dumps(config),
                "quiz": json.dumps(quiz_data)
            })
            s.commit()
        return True
    except Exception:
        return False


def get_custom_quiz_from_db(kode_kuis: str):
    """Mengambil paket Kuis Custom berdasarkan Kode Kuis yang dimasukkan siswa."""
    conn = init_db_connection()
    if not conn: return None

    query = "SELECT config, quiz_data FROM kuis_custom WHERE UPPER(kode_kuis) = UPPER(:kode)"
    try:
        with conn.session as s:
            result = s.execute(text(query), {"kode": kode_kuis.strip()}).fetchone()
            if result:
                cfg = result[0] if isinstance(result[0], dict) else json.loads(result[0])
                quiz = result[1] if isinstance(result[1], list) else json.loads(result[1])
                return {"config": cfg, "quiz": quiz}
    except Exception:
        pass
    return None

def update_progress_siswa(
    session_id: str,
    nama: str,
    jenjang: str,
    mapel: str,
    soal_sekarang: int,
    detail_jawaban: list,
    status: str = "BERJALAN",
    is_custom: bool = False  # <-- Parameter ini wajib ada
):
    """
    Menyimpan atau memperbarui live status siswa ke database terpusat.
    Dukungan skoring otomatis untuk CBT OMI (+4/-1) maupun Kuis Custom (Skala 100).
    """
    conn = init_db_connection()
    if not conn:
        return

    total_soal = len(detail_jawaban) if len(detail_jawaban) > 0 else 10
    jumlah_benar = sum(1 for x in detail_jawaban if x is True)
    jumlah_salah = sum(1 for x in detail_jawaban if x is False)

    # Kalkulasi skor sesuai tipe kuis
    if is_custom:
        nilai_akhir = int(round((jumlah_benar / total_soal) * 100)) if total_soal > 0 else 0
    else:
        nilai_akhir = (jumlah_benar * 4) - (jumlah_salah * 1)

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
                    "mapel": mapel,
                    "soal": soal_sekarang,
                    "detail": detail_json,
                    "benar": jumlah_benar,
                    "salah": jumlah_salah,
                    "nilai": nilai_akhir,
                    "status": status,
                },
            )
            s.commit()
    except Exception:
        pass

#generate LKPD
def generate_lkpd_content(mapel: str, kelas: str, topik: str):
    """
    Menghasilkan isi materi LKPD HOTS khas Al-Irsyad Bondowoso menggunakan Gemini 3.x
    dengan aturan format Unicode murni agar kompatibel dengan ReportLab PDF dan Word.
    """
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

    Instruksi Penyusunan Konten:
    1. Tujuan Pembelajaran: Buatkan 2 poin tujuan berbasis indikator HOTS.
    2. Apersepsi & Ringkasan Konsep: Sajikan materi singkat, tajam, dan korelasikan dengan nilai-nilai Keislaman/Tadabbur Sains.
    3. Tugas Eksplorasi Mandiri: Buat 2 soal studi kasus/problem solving HOTS yang melatih logika nalar santri/siswi.
    4. Refleksi Keislaman: Tuliskan 1 kalimat hikmah/perenungan dari mempelajari materi {topik}.

    Format keluaran WAJIB objek JSON murni:
    {{
        "tujuan": ["Poin tujuan 1", "Poin tujuan 2"],
        "ringkasan": "Teks ringkasan konsep dan keislaman...",
        "soal_1": "Pertanyaan eksplorasi HOTS nomor 1",
        "soal_2": "Pertanyaan eksplorasi HOTS nomor 2",
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

#generate KUIS CUSTOM
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
    """
    Generator Kuis Custom untuk guru di ai_engine.py.
    Memakai call_gemini_with_rotation + clean_json_text bawaan engine.
    """
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
