"""Small, friendly learning games for the RoboMANTAP Student Intelligence portal.

Scores live in Streamlit session state only; these are practice games, not official exams.
"""

from __future__ import annotations

import random
import streamlit as st

GAME_BANKS = {
    "🔢 Matematika": {
        "accent": "#fff0c9",
        "tagline": "Asah logika, satu soal kecil setiap hari.",
        "questions": [
            {"q": "Berapakah hasil 7 × 8?", "options": ["54", "56", "58", "64"], "answer": "56", "why": "7 × 8 = 56. Kamu bisa mengingatnya dengan latihan perkalian sedikit demi sedikit."},
            {"q": "Hasil dari ½ + ¼ adalah …", "options": ["¾", "⅔", "⅕", "1"], "answer": "¾", "why": "Samakan penyebutnya: ½ = 2/4, lalu 2/4 + 1/4 = 3/4."},
            {"q": "Sebuah persegi memiliki sisi 5 cm. Berapa kelilingnya?", "options": ["10 cm", "15 cm", "20 cm", "25 cm"], "answer": "20 cm", "why": "Persegi memiliki empat sisi sama panjang, jadi keliling = 4 × 5 = 20 cm."},
            {"q": "Bilangan prima di bawah ini adalah …", "options": ["9", "15", "17", "21"], "answer": "17", "why": "17 hanya mempunyai dua faktor positif: 1 dan 17."},
            {"q": "Jika 3 buku berharga Rp24.000, berapa harga 1 buku dengan harga sama?", "options": ["Rp6.000", "Rp8.000", "Rp9.000", "Rp12.000"], "answer": "Rp8.000", "why": "Rp24.000 ÷ 3 = Rp8.000 per buku."},
        ],
    },
    "🔬 Sains Ceria": {
        "accent": "#dff8f2",
        "tagline": "Jelajahi alam dan temukan alasan di baliknya.",
        "questions": [
            {"q": "Organ tubuh yang memompa darah adalah …", "options": ["Paru-paru", "Jantung", "Lambung", "Ginjal"], "answer": "Jantung", "why": "Jantung memompa darah agar oksigen dan zat gizi diedarkan ke tubuh."},
            {"q": "Perubahan air cair menjadi uap disebut …", "options": ["Membeku", "Mengembun", "Menguap", "Mencair"], "answer": "Menguap", "why": "Penguapan adalah perubahan wujud zat cair menjadi gas."},
            {"q": "Tumbuhan membuat makanan terutama melalui proses …", "options": ["Fotosintesis", "Pencernaan", "Fermentasi", "Pengembunan"], "answer": "Fotosintesis", "why": "Fotosintesis menggunakan energi cahaya untuk membantu tumbuhan menghasilkan gula dari air dan karbon dioksida."},
            {"q": "Planet yang dikenal sebagai Planet Merah adalah …", "options": ["Venus", "Mars", "Jupiter", "Saturnus"], "answer": "Mars", "why": "Permukaan Mars tampak kemerahan karena mineral yang kaya oksida besi."},
            {"q": "Sumber energi utama bagi sebagian besar kehidupan di Bumi adalah …", "options": ["Bulan", "Matahari", "Angin malam", "Batu bara saja"], "answer": "Matahari", "why": "Matahari memasok energi untuk fotosintesis dan menggerakkan banyak proses alam."},
        ],
    },
    "🌷 Adab & Akhlak": {
        "accent": "#ffe5ef",
        "tagline": "Latih pilihan baik dalam keseharian.",
        "questions": [
            {"q": "Kamu melihat teman kesulitan membawa buku. Apa sikap yang baik?", "options": ["Menertawakannya", "Membantu sesuai kemampuan", "Berpura-pura tidak melihat", "Merebut bukunya"], "answer": "Membantu sesuai kemampuan", "why": "Tolong-menolong dengan cara yang baik menunjukkan kepedulian dan akhlak terpuji."},
            {"q": "Saat akan makan, kebiasaan baik yang diajarkan dalam Islam adalah …", "options": ["Berebut makanan", "Mencela makanan", "Membaca basmalah dan menjaga kebersihan", "Membuang makanan"], "answer": "Membaca basmalah dan menjaga kebersihan", "why": "Membaca basmalah, makan dengan tertib, dan menjaga kebersihan adalah kebiasaan baik."},
            {"q": "Kamu menemukan barang milik teman di kelas. Sebaiknya …", "options": ["Menyimpannya diam-diam", "Mengaku sebagai pemilik", "Mengembalikan atau menyerahkannya kepada guru", "Meninggalkannya begitu saja"], "answer": "Mengembalikan atau menyerahkannya kepada guru", "why": "Menjaga amanah berarti berusaha mengembalikan barang kepada pemiliknya."},
            {"q": "Ketika guru atau teman sedang berbicara, kita sebaiknya …", "options": ["Mendengarkan dengan baik", "Memotong pembicaraan", "Berteriak lebih keras", "Bermain sendiri sambil mengejek"], "answer": "Mendengarkan dengan baik", "why": "Mendengarkan dengan hormat membantu kita belajar dan menghargai orang lain."},
            {"q": "Jika melakukan kesalahan kepada teman, langkah baik adalah …", "options": ["Menyalahkan orang lain", "Meminta maaf dan memperbaiki kesalahan", "Menyebarkan rahasianya", "Berpura-pura tidak terjadi apa-apa"], "answer": "Meminta maaf dan memperbaiki kesalahan", "why": "Mengakui kesalahan, meminta maaf, dan berusaha memperbaikinya adalah sikap bertanggung jawab."},
        ],
    },
    "📚 Bahasa & Literasi": {
        "accent": "#e9e7ff",
        "tagline": "Bermain dengan kata, makna, dan cerita.",
        "questions": [
            {"q": "Sinonim kata 'rajin' adalah …", "options": ["Tekun", "Malas", "Lalai", "Lambat"], "answer": "Tekun", "why": "Rajin dan tekun sama-sama menggambarkan kesungguhan dalam melakukan sesuatu."},
            {"q": "Kalimat tanya yang ditulis dengan tanda baca …", "options": ["Titik (.)", "Koma (,) ", "Tanya (?)", "Titik dua (:)"], "answer": "Tanya (?)", "why": "Tanda tanya digunakan untuk mengakhiri kalimat tanya langsung."},
            {"q": "Bahasa Inggris dari 'perpustakaan' adalah …", "options": ["Laboratory", "Library", "Kitchen", "Classroom"], "answer": "Library", "why": "Library berarti perpustakaan."},
            {"q": "Lawan kata 'hemat' adalah …", "options": ["Cermat", "Irit", "Boros", "Teliti"], "answer": "Boros", "why": "Hemat berarti menggunakan sesuatu secara bijaksana; lawan katanya adalah boros."},
            {"q": "Ide utama yang dibahas dalam sebuah paragraf disebut …", "options": ["Kata sambung", "Gagasan pokok", "Tanda baca", "Kutipan"], "answer": "Gagasan pokok", "why": "Gagasan pokok adalah ide utama yang menjadi fokus paragraf."},
        ],
    },
}


