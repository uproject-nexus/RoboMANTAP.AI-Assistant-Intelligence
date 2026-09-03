import os
import json
import re
import streamlit as st
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Ambil daftar API Keys dari Streamlit Secrets atau .env
api_keys = []
if "GEMINI_API_KEYS" in st.secrets:
    api_keys = list(st.secrets["GEMINI_API_KEYS"])
elif os.getenv("GEMINI_API_KEY"):
    api_keys = [os.getenv("GEMINI_API_KEY")]

if not api_keys:
    raise ValueError("GEMINI_API_KEYS tidak ditemukan. Pastikan Secrets sudah dikonfigurasi.")

# ============================================================================
# MODEL ROUTING
# ============================================================================
QUIZ_PRIMARY_MODEL = "gemini-3.5-flash-lite"
QUIZ_FALLBACK_MODEL = "gemini-3.1-flash-lite"

VERIFIER_PRIMARY_MODEL = "gemini-3.5-flash-lite"
VERIFIER_FALLBACK_MODEL = "gemini-3.1-flash-lite"

HINT_PRIMARY_MODEL = "gemini-3.1-flash-lite"
HINT_FALLBACK_MODEL = "gemini-3.5-flash-lite"

SOLUTION_PRIMARY_MODEL = "gemini-3.5-flash-lite"
SOLUTION_FALLBACK_MODEL = "gemini-3.1-flash-lite"

# Thinking disesuaikan berdasarkan fungsi.
QUIZ_THINKING_LEVEL = "medium"
VERIFIER_THINKING_LEVEL = "high"
HINT_THINKING_LEVEL = "minimal"
SOLUTION_THINKING_LEVEL = "medium"

STREAM_HINT_MAX_TOKENS = 4000
STREAM_SOLUTION_MAX_TOKENS = 4000
QUIZ_MAX_OUTPUT_TOKENS = 8000
VERIFIER_MAX_OUTPUT_TOKENS = 4000
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


def _make_generation_config(
    *,
    max_output_tokens: int,
    thinking_level: str | None = None,
    response_mime_type: str | None = None,
):
    kwargs = {"max_output_tokens": max_output_tokens}
    if response_mime_type:
        kwargs["response_mime_type"] = response_mime_type
    if thinking_level:
        kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_level=thinking_level
        )
    return types.GenerateContentConfig(**kwargs)


def _buffer_stream_text(source, min_chars: int = 12, flush_seconds: float = 0.04):
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


def _stream_from_clients(
    prompt: str,
    max_output_tokens: int,
    primary_model: str,
    fallback_model: str,
    thinking_level: str,
):
    """
    Streaming aman:
    - client di-cache
    - retry internal SDK = 1 attempt
    - fallback hanya SEBELUM token pertama benar-benar diterima
    - setelah token pertama diterima, error tidak boleh pindah model
    """
    clients = get_gemini_clients()

    if not clients:
        yield "⚠️ Tidak ada koneksi AI yang aktif. Periksa API key/server."
        return

    models = (primary_model, fallback_model)

    for client in clients:
        for model_name in models:
            emitted_any_text = False

            try:
                response = client.models.generate_content_stream(
                    model=model_name,
                    contents=prompt,
                    config=_make_generation_config(
                        max_output_tokens=max_output_tokens,
                        thinking_level=thinking_level,
                    ),
                )

                def raw_stream():
                    nonlocal emitted_any_text
                    for chunk in response:
                        chunk_text = getattr(chunk, "text", None)
                        if chunk_text:
                            emitted_any_text = True
                            yield chunk_text

                for piece in _buffer_stream_text(raw_stream()):
                    yield piece

                # Stream selesai normal. Jangan panggil model lain.
                return

            except Exception:
                # Jika sudah pernah menerima teks, JANGAN mencampur output
                # dengan model lain. Akhiri stream secara eksplisit.
                if emitted_any_text:
                    yield (
                        "\n\n⚠️ Koneksi AI terputus sebelum jawaban selesai. "
                        "Silakan klik kembali untuk meminta ulang."
                    )
                    return

                # Belum ada output -> aman fallback.
                continue

    yield (
        "⚠️ Maaf, AI belum dapat merespons pada percobaan ini. "
        "Silakan coba kembali beberapa saat lagi."
    )

