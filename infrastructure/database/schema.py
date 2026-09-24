"""Database schema bootstrap extracted from the audited application.

No schema redesign is performed in stage 2; this is a direct responsibility
move so later repository modules can own individual tables.
"""
from __future__ import annotations
from infrastructure.database.connection import init_db_connection


def create_table_if_not_exists() -> None:
    conn = init_db_connection()
    if not conn:
        return
    query = """
    CREATE TABLE IF NOT EXISTS sesi_ujian (
        id_sesi VARCHAR(100) PRIMARY KEY,
        nama_siswa VARCHAR(100) NOT NULL,
        jenjang VARCHAR(50),
        mapel VARCHAR(50),
        soal_sekarang INT DEFAULT 1,
        detail_jawaban JSONB DEFAULT '[]'::jsonb,
        jumlah_benar INT DEFAULT 0,
        jumlah_salah INT DEFAULT 0,
        nilai_akhir INT DEFAULT 0,
        status VARCHAR(20) DEFAULT 'BERJALAN',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS kuis_custom (
        kode_kuis VARCHAR(20) PRIMARY KEY,
        config JSONB NOT NULL,
        quiz_data JSONB NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS material_hub (
        bundle_code VARCHAR(32) PRIMARY KEY,
        config JSONB DEFAULT '{}'::jsonb,
        bundle_data JSONB NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    try:
        if hasattr(conn, "engine"):
            with conn.engine.begin() as connection:
                for statement in [q.strip() for q in query.split(";") if q.strip()]:
                    connection.exec_driver_sql(statement)
        else:
            conn.query(query)
    except Exception as exc:
        print(f"Gagal bootstrap schema: {exc}")