def _subject_slug(subject: str) -> str:
    return {"🔢 Matematika": "math", "🔬 Sains Ceria": "science", "🌷 Adab & Akhlak": "adab", "📚 Bahasa & Literasi": "literacy"}.get(subject, "math")


def render_student_game_lab() -> None:
    """Render a colourful, phone-friendly collection of short practice games."""
    st.markdown(
        """
        <div class="game-lab-hero">
          <div class="game-lab-eyebrow">STUDENT INTELLIGENCE · GAME LAB</div>
          <div class="game-lab-title">Belajar, bermain, lalu makin MANTAP! ✨</div>
          <div class="game-lab-copy">Mini-game singkat untuk melatih logika, rasa ingin tahu, literasi, dan kebiasaan baik. Pilih arena favoritmu dan kumpulkan bintang.</div>
          <div class="game-lab-chips"><span>📱 Nyaman di HP</span><span>🌈 Cerah & ringan</span><span>🎯 Latihan, bukan ujian</span></div>
        </div>
        <style>
        .game-lab-hero{padding:22px 20px;border-radius:24px;background:linear-gradient(125deg,#ffe0ec 0%,#fff0cf 52%,#dff9ee 100%);border:1px solid #f3dfe4;box-shadow:0 12px 28px rgba(83,65,89,.06);margin:4px 0 18px;color:#29354e;}
        .game-lab-eyebrow{font-size:10px;letter-spacing:.16em;font-weight:900;color:#be4771;}
        .game-lab-title{font-size:clamp(24px,5vw,34px);font-weight:950;line-height:1.08;letter-spacing:-.04em;margin:9px 0;color:#29354e;}
        .game-lab-copy{font-size:13px;line-height:1.65;max-width:680px;color:#56627a;}
        .game-lab-chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:13px;}
        .game-lab-chips span{padding:7px 10px;border-radius:999px;background:rgba(255,255,255,.76);font-size:11px;font-weight:800;color:#46526b;border:1px solid rgba(255,255,255,.9);}
        .game-prompt{padding:18px;border-radius:21px;background:#fff;border:1px solid #f0e4df;box-shadow:0 8px 23px rgba(73,67,91,.045);}
        .game-question-number{color:#d34f7c;font-size:10px;letter-spacing:.12em;font-weight:900;text-transform:uppercase;margin-bottom:8px;}
        .game-question-text{color:#29354e;font-size:clamp(19px,3.5vw,24px);line-height:1.3;font-weight:900;margin-bottom:8px;}
        .game-feedback{border-radius:17px;padding:14px 15px;margin:10px 0;background:#f0fcf5;border:1px solid #cdeed9;color:#28543b;}
        .game-feedback.wrong{background:#fff5ed;border-color:#f8dcc5;color:#80522a;}
        @media(max-width:640px){.game-lab-hero{padding:19px 16px;border-radius:21px}.game-prompt{padding:15px;border-radius:18px}.game-question-text{font-size:19px}}
        </style>
        """,
        unsafe_allow_html=True,
    )

    subjects = list(GAME_BANKS)
    current_subject = st.radio(
        "Pilih arena permainan",
        subjects,
        horizontal=True,
        key="rm_game_subject",
        label_visibility="collapsed",
    )
    game_id = _subject_slug(current_subject)
    questions = GAME_BANKS[current_subject]["questions"]
    idx_key = f"rm_game_idx_{game_id}"
    stats_key = f"rm_game_stats_{game_id}"
    result_key = f"rm_game_result_{game_id}"
    question_index = int(st.session_state.get(idx_key, 0)) % len(questions)
    question = questions[question_index]
    stats = st.session_state.get(stats_key, {"played": 0, "correct": 0})

    top_left, top_right = st.columns([1.4, 1])
    with top_left:
        st.markdown(f"### {current_subject}")
        st.caption(GAME_BANKS[current_subject]["tagline"])
    with top_right:
        accuracy = round((stats["correct"] / stats["played"]) * 100) if stats["played"] else 0
        st.metric("⭐ Bintang", f"{stats['correct']} / {stats['played']}", f"Akurasi {accuracy}%" if stats["played"] else "Mulai kumpulkan!")

    st.progress((question_index + 1) / len(questions), text=f"Tantangan {question_index + 1} dari {len(questions)}")
    st.markdown(
        f'<div class="game-prompt"><div class="game-question-number">SOAL {question_index + 1:02d} · PILIH JAWABAN TERBAIK</div><div class="game-question-text">{question["q"]}</div></div>',
        unsafe_allow_html=True,
    )

    current_result = st.session_state.get(result_key)
    has_answered = isinstance(current_result, dict) and current_result.get("idx") == question_index
    if not has_answered:
        with st.form(f"rm_game_form_{game_id}_{question_index}"):
            selected = st.radio(
                "Jawabanmu",
                question["options"],
                key=f"rm_game_answer_{game_id}_{question_index}",
                label_visibility="collapsed",
            )
            submitted = st.form_submit_button("Periksa jawabanku ✨", use_container_width=True, type="primary")
        if submitted:
            is_correct = selected == question["answer"]
            latest_stats = dict(st.session_state.get(stats_key, {"played": 0, "correct": 0}))
            latest_stats["played"] = int(latest_stats.get("played", 0)) + 1
            latest_stats["correct"] = int(latest_stats.get("correct", 0)) + int(is_correct)
            st.session_state[stats_key] = latest_stats
            st.session_state[result_key] = {"idx": question_index, "selected": selected, "correct": is_correct}
            st.rerun()
    else:
        if current_result.get("correct"):
            st.markdown(f'<div class="game-feedback"><b>🎉 MasyaAllah, tepat sekali!</b><br>{question["why"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="game-feedback wrong"><b>🌱 Belum tepat, tidak apa-apa!</b><br>Jawaban yang tepat: <b>{question["answer"]}</b><br>{question["why"]}</div>', unsafe_allow_html=True)
        a, b = st.columns(2)
        with a:
            if st.button("Soal berikutnya ➜", type="primary", use_container_width=True, key=f"rm_game_next_{game_id}_{question_index}"):
                st.session_state[idx_key] = (question_index + 1) % len(questions)
                st.rerun()
        with b:
            if st.button("🔀 Ulang arena", use_container_width=True, key=f"rm_game_reset_{game_id}_{question_index}"):
                st.session_state[idx_key] = 0
                st.session_state[stats_key] = {"played": 0, "correct": 0}
                st.session_state.pop(result_key, None)
                st.rerun()

    st.caption("Skor mini-game tersimpan selama sesi aplikasi ini aktif. Permainan ini untuk latihan mandiri dan tidak mengubah nilai ujian resmi.")
