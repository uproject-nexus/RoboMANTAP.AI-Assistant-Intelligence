import os
import json
import streamlit as st
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key and "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]

if not api_key:
    raise ValueError("GEMINI_API_KEY tidak ditemukan. Pastikan Secrets/file .env sudah dikonfigurasi.")

client = genai.Client(api_key=api_key)

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

@st.cache_data(ttl=3600, show_spinner=False)
def generate_quiz_batch(jenjang: str, mapel: str, stage: str, selected_submateri: list):
    """
    Menghasilkan 1 paket latihan CBT 5 soal berbasis Kisi-Kisi Operasional OMI 2026.
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
    Rancanglah 1 paket latihan CBT berisi TEPAT 5 SOAL PILIHAN GANDA yang orisinal, presisi, dan terintegrasi.

    Spesifikasi Soal OMI 2026:
    - Jenjang: {jenjang}
    - Bidang / Mata Pelajaran: {mapel}
    - Tahap Pembinaan: {stage} ({stage_description})
    - Cakupan Submateri: {submateri_text}
    - Karakteristik Soal: Mengintegrasikan konsep sains/matematika murni dengan literasi data, teknologi, lingkungan, serta nilai-nilai keislaman secara kontekstual.

    ATURAN KHUSUS FORMATTING:
    - Jika ada formula/notasi matematika/simbol fisika-kimia, WAJIB diapit tanda dollar '$' (Contoh: "$x^2 + 2x = 0$", "$\\tfrac{{1}}{{2}}$").
    - Jangan pernah menulis perintah LaTeX (seperti \\frac, \\sqrt) tanpa diapit '$'.

    Format keluaran WAJIB berupa objek JSON murni:
    {{
        "quiz": [
            {{
                "id": 1,
                "question": "Teks soal 1 lengkap dengan konteks OMI 2026",
                "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
                "correct_answer": "Pilihan jawaban tepat (harus persis sama dengan salah satu opsi di atas)",
                "hint": "Petunjuk logika awal RoboMANTAP tanpa membocorkan jawaban akhir",
                "solution": "Pembahasan runtut dan analitis step-by-step"
            }}
        ]
    }}
    """

    try:
        # Menggunakan model resmi Google API (gemini-2.5-flash)
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=system_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        data = json.loads(response.text)
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
        st.error("Terjadi kendala saat menghubungkan AI Engine. Silakan klik tombol sekali lagi.")
        return []

def get_ai_hint(question: str, user_attempt: str, mapel: str = "Matematika"):
    prompt = f"""
    Kamu adalah 'RoboMANTAP', teman belajar dan asisten AI yang ramah, santai, ceria, dan sangat suportif dari MTs & MA Al Irsyad Putri Bondowoso (MANTAP).
    Gunakan gaya bahasa menyapa 'aku' dan 'kamu' yang bersahabat namun tetap edukatif.

    Mata Pelajaran: {mapel}
    Soal OMI: {question}
    Ide Pengerjaan Siswa: {user_attempt}

    Berikan petunjuk atau bimbingan logika interaktif yang menyemangati, memuji usahanya, dan membantu siswa menemukan celah penyelesaian soal {mapel} ini tanpa membocorkan jawaban akhir.
    Ingat: Fokus pembimbingan tetap pada materi {mapel}, meskipun soal menggunakan konteks cerita integrasi.
    Gunakan format LaTeX $...$ untuk setiap notasi matematika atau sains.
    """
    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )
        return response.text
    except Exception:
        return "Yuk perhatikan lagi rumus dan petunjuk pada soal ini! Coba periksa kembali langkah perhitunganmu ya."
