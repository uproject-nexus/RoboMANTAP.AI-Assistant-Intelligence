from __future__ import annotations

import re
from typing import Any


def detect_subject_context(mapel: str) -> dict[str, Any]:
    """
    Mendeteksi karakteristik mata uji untuk menentukan:
    - Bahasa pengantar utama (Indonesia, Inggris, Arab, Jepang, Mandarin, dll)
    - Opsi respons Kategori bawaan (True/False vs Benar/Salah)
    - Apakah fitur LaTeX ($...$) aktif atau non-aktif (hanya untuk eksak)
    """
    m = str(mapel or "").strip().lower()

    # 1. Deteksi Bahasa Inggris
    if any(kw in m for kw in ["inggris", "english", "toefl", "toeic", "ielts"]):
        return {
            "lang_code": "en",
            "lang_name": "English",
            "instruction_lang": "English",
            "category_options": ["True", "False"],
            "use_latex": False,
            "rules": (
                "CRITICAL LANGUAGE RULE: The entire question text, stimulus, options, "
                "category statements, category options (e.g. True/False, Yes/No), and solution_basis "
                "MUST be written 100% in ENGLISH. Do NOT mix with Indonesian words."
            ),
        }

    # 2. Deteksi Bahasa Arab
    if any(kw in m for kw in ["arab", "arabic", "nahwu", "shorof"]):
        return {
            "lang_code": "ar",
            "lang_name": "Arabic",
            "instruction_lang": "Arabic",
            "category_options": ["صحيح", "خطأ"],
            "use_latex": False,
            "rules": (
                "CRITICAL LANGUAGE RULE: The entire question text, stimulus, options, "
                "category statements, and solution_basis MUST be written 100% in ARABIC."
            ),
        }

    # 3. Deteksi Bahasa Asing Lain (Jepang, Mandarin, Jerman, Prancis)
    if any(kw in m for kw in ["jepang", "japanese", "mandarin", "chinese", "jerman", "german", "prancis", "french"]):
        return {
            "lang_code": "foreign",
            "lang_name": mapel.title(),
            "instruction_lang": mapel.title(),
            "category_options": ["True", "False"],
            "use_latex": False,
            "rules": f"CRITICAL LANGUAGE RULE: The questions and choices MUST be written in {mapel.title()}.",
        }

    # 4. Deteksi Mata Uji Eksak/Sains (Matematika, Fisika, Kimia)
    is_exact = any(kw in m for kw in [
        "matematika", "math", "fisika", "physics", "kimia", "chemistry",
        "sains", "ipa", "numerasi", "kalkulus", "statistika"
    ])

    return {
        "lang_code": "id",
        "lang_name": "Bahasa Indonesia",
        "instruction_lang": "Bahasa Indonesia",
        "category_options": ["Benar", "Salah"],
        "use_latex": is_exact,
        "rules": (
            "Gunakan Bahasa Indonesia baku, jelas, dan komunikatif. "
            + ("Gunakan notasi LaTeX $...$ HANYA untuk persamaan/rumus matematika." if is_exact else "DILARANG keras menggunakan notasi LaTeX $...$ atau tag \\text{...} pada teks biasa.")
        ),
    }


