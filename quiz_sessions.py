"""Database-backed quiz-session ordering and persistence helpers."""
import hashlib
import json
import random
from sqlalchemy import text
from ai_engine import init_db_connection

def _quiz_signature(quiz_data):
    """Fingerprint master quiz agar urutan tidak tertukar ketika paket berubah."""
    payload = []
    for idx, q in enumerate(quiz_data):
        payload.append({
            "id": q.get("id", idx + 1),
            "question": q.get("question", ""),
            "options": q.get("options", []),
            "correct_answer": q.get("correct_answer", ""),
        })
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _quiz_question_ids(quiz_data):
    """ID logis soal. Jika ID generator tidak valid/duplikat, gunakan indeks."""
    ids = []
    seen = set()
    for idx, q in enumerate(quiz_data):
        candidate = str(q.get("id", idx + 1))
        if not candidate or candidate in seen:
            candidate = f"IDX-{idx + 1}"
        seen.add(candidate)
        ids.append(candidate)
    return ids

def build_stable_student_quiz_order(quiz_data, session_id, question_order=None):
    """
    Mengembalikan quiz dalam urutan siswa yang stabil.
    question_order adalah daftar ID soal yang sudah disimpan di database.
    Fallback memakai seed session_id untuk kompatibilitas sesi lama.
    """
    if not quiz_data:
        return []

    if question_order:
        by_id = {str(q.get("id", i + 1)): q for i, q in enumerate(quiz_data)}
        ordered = [by_id[qid] for qid in map(str, question_order) if qid in by_id]
        if len(ordered) == len(quiz_data):
            return ordered

    # Fallback kompatibilitas dengan implementasi randomisasi sebelumnya.
    shuffled = list(quiz_data)
    random.Random(str(session_id)).shuffle(shuffled)
    return shuffled

def ensure_quiz_session_order_table():
    """
    Memastikan tabel persistensi urutan soal tersedia.

    Catatan penting: Streamlit SQLConnection/SQLAlchemy tidak selalu menerima
    beberapa statement DDL dalam satu execute(). Karena itu CREATE TABLE dan
    CREATE INDEX dijalankan terpisah agar kompatibel dengan deployment
    PostgreSQL/Supabase yang digunakan RoboMANTAP.
    """
    conn = init_db_connection()
    if conn is None:
        print("LOG DB quiz order init: koneksi PostgreSQL tidak tersedia.")
        return False

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS kuis_session_orders (
        session_id VARCHAR(100) PRIMARY KEY,
        kode_kuis VARCHAR(20) NOT NULL,
        quiz_signature VARCHAR(64) NOT NULL,
        question_order JSONB NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """

    create_index_sql = """
    CREATE INDEX IF NOT EXISTS idx_kuis_session_orders_kode
        ON kuis_session_orders (kode_kuis)
    """

    try:
        with conn.session as s:
            # Jalankan DDL satu per satu. Jangan menggabungkannya dalam satu
            # execute() karena driver/deployment tertentu menolak multi-statement.
            s.execute(text(create_table_sql))
            s.commit()

            s.execute(text(create_index_sql))
            s.commit()

        return True
    except Exception as e:
        print(f"LOG DB quiz order init error: {type(e).__name__}: {e}")
        return False

def _get_saved_quiz_order(session_id, quiz_signature):
    conn = init_db_connection()
    if not conn:
        return None
    try:
        with conn.session as s:
            row = s.execute(
                text("""
                    SELECT question_order
                    FROM kuis_session_orders
                    WHERE session_id = :session_id
                      AND quiz_signature = :quiz_signature
                    LIMIT 1
                """),
                {"session_id": session_id, "quiz_signature": quiz_signature},
            ).fetchone()
            if row:
                return row[0] if isinstance(row[0], list) else json.loads(row[0])
    except Exception as e:
        print(f"LOG DB get quiz order error: {e}")
    return None

def get_or_create_student_quiz_order(kode_kuis, mapel, quiz_data, session_id):
    """
    Versi Super Cepat (Anti-Lag / Zero DB Lock):
    Mengacak urutan soal secara unik berdasarkan session_id siswa di memori lokal.
    """
    if not quiz_data:
        return [], None

    # Gunakan session_id sebagai Seed agar pengacakan unik per siswa 
    # tetapi tetap konsisten (tidak berubah-ubah saat rerun/refresh)
    shuffled = list(quiz_data)
    random.Random(str(session_id)).shuffle(shuffled)
    
    return shuffled, None

# Database Kisi-Kisi Operasional OMI 2026
