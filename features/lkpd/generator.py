"""LKPD content generation service."""
from __future__ import annotations
import json
from infrastructure.ai.service import call_gemini_with_rotation, clean_json_text
from features.material.knowledge_pack import source_context_for_prompt

def generate_lkpd_content(mapel,kelas,topik,source_pack=None):
    prompt=f"""Anda adalah Tim Ahli Kurikulum Lembaga Pendidikan Al-Irsyad Al-Islamiyah Putri Bondowoso. Rancang isi LKPD berbasis HOTS dan terintegrasi nilai Keislaman. Mata Pelajaran: {mapel}; Kelas/Jenjang: {kelas}; Topik: {topik}. SUMBER MATERI UTAMA: {source_context_for_prompt(source_pack,65000)}. Keluarkan JSON murni dengan tujuan (3 poin), ringkasan, soal_1 sampai soal_5, dan refleksi. Untuk matematika/fisika/kimia hindari delimiter LaTeX dollar/backslash; gunakan simbol Unicode/HTML sederhana sesuai aturan dokumen yang ada."""
    raw=call_gemini_with_rotation(prompt,is_json=True)
    if not raw: return None
    try: return json.loads(clean_json_text(raw),strict=False)
    except Exception: return None
