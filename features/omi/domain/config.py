"""OMI 2026 configuration extracted from the audited OMI flow.

This file intentionally preserves the existing OMI jenjang, subject and
submateri catalogue. It is configuration, not Streamlit UI state.
"""
from __future__ import annotations

KISI_KISI_OMI = {
    "MTs (Sederajat SMP)": {
        "Matematika": ["Bilangan", "Aljabar", "Aritmetika Sosial", "Geometri", "Peluang", "Statistika", "Perbandingan & Proporsi", "Problem Solving", "Konteks OMI (Keislaman & Sains)"],
        "IPA Terintegrasi": ["Makhluk Hidup & Sel", "Sistem Organ", "Genetika & Keanekaragaman", "Ekologi", "Zat & Perubahannya", "Energi & Kalor", "Gerak & Gaya", "Getaran, Gelombang & Optik", "Listrik & Kemagnetan", "Bumi & Antariksa", "Eksperimen & Data", "Konteks OMI"],
        "IPS Terintegrasi": ["Geografi", "Kependudukan", "Ekonomi", "Sejarah Indonesia", "Sejarah Islam", "Sosial & Budaya", "Kewarganegaraan", "Lingkungan & Pembangunan", "Literasi Data", "Konteks OMI"],
    },
    "MA (Sederajat SMA)": {
        "Matematika Terintegrasi": ["Bilangan & Teori Bilangan", "Aljabar & Fungsi", "Geometri", "Kombinatorika & Peluang", "Statistika", "Problem Solving", "Konteks OMI"],
        "Biologi Terintegrasi": ["Sel & Biokimia", "Genetika", "Fisiologi", "Botani & Zoologi", "Ekologi", "Evolusi & Keanekaragaman", "Bioteknologi & Lingkungan", "Konteks OMI"],
        "Fisika Terintegrasi": ["Mekanika", "Fluida", "Getaran & Gelombang", "Optik", "Suhu & Kalor", "Listrik & Magnet", "Fisika Modern", "Eksperimen & Data", "Konteks OMI"],
        "Kimia Terintegrasi": ["Struktur Atom & Periodik", "Ikatan Kimia", "Stoikiometri", "Larutan & Asam-Basa", "Redoks", "Termokimia & Kinetika", "Kesetimbangan", "Organik & Lingkungan", "Konteks OMI"],
        "Ekonomi Terintegrasi": ["Ekonomi Dasar", "Mikroekonomi", "Makroekonomi", "Kebijakan Ekonomi", "Akuntansi", "Pasar Modal & Keuangan", "Ekonomi Digital", "Ekonomi Islam", "Analisis Data"],
        "Geografi Terintegrasi": ["Peta & Keruangan", "Geologi & Geomorfologi", "Atmosfer & Iklim", "Hidrosfer", "Biosfer", "Kependudukan", "Sumber Daya & Lingkungan", "Bencana", "SIG & Data Spasial", "Konteks OMI"],
    },
}

STAGES = ("Internal", "Kab/Kota", "Provinsi", "Nasional")
QUESTION_COUNT = 10


def normalize_jenjang(value: str) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"mts", "smp", "mtssederajatsmp"} or "mts" in raw:
        return "MTs (Sederajat SMP)"
    if raw in {"ma", "sma", "masederajatsma"} or raw.startswith("ma") or "aliyah" in raw:
        return "MA (Sederajat SMA)"
    raise ValueError("Jenjang OMI tidak dikenali. Gunakan MTs atau MA.")


def subjects_for_jenjang(jenjang: str) -> dict[str, list[str]]:
    return KISI_KISI_OMI[normalize_jenjang(jenjang)]


def validate_subject(jenjang: str, mapel: str) -> list[str]:
    subjects = subjects_for_jenjang(jenjang)
    if mapel not in subjects:
        raise ValueError("Bidang OMI tidak ditemukan untuk jenjang yang dipilih.")
    return list(subjects[mapel])
