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
MODELS_TO_TRY = ["gemini-3.6-flash", "gemini-2.5-flash"]

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
    Memanggil API Gemini untuk format teks/JSON biasa.
    """
    for key in api_keys:
        try:
            # Ditambahkan timeout agar tidak hanging saat koneksi lelet
            client = genai.Client(api_key=key)
            for model_name in MODELS_TO_TRY:
                try:
                    config = types.GenerateContentConfig(response_mime_type="application/json") if is_json else None
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=config
                    )
                    if response.text:
                        return response.text
                except Exception:
                    continue
        except Exception:
            continue
    return None

def stream_ai_text(prompt: str):
    """
    Fitur baru untuk Streaming API.
    Menghasilkan teks (typing effect) kata demi kata secara real-time.
    """
    for key in api_keys:
        try:
            client = genai.Client(api_key=key)
            for model_name in MODELS_TO_TRY:
                try:
                    response = client.models.generate_content_stream(
                        model=model_name,
                        contents=prompt
                    )
                    for chunk in response:
                        if chunk.text:
                            yield chunk.text
                    return  # Sukses stream, keluar dari fungsi
                except Exception:
                    continue
        except Exception:
            continue
    
    yield "⚠️ Maaf, koneksi API sedang penuh atau terputus. Silakan coba klik kembali."

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
2. Variasi Bahasa Arab & Indonesia:
   - Jika submateri berisi "Semua Submateri" (ALL) atau secara acak: UTAMAKAN karakteristik khusus OMI! Buat variasi campuran acak:
     * Variasi 1: Teks Soal ditulis dalam BAHASA ARAB (fasih & ber-harakat/standar), sedangkan Pilihan Jawaban (A, B, C, D) dalam BAHASA INDONESIA.
     * Variasi 2: Teks Soal dalam BAHASA INDONESIA, tetapi Pilihan Jawaban (A, B, C, D) / Istilah Kunci ditulis dalam BAHASA ARAB.
     * Variasi 3: Soal Tematik OMI Standar (Full Bahasa Indonesia berkonteks Keislaman/Lingkungan/Teknologi).

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
        st.error("⚠️ Waduh kuota sedang penuh nih. Coba Klik lagi ya...")
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
- Berikan petunjuk atau bimbingan logika interaktif yang menyemangati dan memuji usaha siswa.
- Bantu siswa menemukan celah penyelesaian soal bidang {mapel} ini secara natural tanpa membocorkan jawaban akhir.
- Gunakan format LaTeX $...$ HANYA jika terdapat notasi matematika/sains.
"""
    return stream_ai_text(prompt)

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
- Jelaskan secara natural, tajam, dan edukatif mengapa jawaban tersebut benar.
- Jika ada unsur Bahasa Arab, terjemahkan atau kupas secara singkat.
- Jika ada hitungan, tunjukkan proses rumusnya dengan jelas.
- WAJIB gunakan format LaTeX $...$ untuk semua notasi matematika/simbol fisika-kimia.
"""
    return stream_ai_text(prompt)
