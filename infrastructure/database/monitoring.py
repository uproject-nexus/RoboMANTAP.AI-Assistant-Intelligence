"""CBT progress and heartbeat persistence."""
from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
try:
    from sqlalchemy import text
except Exception:
    text = None
from infrastructure.database.connection import init_db_connection
def update_progress_siswa(
    session_id: str,
    nama: str,
    jenjang: str,
    mapel: str,
    soal_sekarang: int,
    detail_jawaban: list,
    status: str = "BERJALAN",
    is_custom: bool = False,
    user_answers_dict: dict = None,
    quiz_data_list: list = None,
    anti_cheat: dict = None
):
    """
    Menyimpan progress CBT dengan proteksi state final.

    Prinsip penting:
    - created_at hanya dibuat saat INSERT pertama.
    - Sesi SELESAI / TRIAL / ARCHIVED tidak boleh hidup kembali menjadi BERJALAN.
    - Metadata anti-cheat dipertahankan walau save-answer berikutnya datang terlambat.
    - Format detail_jawaban tetap kompatibel dengan format list lama.
    """
    conn = init_db_connection()
    if not conn:
        return False

    mapel_db = f"{mapel} (Quiz)" if (is_custom and "(Quiz)" not in mapel) else mapel

    detail_jawaban = detail_jawaban if isinstance(detail_jawaban, list) else []
    total_soal = len(detail_jawaban) if detail_jawaban else (
        len(quiz_data_list) if isinstance(quiz_data_list, list) and quiz_data_list else 10
    )
    jumlah_benar = sum(1 for x in detail_jawaban if x is True)
    jumlah_salah = sum(1 for x in detail_jawaban if x is False)

    if is_custom:
        nilai_akhir = int(round((jumlah_benar / total_soal) * 100)) if total_soal > 0 else 0
    else:
        nilai_akhir = (jumlah_benar * 4) - (jumlah_salah * 1)

    # Ambil metadata anti-cheat sebelumnya agar tidak hilang karena save-answer biasa.
    existing_anti_cheat = None
    try:
        with conn.session as s:
            existing = s.execute(
                text("""
                    SELECT detail_jawaban
                    FROM sesi_ujian
                    WHERE id_sesi = :id_sesi
                    LIMIT 1
                """),
                {"id_sesi": session_id},
            ).fetchone()

        if existing:
            raw_existing = existing[0]
            if isinstance(raw_existing, str):
                try:
                    raw_existing = json.loads(raw_existing)
                except Exception:
                    raw_existing = None

            if isinstance(raw_existing, dict):
                existing_anti_cheat = raw_existing.get("anti_cheat")
    except Exception as e:
        print(f"[DB WARN] Gagal membaca metadata anti-cheat lama: {e}")

    effective_anti_cheat = anti_cheat if isinstance(anti_cheat, dict) else existing_anti_cheat

    # Payload JSONB.
    # Tanpa metadata tambahan, format list lama tetap dipertahankan untuk kompatibilitas.
    if user_answers_dict is not None or quiz_data_list is not None or effective_anti_cheat is not None:
        payload = {
            "detail_boolean": detail_jawaban,
            "user_answers": user_answers_dict or {},
            "quiz_data": quiz_data_list or [],
        }

        if effective_anti_cheat is not None:
            payload["anti_cheat"] = effective_anti_cheat

        detail_json = json.dumps(payload, default=str)
    else:
        detail_json = json.dumps(detail_jawaban)

    query = """
    INSERT INTO sesi_ujian (
        id_sesi, nama_siswa, jenjang, mapel, soal_sekarang, detail_jawaban,
        jumlah_benar, jumlah_salah, nilai_akhir, status, created_at, updated_at
    )
    VALUES (
        :id_sesi, :nama, :jenjang, :mapel, :soal, :detail,
        :benar, :salah, :nilai, :status,
        NOW() AT TIME ZONE 'Asia/Jakarta',
        NOW() AT TIME ZONE 'Asia/Jakarta'
    )
    ON CONFLICT (id_sesi) DO UPDATE SET
        nama_siswa = EXCLUDED.nama_siswa,
        jenjang = EXCLUDED.jenjang,
        mapel = EXCLUDED.mapel,
        soal_sekarang = EXCLUDED.soal_sekarang,
        detail_jawaban = EXCLUDED.detail_jawaban,
        jumlah_benar = EXCLUDED.jumlah_benar,
        jumlah_salah = EXCLUDED.jumlah_salah,
        nilai_akhir = EXCLUDED.nilai_akhir,
    
        -- created_at adalah WAKTU MULAI.
        -- Jangan pernah mengambil created_at dari request/update berikutnya.
        created_at = sesi_ujian.created_at,
    
        -- Status final tidak boleh hidup kembali menjadi BERJALAN.
        status = CASE
            WHEN sesi_ujian.status IN ('SELESAI', 'TRIAL', 'ARCHIVED')
                THEN sesi_ujian.status
            ELSE EXCLUDED.status
        END,
    
        -- Untuk sesi aktif: heartbeat/save-answer memperbarui updated_at.
        -- Untuk sesi final: waktu selesai dikunci.
        updated_at = CASE
            WHEN sesi_ujian.status IN ('SELESAI', 'TRIAL', 'ARCHIVED')
                THEN sesi_ujian.updated_at
            ELSE
                NOW() AT TIME ZONE 'Asia/Jakarta'
        END;
    """

    try:
        with conn.session as s:
            s.execute(
                text(query),
                {
                    "id_sesi": session_id,
                    "nama": nama,
                    "jenjang": jenjang,
                    "mapel": mapel_db,
                    "soal": int(soal_sekarang or 1),
                    "detail": detail_json,
                    "benar": jumlah_benar,
                    "salah": jumlah_salah,
                    "nilai": nilai_akhir,
                    "status": status,
                },
            )
            s.commit()
        return True
    except Exception as e:
        print(f"Error update_progress_siswa: {e}")
        return False


def touch_session_heartbeat(session_id: str) -> bool:
    """Memperbarui heartbeat sesi aktif tanpa mengubah status final."""
    conn = init_db_connection()
    if not conn:
        return False

    query = """
    UPDATE sesi_ujian
    SET updated_at = NOW() AT TIME ZONE 'Asia/Jakarta'
    WHERE id_sesi = :id_sesi
      AND status = 'BERJALAN';
    """

    try:
        with conn.session as s:
            s.execute(text(query), {"id_sesi": session_id})
            s.commit()
        return True
    except Exception as e:
        print(f"Error touch_session_heartbeat: {e}")
        return False
