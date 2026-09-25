"""Gemini calls owned by CBT OMI.

This module deliberately keeps OMI generation/hint/solution separate from the
teacher Quiz Custom AI path. Both still use the shared Gemini transport and key
rotation in ``infrastructure.ai.service``.
"""
from __future__ import annotations

import json

from infrastructure.ai.policy import (
    _is_arabic_subject,
    _is_religious_subject,
    _split_option_label,
    build_language_guidance,
    format_latex_options,
    normalize_quiz_options,
    option_labels_for_jenjang,
)
from infrastructure.ai.service import call_gemini_with_rotation, clean_json_text, stream_ai_text
from config.settings import STREAM_HINT_MAX_TOKENS, STREAM_SOLUTION_MAX_TOKENS


def generate_omi_quiz_batch(jenjang: str, mapel: str, stage: str, selected_submateri: list[str] | None):
    """Generate exactly 10 OMI questions using the existing OMI contract."""
    selected_submateri = list(selected_submateri or [])
    submateri_text = ", ".join(selected_submateri) if selected_submateri else "Semua Submateri Terintegrasi"
    option_labels = option_labels_for_jenjang(jenjang)
    option_count = len(option_labels)
    language_guidance = build_language_guidance(mapel, "", "OMI / Olimpiade")

    stage_descriptions = {
        "Internal": "Internal: Fokus pada diagnostik, pemetaan bidang, dan penguatan konsep dasar.",
        "Kab/Kota": "Kab/Kota: Fokus pada pilihan ganda terstandar CBT, HOTS, dan analisis data.",
        "Provinsi": "Provinsi: Fokus pada analisis lintas konsep, pilihan ganda kompleks, serta keterkaitan sains, teknologi, dan nilai keislaman.",
        "Nasional": "Nasional: Fokus pada tingkat lanjutan (High-Level HOTS), eksplorasi problem solving, analisis eksperimen, dan penalaran ilmiah mendalam.",
    }
    stage_description = stage_descriptions.get(stage, "Fokus pada penguatan konsep OMI.")

    if _is_arabic_subject(mapel):
        arabic_distribution = "Semua soal dapat menggunakan Bahasa Arab Fusha yang natural; jangan membatasi jumlah soal berbahasa Arab."
    elif _is_religious_subject(mapel):
        arabic_distribution = "Gunakan istilah/kutipan Arab asli hanya pada bagian yang memang berkaitan dengan materi keagamaan dan didukung sumber/konsep."
    else:
        arabic_distribution = "Bahasa utama tetap Bahasa Indonesia; Bahasa Arab hanya untuk istilah yang relevan."

    system_prompt = f"""
Anda adalah Pelatih Utama Bina Prestasi OMI 2026 (Olimpiade Sains & Matematika Al Irsyad) untuk tingkat {jenjang}.
Rancang 1 paket latihan CBT berisi TEPAT 10 SOAL PILIHAN GANDA yang orisinal, presisi, dan tematik OMI.

Spesifikasi:
- Jenjang: {jenjang}
- Bidang / Mata Pelajaran: {mapel}
- Tahap Pembinaan: {stage} ({stage_description})
- Cakupan Submateri: {submateri_text}
- Jumlah opsi WAJIB: {option_count} opsi, dengan label {', '.join(option_labels)}.

INTEGRASI TEMATIK & BAHASA MADRASAH:
- Konteks boleh mengaitkan Lingkungan, Teknologi, Kehidupan Sehari-hari, atau Nilai-Nilai Keislaman bila relevan.
- {language_guidance}
- {arabic_distribution}
- Jangan menggunakan transliterasi Latin untuk istilah Arab yang memang harus ditulis dalam aksara Arab.

ATURAN FORMATTING:
- Jangan sertakan field hint atau solution di sini.
- Angka biasa, nominal uang, satuan, dan jam ditulis sebagai teks biasa tanpa backslash.
- LaTeX $...$ hanya untuk rumus matematika asli, pecahan, akar, dan variabel.
- Jangan menaruh kalimat bahasa Indonesia di dalam delimiter matematika.
- Jangan membuat perintah LaTeX ilegal seperti '\\60.000.000' atau '\\14'.

Format keluaran JSON murni:
{{
  "quiz": [
    {{
      "id": 1,
      "question": "...",
      "options": ["{option_labels[0]}. ...", "{option_labels[1]}. ...", "{option_labels[2]}. ...", "{option_labels[3]}. ..."{', "' + option_labels[4] + '. ..."' if option_count == 5 else ''}],
      "correct_answer": "{option_labels[0]}. ..."
    }}
  ]
}}
"""

    raw_response = call_gemini_with_rotation(system_prompt, is_json=True)
    if not raw_response:
        print("[OMI AI] Gemini tidak mengembalikan paket soal.")
        return []

    try:
        cleaned_response = clean_json_text(raw_response)
        data = json.loads(cleaned_response, strict=False)
        quiz_list = data.get("quiz", [])
        if not isinstance(quiz_list, list) or len(quiz_list) != 10:
            print(f"[OMI AI] Paket tidak berisi tepat 10 soal: {len(quiz_list) if isinstance(quiz_list, list) else 'invalid'}")
            return []

        normalized = []
        for idx, q in enumerate(quiz_list, start=1):
            if not isinstance(q, dict):
                return []
            question = str(q.get("question", "")).strip()
            options = q.get("options", [])
            if not question or not isinstance(options, list):
                return []
            norm_options, _ = normalize_quiz_options(options, jenjang)
            if len(norm_options) != option_count:
                return []
            answer = str(q.get("correct_answer", "")).strip()
            answer_label, _ = _split_option_label(answer, 0)
            answer_match = next((opt for opt in norm_options if opt.startswith(f"{answer_label}.")), None)
            if answer_match is None:
                answer_match = next((opt for opt in norm_options if opt == answer), None)
            if answer_match is None:
                return []
            normalized.append({
                "id": idx,
                "question": question,
                "options": format_latex_options(norm_options),
                "correct_answer": answer_match,
            })
        return normalized
    except Exception as exc:
        print(f"[OMI AI] Gagal memproses JSON soal: {exc}")
        return []


def get_omi_hint_stream(question: str, user_attempt: str, mapel: str = "Umum"):
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


def get_omi_solution_stream(question: str, correct_answer: str, mapel: str = "Umum"):
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
