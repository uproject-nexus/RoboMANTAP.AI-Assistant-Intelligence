"""Teacher-side per-session pedagogical diagnosis service."""
from infrastructure.ai.service import call_gemini_with_rotation

def generate_individual_analysis_ai(nama_siswa: str, mapel: str, jenjang: str, nilai: int, detail_jawaban_list: list, quiz_data: list = None, user_answers: dict = None):
    """Generates a deep, prescriptive pedagogical analysis for an individual student."""
    
    total_soal = len(detail_jawaban_list) if detail_jawaban_list else 10
    benar = sum(1 for x in detail_jawaban_list if x is True)
    salah = sum(1 for x in detail_jawaban_list if x is False)
    kosong = total_soal - (benar + salah)

    # Susun detail analisis per nomor jika ada data quiz
    detail_soal_text = ""
    if quiz_data and user_answers:
        for idx, q in enumerate(quiz_data):
            u_ans = user_answers.get(idx, user_answers.get(str(idx), "Tidak Diisi"))
            c_ans = q.get("correct_answer", "-")
            status_item = "✅ BENAR" if u_ans == c_ans else "❌ SALAH"
            detail_soal_text += f"\n- Soal {idx+1} [{status_item}]: {q.get('question','')[:80]}... | Jwb Siswa: {u_ans} | Kunci: {c_ans}"

    prompt = f"""
    Anda adalah Pakar Evaluasi Pendidikan & Konsultan Pedagogi OMI/CBT untuk Madrasah Al Irsyad.
    Berikan Analisis Diagnosis Preskriptif yang tajam, akurat, dan sangat berguna bagi Guru mengenai hasil kuis santri berikut:

    DATA SISWA:
    - Nama Santri: {nama_siswa}
    - Mata Pelajaran: {mapel} ({jenjang})
    - Skor Akhir: {nilai} / 100
    - Transkrip Performa: {benar} Benar, {salah} Salah, {kosong} Kosong (Total {total_soal} Soal)
    {detail_soal_text}

    FORMAT KELUARAN (Gunakan Markdown rapi dengan Icon & Elemen Visual):

    ### 🎯 1. Profil Kognitif & Diagnosa Cepat
    - **Tingkat Penguasaan:** [Sangat Mahir / Berkembang / Perlu Intervensi Khusus / Miskonsepsi Berat]
    - **Pola Pengerjaan:** [Analisis singkat apakah siswa paham konsep dasar, sering salah hitung, atau asal tebak]

    ### 🔍 2. Bedah Akar Miskonsepsi
    - **Akar Masalah Utama:** [Jelaskan secara tajam di mana letak kelemahan logika/konsep siswa]
    - **Tipe Kesalahan:** [Konseptual / Prosedural-Kalkulasi / Penalaran HOTS]

    ### 💡 3. Rekomendasi Intervensi Guru (Preskriptif)
    - **Tindakan Remedial Guru:** [Langkah praktis yang harus dilakukan guru dalam 1-on-1 coaching]
    - **Fokus Latihan Lanjutan:** [Beri saran 2-3 topik/submateri spesifik yang harus diberikan ke siswa ini]

    ### 📲 4. Umpan Balik Santri & Ortu (WA-Ready)
    *(Pesan singkat, hangat, bernuansa keislaman & menyemangati yang bisa dicopy guru untuk dikirim via WA)*
    """

    return call_gemini_with_rotation(prompt, is_json=False)
