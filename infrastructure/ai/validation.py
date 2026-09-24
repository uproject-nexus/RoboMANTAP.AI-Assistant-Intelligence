"""Quiz validation/repair AI service."""
from __future__ import annotations
import json, re
from infrastructure.ai.service import call_gemini_with_rotation, clean_json_text
from infrastructure.ai.policy import *
def validate_and_repair_quiz(quiz: list, source_pack: dict | None, config: dict) -> list:
    if not quiz:
        return []
    count = len(quiz)
    jenjang = str(config.get("jenjang", "MTs"))
    mapel = str(config.get("mapel", ""))
    bahasa = str(config.get("bahasa", ""))
    konteks = str(config.get("konteks", ""))
    expected_labels = option_labels_for_jenjang(jenjang)
    option_count = len(expected_labels)
    language_guidance = build_language_guidance(mapel, bahasa, konteks, source_pack)
    source_locator_rule = "Tambahkan source_locator bila sumber tersedia; jangan memalsukan nomor halaman/slide."
    prompt = f"""
Anda adalah QA Validator RoboMANTAP untuk kuis madrasah.
Periksa lalu perbaiki draft soal. Pertahankan tepat {count} soal.
Konfigurasi: {json.dumps(config, ensure_ascii=False)}

KEBIJAKAN OPSI BERDASARKAN JENJANG:
- Jenjang MTs: tepat 4 opsi, label A-D.
- Jenjang MA: tepat 5 opsi, label A-E.
- Opsi harus berupa pilihan yang masuk akal dan hanya satu yang benar.
- Bila draft MA masih berisi 4 opsi, WAJIB tambahkan satu distraktor berkualitas menjadi E tanpa mengubah kebenaran jawaban.
- Bila draft memiliki format label yang tidak rapi, normalkan menjadi A. ... hingga label terakhir.

ATURAN BAHASA:
{language_guidance}

SUMBER UTAMA:
{_source_context_for_prompt(source_pack)}

DRAFT:
{json.dumps(quiz, ensure_ascii=False)}

ATURAN KUALITAS:
- Tepat {count} soal.
- Tepat {option_count} opsi per soal: {', '.join(expected_labels)}.
- correct_answer harus persis sama dengan salah satu opsi lengkap.
- Hindari ambiguitas, petunjuk jawaban yang terlalu mudah, duplikasi, dan pilihan yang tumpang tindih.
- Untuk soal numerik, solution_basis harus memuat proses hitungan inti dan hasil akhir.
- Jangan mengarang fakta inti yang tidak didukung sumber ketika sumber tersedia.
- {source_locator_rule}
- Keluarkan JSON murni.

FORMAT:
{{"quiz":[{{"id":1,"question":"...","options":["{expected_labels[0]}. ...", "{expected_labels[1]}. ...", "{expected_labels[2]}. ...", "{expected_labels[3]}. ..."{', "' + expected_labels[4] + '. ...' if option_count == 5 else ''}],"correct_answer":"{expected_labels[0]}. ...","solution_basis":"...","source_locator":"..."}}]}}
"""
    raw = call_gemini_with_rotation(prompt, is_json=True)
    if not raw:
        return quiz
    try:
        payload = json.loads(clean_json_text(raw), strict=False)
        validated = payload.get("quiz", [])
        return validated if isinstance(validated, list) and len(validated) == count else quiz
    except Exception:
        return quiz