def format_latex_options(options):
    formatted = []
    for opt in options:
        opt = opt.replace(r"\frac", r"\tfrac")
        if "\\" in opt and "$" not in opt:
            parts = opt.split(" ", 1)
            if len(parts) == 2 and parts[0].endswith("."):
                opt = f"{parts[0]} ${parts[1]}$"
            else:
                opt = f"${opt}$"
        formatted.append(opt)
    return formatted

def clean_json_text(text: str) -> str:
    """
    Membersihkan string JSON secara permanen dari balikan AI yang mengandung 
    notasi LaTeX atau Bahasa Arab agar tidak memicu error 'Invalid \\escape'.
    """
    if not text:
        return ""
    
    text = text.strip()
    # Hapus pemungkus markdown ```json ... ``` jika ada
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    # Perbaikan Anti-Error: Pertahankan \" dan \\ yang valid, ubah sisa \ tunggal menjadi \\
    def fix_slash(m):
        g = m.group(0)
        if g in (r'\"', r'\\'):
            return g
        return r'\\'

    return re.sub(r'\\"|\\\\|\\', fix_slash, text)

def _call_json_model(
    prompt: str,
    models: tuple[str, ...],
    thinking_level: str,
    max_output_tokens: int,
):
    clients = get_gemini_clients()
    if not clients:
        return None

    for client in clients:
        for model_name in models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=_make_generation_config(
                        max_output_tokens=max_output_tokens,
                        thinking_level=thinking_level,
                        response_mime_type="application/json",
                    ),
                )
                if response.text:
                    return response.text
            except Exception:
                continue
    return None


def call_gemini_with_rotation(prompt: str, is_json: bool = False):
    if not is_json:
        return None
    return _call_json_model(
        prompt,
        (QUIZ_PRIMARY_MODEL, QUIZ_FALLBACK_MODEL),
        QUIZ_THINKING_LEVEL,
        QUIZ_MAX_OUTPUT_TOKENS,
    )


def _verify_quiz_batch(quiz_list: list, jenjang: str, mapel: str, stage: str) -> list:
    if len(quiz_list) != 5:
        return []

    verifier_payload = []
    for q in quiz_list:
        verifier_payload.append({
            "id": q.get("id"),
            "question": q.get("question", ""),
            "options": q.get("options", []),
            "correct_answer": q.get("correct_answer", ""),
            "solution_basis": q.get("solution_basis", ""),
        })

    prompt = f"""
Anda adalah VERIFIER AKADEMIK untuk sistem pembinaan Olimpiade tingkat nasional.

Jenjang: {jenjang}
Bidang: {mapel}
Tahap: {stage}

Tugas: verifikasi SEMUA 5 soal berikut. Untuk setiap soal, periksa secara independen:
1. Apakah soal memiliki hanya satu jawaban yang benar.
2. Apakah correct_answer benar-benar didukung oleh perhitungan/logika.
3. Apakah solution_basis konsisten dengan soal dan opsi.
4. Tidak boleh menganggap kunci generator benar hanya karena diberi label 'correct_answer'.
5. Jika salah, tandai invalid. JANGAN memperbaiki soal; hanya verifikasi.

Kembalikan JSON murni:
{{
  "results": [
    {{
      "id": 1,
      "valid": true,
      "verified_answer": "C. ...",
      "reason": "alasan verifikasi singkat"
    }}
  ],
  "batch_valid": true
}}

DATA SOAL:
{json.dumps(verifier_payload, ensure_ascii=False)}
"""

    raw = _call_json_model(
        prompt,
        (VERIFIER_PRIMARY_MODEL, VERIFIER_FALLBACK_MODEL),
        VERIFIER_THINKING_LEVEL,
        VERIFIER_MAX_OUTPUT_TOKENS,
    )
    if not raw:
        return []

    try:
        data = json.loads(clean_json_text(raw), strict=False)
        results = {str(x.get("id")): x for x in data.get("results", [])}

        if not data.get("batch_valid", False):
            return []

        verified = []
        for q in quiz_list:
            r = results.get(str(q.get("id")))
            if not r or not r.get("valid"):
                return []

            # Kunci yang terverifikasi harus sama dengan kunci generator.
            if r.get("verified_answer") != q.get("correct_answer"):
                return []

            q["verification"] = {
                "valid": True,
                "reason": r.get("reason", "Terverifikasi oleh verifier."),
            }
            verified.append(q)

        return verified
    except Exception:
        return []