def build_tka_prompt(
    *,
    jenjang: str,
    mapel: str,
    question_type: str,
    count: int,
    image_count: int,
    image_ids: list[str] | None = None,
    option_labels: tuple[str, ...],
    path_type: str = "GURU",  # 'GURU' atau 'MANDIRI'
) -> str:
    """
    Membangun prompt terstruktur untuk Gemini API.
    Memisahkan spesifikasi jalur GURU dan MANDIRI.
    """
    ctx = detect_subject_context(mapel)
    labels_str = ", ".join(option_labels)
    img_ids_formatted = ", ".join(str(x) for x in (image_ids or [])) or "(tidak ada)"

    # Aturan khusus berdasarkan jalur
    path_instruction = ""
    if path_type.upper() == "MANDIRI":
        path_instruction = """
JALUR: LATIHAN MANDIRI SISWA
- Buat soal dengan variasi tipe dan kasus konteks kehidupan nyata (literasi/numerasi).
- Pastikan tingkat kesulitan adaptif dari sedang hingga HOTS tinggi (C4-C6).
"""
    else:
        path_instruction = """
JALUR: TKA STUDIO / CUSTOM GURU
- Buat paket soal terstandar kurikulum untuk ujian resmi madrasah/sekolah.
- Setiap butir wajib terstruktur secara ketat mengikuti kurikulum TKA 2026.
"""

    # Aturan Format Tipe Soal
    qtype = question_type.upper()
    if qtype == "PG":
        type_rules = f"""
BENTUK: PILIHAN GANDA (PG)
- Tepat 1 jawaban benar.
- options wajib tepat {len(option_labels)} pilihan dengan label {labels_str}.
- correct_answer adalah SATU label huruf (misal: "B").
"""
        schema = f'''"options": ["{option_labels[0]}. ...", "{option_labels[1]}. ..."],
      "correct_answer": "B",
      "correct_answers": []'''

    elif qtype == "MCMA":
        type_rules = f"""
BENTUK: PILIHAN GANDA KOMPLEKS (MCMA)
- Tepat {len(option_labels)} pilihan tersedia dengan label {labels_str}.
- DUA ATAU LEBIH jawaban harus benar (jangan hanya satu).
- correct_answers berisi 2 atau lebih LABEL huruf unik dan WAJIB URUT ALFABETIS (misal: ["A", "C"]).
- correct_answer diisi sama dengan correct_answers.
"""
        schema = f'''"options": ["{option_labels[0]}. ...", "{option_labels[1]}. ..."],
      "correct_answer": ["A", "C"],
      "correct_answers": ["A", "C"]'''

    elif qtype == "KATEGORI":
        cat_opt1 = ctx["category_options"][0]
        cat_opt2 = ctx["category_options"][1]
        type_rules = f"""
BENTUK: PILIHAN GANDA KOMPLEKS (KATEGORI)
- Buat 3-5 pernyataan yang berkaitan dengan stimulus.
- Setiap pernyataan wajib memiliki pilihan respons dalam bahasa yang sesuai dengan mata uji: {ctx["category_options"]}.
- DILARANG menggunakan kata "Benar/Salah" jika mata uji adalah Bahasa Inggris (Gunakan "True/False" atau "Yes/No").
"""
        schema = f'''"options": [],
      "correct_answer": ["{cat_opt1}", "{cat_opt2}", "{cat_opt1}"],
      "correct_answers": ["{cat_opt1}", "{cat_opt2}", "{cat_opt1}"],
      "category_items": [
        {{
          "statement": "...",
          "options": {ctx["category_options"]},
          "correct_response": "{cat_opt1}"
        }}
      ]'''

    else:  # MIXED
        type_rules = f"""
BENTUK: CAMPURAN (MIXED)
- Gunakan variasi tipe PG, MCMA, dan KATEGORI.
- Terapkan aturan bahasa dan kategori yang sesuai dengan mata uji {mapel}.
"""
        schema = '''"options": [], "correct_answer": [], "correct_answers": [], "category_items": []'''

    # Aturan penggunaan LaTeX
    latex_rule = (
        "FORMAT MATEMATIKA: Gunakan $...$ hanya untuk rumus/akar/pecahan matematika."
        if ctx["use_latex"]
        else "DILARANG KERAS MENGGUNAKAN SINTAKS LATEX ($...$ ATAU \\text{...}). Tulis seluruh kata dan simbol secara teks biasa."
    )

    return f'''
Anda adalah Question Architect TKA RoboMANTAP untuk jenjang {jenjang}, Mata Uji: {mapel}.
Bahasa Pengantar Utama: {ctx["lang_name"]}.
{ctx["rules"]}

{path_instruction}

ATURAN ALOKASI STIMULUS & GAMBAR (WAJIB):
1. Dalam batch {count} soal ini, WAJIB minimal 1-2 soal berstatus "TEKS POLOS TANPA GAMBAR" (`image_id`: null, `image_ids`: []).
2. Jika soal TIDAK menggunakan gambar: isi `"image_id": null` dan `"image_ids": []`.
3. Jika soal HANYA menanyakan 1 gambar (misal "Gambar 1" / "Image 1"): isi `"image_id": "ID_GAMBAR_1"` dan `"image_ids": [{{"id": "ID_GAMBAR_1", "no": 1}}].
4. Jika soal MEMBANDINGKAN 2 atau lebih gambar ("Comparing Image 1 and 2" / "Membandingkan Gambar 1 dan 2"): cantumkan seluruh ID gambar di array `"image_ids"`.

STANDAR KUALITAS & PEMBAHASAN:
- LEVEL KOGNITIF: Hanya buat soal level C4 (Analisis), C5 (Evaluasi), atau C6 (Solusi).
- PEMBAHASAN BERSIH (`solution_basis`): Wajib berupa langkah penyelesaian final yang bersih tanpa kalimat trial-and-error/self-correction.
- {latex_rule}

{type_rules}

ID Gambar yang tersedia:
{img_ids_formatted}

OUTPUT JSON MURNI:
{{
  "questions": [
    {{
      "id": 1,
      "question_type": "{qtype}",
      "question": "...",
      {schema},
      "stimulus_text": "...",
      "stimulus_group": null,
      "image_id": null,
      "image_ids": [],
      "topic": "...",
      "cognitive_level": "C4",
      "solution_basis": "..."
    }}
  ]
}}
'''