"""Quiz persistence repository.

SQL/schema behavior is preserved from the audited engine; this module owns persistence only.
"""
from __future__ import annotations
import json, os
import pandas as pd
try:
    from sqlalchemy import text
except Exception:
    text = None
from infrastructure.database.connection import init_db_connection
from infrastructure.ai.policy import normalize_custom_timer_config
def publish_custom_quiz_to_db(kode_kuis: str, config: dict, quiz_data: list) -> bool:
    config = normalize_custom_timer_config(config)
    conn = init_db_connection()
    if not conn: 
        return False

    query = """
    INSERT INTO kuis_custom (kode_kuis, config, quiz_data, created_at)
    VALUES (:kode, :cfg, :quiz, NOW() AT TIME ZONE 'Asia/Jakarta')
    ON CONFLICT (kode_kuis) DO UPDATE SET
        config = EXCLUDED.config,
        quiz_data = EXCLUDED.quiz_data;
    """
    try:
        with conn.session as s:
            s.execute(text(query), {
                "kode": kode_kuis.strip().upper(),
                "cfg": json.dumps(config, default=str),
                "quiz": json.dumps(quiz_data, default=str)
            })
            s.commit()
            return True
    except Exception as e:
        print(f"Error publish_custom_quiz_to_db: {e}")
        return False


def get_custom_quiz_from_db(kode_kuis: str):
    conn = init_db_connection()
    if not conn: 
        return None

    query = "SELECT config, quiz_data FROM kuis_custom WHERE UPPER(kode_kuis) = UPPER(:kode)"
    try:
        with conn.session as s:
            result = s.execute(text(query), {"kode": kode_kuis.strip()}).fetchone()
            if result:
                cfg = result[0] if isinstance(result[0], dict) else json.loads(result[0])
                cfg = normalize_custom_timer_config(cfg)
                quiz = result[1] if isinstance(result[1], list) else json.loads(result[1])
                return {"config": cfg, "quiz": quiz}
    except Exception as e:
        print(f"Error get_custom_quiz_from_db: {e}")
    return None


def check_active_session_from_db(nama_siswa: str, mapel: str):
    conn = init_db_connection()
    if not conn: 
        return None

    query = """
    SELECT id_sesi, detail_jawaban, created_at, soal_sekarang
    FROM sesi_ujian
    WHERE LOWER(TRIM(nama_siswa)) = LOWER(TRIM(:nama))
      AND (
          LOWER(TRIM(mapel)) = LOWER(TRIM(:mapel))
          OR LOWER(mapel) LIKE LOWER(:mapel_like)
      )
      AND status = 'BERJALAN'
    ORDER BY created_at DESC LIMIT 1;
    """
    try:
        with conn.session as s:
            res = s.execute(text(query), {
                "nama": nama_siswa.strip(), 
                "mapel": mapel.strip(),
                "mapel_like": f"%{mapel.strip()}%"
            }).fetchone()
            
            if res:
                detail_ans = res[1]
                if isinstance(detail_ans, str):
                    try:
                        detail_ans = json.loads(detail_ans)
                    except Exception:
                        detail_ans = []

                anti_cheat = None
                if isinstance(detail_ans, dict):
                    anti_cheat = detail_ans.get("anti_cheat")
                    detail_boolean = detail_ans.get("detail_boolean", [])
                    user_answers = detail_ans.get("user_answers", {})
                else:
                    detail_boolean = detail_ans
                    user_answers = {}

                return {
                    "id_sesi": res[0],
                    "detail_jawaban": detail_boolean if isinstance(detail_boolean, list) else [],
                    "user_answers": user_answers if isinstance(user_answers, dict) else {},
                    "anti_cheat": anti_cheat if isinstance(anti_cheat, dict) else None,
                    "created_at": res[2],
                    "soal_sekarang": res[3] if len(res) > 3 and res[3] is not None else 1
                }
    except Exception as e:
        print(f"Error check_active_session_from_db: {e}")
    return None


def load_session_review_from_db(session_id: str):
    """Membaca data sesi ujian dari Supabase untuk ditampilkan di Streamlit."""
    conn = init_db_connection()
    if not conn:
        return None

    query = "SELECT nama_siswa, jenjang, mapel, detail_jawaban, nilai_akhir FROM sesi_ujian WHERE id_sesi = :id"
    try:
        with conn.session as s:
            res = s.execute(text(query), {"id": session_id.strip()}).fetchone()
            if res:
                nama, jenjang, mapel, detail_raw, nilai = res
                
                # Parsing detail_jawaban (apakah berupa dict payload baru atau list boolean lama)
                if isinstance(detail_raw, dict):
                    payload = detail_raw
                elif isinstance(detail_raw, str):
                    try:
                        payload = json.loads(detail_raw)
                    except Exception:
                        payload = {}
                else:
                    payload = {}

                if isinstance(payload, dict):
                    raw_user_answers = payload.get("user_answers", {})
                    quiz_data = payload.get("quiz_data", [])
                else:
                    raw_user_answers = {}
                    quiz_data = []

                # Format ulang key dictionary ke integer agar cocok dengan state Streamlit
                formatted_user_answers = {}
                for k, v in raw_user_answers.items():
                    try:
                        formatted_user_answers[int(k)] = v
                    except ValueError:
                        formatted_user_answers[k] = v

                return {
                    "nama": nama,
                    "jenjang": jenjang or "MA",
                    "mapel": mapel.replace(" (Quiz)", "") if mapel else "Kuis",
                    "quiz_data": quiz_data,
                    "user_answers": formatted_user_answers,
                    "nilai": nilai
                }
    except Exception as e:
        print(f"Error load_session_review_from_db: {e}")
    return None
