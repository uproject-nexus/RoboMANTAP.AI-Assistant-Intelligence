"""Shared quiz policy and madrasah language rules."""
from __future__ import annotations
import re
OPTION_LABELS_MTS = ("A", "B", "C", "D")
OPTION_LABELS_MA = ("A", "B", "C", "D", "E")
def format_latex_options(options):
    formatted = []
    for opt in options:
        opt = str(opt).replace(r"\frac", r"\tfrac")
        if "\\" in opt and "$" not in opt:
            parts = opt.split(". ", 1)
            opt = f"{parts[0]}. ${parts[1]}$" if len(parts) == 2 else f"${opt}$"
        formatted.append(opt)
    return formatted


def option_labels_for_jenjang(jenjang: str) -> tuple[str, ...]:
    """MTs -> A-D, MA -> A-E. Default aman mengikuti MTs untuk jenjang tidak dikenal."""
    value = str(jenjang or "").strip().lower()
    if "ma" in value or "aliyah" in value:
        return OPTION_LABELS_MA
    return OPTION_LABELS_MTS


def option_count_for_jenjang(jenjang: str) -> int:
    return len(option_labels_for_jenjang(jenjang))


def normalize_custom_timer_config(config: dict | None) -> dict:
    """Normalisasi durasi kuis custom ke satu sumber kebenaran: timer_seconds.

    Tetap mempertahankan timer_h/timer_m/timer_s untuk kompatibilitas UI lama,
    tetapi engine CBT harus membaca total detik agar durasi 1-23 jam tidak
    terpotong menjadi timer_m saja.
    """
    cfg = dict(config or {})
    try:
        stored_seconds = cfg.get("timer_seconds")
        stored_total = int(stored_seconds or 0) if stored_seconds is not None else 0
        h = max(0, int(cfg.get("timer_h", 0) or 0))
        m = max(0, int(cfg.get("timer_m", 0) or 0))
        sec = max(0, int(cfg.get("timer_s", 0) or 0))
        component_total = h * 3600 + m * 60 + sec
        # timer_seconds menjadi sumber utama bila bernilai positif. Bila 0
        # tetapi komponen jam/menit/detik berisi nilai, pulihkan dari komponen
        # agar konfigurasi lama yang tidak konsisten tidak berubah menjadi
        # "tanpa batas waktu".
        total = stored_total if stored_total > 0 else component_total
    except (TypeError, ValueError):
        total = 0

    cfg["timer_seconds"] = total
    cfg["timer_h"] = total // 3600
    cfg["timer_m"] = (total % 3600) // 60
    cfg["timer_s"] = total % 60
    return cfg


def _split_option_label(value: str, fallback_index: int = 0):
    text = str(value or "").strip()
    match = re.match(r"^\s*([A-Ea-e])\s*[\.\)\:\-]\s*(.*)$", text, flags=re.DOTALL)
    if match:
        return match.group(1).upper(), match.group(2).strip()
    fallback = chr(65 + fallback_index)
    return fallback, text


def normalize_quiz_options(options, jenjang: str):
    """Normalisasi label opsi ke A. ... / B. ... tanpa mengubah isi pilihan."""
    expected = option_labels_for_jenjang(jenjang)
    normalized = []
    for idx, raw in enumerate(options or []):
        label, body = _split_option_label(raw, idx)
        normalized.append(f"{label}. {body}" if body else f"{label}.")
    return normalized, expected


def _is_arabic_subject(mapel: str, bahasa: str = "") -> bool:
    hay = f"{mapel or ''} {bahasa or ''}".lower()
    keys = (
        "bahasa arab", "nahwu", "sharaf", "qawaid", "muhadatsah",
        "insya", "balaghah", "mufradat", "qiraah", "qiroah", "imla"
    )
    return any(k in hay for k in keys)


def _is_religious_subject(mapel: str, konteks: str = "") -> bool:
    hay = f"{mapel or ''} {konteks or ''}".lower()
    keys = (
        "fiqih", "fikih", "aqidah", "akidah", "akhlak", "al-qur", "alqur",
        "hadis", "hadits", "ski", "sejarah kebudayaan islam", "keislaman",
        "ushul", "tarikh", "waris", "zakat", "ibadah"
    )
    return any(k in hay for k in keys)


def build_language_guidance(mapel: str, bahasa: str = "", konteks: str = "", source_pack: dict | None = None) -> str:
    """Instruksi bahasa yang tegas tetapi hanya mengaktifkan Arab penuh pada konteks yang relevan."""
    arabic_subject = _is_arabic_subject(mapel, bahasa)
    religious_subject = _is_religious_subject(mapel, konteks)
    if arabic_subject:
        return (
            "MODE BAHASA ARAB MADRASAH: Karena mata pelajaran/konfigurasi berhubungan langsung dengan Bahasa Arab, "
            "gunakan Bahasa Arab Fusha/Modern Standard Arabic yang natural, gramatikal, dan modern. Pertahankan seluruh "
            "teks soal, pilihan jawaban, dan solution_basis dalam aksara Arab; jangan gunakan transliterasi Latin. "
            "Gunakan harakat secara selektif pada kosakata/struktur yang berpotensi ambigu. Pertahankan simbol matematika "
            "dan satuan secara jelas. Untuk kutipan keagamaan, jangan mengarang teks Arab dan jangan memparafrasekan sebagai kutipan langsung."
        )
    if religious_subject:
        return (
            "MODE MATERI KEAGAMAAN: Bahasa utama mengikuti pilihan guru. Gunakan istilah, ungkapan, atau kutipan Arab asli "
            "hanya saat memang relevan dengan konsep/materi. Jika menyertakan teks Al-Qur'an, Hadis, doa, atau istilah Arab, "
            "tulis aksara Arab dengan benar dan jangan membuat kutipan Arab yang tidak didukung sumber. Sertakan penjelasan "
            "yang mudah dipahami dalam bahasa utama. Jangan memaksa seluruh soal menjadi Bahasa Arab."
        )
    return (
        "MODE UMUM MADRASAH: Gunakan bahasa utama yang dipilih guru. Bahasa Arab hanya digunakan untuk istilah yang memang "
        "relevan, bukan sebagai hiasan. Jangan menggunakan transliterasi Latin jika suatu istilah Arab asli memang diperlukan."
    )
