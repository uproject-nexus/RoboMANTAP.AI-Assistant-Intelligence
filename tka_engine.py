from __future__ import annotations

import json
import os
import random
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from ai_engine import (
    init_db_connection,
    get_gemini_clients,
    option_labels_for_jenjang,
    option_count_for_jenjang,
    normalize_quiz_options,
    clean_json_text,
    _split_option_label,
)

TKA_TOTAL_QUESTIONS = 30
TKA_DEFAULT_DURATION_SECONDS = 90 * 60
TKA_DEFAULT_ACTIVE_HOURS = 24
TKA_IMAGE_MAX_BYTES = 8 * 1024 * 1024
TKA_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
TKA_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")


def _now_wib_naive() -> datetime:
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)


def _json(value: Any, default: Any):
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def normalize_tka_jenjang(value: str) -> str:
    raw = str(value or "MTs").strip().lower()
    if "ma" in raw or "aliyah" in raw:
        return "MA"
    return "MTs"


def tka_option_labels(jenjang: str) -> tuple[str, ...]:
    return option_labels_for_jenjang(normalize_tka_jenjang(jenjang))


def tka_mapel_name(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "").strip())
    return value[:80] or "Matematika"


def ensure_tka_tables() -> bool:
    conn = init_db_connection()
    if not conn:
        return False
    statements = [
        """
        CREATE TABLE IF NOT EXISTS tka_custom (
            kode_tka VARCHAR(40) PRIMARY KEY,
            config JSONB NOT NULL DEFAULT '{}'::jsonb,
            tka_data JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS tka_image_library (
            image_id UUID PRIMARY KEY,
            source_type VARCHAR(20) NOT NULL DEFAULT 'GURU',
            owner_key VARCHAR(180),
            filename VARCHAR(255) NOT NULL,
            mime_type VARCHAR(80) NOT NULL,
            image_data BYTEA NOT NULL,
            jenjang VARCHAR(40),
            mapel VARCHAR(100),
            topic VARCHAR(160),
            tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_tka_image_library_source ON tka_image_library(source_type, is_active)",
        "CREATE INDEX IF NOT EXISTS idx_tka_image_library_owner ON tka_image_library(owner_key, is_active)",
    ]
    try:
        with conn.session as s:
            for statement in statements:
                s.execute(text(statement))
            s.commit()
        return True
    except Exception as exc:
        print(f"[TKA DB INIT] {exc}")
        return False


def save_tka_image(
    *,
    data: bytes,
    filename: str,
    mime_type: str,
    source_type: str,
    owner_key: str = "",
    jenjang: str = "",
    mapel: str = "",
    topic: str = "",
    tags: list[str] | None = None,
) -> str | None:
    if not data or len(data) > TKA_IMAGE_MAX_BYTES or mime_type not in TKA_IMAGE_MIME_TYPES:
        return None
    image_id = str(uuid.uuid4())
    conn = init_db_connection()
    if not conn:
        return None
    query = """
    INSERT INTO tka_image_library
      (image_id, source_type, owner_key, filename, mime_type, image_data,
       jenjang, mapel, topic, tags, is_active, created_at, updated_at)
    VALUES
      (:id, :source, :owner, :filename, :mime, :data, :jenjang, :mapel,
       :topic, :tags, TRUE, NOW() AT TIME ZONE 'Asia/Jakarta', NOW() AT TIME ZONE 'Asia/Jakarta')
    """
    try:
        with conn.session as s:
            s.execute(text(query), {
                "id": image_id,
                "source": "SYSTEM" if str(source_type).upper() == "SYSTEM" else "GURU",
                "owner": owner_key[:180] if owner_key else None,
                "filename": os.path.basename(filename)[:255],
                "mime": mime_type,
                "data": data,
                "jenjang": normalize_tka_jenjang(jenjang) if jenjang else None,
                "mapel": tka_mapel_name(mapel) if mapel else None,
                "topic": str(topic or "")[:160] or None,
                "tags": json.dumps(tags or []),
            })
            s.commit()
        return image_id
    except Exception as exc:
        print(f"[TKA IMAGE SAVE] {exc}")
        return None


def list_tka_images(source_type: str | None = None, owner_key: str | None = None, jenjang: str | None = None, mapel: str | None = None, limit: int = 100) -> list[dict]:
    conn = init_db_connection()
    if not conn:
        return []
    clauses = ["is_active = TRUE"]
    params: dict[str, Any] = {"limit": max(1, min(int(limit), 500))}
    if source_type:
        clauses.append("source_type = :source_type")
        params["source_type"] = source_type.upper()
    if owner_key:
        clauses.append("(source_type = 'SYSTEM' OR LOWER(owner_key) = LOWER(:owner_key))")
        params["owner_key"] = owner_key
    if jenjang:
        clauses.append("(jenjang IS NULL OR jenjang = :jenjang)")
        params["jenjang"] = normalize_tka_jenjang(jenjang)
    if mapel:
        clauses.append("(mapel IS NULL OR LOWER(mapel) = LOWER(:mapel))")
        params["mapel"] = tka_mapel_name(mapel)
    query = f"""
      SELECT image_id, source_type, owner_key, filename, mime_type, jenjang, mapel,
             topic, tags, created_at
      FROM tka_image_library
      WHERE {' AND '.join(clauses)}
      ORDER BY created_at DESC
      LIMIT :limit
    """
    try:
        with conn.session as s:
            rows = s.execute(text(query), params).mappings().all()
        return [dict(r) for r in rows]
    except Exception as exc:
        print(f"[TKA IMAGE LIST] {exc}")
        return []


def _coerce_image_bytes(image_data: Any) -> bytes | None:
    """Normalize PostgreSQL BYTEA values for Streamlit/FastAPI/Gemini consumers."""
    if image_data is None:
        return None
    if isinstance(image_data, memoryview):
        return image_data.tobytes()
    if isinstance(image_data, bytearray):
        return bytes(image_data)
    if isinstance(image_data, bytes):
        return image_data
    try:
        return bytes(image_data)
    except Exception:
        return None


def get_tka_image(image_id: str) -> dict | None:
    conn = init_db_connection()
    if not conn:
        return None
    try:
        with conn.session as s:
            row = s.execute(text("""
                SELECT image_id, source_type, owner_key, filename, mime_type, image_data,
                       jenjang, mapel, topic, tags, created_at
                FROM tka_image_library
                WHERE image_id = :id AND is_active = TRUE
                LIMIT 1
            """), {"id": str(image_id)}).mappings().first()
        if not row:
            return None
        record = dict(row)
        record["image_data"] = _coerce_image_bytes(record.get("image_data"))
        return record
    except Exception as exc:
        print(f"[TKA IMAGE GET] {exc}")
        return None


def delete_tka_image(image_id: str, owner_key: str | None = None, allow_system: bool = False) -> bool:
    conn = init_db_connection()
    if not conn:
        return False
    clauses = ["image_id = :id", "is_active = TRUE"]
    params = {"id": str(image_id)}
    if not allow_system:
        clauses.append("source_type = 'GURU'")
        if owner_key:
            clauses.append("LOWER(owner_key) = LOWER(:owner)")
            params["owner"] = owner_key
    try:
        with conn.session as s:
            result = s.execute(text(f"UPDATE tka_image_library SET is_active = FALSE, updated_at = NOW() AT TIME ZONE 'Asia/Jakarta' WHERE {' AND '.join(clauses)}"), params)
            s.commit()
            return result.rowcount > 0
    except Exception as exc:
        print(f"[TKA IMAGE DELETE] {exc}")
        return False


def _image_part(data: bytes, mime_type: str):
    try:
        from google.genai import types
        return types.Part.from_bytes(data=data, mime_type=mime_type)
    except Exception:
        return None


def _tka_prompt(*, jenjang: str, mapel: str, image_count: int, questions_per_image: int) -> str:
    labels = tka_option_labels(jenjang)
    return f"""
Anda adalah Question Architect TKA RoboMANTAP untuk {jenjang}.
Buat tepat {questions_per_image} soal Pilihan Ganda TKA untuk satu stimulus gambar.
Mata pelajaran: {mapel}.
Jumlah opsi WAJIB tepat {len(labels)} dengan label {', '.join(labels)}.

KARAKTER TKA:
- Soal berbasis penalaran, literasi/numerasi, analisis data, interpretasi visual, dan pemecahan masalah sesuai materi mapel.
- Gunakan stimulus gambar sebagai sumber utama fakta. Jangan mengarang detail visual yang tidak tampak.
- Satu stimulus dapat melahirkan beberapa soal yang saling independen tetapi tetap mengacu pada gambar.
- Utamakan C4-C6 bila relevan; jangan memaksakan level jika tidak cocok dengan materi.
- Jangan membuat soal matching/menjodohkan, isian, atau uraian.
- MTs/SMP wajib A-D. MA/SMA wajib A-E.
- Hanya satu jawaban benar.
- correct_answer harus persis sama dengan opsi lengkap.
- Gunakan LaTeX $...$ hanya untuk rumus/pecahan/akar/variabel matematika.
- Jangan menaruh teks biasa di dalam delimiter matematika.
- Setiap soal harus memiliki topic, cognitive_level, solution_basis.

OUTPUT JSON MURNI:
{{
  "questions": [
    {{
      "id": 1,
      "question": "...",
      "options": [{', '.join([f'"{x}. ..."' for x in labels])}],
      "correct_answer": "{labels[0]}. ...",
      "topic": "...",
      "cognitive_level": "C4",
      "solution_basis": "..."
    }}
  ]
}}
"""


def _normalize_tka_questions(raw_questions: Any, jenjang: str, image_id: str | None) -> list[dict]:
    labels = tka_option_labels(jenjang)
    count = len(labels)
    if not isinstance(raw_questions, list):
        return []
    out = []
    for idx, item in enumerate(raw_questions, 1):
        if not isinstance(item, dict):
            return []
        question = str(item.get("question", "")).strip()
        raw_options = item.get("options", [])
        answer = str(item.get("correct_answer", "")).strip()
        if not question or not isinstance(raw_options, list):
            return []
        options, _ = normalize_quiz_options(raw_options, jenjang)
        if len(options) != count:
            return []
        label, _ = _split_option_label(answer, 0)
        correct = next((o for o in options if o.startswith(f"{label}.")), None)
        if correct is None and answer in options:
            correct = answer
        if correct is None:
            return []
        out.append({
            "id": idx,
            "question": question,
            "options": options,
            "correct_answer": correct,
            "topic": str(item.get("topic") or "TKA").strip()[:120],
            "cognitive_level": str(item.get("cognitive_level") or "C4").strip()[:10],
            "solution_basis": str(item.get("solution_basis") or "").strip(),
            "image_id": image_id,
        })
    return out


def generate_tka_questions_for_image(*, jenjang: str, mapel: str, mapel_type: str = "Wajib", image_id: str | None, image_data: bytes | None, mime_type: str | None, count: int = 6) -> list[dict]:
    clients = get_gemini_clients()
    if not clients:
        return []
    contents: list[Any] = []
    prompt = _tka_prompt(jenjang=normalize_tka_jenjang(jenjang), mapel=tka_mapel_name(mapel) + f" (Mapel {mapel_type})", image_count=1 if image_data else 0, questions_per_image=count)
    if image_data and mime_type:
        part = _image_part(image_data, mime_type)
        if part is not None:
            contents.append(part)
            contents.append("Gambar di atas adalah stimulus TKA. Analisis hanya informasi yang benar-benar terlihat pada gambar.")
    contents.append(prompt)
    for client in clients:
        for model in TKA_MODELS:
            try:
                from google.genai import types
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.3,
                    ),
                )
                raw = getattr(response, "text", "") or ""
                try:
                    data = json.loads(clean_json_text(raw), strict=False)
                except Exception:
                    m = re.search(r"\{.*\}", raw, flags=re.S)
                    data = json.loads(m.group(0), strict=False) if m else {}
                normalized = _normalize_tka_questions(data.get("questions", []), jenjang, image_id)
                if len(normalized) == count:
                    return normalized
            except Exception as exc:
                print(f"[TKA AI] {type(exc).__name__}: {exc}")
                continue
    return []


def generate_tka_30(*, jenjang: str, mapel: str, mapel_type: str = "Wajib", image_ids: list[str] | None = None) -> list[dict]:
    """Generate exactly 30 image-grounded TKA questions: up to five stimuli × six questions."""
    jenjang = normalize_tka_jenjang(jenjang)
    mapel = tka_mapel_name(mapel)
    selected = list(dict.fromkeys(image_ids or []))[:5]
    if not selected:
        selected = [str(x["image_id"]) for x in list_tka_images(source_type="SYSTEM", jenjang=jenjang, mapel=mapel, limit=5)]
    if not selected:
        selected = [str(x["image_id"]) for x in list_tka_images(source_type="SYSTEM", jenjang=jenjang, limit=5)]
    if not selected:
        return []

    image_records = []
    for image_id in selected:
        record = get_tka_image(image_id)
        if record:
            image_records.append(record)
    image_records = image_records[:5]
    all_questions: list[dict] = []
    for record in image_records:
        batch = generate_tka_questions_for_image(
            jenjang=jenjang, mapel=mapel, mapel_type=mapel_type, image_id=str(record["image_id"]),
            image_data=record.get("image_data"), mime_type=record.get("mime_type"), count=6,
        )
        if len(batch) != 6:
            continue
        all_questions.extend(batch)
    if len(all_questions) < TKA_TOTAL_QUESTIONS:
        return []
    for idx, question in enumerate(all_questions[:TKA_TOTAL_QUESTIONS], 1):
        question["id"] = idx
    return all_questions[:TKA_TOTAL_QUESTIONS]


def validate_tka_30(questions: list[dict], jenjang: str) -> tuple[bool, str]:
    if not isinstance(questions, list) or len(questions) != TKA_TOTAL_QUESTIONS:
        return False, f"TKA wajib tepat {TKA_TOTAL_QUESTIONS} soal."
    labels = tka_option_labels(jenjang)
    for idx, q in enumerate(questions, 1):
        if not isinstance(q, dict) or not str(q.get("question", "")).strip():
            return False, f"Soal nomor {idx} tidak valid."
        options = q.get("options")
        if not isinstance(options, list) or len(options) != len(labels):
            return False, f"Soal nomor {idx} harus memiliki tepat {len(labels)} opsi ({'/'.join(labels)})."
        if not str(q.get("correct_answer", "")).strip() or q.get("correct_answer") not in options:
            return False, f"Kunci soal nomor {idx} tidak valid."
    return True, "OK"


def publish_tka_to_db(kode_tka: str, config: dict, questions: list[dict]) -> bool:
    ok, reason = validate_tka_30(questions, config.get("jenjang", "MTs"))
    if not ok:
        print(f"[TKA PUBLISH] {reason}")
        return False
    code = re.sub(r"[^A-Z0-9_-]", "", str(kode_tka or "").upper())[:40]
    if not code:
        return False
    active_from = config.get("active_from") or _now_wib_naive().isoformat()
    active_until = config.get("active_until") or (_now_wib_naive() + timedelta(hours=TKA_DEFAULT_ACTIVE_HOURS)).isoformat()
    cfg = {
        **config,
        "jenis": "TKA",
        "total_soal": TKA_TOTAL_QUESTIONS,
        "jenjang": normalize_tka_jenjang(config.get("jenjang", "MTs")),
        "mapel": tka_mapel_name(config.get("mapel", "Matematika")),
        "timer_seconds": int(config.get("timer_seconds") or TKA_DEFAULT_DURATION_SECONDS),
        "active_from": active_from,
        "active_until": active_until,
    }
    conn = init_db_connection()
    if not conn:
        return False
    try:
        with conn.session as s:
            s.execute(text("""
                INSERT INTO tka_custom (kode_tka, config, tka_data, created_at, updated_at)
                VALUES (:code, :cfg, :data, NOW() AT TIME ZONE 'Asia/Jakarta', NOW() AT TIME ZONE 'Asia/Jakarta')
                ON CONFLICT (kode_tka) DO UPDATE SET
                  config = EXCLUDED.config,
                  tka_data = EXCLUDED.tka_data,
                  updated_at = NOW() AT TIME ZONE 'Asia/Jakarta'
            """), {"code": code, "cfg": json.dumps(cfg, default=str), "data": json.dumps(questions, default=str)})
            s.commit()
        return True
    except Exception as exc:
        print(f"[TKA PUBLISH] {exc}")
        return False


def get_tka_from_db(kode_tka: str) -> dict | None:
    conn = init_db_connection()
    if not conn:
        return None
    try:
        with conn.session as s:
            row = s.execute(text("SELECT config, tka_data FROM tka_custom WHERE UPPER(kode_tka)=UPPER(:code) LIMIT 1"), {"code": str(kode_tka).strip()}).mappings().first()
        if not row:
            return None
        return {"config": _json(row["config"], {}), "tka": _json(row["tka_data"], [])}
    except Exception as exc:
        print(f"[TKA GET] {exc}")
        return None


def update_tka_progress(
    *, session_id: str, nama: str, jenjang: str, mapel: str, soal_sekarang: int,
    detail_jawaban: list, status: str = "BERJALAN", user_answers: dict | None = None,
    questions: list | None = None, anti_cheat: dict | None = None,
) -> bool:
    conn = init_db_connection()
    if not conn:
        return False
    detail = detail_jawaban if isinstance(detail_jawaban, list) else []
    total = len(detail) or (len(questions) if isinstance(questions, list) else TKA_TOTAL_QUESTIONS)
    benar = sum(1 for x in detail if x is True)
    salah = sum(1 for x in detail if x is False)
    nilai = int(round(benar / total * 100)) if total else 0
    payload = {
        "activity_type": "TKA",
        "detail_boolean": detail,
        "user_answers": user_answers or {},
        "quiz_data": questions or [],
    }
    if anti_cheat is not None:
        payload["anti_cheat"] = anti_cheat
    mapel_db = mapel if "(TKA)" in mapel else f"{mapel} (TKA)"
    query = """
    INSERT INTO sesi_ujian
      (id_sesi, nama_siswa, jenjang, mapel, soal_sekarang, detail_jawaban,
       jumlah_benar, jumlah_salah, nilai_akhir, status, created_at, updated_at)
    VALUES
      (:id, :nama, :jenjang, :mapel, :soal, :detail, :benar, :salah, :nilai, :status,
       NOW() AT TIME ZONE 'Asia/Jakarta', NOW() AT TIME ZONE 'Asia/Jakarta')
    ON CONFLICT (id_sesi) DO UPDATE SET
      nama_siswa=EXCLUDED.nama_siswa,
      jenjang=EXCLUDED.jenjang,
      mapel=EXCLUDED.mapel,
      soal_sekarang=EXCLUDED.soal_sekarang,
      detail_jawaban=EXCLUDED.detail_jawaban,
      jumlah_benar=EXCLUDED.jumlah_benar,
      jumlah_salah=EXCLUDED.jumlah_salah,
      nilai_akhir=EXCLUDED.nilai_akhir,
      status=CASE WHEN sesi_ujian.status IN ('SELESAI','TRIAL','ARCHIVED') THEN sesi_ujian.status ELSE EXCLUDED.status END,
      created_at=sesi_ujian.created_at,
      updated_at=CASE WHEN sesi_ujian.status IN ('SELESAI','TRIAL','ARCHIVED') THEN sesi_ujian.updated_at ELSE NOW() AT TIME ZONE 'Asia/Jakarta' END
    """
    try:
        with conn.session as s:
            s.execute(text(query), {
                "id": session_id, "nama": nama, "jenjang": normalize_tka_jenjang(jenjang),
                "mapel": mapel_db, "soal": int(soal_sekarang or 1),
                "detail": json.dumps(payload, default=str), "benar": benar,
                "salah": salah, "nilai": nilai, "status": status,
            })
            s.commit()
        return True
    except Exception as exc:
        print(f"[TKA PROGRESS] {exc}")
        return False


def touch_tka_heartbeat(session_id: str) -> bool:
    conn = init_db_connection()
    if not conn:
        return False
    try:
        with conn.session as s:
            s.execute(text("UPDATE sesi_ujian SET updated_at=NOW() AT TIME ZONE 'Asia/Jakarta' WHERE id_sesi=:id AND status='BERJALAN'"), {"id": session_id})
            s.commit()
        return True
    except Exception:
        return False
