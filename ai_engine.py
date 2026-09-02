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

MODELS_TO_TRY = ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-1.5-flash"]

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
    Membersihkan string JSON dari balikan AI yang mengandung notasi LaTeX
    agar tidak menyebabkan error 'Invalid \\escape' saat json.loads().
    """
    if not text:
        return ""
    
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    # PERBAIKAN UTAMA: Ubah SEMUA backslash LaTeX (\rho, \frac, \(, \], dll) menjadi \\
    # KECUALI backslash bawaan quote JSON (\") dan backslash ganda (\\)
    text = re.sub(r'\\(?!["\\])', r'\\\\', text)
    return text

def call_gemini_with_rotation(prompt: str, is_json: bool = False):
    """
    Memanggil API Gemini dengan perputaran otomatis API Key dan Model ID.
    """
    for key in api_keys:
        try:
            # Timeout 15 detik untuk mencegah koneksi diputus Streamlit
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

def generate_quiz_batch(jenjang: str, mapel: str, stage: str, selected_submateri: list):
    """
    Menghasilkan 1 paket latihan CBT 3 soal berbasis Kisi-Kisi Operasional OMI 2026.
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
Rancanglah 1 paket latihan CBT berisi TEPAT 3 SOAL PILIHAN GANDA yang orisinal, presisi, dan terintegrasi.

Spesifikasi Soal OMI 2026:
- Jenjang: {jenjang}
- Bidang / Mata Pelajaran: {mapel}
- Tahap Pembinaan: {stage} ({stage_description})
- Cakupan Submateri: {submateri_text}
- Karakteristik Soal: Mengintegrasikan konsep sains/matematika murni dengan literasi data, teknologi, lingkungan, serta nilai-nilai keislaman secara kontekstual. Penggunaan istilah/karakter Bahasa Arab dilakukan TANPA harakat berlebihan agar pemrosesan cepat.

ATURAN KECEPATAN & FORMATTING:
- Teks soal padat, efektif, langsung pada inti masalah (MAKSIMAL 30 kata per soal).
- Pembahasan (solution) MAKSIMAL 35 kata atau 2-3 kalimat ringkas (langsung ke rumus utama/langkah kunci).
- Setiap opsi jawaban (options) dibuat singkat dan padat (MAKSIMAL 7 kata per opsi).
- Jika ada formula/notasi matematika/simbol fisika-kimia, WAJIB diapit tanda dollar '$' (Contoh: "$x^2 + 2x = 0$", "$\\tfrac{{1}}{{2}}$").
- PENTING: Semua backslash LaTeX dalam JSON wajib ditulis ganda '\\\\' agar format JSON valid.

Format keluaran WAJIB berupa objek JSON murni:
{{
    "quiz": [
        {{
            "id": 1,
            "question": "Teks soal 1 lengkap dengan konteks OMI 2026",
            "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
            "correct_answer": "Pilihan jawaban tepat (harus persis sama dengan salah satu opsi di atas)",
            "hint": "Petunjuk logika awal RoboMANTAP tanpa membocorkan jawaban akhir",
            "solution": "Pembahasan singkat 2-3 kalimat."
        }}
    ]
}}
"""

    raw_response = call_gemini_with_rotation(system_prompt, is_json=True)

    if not raw_response:
        st.error("⚠️ Semua kuota cadangan API sedang penuh. Silakan coba beberapa saat lagi.")
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
        st.error(f"Gagal memproses format soal: {e}")
        return []

@st.cache_data(ttl=600, show_spinner=False)
def get_ai_hint(question: str, user_attempt: str, mapel: str = "Umum"):
    prompt = f"""
Kamu adalah 'RoboMANTAP', teman belajar dan asisten AI yang ramah, santai, ceria, dan sangat suportif dari MTs & MA Al Irsyad Putri Bondowoso (MANTAP).

Mata Pelajaran: {mapel}
Soal OMI: {question}
Ide Siswa: {user_attempt}

ATURAN KECEPATAN & RESPON:
- Berikan petunjuk/bimbingan logika singkat MAKSIMAL 2-3 KALIMAT padat (maks 40 kata).
- Langsung ke inti celah penyelesaian tanpa pembuka/basa-basi berlebihan.
- Dilarang membocorkan jawaban akhir atau pilihan opsi yang benar.
- Gunakan format LaTeX $...$ HANYA jika terdapat notasi matematika/sains pada penjelasan.
"""
    
    hint_text = call_gemini_with_rotation(prompt, is_json=False)
    if hint_text:
        return hint_text

    return "Yuk perhatikan lagi konsep dasar dan petunjuk pada soal ini! Coba periksa kembali langkah analisis atau pemahaman kamu ya."
