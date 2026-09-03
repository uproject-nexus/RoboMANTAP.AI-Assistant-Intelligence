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

# Fokus ke model paling kencang agar tidak ada jeda retry yang bikin lemot
# Model untuk pembuatan soal
QUIZ_MODELS = ("gemini-3.5-flash-lite", "gemini-2.5-flash")

# Model khusus interaksi LIVE: prioritaskan latency rendah.
STREAM_MODELS = ("gemini-3.5-flash-lite", "gemini-2.5-flash-lite")

STREAM_HINT_MAX_TOKENS = 1200
STREAM_SOLUTION_MAX_TOKENS = 2500
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
                thinking_level="minimal"
            ),
        )

    return types.GenerateContentConfig(
        max_output_tokens=max_output_tokens,
        thinking_config=types.ThinkingConfig(
            thinking_budget=0,
            include_thoughts=False,
        ),
    )


def _buffer_stream_text(source, min_chars: int = 12, flush_seconds: float = 0.04):
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
        yield "⚠️ Tidak ada koneksi yang aktif nih. Aku periksa server dulu ya.."
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
                        thinking_level="minimal"
                    )
                elif model_name == "gemini-2.5-flash":
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
    - JANGAN sertakan field `hint` atau `solution` di sini. Fokus saja merancang 5 teks soal cerita dan jawaban agar proses AI kencang.
    - Jika ada formula/notasi matematika/simbol fisika-kimia, WAJIB diapit tanda dollar '$' (Contoh: "$x^2 + 2x = 0$", "$\\tfrac{{1}}{{2}}$").
    - Semua backslash LaTeX wajib ditulis ganda '\\\\'.

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
        st.error("⚠️ Waduh kuota sedang penuh nih. Silakan coba beberapa saat lagi ya...")
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
    Gunakan gaya bahasa menyapa 'aku' dan 'kamu' yang bersahabat namun tetap edukatif.

    Mata Pelajaran: {mapel}
    Soal OMI: {question}
    Ide Pengerjaan Siswa: {user_attempt}

    Instruksi:
    - Jangan berikan salam pembuka yang berlebihan.
    - Berikan petunjuk atau bimbingan logika interaktif yang menyemangati dan memuji usaha siswa.
    - Bantu siswa menemukan celah penyelesaian soal bidang {mapel} ini secara natural tanpa membocorkan jawaban akhir.
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
    - Jika ada unsur Bahasa Arab, terjemahkan atau kupas secara singkat.
    - Jika ada hitungan, tunjukkan proses rumusnya dengan jelas.
    - WAJIB gunakan format LaTeX $...$ untuk semua notasi matematika/simbol fisika-kimia.
    """
    return stream_ai_text(prompt, max_output_tokens=STREAM_SOLUTION_MAX_TOKENS)