def stream_ai_text(
    prompt: str,
    max_output_tokens: int = STREAM_HINT_MAX_TOKENS,
    primary_model: str = HINT_PRIMARY_MODEL,
    fallback_model: str = HINT_FALLBACK_MODEL,
    thinking_level: str = HINT_THINKING_LEVEL,
):
    yield from _stream_from_clients(
        prompt,
        max_output_tokens=max_output_tokens,
        primary_model=primary_model,
        fallback_model=fallback_model,
        thinking_level=thinking_level,
    )


def generate_quiz_batch(jenjang: str, mapel: str, stage: str, selected_submateri: list):
    """
    Menghasilkan 1 paket latihan CBT 5 soal berkualitas tinggi dan natural.
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
    Rancanglah 1 paket latihan CBT berisi TEPAT 5 SOAL PILIHAN GANDA yang orisinal, presisi, dan tematik OMI.

    Spesifikasi Soal OMI 2026:
    - Jenjang: {jenjang}
    - Bidang / Mata Pelajaran: {mapel}
    - Tahap Pembinaan: {stage} ({stage_description})
    - Cakupan Submateri: {submateri_text}

    INTEGRASI TEMATIK & BAHASA ARAB OMI (BIARKAN PANJANG DAN NATURAL):
    1. Konteks Tematik: Wajib mengintegrasikan materi dengan tema Lingkungan, Teknologi, Kehidupan Sehari-hari, atau Nilai-Nilai Keislaman (seperti Zakat, Waktu Shalat, Penanggalan Hijriyah, Arah Kiblat, Waris, atau Sejarah Islam).
    2. Aturan Porsi & Variasi Bahasa (SANGAT PENTING):
    - Jika submateri berisi "Semua Submateri" (ALL) atau secara acak: UTAMAKAN karakteristik khusus OMI!
    - Dari total 5 soal yang dibuat, 3 soal WAJIB menggunakan Full Bahasa Indonesia berkonteks Keislaman, Lingkungan, Teknologi atau Umum.
    - HANYA MAKSIMAL 2 SOAL SAJA yang diperbolehkan menggunakan Variasi Bahasa Arab (Teks Soal ditulis dalam Bahasa Arab fasih tanpa harakat, sedangkan Pilihan Jawaban A, B, C, D dalam Bahasa Indonesia atau Teks Soal dalam BAHASA INDONESIA, sedangkan Pilihan Jawaban A, B, C, D dalam BAHASA ARAB fasih tanpa harakat). 
    - Jangan pernah membuat lebih dari 2 soal berbahasa Arab dalam satu paket kuis.

    ATURAN KHUSUS FORMATTING & KECEPATAN:
    - WAJIB sertakan field `solution_basis` untuk setiap soal.
- `solution_basis` adalah penyelesaian ringkas yang mendukung kunci jawaban, termasuk perhitungan inti bila ada.
- Jangan sertakan `hint` siswa di sini.
    - Jika ada formula/notasi matematika/simbol fisika-kimia, WAJIB diapit tanda dollar '$' (Contoh: "$x^2 + 2x = 0$", "$\\tfrac{{1}}{{2}}$").
    - Semua backslash LaTeX wajib ditulis ganda '\\\\'.

    Format keluaran WAJIB berupa objek JSON murni:
    {{
        "quiz": [
            {{
                "id": 1,
                "question": "Teks soal cerita nomor 1 lengkap dan mendalam",
                "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
                "correct_answer": "Pilihan jawaban tepat (harus persis sama dengan salah satu opsi)",
                "solution_basis": "Dasar penyelesaian terverifikasi, ringkas tetapi cukup untuk memeriksa kunci."
            }}
        ]
    }}
    """

    raw_response = call_gemini_with_rotation(system_prompt, is_json=True)

    if not raw_response:
        st.error("⚠️ Waduh kuota sedang penuh nih. Silakan coba beberapa saat lagi ya...")
        return []

    try:
        cleaned_response = clean_json_text(raw_response)
        data = json.loads(cleaned_response, strict=False)
        quiz_list = data.get("quiz", [])

        if len(quiz_list) != 5:
            return []

        for q in quiz_list:
            if "options" in q:
                q["options"] = format_latex_options(q["options"])
            if "correct_answer" in q:
                for opt in q["options"]:
                    if opt.startswith(q["correct_answer"][:2]):
                        q["correct_answer"] = opt
                        break
            if not q.get("solution_basis"):
                return []

        # Jangan kirim soal yang belum lolos verifier ke siswa.
        verified_quiz = _verify_quiz_batch(
            quiz_list,
            jenjang,
            mapel,
            stage,
        )
        return verified_quiz
    except Exception as e:
        st.error(f"Gagal memproses / memverifikasi soal: {e}")
        return []

