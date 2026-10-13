from __future__ import annotations

import re
from typing import Any

# =====================================================================
# RINGKASAN KISI-KISI TKA 2026 (SMP/MTs & SMA/MA)
# Dipetakan langsung dari Dokumen Resmi TKA 2026
# =====================================================================
TKA_KISI_KISI_2026: dict[str, dict[str, str]] = {
    # --- I. SMP/MTs ---
    "bahasa indonesia (smp/mts)": {
        "focus": "Literasi Membaca dan Menafsirkan Teks",
        "topics": "Teks informasi, deskripsi, narasi, prosedur, eksplanasi, argumentasi; gagasan utama, informasi rinci, simpulan; fakta/opini; hubungan antarkalimat/paragraf, kohesi, koherensi; unsur sastra (tokoh, latar, konflik, amanat); pembandingan dua teks.",
    },
    "matematika (smp/mts)": {
        "focus": "Penalaran Matematika dan Pemodelan Kontekstual",
        "topics": "Bilangan, operasi hitung, rasio, proporsi, persen; aljabar, persamaan/pertidaksamaan, SPLDV; pola bilangan, barisan, relasi/fungsi; geometri bidang/ruang, kesebangunan, luas/volume; statistika (mean, median, modus, diagram); peluang sederhana; pemodelan masalah sehari-hari.",
    },
    # --- II. SMA/MA WAJIB ---
    "bahasa indonesia": {
        "focus": "Literasi Membaca Kompleks dan Evaluasi Wacana",
        "topics": "Teks argumentatif, editorial, eksposisi, artikel, laporan; gagasan utama, detail pendukung, sikap penulis, simpulan; fakta/opini, kualitas bukti, asumsi, bias; struktur wacana, kohesi, koherensi; sastra (puisi, cerpen, novel, drama, simbol, gaya bahasa); sintesis lintas teks.",
    },
    "matematika": {
        "focus": "Penalaran Matematika Multi-Langkah dan Analisis Data",
        "topics": "Aljabar, persamaan/pertidaksamaan, sistem persamaan; fungsi, komposisi/invers, eksponen, logaritma; barisan dan deret; geometri, pengukuran, trigonometri; statistika, interpretasi data, ukuran pemusatan/penyebaran; peluang, kombinatorika, pengambilan keputusan berbasis data.",
    },
    "bahasa inggris": {
        "focus": "Reading Comprehension, Inference, and Argument Evaluation",
        "topics": "Informative articles, opinion essays, narratives; main idea, supporting details, author's purpose, tone, attitude; inference, implied meaning, vocabulary in context; text structure, claims, evidence, assumptions, bias, credibility; cross-text synthesis.",
    },
    # --- III. SMA/MA PILIHAN (19 Mata Uji) ---
    "matematika lanjutan": {
        "focus": "Pendalaman Aljabar, Analisis Fungsi, dan Kalkulus",
        "topics": "Polinomial, persamaan/pertidaksamaan kompleks; fungsi eksponensial, logaritma, trigonometri, grafik; limit, turunan, integral, optimasi; geometri analitik, vektor, barisan/deret; peluang dan kombinatorika.",
    },
    "bahasa indonesia lanjutan": {
        "focus": "Analisis Wacana Akademik dan Kritik Sastra Mendalam",
        "topics": "Teks akademik populer, editorial, esai, kritik, argumentasi; analisis sastra (simbol, konflik, sudut pandang, stilistika); struktur wacana, kohesi, koherensi, makna tersirat; evaluasi bukti, asumsi, bias; sintesis wacana kompleks.",
    },
    "bahasa inggris lanjutan": {
        "focus": "Advanced Academic Reading, Critical Analysis, and Discourse Synthesis",
        "topics": "Academic essays, opinion pieces, literary texts; deep inference, implied meaning, author's tone and attitude; structural logic, claim-evidence-assumption critique, bias detection; cross-textual synthesis.",
    },
    "fisika": {
        "focus": "Penalaran Fisika, Analisis Grafik, dan Hubungan Variabel",
        "topics": "Pengukuran, vektor, kinematika, dinamika, usaha-energi, momentum, tumbukan; rotasi, gravitasi, fluida; getaran, gelombang, bunyi, kalor, termodinamika; listrik, magnet, induksi, rangkaian AC/DC; optik dan konsep fisika modern.",
    },
    "kimia": {
        "focus": "Analisis Perubahan Reaksi, Stoikiometri, dan Eksperimen",
        "topics": "Struktur atom, sistem periodik, ikatan kimia, bentuk molekul; stoikiometri, mol, pereaksi pembatas; larutan, termokimia, laju reaksi, kesetimbangan; asam-basa, pH, penyangga, hidrolisis; redoks, elektrokimia, kimia organik, dan lingkungan.",
    },
    "biologi": {
        "focus": "Analisis Data Eksperimen, Sistem Biologis, dan Genetika",
        "topics": "Keanekaragaman, ekologi; sel, membran, pembelahan, biomolekul, enzim; respirasi, fotosintesis, metabolisme; DNA/RNA, sintesis protein, genetika, mutasi, evolusi; fisiologi manusia; bioteknologi dan lingkungan.",
    },
    "ekonomi": {
        "focus": "Analisis Kebijakan Ekonomi, Pasar, dan Interpretasi Data",
        "topics": "Kelangkaan, biaya peluang, permintaan-penawaran, elastisitas; perilaku konsumen/produsen, struktur pasar; PDB, inflasi, pengangguran; kebijakan fiskal/moneter, perpajakan; perdagangan internasional, kurs; akuntansi dasar.",
    },
    "sosiologi": {
        "focus": "Analisis Kasus Sosial, Masalah Kemasyarakatan, dan Metode Penelitian",
        "topics": "Interaksi sosial, nilai, norma, sosialisasi; kelompok, identitas, stratifikasi, mobilitas; konflik, integrasi, perubahan sosial, globalisasi; penyimpangan sosial; metode penelitian sosial (sampel, data, interpretasi).",
    },
    "geografi": {
        "focus": "Analisis Spasial, Peta/Citra, dan Pembangunan Berkelanjutan",
        "topics": "Konsep geografi, peta, koordinat, SIG; litosfer, atmosfer, hidrosfer, biosfer; kependudukan, migrasi, urbanisasi, interaksi desa-kota; tata ruang, sumber daya, mitigasi bencana, penginderaan jauh.",
    },
    "sejarah": {
        "focus": "Analisis Sumber Sejarah, Kasus Kausalitas, dan Perubahan Global",
        "topics": "Konsep waktu, kronologi, periodisasi, sumber sejarah; Hindu-Buddha, Islam di Indonesia; kolonialisme, pergerakan nasional, proklamasi, revolusi, Indonesia pascakemerdekaan; Perang Dunia, Perang Dingin, tatanan global.",
    },
    "antropologi": {
        "focus": "Analisis Budaya, Dinamika Masyarakat, dan Etnografi",
        "topics": "Konsep budaya, keberagaman, relativisme budaya, multikulturalisme; kekerabatan, organisasi sosial, ritual, simbol; etnografi, observasi, etika penelitian; akulturasi, asimilasi, globalisasi.",
    },
    "ppkn / pendidikan pancasila": {
        "focus": "Analisis Studi Kasus Kewarganegaraan dan Prinsip Konstitusional",
        "topics": "Nilai dan penerapan Pancasila; UUD NRI 1945, hak dan kewajiban warga negara; NKRI, Bhinneka Tunggal Ika, integrasi nasional; demokrasi, pemilu, lembaga negara; HAM, hukum, keadilan; etika digital dan ketahanan nasional.",
    },
    "bahasa arab": {
        "focus": "Pemahaman Teks Arab, Struktur Gramatikal, dan Inferensi",
        "topics": "Pendidikan, keluarga, kesehatan, pekerjaan; teks, dialog, pengumuman; isim, fi'il, huruf, jumlah ismiyah/fi'liyah; sharaf, dhamir, idhafah, na'at-man'ut; gagasan utama, tujuan penulis, rujukan kata.",
    },
    "bahasa jerman": {
        "focus": "Leseverstehen, Textstruktur, und Kommunikationsabsicht",
        "topics": "Alltag, Bildung, Arbeit, Umwelt; Artikel, Ankündigungen, Dialoge; Konjugation, Kasus, Pronomen, Satzbau, Zeitformen, Konnektoren; Hauptgedanke, Implikation, Kommunikationsziel.",
    },
    "bahasa prancis": {
        "focus": "Compréhension Écrite, Logique Textuelle, et Inférence",
        "topics": "Éducation, famille, culture, environnement; articles, dialogues, annonces; conjugaison, pronoms, prépositions, structure de la phrase, connecteurs; idée principale, sens implicit, inférence.",
    },
    "bahasa jepang": {
        "focus": "読解 (Dokkai), 文法 (Bunpou), dan Kontekstualisasi Ungkapan",
        "topics": "Hiragana, katakana, kanji; dialog, pengumuman, narasi; partikel (助詞), pola kalimat, konjugasi, bentuk sopan/hormat (敬語); rujukan, tujuan komunikasi, makna tersirat.",
    },
    "bahasa korea": {
        "focus": "읽기 (Reading), 문법 (Grammar), dan Analisis Dialog",
        "topics": "Hangeul, kosakata sehari-hari & akademik; dialog, pesan, pengumuman; partikel (조사), akhiran kalimat, 변화 (konjugasi kata kerja), tingkat kesopanan; 주제 (gagasan utama), 추론 (inferensi).",
    },
    "bahasa mandarin": {
        "focus": "阅读理解 (Reading Comprehension), 语法 (Grammar), dan Inferensi Teks",
        "topics": "Hanzi (汉字), kosakata; dialog, pengumuman, narasi; kata ukur (量词), partikel, pola gramatikal; hubungan kalimat, tujuan komunikasi, gagasan utama, detail tersirat.",
    },
    "produk / projek kreatif dan kewirausahaan": {
        "focus": "Analisis Studi Kasus Usaha, Perhitungan Biaya/Laba, dan Strategi Bisnis",
        "topics": "Peluang usaha, riset pasar, segmentasi, target pasar; desain produk, prototipe, proposisi nilai; model bisnis, HPP, harga jual, omzet, laba, BEP (titik impas); promosi digital, pemasaran, risiko, legalitas, evaluasi usaha.",
    },
}


