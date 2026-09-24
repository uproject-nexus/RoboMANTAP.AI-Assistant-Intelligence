"""AI quiz generation services.

The generation logic is copied from the audited engine first; later stages can split
these responsibilities further without changing the generation contract.
"""
from __future__ import annotations
import json, re
from infrastructure.ai.service import call_gemini_with_rotation, clean_json_text, show_error, stream_ai_text
from infrastructure.ai.policy import *
from config.settings import STREAM_HINT_MAX_TOKENS, STREAM_SOLUTION_MAX_TOKENS
def generate_quiz_batch(jenjang: str, mapel: str, stage: str, selected_submateri: list):
    submateri_text = ", ".join(selected_submateri) if selected_submateri else "Semua Submateri Terintegrasi"
    option_labels = option_labels_for_jenjang(jenjang)
    option_count = len(option_labels)
    language_guidance = build_language_guidance(mapel, "", "OMI / Olimpiade")

    stage_descriptions = {
        "Internal": "Internal: Fokus pada diagnostik, pemetaan bidang, dan penguatan konsep dasar.",
        "Kab/Kota": "Kab/Kota: Fokus pada pilihan ganda terstandar CBT, HOTS, dan analisis data.",
        "Provinsi": "Provinsi: Fokus pada analisis lintas konsep, pilihan ganda kompleks, serta keterkaitan sains, teknologi, dan nilai keislaman.",
        "Nasional": "Nasional: Fokus pada tingkat lanjutan (High-Level HOTS), eksplorasi problem solving, analisis eksperimen, dan penalaran ilmiah mendalam."
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
      "options": ["{option_labels[0]}. ...", "{option_labels[1]}. ...", "{option_labels[2]}. ...", "{option_labels[3]}. ..."{', "' + option_labels[4] + '. ...' if option_count == 5 else ''}],
      "correct_answer": "{option_labels[0]}. ..."
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
        if not isinstance(quiz_list, list) or len(quiz_list) != 10:
            return []
        normalized = []
        for idx, q in enumerate(quiz_list, start=1):
            options = q.get("options", []) if isinstance(q, dict) else []
            norm_options, _ = normalize_quiz_options(options, jenjang)
            if len(norm_options) != option_count:
                return []
            answer = str(q.get("correct_answer", "")).strip()
            answer_label, answer_body = _split_option_label(answer, 0)
            answer_match = next((opt for opt in norm_options if opt.startswith(f"{answer_label}.")), None)
            if answer_match is None:
                answer_match = next((opt for opt in norm_options if opt == answer), "")
            if not answer_match:
                return []
            normalized.append({
                "id": idx,
                "question": str(q.get("question", "")).strip(),
                "options": format_latex_options(norm_options),
                "correct_answer": answer_match,
            })
        return normalized
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
    source_pack: dict | None = None,
):
    option_labels = option_labels_for_jenjang(jenjang)
    option_count = len(option_labels)
    source_context = _source_context_for_prompt(source_pack, 90000)
    language_guidance = build_language_guidance(mapel, bahasa, konteks, source_pack)
    option_example = ', '.join([f'"{label}. ..."' for label in option_labels])
    prompt = f"""
Anda adalah Question Architect RoboMANTAP untuk guru madrasah.
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

KEBIJAKAN OPSI WAJIB:
- {jenjang}: tepat {option_count} pilihan jawaban.
- Label wajib: {', '.join(option_labels)}.
- MTs = A-D (4 pilihan).
- MA = A-E (5 pilihan).
- Jangan pernah menghasilkan opsi tambahan di luar label yang ditentukan.
- Hanya satu opsi benar.

KEBIJAKAN BAHASA:
{language_guidance}

SUMBER MATERI TERLAMPIR / SOURCE GROUNDING:
{source_context}

ATURAN KUALITAS:
0. Bila sumber materi terlampir tersedia, jadikan sumber tersebut sebagai sumber fakta utama. Jangan mengarang fakta inti di luar sumber.
1. Tepat {jumlah_soal} soal, jangan kurang dan jangan lebih.
2. Setiap soal memiliki tepat {option_count} opsi: {', '.join(option_labels)}.
3. Hanya satu opsi yang benar.
4. correct_answer harus persis sama dengan salah satu opsi lengkap.
5. Hindari ambiguitas, data yang kurang, dan asumsi yang tidak disebutkan.
6. Untuk soal numerik, solution_basis harus memuat proses hitungan inti dan hasil akhir.
7. Untuk HOTS/olimpiade, gunakan penalaran yang benar-benar relevan dengan level.
8. Jangan memasukkan jawaban atau pembahasan yang saling bertentangan.
9. Jika menggunakan LaTeX, gunakan $...$ dan escape backslash secara valid untuk JSON.
10. Jangan menambahkan markdown atau teks pembuka di luar JSON.
11. Untuk matriks/array, gunakan blok $$...$$ dan jangan menulis environment matriks tanpa delimiter.
12. Hindari transliterasi Latin untuk kosakata Arab yang memang harus ditulis dalam aksara Arab.
13. Untuk Bahasa Arab, gunakan Bahasa Arab Fusha/Modern Standard Arabic yang natural, dengan harakat selektif jika membantu kejelasan. Jangan membuat kutipan agama yang tidak didukung sumber.

OUTPUT JSON MURNI:
{{
  "quiz": [
    {{
      "id": 1,
      "question": "...",
      "options": [{option_example}],
      "correct_answer": "{option_labels[0]}. ...",
      "solution_basis": "..."
    }}
  ],
  "config": {{"duration_seconds": {timer_seconds}}}
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
    for idx, item in enumerate(quiz, start=1):
        if not isinstance(item, dict):
            return []
        question = str(item.get("question", "")).strip()
        raw_options = item.get("options", [])
        answer = str(item.get("correct_answer", "")).strip()
        solution_basis = str(item.get("solution_basis", "")).strip()
        if not question or not isinstance(raw_options, list) or not solution_basis:
            return []

        options, _ = normalize_quiz_options(raw_options, jenjang)
        # Beri kesempatan validator memperbaiki draft yang jumlah opsinya belum tepat.
        if len(options) not in (option_count, 4, 5):
            return []
        answer_label, _ = _split_option_label(answer, 0)
        answer_match = next((x for x in options if x.startswith(f"{answer_label}.")), None)
        if answer_match is None and answer in options:
            answer_match = answer
        if answer_match is None:
            return []
        normalized.append({
            "id": idx,
            "question": question,
            "options": format_latex_options(options),
            "correct_answer": answer_match,
            "solution_basis": solution_basis,
            "source_locator": str(item.get("source_locator", "")).strip(),
        })

    validation_config = {
        "mapel": mapel,
        "jenjang": jenjang,
        "kelas": kelas,
        "materi": materi,
        "submateri": submateri,
        "kesulitan": kesulitan,
        "tipe_soal": tipe_soal,
        "bahasa": bahasa,
        "konteks": konteks,
        "option_count": option_count,
        "option_labels": option_labels,
    }
    validated = validate_and_repair_quiz(normalized, source_pack, validation_config)

    final_items = []
    for idx, item in enumerate(validated, start=1):
        if not isinstance(item, dict):
            continue
        opts, _ = normalize_quiz_options(item.get("options", []), jenjang)
        if len(opts) != option_count:
            continue
        opts = format_latex_options(opts)
        ans = str(item.get("correct_answer", "")).strip()
        ans_label, _ = _split_option_label(ans, 0)
        matching = next((x for x in opts if x.startswith(f"{ans_label}.")), None)
        if matching is None:
            exact = next((x for x in opts if x == ans), None)
            matching = exact
        if matching is None:
            continue
        final_items.append({
            "id": idx,
            "question": str(item.get("question", "")).strip(),
            "options": opts,
            "correct_answer": matching,
            "solution_basis": str(item.get("solution_basis", "")).strip(),
            "source_locator": str(item.get("source_locator", "")).strip(),
        })

    if len(final_items) == jumlah_soal:
        return final_items
    # Hanya boleh fallback ke raw draft jika raw draft sudah memenuhi aturan jenjang secara utuh.
    if all(len(x.get("options", [])) == option_count for x in normalized):
        return normalized
    return []
