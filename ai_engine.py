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

MODELS_TO_TRY = ["gemini-3.6-flash", "gemini-2.5-flash","gemini-1.5-flash" ]

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
    
    # Hapus pemungkus markdown ```json ... ``` jika ada
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?```$", "", text)

    # Ubah backslash tunggal LaTeX (seperti \sqrt, \frac, \alpha, \{, \}) menjadi double backslash \\
    text = re.sub(r'(?<!\\)\\([a-zA-Z\{\}\!\,;:_%\$\&\+\-\=])', r'\\\\\1', text)
    return text

def call_gemini_with_rotation(prompt: str, is_json: bool = False):
    """
    Memanggil API Gemini dengan perputaran otomatis API Key dan Model ID.
    """
    for key in api_keys:
        try:
            # Tambahkan http_options dengan timeout 15000 ms (15 detik)
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

def clean_display_text(text: str) -> str:
    if not text:
        return text
    # 1. Ubah semua variasi \n berlapis (\\n, \\\n, dll) jadi newline nyata
    text = re.sub(r'\\+n', '\n', text)
    # 2. Hapus backslash liar yang menggantung di akhir/awal baris (\n\ atau \\\n)
    text = re.sub(r'\n\\+', '\n', text)
    text = re.sub(r'\\+\n', '\n', text)
    return text

@st.cache_data(ttl=600, show_spinner=False)
def generate_quiz_batch(jenjang: str, mapel: str, stage: str, selected_submateri: list):
    """
    Menghasilkan 1 paket latihan CBT 3 soal berbasis Kisi-Kisi Operasional OMI 2026.
    """
    submateri_text = ", ".join(selected_submateri) if selected_submateri else "Semua Submateri Terintegrasi"

    stage_descriptions = {
        "Internal": "Internal: Fokus pada diagnostik, pemetaan bidang, dan penguatan konsep dasar.",
        "Kab/Kota": "Kab/Kota: Fokus pada 25 pilihan ganda terstandar CBT, HOTS, dan analisis data.",
        "Provinsi": "Provinsi: Fokus pada analisis lintas konsep, pilihan ganda kompleks, serta keterkaitan sains, teknologi, dan nilai keislaman.",
        "Nasional": "Nasional: Fokus pada tingkat lanjutan (High-Level HOTS), eksplorasi problem solving, analisis eksperimen, dan penalaran ilmiah mendalam."
    }
    stage_description = stage_descriptions.get(stage, "Fokus pada penguatan konsep OMI.")

    system_prompt = f"""
    Anda adalah Pelatih Utama Bina Prestasi OMI 2026 (Olimpiade Sains & Matematika Al Irsyad) untuk tingkat {jenjang}.
    Rancanglah 1 paket latihan CBT berisi TEPAT 3 SOAL PILIHAN GANDA yang orisinal, presisi, dan tematik OMI.
    
    Spesifikasi Soal OMI 2026:
    - Jenjang: {jenjang}
    - Bidang / Mata Pelajaran: {mapel}
    - Tahap Pembinaan: {stage} ({stage_description})
    - Cakupan Submateri: {submateri_text}
    
    INTEGRASI TEMATIK OMI:
    - Integrasikan materi dengan tema Lingkungan, Teknologi, atau Nilai Keislaman.
    - Penggunaan istilah Bahasa Arab bersifat opsional/secara alami jika relevan (Gunakan Bahasa Arab standar TANPA harakat berlebihan agar pemrosesan cepat).
    
    ATURAN KECEPATAN & FORMATTING:
    - Teks soal padat, efektif, dan langsung pada inti masalah.
    - Pembahasan (solution) MAKSIMAL 2-3 kalimat ringkas (langsung ke rumus atau langkah kunci).
    - Jika ada formula/notasi matematika/simbol fisika-kimia, WAJIB diapit tanda dollar '$'.
    - PENTING: Semua backslash LaTeX dalam JSON wajib ditulis ganda '\\\\' agar format JSON valid.
    
    Format keluaran WAJIB berupa objek JSON murni:
    {{
      "quiz": [
        {{
          "id": 1,
          "question": "Teks soal 1 singkat & padat",
          "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
          "correct_answer": "Pilihan jawaban tepat",
          "solution": "Pembahasan singkat 2-3 kalimat."
        }}
      ]
    }}
    """



    raw_response = call_gemini_with_rotation(system_prompt, is_json=True)

    if not raw_response:
        st.error("⚠️ Kuota sedang penuh nih. Silakan coba beberapa saat lagi ya!")
        return []

    try:
        cleaned_response = clean_json_text(raw_response)
        data = json.loads(cleaned_response)
        quiz_list = data.get("quiz", [])
        for q in quiz_list:
            # 1. Bersihkan Teks Soal
            if "question" in q:
                q["question"] = clean_display_text(q["question"])    
            # 2. Bersihkan Pembahasan (INI YANG BIKIN EROR DI GAMBAR)
            if "solution" in q:
                q["solution"] = clean_display_text(q["solution"])

            # 3. Bersihkan Opsi Jawaban
            if "options" in q:
                cleaned_opts = []
                for opt in q["options"]:
                    clean_opt = clean_display_text(opt.replace("\\'", "").replace("'", ""))
                    cleaned_opts.append(clean_opt)
                q["options"] = format_latex_options(cleaned_opts)
            
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
Kamu adalah 'RoboMANTAP', asisten AI suportif dari MTs & MA Al Irsyad Putri Bondowoso.

Soal {mapel}: {question}
Ide Siswa: {user_attempt}

ATURAN KECEPATAN & RESPON:
- Berikan petunjuk/bimbingan logika singkat MAKSIMAL 2-3 KALIMAT padat (maks 40 kata).
- Langsung ke inti celah penyelesaian tanpa pembuka/basa-basi berlebihan.
- Dilarang membocorkan jawaban akhir atau pilihan opsi yang benar.
- Gunakan format LaTeX $...$ hanya jika ada rumus matematika/sains.
"""

    hint_text = call_gemini_with_rotation(prompt, is_json=False)
    if hint_text:
        return clean_display_text(hint_text)
    return "Maaf, RoboMANTAP belum bisa memberikan petunjuk saat ini. Coba periksa kembali logika pengerjaanmu!"