def detect_subject_context(mapel: str) -> dict[str, Any]:
    """
    Mendeteksi karakteristik mata uji berdasarkan Kisi-Kisi Resmi TKA 2026 untuk menentukan:
    - Bahasa pengantar utama & Aturan isolasi bahasa (Zero Mixed Language)
    - Opsi respons Kategori bawaan (True/False vs Benar/Salah vs Bahasa Asing lain)
    - Fitur LaTeX ($...$) aktif HANYA untuk mata uji eksak
    - Panduan topik & fokus kompetensi dari kisi-kisi resmi
    """
    m_clean = str(mapel or "").strip().lower()
    m_normalized = re.sub(r"\s+", " ", m_clean)

    # Cari pedoman kisi-kisi berdasarkan nama mata uji
    matched_kisi = None
    for key, val in TKA_KISI_KISI_2026.items():
        if key in m_normalized or m_normalized in key:
            matched_kisi = val
            break

    kisi_focus = matched_kisi["focus"] if matched_kisi else "Penalaran HOTS dan Evaluasi Kontekstual"
    kisi_topics = matched_kisi["topics"] if matched_kisi else "Materi terstandar kurikulum TKA 2026."

    # 1. Bahasa Inggris (Wajib & Lanjutan)
    if any(kw in m_normalized for kw in ["inggris", "english", "toefl", "toeic", "ielts"]):
        return {
            "lang_code": "en",
            "lang_name": "English",
            "instruction_lang": "English",
            "category_options": ["True", "False"],
            "use_latex": False,
            "kisi_focus": kisi_focus,
            "kisi_topics": kisi_topics,
            "rules": (
                "CRITICAL ZERO-MIXED-LANGUAGE RULE: The entire output (question text, stimulus, "
                "options, category statements, category options like True/False or Yes/No, and solution_basis) "
                "MUST be written 100% in ENGLISH. Absolutely NO Indonesian words allowed anywhere."
            ),
        }

    # 2. Bahasa Arab
    if any(kw in m_normalized for kw in ["arab", "arabic", "nahwu", "shorof"]):
        return {
            "lang_code": "ar",
            "lang_name": "Arabic",
            "instruction_lang": "Arabic",
            "category_options": ["صحيح", "خطأ"],
            "use_latex": False,
            "kisi_focus": kisi_focus,
            "kisi_topics": kisi_topics,
            "rules": (
                "CRITICAL LANGUAGE RULE: The entire question text, stimulus, options, "
                "category statements, category options (صحيح/خطأ), and solution_basis MUST be written 100% in ARABIC."
            ),
        }

    # 3. Bahasa Jerman
    if "jerman" in m_normalized or "german" in m_normalized:
        return {
            "lang_code": "de",
            "lang_name": "German",
            "instruction_lang": "German",
            "category_options": ["Richtig", "Falsch"],
            "use_latex": False,
            "kisi_focus": kisi_focus,
            "kisi_topics": kisi_topics,
            "rules": "CRITICAL LANGUAGE RULE: All output MUST be written 100% in GERMAN (Richtig/Falsch for Category options).",
        }

    # 4. Bahasa Prancis
    if "prancis" in m_normalized or "french" in m_normalized:
        return {
            "lang_code": "fr",
            "lang_name": "French",
            "instruction_lang": "French",
            "category_options": ["Vrai", "Faux"],
            "use_latex": False,
            "kisi_focus": kisi_focus,
            "kisi_topics": kisi_topics,
            "rules": "CRITICAL LANGUAGE RULE: All output MUST be written 100% in FRENCH (Vrai/Faux for Category options).",
        }

    # 5. Bahasa Jepang
    if "jepang" in m_normalized or "japanese" in m_normalized:
        return {
            "lang_code": "ja",
            "lang_name": "Japanese",
            "instruction_lang": "Japanese",
            "category_options": ["正しい", "誤り"],
            "use_latex": False,
            "kisi_focus": kisi_focus,
            "kisi_topics": kisi_topics,
            "rules": "CRITICAL LANGUAGE RULE: All output MUST be written in JAPANESE (Kanji/Kana). Category options: 正しい / 誤り.",
        }

    # 6. Bahasa Korea
    if "korea" in m_normalized or "korean" in m_normalized:
        return {
            "lang_code": "ko",
            "lang_name": "Korean",
            "instruction_lang": "Korean",
            "category_options": ["맞음", "틀림"],
            "use_latex": False,
            "kisi_focus": kisi_focus,
            "kisi_topics": kisi_topics,
            "rules": "CRITICAL LANGUAGE RULE: All output MUST be written in KOREAN (Hangeul). Category options: 맞음 / 틀림.",
        }

    # 7. Bahasa Mandarin
    if "mandarin" in m_normalized or "chinese" in m_normalized:
        return {
            "lang_code": "zh",
            "lang_name": "Mandarin",
            "instruction_lang": "Mandarin",
            "category_options": ["正确", "错误"],
            "use_latex": False,
            "kisi_focus": kisi_focus,
            "kisi_topics": kisi_topics,
            "rules": "CRITICAL LANGUAGE RULE: All output MUST be written in MANDARIN (Hanzi). Category options: 正确 / 错误.",
        }

    # 8. Mata Uji Eksak / Sains (LaTeX Aktif)
    is_exact = any(kw in m_normalized for kw in [
        "matematika", "math", "fisika", "physics", "kimia", "chemistry",
        "sains", "ipa", "numerasi", "kalkulus", "statistika"
    ])

    return {
        "lang_code": "id",
        "lang_name": "Bahasa Indonesia",
        "instruction_lang": "Bahasa Indonesia",
        "category_options": ["Benar", "Salah"],
        "use_latex": is_exact,
        "kisi_focus": kisi_focus,
        "kisi_topics": kisi_topics,
        "rules": (
            "Gunakan Bahasa Indonesia baku, jelas, dan komunikatif. "
            + (
                "Gunakan notasi LaTeX $...$ HANYA untuk persamaan, akar, pecahan, atau rumus matematika/fisika/kimia."
                if is_exact
                else "DILARANG KERAS menggunakan notasi LaTeX $...$ atau tag \\text{...} pada teks biasa. Tulis seluruh kata secara eksplisit."
            )
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
    Menyusun System Prompt presisi tinggi berdasarkan Kisi-Kisi Resmi TKA 2026.
    """
    ctx = detect_subject_context(mapel)
    labels_str = ", ".join(option_labels)
    img_ids_formatted = ", ".join(str(x) for x in (image_ids or [])) or "(TIDAK ADA GAMBAR)"

    # Instruksi Khusus Jalur Pengerjaan
    if path_type.upper() == "MANDIRI":
        path_instruction = """
JALUR: LATIHAN MANDIRI SISWA (ADAPTIVE PRACTICE)
- Buat soal dengan konteks kehidupan nyata (literasi/numerasi) yang menarik dan relevan.
- Variasikan tingkat kesulitan dari sedang hingga HOTS tinggi (C4 Analisis, C5 Evaluasi, C6 Solusi).
- Pembahasan (`solution_basis`) wajib bersifat mendidik, memberikan pemahaman konsep mendasar secara rinci.
"""
    else:
        path_instruction = """
JALUR: TKA STUDIO / CUSTOM GURU (EXAM STANDARD)
- Buat paket soal terstandar ujian resmi madrasah/sekolah sesuai Juknis TKA 2026.
- Setiap butir wajib terstruktur secara ketat mengikuti kompetensi kurikulum resmi.
- Pembahasan (`solution_basis`) wajib berupa langkah penyelesaian formal yang lugas dan bersih.
"""

    qtype = question_type.upper()

    # Dynamic Rule Format Soal
    if qtype == "PG":
        type_rules = f"""
BENTUK SOAL: PILIHAN GANDA (PG)
- Tepat 1 jawaban benar.
- Array `options` wajib memiliki tepat {len(option_labels)} pilihan berlabel {labels_str}.
- `correct_answer` adalah SATU label huruf string murni (misal: "B").
- Array `correct_answers` diisi kosong [].
"""
        schema = f'''"options": ["{option_labels[0]}. ...", "{option_labels[1]}. ..."],
      "correct_answer": "B",
      "correct_answers": []'''

    elif qtype == "MCMA":
        type_rules = f"""
BENTUK SOAL: PILIHAN GANDA KOMPLEKS (MCMA)
- Tepat {len(option_labels)} pilihan tersedia berlabel {labels_str}.
- DUA ATAU LEBIH jawaban WAJIB benar (dilarang hanya 1 jawaban benar).
- `correct_answers` berisi array 2+ LABEL huruf unik dan WAJIB TERURUT ALFABETIS (misal: ["A", "C"]).
- `correct_answer` diisi sama persis dengan `correct_answers`.
"""
        schema = f'''"options": ["{option_labels[0]}. ...", "{option_labels[1]}. ..."],
      "correct_answer": ["A", "C"],
      "correct_answers": ["A", "C"]'''

    elif qtype == "KATEGORI":
        cat_opt1 = ctx["category_options"][0]
        cat_opt2 = ctx["category_options"][1]
        type_rules = f"""
BENTUK SOAL: PILIHAN GANDA KOMPLEKS (KATEGORI)
- Buat 3 hingga 5 pernyataan independen yang berakar dari stimulus.
- Setiap pernyataan wajib memiliki opsi respons dalam bahasa mata uji: {ctx["category_options"]}.
- DILARANG MENGGUNAKAN "Benar/Salah" jika mata uji adalah Bahasa Inggris (WAJIB "True/False" atau "Yes/No").
- `category_items` berisi objek {{ "statement": "...", "options": {ctx["category_options"]}, "correct_response": "{cat_opt1}" }}.
- `correct_answers` diisi array hasil respons tiap pernyataan secara berurutan.
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

    else:
        type_rules = f"""
BENTUK SOAL: MIXED (PG / MCMA / KATEGORI)
- Buat variasi bentuk soal yang sesuai dengan karakteristik mata uji {mapel}.
"""
        schema = '''"options": [], "correct_answer": [], "correct_answers": [], "category_items": []'''

    # Aturan Gambar (Image Linking Rules)
    if image_count <= 0 or not image_ids:
        image_rules = """
ATURAN GAMBAR (KOSONG / TANPA GAMBAR):
- TIDAK ADA gambar yang disediakan untuk batch ini.
- DILARANG KERAS menyebutkan kata "Gambar 1", "Image 1", "Infografis", "Tabel", "Chart", atau "Figure" di dalam teks soal maupun stimulus.
- Seluruh soal wajib murni berbasis teks/skenario tulisan.
- Set `"image_id": null` dan `"image_ids": []` pada seluruh soal.
"""
    else:
        image_rules = f"""
ATURAN GAMBAR & STIMULUS VISUAL:
1. ID Gambar yang tersedia dalam sistem: {img_ids_formatted}.
2. Jika soal HANYA membutuhkan 1 gambar (misal menanyakan Gambar 1):
   - Set `"image_id": "{image_ids[0]}"`
   - Set `"image_ids": [{{"id": "{image_ids[0]}", "no": 1}}]`
   - Sebutkan referensi gambar dalam teks secara alami (misal: "Berdasarkan Gambar 1..." / "According to Image 1...").
3. Jika soal MEMBANDINGKAN 2+ gambar (misal "Comparing Image 1 and Image 2" / "Membandingkan Gambar 1 dan Gambar 2"):
   - Set `"image_id": "{image_ids[0]}"`
   - Set `"image_ids"` berisi seluruh objek gambar yang dibandingkan:
     `[ {{"id": "{image_ids[0]}", "no": 1}}, {{"id": "{image_ids[1] if len(image_ids)>1 else image_ids[0]}", "no": 2}} ]`
4. Dalam 1 batch {count} soal, WAJIB ada minimal 1-2 soal berstatus TEKS POLOS TANPA GAMBAR (`"image_id": null`, `"image_ids": []`).
"""

    latex_rule = (
        "FORMAT MATEMATIKA: Gunakan notasi LaTeX $...$ HANYA untuk rumus, persamaan, pecahan, atau variabel matematika/sains."
        if ctx["use_latex"]
        else "DILARANG KERAS MENGGUNAKAN SINTAKS LATEX ($...$ ATAU \\text{...}). Tulis seluruh kata, istilah, dan simbol secara teks biasa."
    )

    return f'''
Anda adalah Question Architect Utama TKA RoboMANTAP 2026.
Tugas Anda adalah menyusun {count} butir soal terstandar resmi untuk:
- Jenjang: {jenjang}
- Mata Uji: {mapel}
- Bahasa Pengantar Utama: {ctx["lang_name"]}
- Fokus Utama Kisi-Kisi 2026: {ctx["kisi_focus"]}
- Pokok Bahasan Kisi-Kisi 2026: {ctx["kisi_topics"]}

{ctx["rules"]}

{path_instruction}

{type_rules}

{image_rules}

STANDAR KUALITAS & FORMATTING:
- KOGNITIF HOTS: Buat soal pada level C4 (Analisis), C5 (Evaluasi/Inferensi), atau C6 (Pemecahan Masalah Multi-Langkah).
- PEMBAHASAN BERSIH (`solution_basis`): Wajib berisi langkah penyelesaian final yang runtut dan bersih. DILARANG mencantumkan kalimat self-correction (seperti "Koreksi opsi...", "Mari periksa kembali...").
- {latex_rule}

OUTPUT JSON MURNI (DILARANG MENAMBAHKAN TEKS APAPUN DI LUAR JSON):
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