def get_ai_hint_stream(question: str, user_attempt: str, mapel: str = "Umum"):
    """
    Menyusun prompt petunjuk dan langsung melemparnya ke generator stream.
    """
    prompt = f"""
    Kamu adalah 'RoboMANTAP', teman belajar dan asisten AI yang ramah, santai, ceria, dan sangat suportif dari MTs & MA Al Irsyad Putri Bondowoso (MANTAP).
    Gunakan gaya bahasa menyapa 'aku' dan 'kamu' yang bersahabat namun tetap edukatif.

    Mata Pelajaran: {mapel}
    Soal OMI: {question}
    Ide Pengerjaan Siswa: {user_attempt}

    Instruksi:
    - Jangan berikan salam pembuka yang berlebihan.
    - Berikan petunjuk atau bimbingan logika interaktif yang menyemangati dan memuji usaha siswa.
    - Bantu siswa menemukan celah penyelesaian soal bidang {mapel} ini secara natural, runtut, dan analitis step-by-step tanpa membocorkan jawaban akhir.
    - Gunakan format LaTeX $...$ HANYA jika terdapat notasi matematika/sains.
    """
    return stream_ai_text(
        prompt,
        max_output_tokens=STREAM_HINT_MAX_TOKENS,
        primary_model=HINT_PRIMARY_MODEL,
        fallback_model=HINT_FALLBACK_MODEL,
        thinking_level=HINT_THINKING_LEVEL,
    )

def get_ai_solution_stream(
    question: str,
    correct_answer: str,
    solution_basis: str,
    mapel: str = "Umum",
):
    """
    Pembahasan menjelaskan SOLUSI YANG SUDAH DIVERIFIKASI.
    AI tidak diberi kewenangan untuk mengganti kunci.
    """
    prompt = f"""
Kamu adalah Pembina OMI 2026 untuk tingkat Olimpiade Nasional.

Tugasmu adalah menjelaskan solusi yang SUDAH DIVERIFIKASI, bukan menyelesaikan ulang
soal dengan jawaban baru.

Bidang: {mapel}

SOAL:
{question}

KUNCI YANG SUDAH DIVERIFIKASI:
{correct_answer}

SOLUTION BASIS YANG SUDAH DIVERIFIKASI:
{solution_basis}

ATURAN MUTLAK:
- Kunci jawaban harus tetap persis: {correct_answer}
- Jangan memilih opsi lain.
- Jangan membuat metode baru yang mengubah hasil solution basis.
- Jelaskan langkah demi langkah secara pedagogis dan analitis.
- Jika ada hitungan, tampilkan rumus dan substitusinya dengan jelas.
- Jika ada unsur Bahasa Arab, terjemahkan dalam bahasa indonesia kemudian kupas secara singkat.
- Gunakan LaTeX $...$ untuk notasi matematika/sains.
- Jika menemukan ketidakkonsistenan pada solution basis, jangan mengarang; nyatakan bahwa
  solusi perlu diverifikasi ulang.
- Jangan berikan salam pembuka panjang.
"""

    return stream_ai_text(
        prompt,
        max_output_tokens=STREAM_SOLUTION_MAX_TOKENS,
        primary_model=SOLUTION_PRIMARY_MODEL,
        fallback_model=SOLUTION_FALLBACK_MODEL,
        thinking_level=SOLUTION_THINKING_LEVEL,
    )
