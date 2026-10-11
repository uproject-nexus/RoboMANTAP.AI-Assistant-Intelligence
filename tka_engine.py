from __future__ import annotations

import json
import os
import random
import re
import time
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

TKA_TOTAL_QUESTIONS = 15
# Generator dan Latihan Mandiri menggunakan 15 soal; request AI dibagi ke batch kecil.
# Nama generate_tka_30 dipertahankan untuk kompatibilitas pemanggil lama.
TKA_GENERATION_QUESTIONS = 15
TKA_GENERATION_MAX_ATTEMPTS = 3
TKA_GENERATION_MAX_IMAGES = 3
# Studio selalu menghasilkan tepat 15 soal, tetapi dikirim ke AI dalam
# tiga request kecil agar tidak terkena 504 DEADLINE_EXCEEDED.
TKA_STUDIO_BATCH_SIZE = 5
TKA_STUDIO_BATCH_TYPES = ("PG", "MCMA", "KATEGORI")
TKA_STUDIO_RETRY_BACKOFF_SECONDS = 1.5
TKA_DEFAULT_DURATION_SECONDS = 75 * 60
TKA_DEFAULT_ACTIVE_HOURS = 24
TKA_IMAGE_MAX_BYTES = 8 * 1024 * 1024
TKA_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
TKA_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")


def _now_wib_naive() -> datetime:
    return datetime.now(timezone.utc).astimezone(
        timezone(timedelta(hours=7))
    ).replace(tzinfo=None)


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


# Mata uji pilihan MA dan kebijakan stimulusnya. Kebijakan ini mengatur
# sumber gambar; gambar tetap opsional jika tidak ada asset yang cocok.
TKA_MA_PILIHAN_MAPELS = (
    "Matematika Lanjutan",
    "Bahasa Indonesia Lanjutan",
    "Bahasa Inggris Lanjutan",
    "Fisika", "Kimia", "Biologi", "Ekonomi", "Sosiologi",
    "Geografi", "Sejarah", "Antropologi",
    "PPKn / Pendidikan Pancasila", "PPKn/Pendidikan Pancasila",
    "Bahasa Arab", "Bahasa Jerman", "Bahasa Prancis",
    "Bahasa Jepang", "Bahasa Korea", "Bahasa Mandarin",
    "Produk / Projek Kreatif dan Kewirausahaan",
    "Produk/Projek Kreatif dan Kewirausahaan",
)

TKA_MA_ELECTIVE_IMAGE_SOURCES = {
    "matematikalanjutan": {"source_jenjang": "MA", "source_mapel": "Matematika"},
    "bahasaindonesialanjutan": {"source_jenjang": "MA", "source_mapel": "Bahasa Indonesia"},
    "bahasainggrislanjutan": {"source_jenjang": "MA", "source_mapel": "Bahasa Inggris"},
    "bahasaarab": {"source_jenjang": "MTs", "source_mapel": "Bahasa Arab"},
}

TKA_MA_ELECTIVE_TEXT_ONLY = {
    "fisika", "kimia", "biologi", "ekonomi", "sosiologi", "geografi",
    "sejarah", "antropologi", "ppknpendidikanpancasila", "bahasajerman",
    "bahasaprancis", "bahasajepang", "bahasakorea", "bahasamandarin",
    "produkprojekkreatifdankewirausahaan",
}

def _mapel_key(value: str) -> str:
    """Normalisasi nama mapel agar variasi spasi/tanda baca tetap dikenali."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

def tka_stimulus_policy(
    jenjang: str, mapel: str, mapel_type: str = "Wajib"
) -> dict[str, Any]:
    """Konfigurasi stimulus untuk jalur Studio maupun Latihan Mandiri."""
    level = normalize_tka_jenjang(jenjang)
    key = _mapel_key(mapel)
    if level == "MA" and key in TKA_MA_ELECTIVE_IMAGE_SOURCES:
        source = TKA_MA_ELECTIVE_IMAGE_SOURCES[key]
        return {
            "mode": "MAPPED_IMAGES",
            "source_jenjang": source["source_jenjang"],
            "source_mapel": source["source_mapel"],
            "max_images": 2,
            "is_elective": True,
        }
    if level == "MA" and key in TKA_MA_ELECTIVE_TEXT_ONLY:
        return {
            "mode": "TEXT_ONLY",
            "source_jenjang": None,
            "source_mapel": None,
            "max_images": 0,
            "is_elective": True,
        }
    return {
        "mode": "NORMAL",
        "source_jenjang": level,
        "source_mapel": tka_mapel_name(mapel),
        "max_images": TKA_GENERATION_MAX_IMAGES,
        "is_elective": False,
    }


def infer_tka_topic(
    filename: str,
    jenjang: str | None = None,
    mapel: str | None = None,
) -> str:
    """Fallback metadata: derive a readable stimulus topic from a descriptive filename."""
    stem = re.sub(
        r"\.[A-Za-z0-9]+$",
        "",
        os.path.basename(str(filename or "")),
    )
    stem = re.sub(r"[_]+", "-", stem)

    prefixes = []

    if mapel:
        prefixes.append(
            re.sub(
                r"[^a-z0-9]+",
                "-",
                tka_mapel_name(mapel).lower(),
            ).strip("-")
        )

    if jenjang:
        prefixes.append(
            normalize_tka_jenjang(jenjang).lower()
        )

    for prefix in prefixes:
        stem = re.sub(
            rf"^{re.escape(prefix)}(?:-+|$)",
            "",
            stem,
            flags=re.I,
        )

    stem = re.sub(r"[-_]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" -_")

    return stem[:160].strip().title() or "Stimulus TKA"


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
        """
        CREATE INDEX IF NOT EXISTS idx_tka_image_library_source
        ON tka_image_library(source_type, is_active)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_tka_image_library_owner
        ON tka_image_library(owner_key, is_active)
        """,
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

    if (
        not data
        or len(data) > TKA_IMAGE_MAX_BYTES
        or mime_type not in TKA_IMAGE_MIME_TYPES
    ):
        return None

    image_id = str(uuid.uuid4())

    conn = init_db_connection()

    if not conn:
        return None

    query = """
    INSERT INTO tka_image_library
      (
        image_id,
        source_type,
        owner_key,
        filename,
        mime_type,
        image_data,
        jenjang,
        mapel,
        topic,
        tags,
        is_active,
        created_at,
        updated_at
      )
    VALUES
      (
        :id,
        :source,
        :owner,
        :filename,
        :mime,
        :data,
        :jenjang,
        :mapel,
        :topic,
        :tags,
        TRUE,
        NOW() AT TIME ZONE 'Asia/Jakarta',
        NOW() AT TIME ZONE 'Asia/Jakarta'
      )
    """

    try:
        with conn.session as s:
            s.execute(
                text(query),
                {
                    "id": image_id,
                    "source": (
                        "SYSTEM"
                        if str(source_type).upper() == "SYSTEM"
                        else "GURU"
                    ),
                    "owner": owner_key[:180] if owner_key else None,
                    "filename": os.path.basename(filename)[:255],
                    "mime": mime_type,
                    "data": data,
                    "jenjang": (
                        normalize_tka_jenjang(jenjang)
                        if jenjang
                        else None
                    ),
                    "mapel": (
                        tka_mapel_name(mapel)
                        if mapel
                        else None
                    ),
                    "topic": (
                        str(topic or "").strip()[:160]
                        or infer_tka_topic(
                            filename,
                            jenjang,
                            mapel,
                        )
                    ),
                    "tags": json.dumps(tags or []),
                },
            )

            s.commit()

        return image_id

    except Exception as exc:
        print(f"[TKA IMAGE SAVE] {exc}")
        return None


def list_tka_images(
    source_type: str | None = None,
    owner_key: str | None = None,
    jenjang: str | None = None,
    mapel: str | None = None,
    search: str | None = None,
    limit: int = 100,
) -> list[dict]:

    conn = init_db_connection()

    if not conn:
        return []

    clauses = ["is_active = TRUE"]

    params: dict[str, Any] = {
        "limit": max(1, min(int(limit), 500))
    }

    if source_type:
        clauses.append("source_type = :source_type")
        params["source_type"] = source_type.upper()

    if owner_key:
        clauses.append(
            "(source_type = 'SYSTEM' OR LOWER(owner_key) = LOWER(:owner_key))"
        )
        params["owner_key"] = owner_key

    if jenjang:
        clauses.append("jenjang = :jenjang")
        params["jenjang"] = normalize_tka_jenjang(jenjang)

    if mapel:
        clauses.append("LOWER(mapel) = LOWER(:mapel)")
        params["mapel"] = tka_mapel_name(mapel)

    if search and str(search).strip():
        clauses.append(
            """
            (
                LOWER(filename) LIKE LOWER(:search)
                OR LOWER(COALESCE(topic, '')) LIKE LOWER(:search)
                OR CAST(
                    COALESCE(tags, '[]'::jsonb)
                    AS TEXT
                ) ILIKE :search
            )
            """
        )

        params["search"] = f"%{str(search).strip()}%"

    query = f"""
      SELECT
        image_id,
        source_type,
        owner_key,
        filename,
        mime_type,
        jenjang,
        mapel,
        topic,
        tags,
        created_at,
        updated_at
      FROM tka_image_library
      WHERE {' AND '.join(clauses)}
      ORDER BY created_at DESC
      LIMIT :limit
    """

    try:
        with conn.session as s:
            rows = (
                s.execute(text(query), params)
                .mappings()
                .all()
            )

        return [dict(r) for r in rows]

    except Exception as exc:
        print(f"[TKA IMAGE LIST] {exc}")
        return []


def backfill_tka_image_topics(limit: int = 500) -> int:
    """
    Fill blank topic metadata from the already-descriptive filename;
    no image bytes are changed.
    """

    conn = init_db_connection()

    if not conn:
        return 0

    try:
        with conn.session as s:
            rows = (
                s.execute(
                    text(
                        """
                        SELECT
                            image_id,
                            filename,
                            jenjang,
                            mapel
                        FROM tka_image_library
                        WHERE
                            is_active = TRUE
                            AND (
                                topic IS NULL
                                OR BTRIM(topic) = ''
                            )
                        ORDER BY created_at ASC
                        LIMIT :limit
                        """
                    ),
                    {
                        "limit": max(
                            1,
                            min(int(limit), 500),
                        )
                    },
                )
                .mappings()
                .all()
            )

            updated = 0

            for row in rows:
                topic = infer_tka_topic(
                    row.get("filename"),
                    row.get("jenjang"),
                    row.get("mapel"),
                )

                if topic:
                    result = s.execute(
                        text(
                            """
                            UPDATE tka_image_library
                            SET
                                topic = :topic,
                                updated_at =
                                    NOW()
                                    AT TIME ZONE 'Asia/Jakarta'
                            WHERE
                                image_id = :id
                                AND (
                                    topic IS NULL
                                    OR BTRIM(topic) = ''
                                )
                            """
                        ),
                        {
                            "id": str(row["image_id"]),
                            "topic": topic[:160],
                        },
                    )

                    updated += int(result.rowcount or 0)

            if updated:
                s.commit()

            return updated

    except Exception as exc:
        print(f"[TKA TOPIC BACKFILL] {exc}")
        return 0


def get_tka_image(image_id: str) -> dict | None:
    conn = init_db_connection()

    if not conn:
        return None

    try:
        with conn.session as s:
            row = (
                s.execute(
                    text(
                        """
                        SELECT
                            image_id,
                            source_type,
                            owner_key,
                            filename,
                            mime_type,
                            image_data,
                            jenjang,
                            mapel,
                            topic,
                            tags,
                            created_at
                        FROM tka_image_library
                        WHERE
                            image_id = :id
                            AND is_active = TRUE
                        LIMIT 1
                        """
                    ),
                    {"id": str(image_id)},
                )
                .mappings()
                .first()
            )

        result = dict(row) if row else None

        if result and isinstance(
            result.get("image_data"),
            memoryview,
        ):
            result["image_data"] = (
                result["image_data"].tobytes()
            )

        elif result and isinstance(
            result.get("image_data"),
            bytearray,
        ):
            result["image_data"] = bytes(
                result["image_data"]
            )

        return result

    except Exception as exc:
        print(f"[TKA IMAGE GET] {exc}")
        return None


def get_tka_image_usage(image_id: str) -> list[dict]:
    """
    Cari paket TKA yang benar-benar mereferensikan image_id.
    Read-only. Tidak mengubah database.
    """

    image_id = str(image_id or "").strip()

    if not image_id:
        return []

    conn = init_db_connection()

    if not conn:
        return []

    try:
        with conn.session as s:
            rows = (
                s.execute(
                    text(
                        """
                        SELECT
                            kode_tka,
                            config,
                            created_at,
                            updated_at
                        FROM tka_custom
                        WHERE
                            jsonb_typeof(COALESCE(tka_data, '[]'::jsonb)) = 'array'
                            AND EXISTS (
                                SELECT 1
                                FROM jsonb_array_elements(
                                    COALESCE(tka_data, '[]'::jsonb)
                                ) AS question
                                WHERE question->>'image_id' = :image_id
                            )
                        ORDER BY created_at DESC
                        """
                    ),
                    {"image_id": image_id},
                )
                .mappings()
                .all()
            )

        usages = []

        for row in rows:
            config = _json(
                row.get("config"),
                {},
            )

            active_from = config.get("active_from")
            active_until = config.get("active_until")

            is_active_window = True
            if active_until:
                try:
                    end_dt = active_until
                    if not isinstance(end_dt, datetime):
                        end_dt = datetime.fromisoformat(
                            str(end_dt).replace("Z", "+00:00")
                        )
                    if getattr(end_dt, "tzinfo", None):
                        end_dt = end_dt.astimezone(
                            timezone(timedelta(hours=7))
                        ).replace(tzinfo=None)
                    is_active_window = end_dt >= _now_wib_naive()
                except Exception:
                    is_active_window = True

            usages.append(
                {
                    "kode_tka": str(
                        row.get("kode_tka") or ""
                    ),
                    "jenjang": (
                        config.get("jenjang")
                        or "-"
                    ),
                    "mapel": (
                        config.get("mapel")
                        or "-"
                    ),
                    "active_from": active_from,
                    "active_until": active_until,
                    "is_active_window": is_active_window,
                    "created_at": row.get(
                        "created_at"
                    ),
                    "updated_at": row.get(
                        "updated_at"
                    ),
                }
            )

        return usages

    except Exception as exc:
        print(f"[TKA IMAGE USAGE] {exc}")
        return []


def get_tka_images_usage_bulk(image_ids: list[str]) -> dict[str, list[dict]]:
    """Cari penggunaan banyak stimulus dalam satu query PostgreSQL."""
    ids = [str(x or "").strip() for x in (image_ids or []) if str(x or "").strip()]
    if not ids:
        return {}

    conn = init_db_connection()
    if not conn:
        return {image_id: [] for image_id in ids}

    try:
        with conn.session as s:
            rows = (
                s.execute(
                    text(
                        """
                        SELECT
                            t.kode_tka,
                            t.config,
                            t.created_at,
                            t.updated_at,
                            q->>'image_id' AS image_id
                        FROM tka_custom AS t
                        CROSS JOIN LATERAL jsonb_array_elements(
                            CASE
                                WHEN jsonb_typeof(COALESCE(t.tka_data, '[]'::jsonb)) = 'array'
                                THEN t.tka_data
                                ELSE '[]'::jsonb
                            END
                        ) AS q
                        WHERE q->>'image_id' = ANY(:image_ids)
                        ORDER BY t.created_at DESC
                        """
                    ),
                    {"image_ids": ids},
                )
                .mappings()
                .all()
            )

        result = {image_id: [] for image_id in ids}
        now = _now_wib_naive()

        for row in rows:
            image_id = str(row.get("image_id") or "")
            if image_id not in result:
                continue

            config = _json(row.get("config"), {})
            active_until = config.get("active_until")
            is_active_window = True
            if active_until:
                try:
                    end_dt = active_until
                    if not isinstance(end_dt, datetime):
                        end_dt = datetime.fromisoformat(str(end_dt).replace("Z", "+00:00"))
                    if getattr(end_dt, "tzinfo", None):
                        end_dt = end_dt.astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)
                    is_active_window = end_dt >= now
                except Exception:
                    is_active_window = True

            result[image_id].append({
                "kode_tka": str(row.get("kode_tka") or ""),
                "jenjang": config.get("jenjang") or "-",
                "mapel": config.get("mapel") or "-",
                "active_from": config.get("active_from"),
                "active_until": active_until,
                "is_active_window": is_active_window,
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            })

        return result
    except Exception as exc:
        print(f"[TKA IMAGE USAGE BULK] {exc}")
        return {image_id: [] for image_id in ids}


def delete_tka_images_safe_bulk(
    items: list[dict],
) -> tuple[list[str], list[dict]]:
    """
    Hapus banyak stimulus secara aman dengan satu pembacaan metadata dan
    satu UPDATE database. Usage sudah diperiksa sebelumnya oleh UI.
    Return: (deleted_ids, blocked_items)
    """
    normalized = []
    for item in items or []:
        image_id = str(item.get("image_id") or "").strip()
        if image_id:
            normalized.append({**item, "image_id": image_id})

    if not normalized:
        return [], []

    conn = init_db_connection()
    if not conn:
        return [], [{"image_id": item["image_id"], "message": "Database tidak tersedia.", "usages": item.get("known_usages") or []} for item in normalized]

    ids = [item["image_id"] for item in normalized]
    placeholders = ", ".join(f":id_{i}" for i in range(len(ids)))
    params = {f"id_{i}": image_id for i, image_id in enumerate(ids)}

    try:
        with conn.session as s:
            rows = (
                s.execute(
                    text(
                        f"""
                        SELECT image_id, source_type, owner_key, is_active
                        FROM tka_image_library
                        WHERE image_id::text IN ({placeholders})
                        """
                    ),
                    params,
                )
                .mappings()
                .all()
            )

            metadata = {str(row["image_id"]): dict(row) for row in rows}
            blocked = []
            safe_items = []

            for item in normalized:
                image_id = item["image_id"]
                image = metadata.get(image_id)
                usages = list(item.get("known_usages") or [])

                if not image or not image.get("is_active"):
                    blocked.append({"image_id": image_id, "message": "Gambar tidak ditemukan atau sudah tidak aktif.", "usages": usages})
                    continue

                source_type = str(image.get("source_type") or "").upper()
                owner_key = item.get("owner_key")
                allow_system = bool(item.get("allow_system"))
                image_owner = str(image.get("owner_key") or "").strip()

                if source_type == "SYSTEM" and not allow_system:
                    blocked.append({"image_id": image_id, "message": "Gambar Sistem UPN tidak dapat dihapus dari area Guru.", "usages": usages})
                    continue

                if source_type == "GURU" and owner_key and image_owner.lower() != str(owner_key).strip().lower():
                    blocked.append({"image_id": image_id, "message": "Gambar Guru ini bukan milik akun/guru yang sedang aktif.", "usages": usages})
                    continue

                active_usages = [u for u in usages if u.get("is_active_window", True)]
                if active_usages:
                    blocked.append({"image_id": image_id, "message": "Masih digunakan oleh TKA yang masa aktifnya belum selesai.", "usages": active_usages})
                    continue

                safe_items.append(item)

            if not safe_items:
                return [], blocked

            conditions = []
            update_params = {}
            for i, item in enumerate(safe_items):
                image_id = item["image_id"]
                p_id = f"safe_id_{i}"
                update_params[p_id] = image_id
                if bool(item.get("allow_system")):
                    conditions.append(f"(image_id = :{p_id} AND source_type = 'SYSTEM')")
                else:
                    p_owner = f"safe_owner_{i}"
                    update_params[p_owner] = item.get("owner_key") or ""
                    conditions.append(
                        f"(image_id = :{p_id} AND source_type = 'GURU' AND LOWER(owner_key) = LOWER(:{p_owner}))"
                    )

            update_sql = f"""
                UPDATE tka_image_library
                SET
                    is_active = FALSE,
                    updated_at = NOW() AT TIME ZONE 'Asia/Jakarta'
                WHERE is_active = TRUE
                  AND ({" OR ".join(conditions)})
                RETURNING image_id
            """
            result = s.execute(text(update_sql), update_params)
            returned = result.mappings().all()
            s.commit()

            deleted_ids = [str(row["image_id"]) for row in returned]
            returned_set = set(deleted_ids)
            for item in safe_items:
                if item["image_id"] not in returned_set:
                    blocked.append({
                        "image_id": item["image_id"],
                        "message": "Gambar berubah status sebelum proses selesai dan tidak dihapus.",
                        "usages": item.get("known_usages") or [],
                    })

            return deleted_ids, blocked

    except Exception as exc:
        print(f"[TKA IMAGE DELETE BULK] {exc}")
        return [], [
            {
                "image_id": item["image_id"],
                "message": f"Penghapusan massal gagal: {exc}",
                "usages": item.get("known_usages") or [],
            }
            for item in normalized
        ]


def can_delete_tka_image(
    image_id: str,
    owner_key: str | None = None,
    allow_system: bool = False,
) -> tuple[bool, str, list[dict]]:
    """
    Validasi apakah sebuah image aman untuk dihapus.
    Return:
        (boleh_hapus, pesan, usages)
    """

    image_id = str(image_id or "").strip()

    if not image_id:
        return (
            False,
            "Image ID tidak valid.",
            [],
        )

    image = get_tka_image(image_id)

    if not image:
        return (
            False,
            "Gambar tidak ditemukan atau sudah tidak aktif.",
            [],
        )

    source_type = str(
        image.get("source_type") or ""
    ).upper()

    image_owner = str(
        image.get("owner_key") or ""
    ).strip()

    if source_type == "SYSTEM" and not allow_system:
        return (
            False,
            "Gambar Sistem UPN tidak dapat dihapus dari area Guru.",
            [],
        )

    if source_type == "GURU" and owner_key:
        if (
            image_owner.lower()
            != str(owner_key).strip().lower()
        ):
            return (
                False,
                "Gambar Guru ini bukan milik akun/guru yang sedang aktif.",
                [],
            )

    usages = get_tka_image_usage(image_id)

    active_usages = [
        usage
        for usage in usages
        if usage.get("is_active_window", True)
    ]

    if active_usages:
        return (
            False,
            "Gambar masih digunakan oleh TKA yang masa aktifnya belum selesai. "
            "Tunggu sampai TKA tersebut selesai/expired sebelum menghapus stimulus.",
            active_usages,
        )

    if usages:
        return (
            True,
            "Semua paket TKA yang pernah memakai stimulus ini sudah selesai. "
            "Gambar aman dikeluarkan dari Library aktif.",
            usages,
        )

    return (
        True,
        "Gambar aman untuk dihapus.",
        [],
    )


def delete_tka_image(
    image_id: str,
    owner_key: str | None = None,
    allow_system: bool = False,
) -> bool:

    conn = init_db_connection()

    if not conn:
        return False

    clauses = [
        "image_id = :id",
        "is_active = TRUE",
    ]

    params = {
        "id": str(image_id)
    }

    if not allow_system:
        clauses.append(
            "source_type = 'GURU'"
        )

        if owner_key:
            clauses.append(
                "LOWER(owner_key) = LOWER(:owner)"
            )
            params["owner"] = owner_key

    try:
        with conn.session as s:
            result = s.execute(
                text(
                    f"""
                    UPDATE tka_image_library
                    SET
                        is_active = FALSE,
                        updated_at =
                            NOW()
                            AT TIME ZONE 'Asia/Jakarta'
                    WHERE {' AND '.join(clauses)}
                    """
                ),
                params,
            )

            s.commit()

            return result.rowcount > 0

    except Exception as exc:
        print(f"[TKA IMAGE DELETE] {exc}")
        return False


def delete_tka_image_safe(
    image_id: str,
    owner_key: str | None = None,
    allow_system: bool = False,
    known_usages: list[dict] | None = None,
) -> tuple[bool, str, list[dict]]:
    """
    Soft-delete image setelah seluruh pemeriksaan keamanan lolos.
    """

    if known_usages is None:
        allowed, message, usages = can_delete_tka_image(
            image_id=image_id,
            owner_key=owner_key,
            allow_system=allow_system,
        )
    else:
        image = get_tka_image(image_id)
        usages = list(known_usages or [])
        if not image:
            return False, "Gambar tidak ditemukan atau sudah tidak aktif.", usages

        source_type = str(image.get("source_type") or "").upper()
        image_owner = str(image.get("owner_key") or "").strip()
        if source_type == "SYSTEM" and not allow_system:
            return False, "Gambar Sistem UPN tidak dapat dihapus dari area Guru.", usages
        if source_type == "GURU" and owner_key and image_owner.lower() != str(owner_key).strip().lower():
            return False, "Gambar Guru ini bukan milik akun/guru yang sedang aktif.", usages

        active_usages = [u for u in usages if u.get("is_active_window", True)]
        if active_usages:
            return (
                False,
                "Gambar masih digunakan oleh TKA yang masa aktifnya belum selesai.",
                active_usages,
            )
        allowed = True
        message = "Gambar aman untuk dihapus."

    if not allowed:
        return (
            False,
            message,
            usages,
        )

    deleted = delete_tka_image(
        image_id=image_id,
        owner_key=owner_key,
        allow_system=allow_system,
    )

    if deleted:
        return (
            True,
            "Gambar berhasil dihapus dari Library TKA.",
            [],
        )

    return (
        False,
        "Gambar gagal dihapus.",
        [],
    )


def _image_part(data: bytes, mime_type: str):
    """Build a compact image part for AI generation."""
    try:
        from google.genai import types

        try:
            from PIL import Image
            import io

            src = Image.open(io.BytesIO(data))
            src.thumbnail((1600, 1600), Image.Resampling.LANCZOS)

            buf = io.BytesIO()
            if src.mode not in ("RGB", "L"):
                src = src.convert("RGB")
            elif src.mode == "L":
                src = src.convert("RGB")
            src.save(buf, format="JPEG", quality=82, optimize=True)
            data = buf.getvalue()
            mime_type = "image/jpeg"
        except Exception:
            pass

        return types.Part.from_bytes(
            data=data,
            mime_type=mime_type,
        )

    except Exception:
        return None


TKA_QUESTION_TYPES = (
    "PG",
    "MCMA",
    "KATEGORI",
)


def _normalize_question_type(value: Any) -> str:
    raw = (
        str(value or "PG")
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )

    if raw == "MIXED":
        return "MIXED"

    if raw in {
        "MCMA",
        "PG_KOMPLEKS",
        "PILIHAN_GANDA_KOMPLEKS",
        "PILIHAN_GANDA_KOMPLEKS_MCMA",
    }:
        return "MCMA"

    if raw in {
        "KATEGORI",
        "CATEGORY",
        "PG_KOMPLEKS_KATEGORI",
        "BENAR_SALAH",
        "SETUJU_TIDAK_SETUJU",
    }:
        return "KATEGORI"

    return "PG"


def _normalize_stimulus(
    item: dict,
) -> tuple[str | None, str | None, str | None]:

    stimulus_text = str(
        item.get("stimulus_text")
        or item.get("stimulus")
        or ""
    ).strip()

    stimulus_group = str(
        item.get("stimulus_group")
        or ""
    ).strip() or None

    image_id = str(
        item.get("image_id")
        or ""
    ).strip() or None

    return (
        stimulus_text or None,
        stimulus_group,
        image_id,
    )


def _tka_prompt(
    *,
    jenjang: str,
    mapel: str,
    question_type: str,
    count: int,
    image_count: int,
    image_ids: list[str] | None = None,
) -> str:
    labels = tka_option_labels(jenjang)
    qtype = _normalize_question_type(question_type)
    policy = tka_stimulus_policy(jenjang, mapel, "Pilihan")
    mapel_key = _mapel_key(mapel)

    if qtype == "MIXED":
        type_rules = """BENTUK: CAMPURAN TKA
- Gunakan PG, MCMA, dan KATEGORI dalam satu paket.
- Jangan mengasumsikan rasio resmi yang tidak disebutkan dalam sumber acuan.
- Pastikan setiap bentuk muncul sekurang-kurangnya sekali dalam paket.
- PG memiliki tepat satu jawaban benar; MCMA memiliki minimal dua jawaban benar; KATEGORI memberi satu respons benar untuk tiap pernyataan."""
        schema = (
            '"options": [],\n'
            '      "correct_answer": [],\n'
            '      "correct_answers": [],\n'
            '      "category_items": []'
        )
    elif qtype == "PG":
        type_rules = f"""BENTUK: PILIHAN GANDA (PG)
- Tepat satu jawaban benar.
- options wajib tepat {len(labels)} pilihan dengan label {', '.join(labels)}.
- correct_answer wajib berupa satu label opsi yang memang benar, misalnya \"B\".
- Jangan mengosongkan kunci dan jangan menebak kunci setelah opsi selesai dibuat."""
        schema = f""""options": ["{labels[0]}. ...", "{labels[1]}. ...", ...],
      "correct_answer": "B",
      "correct_answers": []"""
    elif qtype == "MCMA":
        type_rules = f"""BENTUK: PILIHAN GANDA KOMPLEKS - MCMA
- Tepat {len(labels)} pilihan dengan label {', '.join(labels)}.
- Dua atau lebih jawaban harus benar berdasarkan materi; jangan membuat kunci tambahan hanya untuk memenuhi jumlah.
- correct_answers berisi minimal dua label unik dan seluruhnya harus benar.
- correct_answer harus konsisten dengan correct_answers."""
        schema = f""""options": ["{labels[0]}. ...", "{labels[1]}. ...", ...],
      "correct_answer": ["A", "C"],
      "correct_answers": ["A", "C"]"""
    else:
        type_rules = """BENTUK: PILIHAN GANDA KOMPLEKS - KATEGORI
- Buat 3-5 pernyataan yang benar-benar dapat dinilai berdasarkan materi/stimulus.
- Setiap pernyataan memiliki kategori/respons sendiri, misalnya Benar/Salah atau Setuju/Tidak Setuju.
- Setiap correct_response harus sama persis dengan salah satu opsi pada pernyataan tersebut; jangan memakai fallback."""
        schema = """"options": [],
      "correct_answer": ["Benar", "Salah", "Benar"],
      "correct_answers": ["Benar", "Salah", "Benar"],
      "category_items": [
        {"statement": "...", "options": ["Benar", "Salah"], "correct_response": "Benar"}
      ]"""

    # Profile materi dan bahasa berdasarkan mata uji pilihan MA.
    subject_rules = "Gunakan Bahasa Indonesia akademik yang jelas dan sesuai tingkat MA, kecuali mata uji bahasa yang menetapkan bahasa target."
    if mapel_key == "matematikalanjutan":
        subject_rules = """KHUSUS MATEMATIKA LANJUTAN MA:
- Utamakan penalaran matematis multi-langkah, pemodelan, generalisasi, interpretasi representasi, dan justifikasi strategi; jangan sekadar hitung rutin.
- Variasikan konteks dan konsep matematika lanjutan yang relevan dengan kisi-kisi/kompetensi TKA MA, tanpa mengarang klaim bahwa suatu submateri pasti diwajibkan.
- Teks soal dan narasi matematis harus cukup lengkap untuk dikerjakan tanpa gambar.
- Gambar dari mata uji wajib Matematika MA hanya boleh digunakan bila memang membantu membaca grafik/diagram/representasi; maksimal dua gambar unik dalam satu paket. Soal lain tetap berbasis teks dan penalaran.
- Periksa ulang semua perhitungan, domain, satuan, asumsi, dan kunci jawaban sebelum keluaran."""
    elif mapel_key == "bahasaindonesialanjutan":
        subject_rules = """KHUSUS BAHASA INDONESIA LANJUTAN MA:
- Gunakan teks autentik-buatan yang wajar: editorial, esai, laporan, kritik, argumentasi, atau teks sastra yang jelas judul dan konteksnya.
- Uji inferensi tersirat, evaluasi argumen/bukti, sudut pandang, tujuan retoris, hubungan antargagasan, makna kontekstual, dan revisi pilihan bahasa; hindari pertanyaan literal yang jawabannya tersurat sederhana.
- Maksimal dua gambar unik, hanya dari sumber stimulus mata uji wajib Bahasa Indonesia MA dan hanya bila benar-benar mendukung soal. Utamakan bacaan dan penalaran berbasis teks.
- Tulis teks sendiri; jangan mengaku mengutip berita atau karya nyata tertentu jika tidak diberikan sumbernya."""
    elif mapel_key == "bahasainggrislanjutan":
        subject_rules = """KHUSUS ADVANCED ENGLISH MA:
- Write the reading passages, questions, options, category statements, and answer rationale in natural English.
- Use titled, coherent texts such as an editorial, report, short story, review, speech, or argumentative passage.
- Test inference, author's purpose, tone, evidence quality, argument structure, cohesion, contextual vocabulary, and evaluation across multiple parts of a text; avoid questions answerable by a single obvious keyword.
- At most two unique images may be reused from the compulsory MA English stimulus library, and only when visual interpretation is genuinely required. Prefer text-based questions.
- Do not claim a generated passage is a real published article."""
    elif mapel_key == "bahasaarab":
        subject_rules = """KHUSUS BAHASA ARAB MA:
- Gunakan bahasa Arab baku dalam aksara Arab untuk teks, pertanyaan, opsi, pernyataan kategori, dan kunci penjelas; jangan mengganti teks Arab dengan transliterasi Latin.
- Buat teks berjudul yang wajar, seperti خبر قصير، حوار، رسالة، مقال قصير، أو قصة قصيرة, lalu uji الفهم والاستنتاج والفكرة الرئيسة ومعنى المفردات في السياق والعلاقات بين الجمل ومقصد الكاتب.
- Maksimal dua gambar unik dari library stimulus Bahasa Arab berjenjang MTs boleh digunakan jika benar-benar relevan; jika tidak tersedia, hasilkan paket teks Arab tanpa gambar.
- Pastikan tata bahasa, ejaan, pilihan kata, dan kunci jawaban Arab konsisten."""
    elif mapel_key in {"fisika", "kimia", "biologi", "ekonomi", "sosiologi", "geografi", "sejarah", "antropologi", "ppknpendidikanpancasila", "produkprojekkreatifdankewirausahaan"}:
        subject_rules = f"""KHUSUS MATA UJI {mapel.upper()} MA — MODE TEKS PENUH:
- DILARANG menggunakan gambar, image_id, diagram gambar, atau meminta siswa melihat aset visual. image_id harus null pada semua butir.
- Gunakan stimulus berbasis teks bila membantu: beri judul yang jelas dan buat narasi/kasus/data tertulis yang masuk akal, seperti cerita singkat, laporan/berita simulasi, kutipan wawancara, skenario eksperimen, deskripsi fenomena, tabel tekstual, atau kasus sosial/ekonomi sesuai disiplin {mapel}.
- Stimulus teks boleh dipakai bersama oleh beberapa soal: isi stimulus_text dengan teks lengkap yang diperlukan dan gunakan stimulus_group yang sama untuk grup tersebut. Jangan menyalin teks yang sama dengan variasi kecil ke tiap butir.
- Sebagian soal boleh berdiri sendiri tanpa stimulus bersama jika itu lebih tepat. Semua soal tetap harus dapat dijawab dari informasi tekstual dan pengetahuan disiplin yang relevan.
- Utamakan penerapan konsep, analisis sebab-akibat, evaluasi bukti/data, penalaran multi-langkah, pemilihan kesimpulan terbaik, dan penerapan pada situasi baru; hindari hafalan definisi sebagai mayoritas soal.
- Untuk data numerik, rumus, kronologi, atau istilah teknis, pastikan konsisten dan masuk akal. Jangan menciptakan kutipan atau peristiwa nyata seolah-olah fakta sejarah/berita sungguhan."""
    elif mapel_key == "bahasajerman":
        subject_rules = "Write all student-facing content in natural standard German. Use a titled short text/dialogue/report; assess inference, purpose, context vocabulary, argument, and implied meaning. No images; use text only. Keep grammar, spelling, and answer keys consistent."
    elif mapel_key == "bahasaprancis":
        subject_rules = "Rédigez tout le contenu destiné à l’élève en français naturel et correct. Utilisez un texte ou dialogue titré; évaluez l’inférence, l’intention, le vocabulaire en contexte et l’interprétation. Aucun image; texte uniquement. Vérifiez la grammaire et les réponses."
    elif mapel_key == "bahasajepang":
        subject_rules = "日本語の自然な文章で、本文・設問・選択肢・カテゴリー文を作成してください。必要に応じて漢字・ひらがな・カタカナを適切に使い、ローマ字に置き換えないでください。題名のある短い文章や会話を用い、推論・意図・文脈中の語彙・文章構成を問います。画像は使用せず、テキストのみとします。"
    elif mapel_key == "bahasakorea":
        subject_rules = "모든 지문, 문항, 선택지, 범주 문장을 자연스러운 한국어와 한글로 작성하세요. 제목이 있는 짧은 글이나 대화를 사용하고 추론, 글의 목적, 문맥상 어휘, 근거 평가를 묻습니다. 이미지 없이 텍스트만 사용하며 정답과 문법을 검토하세요."
    elif mapel_key == "bahasamandarin":
        subject_rules = "请使用自然、规范的中文汉字撰写全部学生可见内容，包括短文、题目、选项和分类陈述；不要用拼音代替汉字。使用有明确标题的短文或对话，考查推断、写作目的、语境词义、论证和信息整合。不得使用图片，只能使用文本，并核对语法与答案。"

    if policy["mode"] == "TEXT_ONLY":
        stimulus_rules = """STIMULUS POLICY: TEXT ONLY.
- Jangan memasukkan gambar, image_id, diagram gambar, atau referensi asset visual.
- image_id wajib null untuk semua soal.
- Buat stimulus tekstual berjudul yang relevan jika diperlukan; satu teks boleh mendukung beberapa butir melalui stimulus_group yang sama.
- Jika image_id diberikan di input secara tidak sengaja, abaikan seluruh gambar tersebut."""
    elif policy["mode"] == "MAPPED_IMAGES":
        source = f"{policy['source_mapel']} jenjang {policy['source_jenjang']}"
        stimulus_rules = f"""STIMULUS POLICY: MAXIMUM TWO UNIQUE IMAGES.
- Jika gambar tersedia, gambar hanya boleh berasal dari library mata uji sumber: {source}.
- Maksimal dua gambar unik dalam satu paket; gambar yang sama boleh dipakai oleh beberapa soal bila relevan.
- Jangan memaksa gambar pada setiap soal. Mayoritas soal tetap boleh berupa teks, cerita, penalaran, atau perhitungan.
- Jika tidak ada gambar yang cocok, lanjutkan dengan teks saja; jangan gagal dan jangan mengarang image_id.
- Jika tidak memakai gambar, image_id wajib null. Stimulus teks harus diberi judul yang jelas bila berupa bacaan/narasi."""
    else:
        stimulus_rules = """STIMULUS POLICY:
- Gambar bersifat opsional; gunakan hanya jika relevan dan sesuai mata uji.
- Jangan mengarang fakta visual yang tidak tersedia.
- Stimulus teks dapat diberi judul dan dipakai bersama oleh beberapa soal melalui stimulus_group."""

    if qtype == "MIXED":
        balance_rule = "- Sebarkan posisi kunci PG secara wajar; jangan jadikan A sebagai kunci default atau membuat semua kunci sama. Kunci harus benar secara substansi."
    else:
        balance_rule = "- Untuk PG, jangan selalu memilih huruf A sebagai kunci; sebar posisi kunci secara wajar tanpa mengorbankan kebenaran."

    return f"""Anda adalah perancang asesmen TKA RoboMANTAP untuk jenjang {normalize_tka_jenjang(jenjang)}, mata uji {mapel}.
Buat tepat {count} butir bertipe {qtype}.

KERANGKA PORTAL TKA MA/MTs:
- Gunakan hanya bentuk PG, PG Kompleks-MCMA, dan PG Kompleks-Kategori.
- PG memiliki satu jawaban benar; MCMA memiliki lebih dari satu jawaban benar; Kategori memberi satu respons untuk setiap pernyataan.
- Jangan membuat matching/menjodohkan, isian singkat, atau uraian.
- Ikuti kompetensi mata uji dan jenjang yang diminta. Jangan mengklaim bahwa distribusi, jumlah per submateri, atau aturan rinci tertentu adalah ketentuan resmi jika tidak dinyatakan dalam kisi-kisi yang diberikan.

PROFIL MATA UJI:
{subject_rules}

KUALITAS DAN KESULITAN:
- Buat soal setara asesmen akhir jenjang MA/MTs, bukan latihan hafalan dasar.
- Utamakan analisis, inferensi, evaluasi bukti, interpretasi, penerapan konsep pada konteks baru, dan pemecahan masalah multi-langkah jika sesuai disiplin.
- Distraktor harus masuk akal dan mewakili miskonsepsi umum; jangan membuat jawaban benar paling panjang/paling rinci secara konsisten atau membuat distraktor yang jelas konyol.
- Jangan menggunakan pola kunci yang mudah ditebak. {balance_rule}
- Level C4-C6 digunakan jika benar-benar sesuai dengan proses berpikir soal; jangan memberi label kognitif tinggi pada soal hafalan.
- Setiap soal wajib memiliki topic, cognitive_level, dan solution_basis yang menjelaskan alasan substantif mengapa kunci benar.
- Verifikasi ulang fakta, logika, perhitungan, ejaan, dan semua kunci sebelum menghasilkan JSON.

{type_rules}

{stimulus_rules}

Jika menggunakan stimulus teks, stimulus_text harus memuat teks lengkap yang dibutuhkan siswa dan stimulus_group harus sama untuk soal yang berbagi stimulus. Jika tidak ada stimulus, stimulus_text dan stimulus_group boleh null.
IMAGE_ID yang tersedia: {', '.join(str(x) for x in (image_ids or [])) or '(tidak ada)'}
Jumlah gambar yang diberikan: {image_count}.

OUTPUT JSON MURNI, tanpa markdown atau teks di luar JSON:
{{
  "questions": [
    {{
      "id": 1,
      "question_type": "{'PG|MCMA|KATEGORI' if qtype == 'MIXED' else qtype}",
      "question": "...",
      {schema},
      "category_items": [],
      "stimulus_text": null,
      "stimulus_group": null,
      "image_id": null,
      "topic": "...",
      "cognitive_level": "C4",
      "solution_basis": "..."
    }}
  ]
}}
"""

def _option_map(options: list[str]) -> dict[str, str]:
    result = {}
    for opt in options:
        label, _ = _split_option_label(str(opt), 0)
        if label:
            result[label.upper()] = str(opt).strip()
    return result


def _normalize_tka_questions(
    raw_questions: Any,
    jenjang: str,
    default_image_ids: list[str] | None = None,
) -> list[dict]:
    """
    Auto-correcting robust validator.
    Menerima kesalahan kecil dari Gemini (case sensitivity, jumlah opsi lebih, 
    halusinasi ID gambar) alih-alih menggagalkan seluruh batch TKA.
    """
    labels = tka_option_labels(jenjang)
    label_set = set(labels)

    if not isinstance(raw_questions, list):
        return []

    out = []
    default_image_ids = [str(x) for x in (default_image_ids or []) if x]

    for idx, item in enumerate(raw_questions, 1):
        if not isinstance(item, dict):
            continue

        question = str(item.get("question", "")).strip()
        if not question:
            continue

        qtype = _normalize_question_type(item.get("question_type") or item.get("type"))
        stimulus_text, stimulus_group, image_id = _normalize_stimulus(item)

        # KOREKSI 1: Mengabaikan ID gambar yang dihalusinasikan AI (misal: "null", "none")
        if image_id:
            if str(image_id).lower() in ["null", "none", "tidak ada", "false", ""]:
                image_id = None
            elif not default_image_ids or str(image_id) not in default_image_ids:
                image_id = None

        topic = str(item.get("topic") or "TKA").strip()[:120]
        cognitive = str(item.get("cognitive_level") or "C4").strip()[:10]
        solution = str(item.get("solution_basis") or "").strip()

        base = {
            "id": idx,
            "question_type": qtype,
            "question": question,
            "topic": topic,
            "cognitive_level": cognitive,
            "solution_basis": solution,
            "stimulus_text": stimulus_text,
            "stimulus_group": stimulus_group,
            "image_id": image_id,
        }

        if qtype in {"PG", "MCMA"}:
            raw_options = item.get("options", [])
            if not isinstance(raw_options, list):
                continue

            options, _ = normalize_quiz_options(raw_options, jenjang)
            
            # KOREKSI 2: Mentoleransi jumlah opsi berlebih atau kurang
            if len(options) < len(labels):
                continue
            options = options[:len(labels)]
            
            optmap = _option_map(options)
            if set(optmap) != label_set:
                continue

            raw_answers = item.get("correct_answers")
            if raw_answers is None:
                raw_answers = item.get("correct_answer")

            if isinstance(raw_answers, str):
                answers = [x.strip().upper() for x in re.split(r"[,;|]", raw_answers) if x.strip()]
            elif isinstance(raw_answers, list):
                answers = []
                for value in raw_answers:
                    raw_value = str(value).strip().upper()
                    if raw_value in label_set:
                        candidate = raw_value
                    else:
                        label, _ = _split_option_label(str(value), 0)
                        candidate = label.upper() if label else ""
                    if candidate in label_set:
                        answers.append(candidate)
            else:
                answers = []

            answers = list(dict.fromkeys(answers))
            valid_answers = [a for a in answers if a in label_set]
            
            # Kunci yang kosong/tidak valid tidak boleh diganti otomatis dengan A.
            # Soal invalid ditolak agar tidak menerbitkan kunci jawaban palsu.
            if qtype == "PG":
                if len(valid_answers) != 1:
                    continue
            elif qtype == "MCMA":
                if len(valid_answers) < 2:
                    continue

            # Acak posisi isi opsi, lalu hitung ulang label kunci berdasarkan isi.
            # Ini mencegah pola semua-A tanpa mengubah jawaban yang benar.
            original_map = _option_map(options)
            correct_contents = {
                _split_option_label(original_map[label], 0)[1].strip()
                for label in valid_answers
                if label in original_map
            }
            option_contents = [
                _split_option_label(original_map[label], 0)[1].strip()
                for label in labels
            ]
            random.shuffle(option_contents)
            options = [f"{label}. {content}" for label, content in zip(labels, option_contents)]
            shuffled_map = _option_map(options)
            valid_answers = [
                label for label in labels
                if _split_option_label(shuffled_map[label], 0)[1].strip() in correct_contents
            ]
            if qtype == "PG" and len(valid_answers) != 1:
                continue
            if qtype == "MCMA" and len(valid_answers) < 2:
                continue

            base["options"] = options
            base["correct_answers"] = valid_answers
            base["correct_answer"] = valid_answers[0] if qtype == "PG" else valid_answers
            base["category_items"] = []

        else:
            raw_items = item.get("category_items", [])
            if not isinstance(raw_items, list) or not 3 <= len(raw_items) <= 5:
                continue

            category_items = []
            answers = []
            invalid_category = False

            for cat in raw_items:
                if not isinstance(cat, dict):
                    continue

                statement = str(cat.get("statement") or "").strip()
                choices = cat.get("options")
                correct_response = str(cat.get("correct_response") or cat.get("correct_answer") or "").strip()

                if not statement or not isinstance(choices, list) or len(choices) < 2:
                    continue

                choices = [str(x).strip() for x in choices if str(x).strip()]
                if len(choices) < 2:
                    continue

                # KOREKSI 4: Mengatasi sensitivitas huruf besar/kecil dari Gemini pada "Benar/Salah"
                correct_response_upper = correct_response.upper()
                matched_choice = next((c for c in choices if c.upper() == correct_response_upper), None)
                
                if matched_choice:
                    correct_response = matched_choice
                else:
                    invalid_category = True
                    break

                category_items.append({
                    "statement": statement,
                    "options": choices,
                    "correct_response": correct_response,
                })
                answers.append(correct_response)

            if invalid_category or len(category_items) < 3:
                continue

            base["options"] = []
            base["category_items"] = category_items
            base["correct_answers"] = answers
            base["correct_answer"] = answers

        out.append(base)

    return out


def generate_tka_questions_batch(
    *,
    jenjang: str,
    mapel: str,
    question_type: str,
    count: int,
    image_records: list[dict] | None = None,
) -> list[dict]:
    
    clients = get_gemini_clients()
    if not clients or count <= 0:
        return []

    records = [
        r for r in (image_records or [])
        if r and r.get("image_id") and r.get("image_data")
    ][:TKA_GENERATION_MAX_IMAGES]

    image_ids = [str(r["image_id"]) for r in records]
    contents: list[Any] = []

    for n, record in enumerate(records, 1):
        data = record.get("image_data")
        if isinstance(data, memoryview):
            data = data.tobytes()
        elif isinstance(data, bytearray):
            data = bytes(data)

        part = _image_part(
            data,
            record.get("mime_type") or "image/png",
        ) if data else None

        if part is not None:
            contents.append(part)
            contents.append(
                f"IMAGE_ID={record['image_id']} | "
                f"Stimulus gambar {n}: {record.get('filename', '')}"
            )

    normalized_jenjang = normalize_tka_jenjang(jenjang)
    normalized_type = _normalize_question_type(question_type)

    contents.append(
        _tka_prompt(
            jenjang=normalized_jenjang,
            mapel=tka_mapel_name(mapel),
            question_type=normalized_type,
            count=count,
            image_count=len(records),
            image_ids=image_ids,
        )
    )

    attempts = []
    candidate_pairs = []
    if clients:
        candidate_pairs.append((clients[0], TKA_MODELS[0]))
        if len(TKA_MODELS) > 1:
            candidate_pairs.append((clients[0], TKA_MODELS[1]))
        if len(clients) > 1:
            candidate_pairs.append((clients[1], TKA_MODELS[0]))

    for pair in candidate_pairs:
        attempts.append(pair)
        if len(attempts) >= TKA_GENERATION_MAX_ATTEMPTS:
            break

    if normalized_type == "KATEGORI":
        max_output_tokens = 6500
    else:
        max_output_tokens = 5000

    for attempt_no, (client, model) in enumerate(attempts, 1):
        try:
            from google.genai import types

            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.25,
                    max_output_tokens=max_output_tokens,
                ),
            )

            raw = getattr(response, "text", "") or ""
            try:
                data = json.loads(clean_json_text(raw), strict=False)
            except Exception:
                m = re.search(r"\{.*\}", raw, flags=re.S)
                data = json.loads(m.group(0), strict=False) if m else {}

            if not isinstance(data, dict):
                data = {}

            normalized = _normalize_tka_questions(
                data.get("questions", []),
                normalized_jenjang,
                image_ids,
            )

            if len(normalized) == count:
                print(
                    f"[TKA AI] batch {normalized_type} berhasil: "
                    f"{len(normalized)}/{count} soal (attempt {attempt_no})."
                )
                return normalized

            print(
                f"[TKA AI] batch {normalized_type} output tidak lengkap/invalid: "
                f"{len(normalized)}/{count} soal (attempt {attempt_no})."
            )

        except Exception as exc:
            print(
                f"[TKA AI] batch {normalized_type} gagal "
                f"(attempt {attempt_no}/{len(attempts)}): "
                f"{type(exc).__name__}: {exc}"
            )

        if attempt_no < len(attempts):
            time.sleep(TKA_STUDIO_RETRY_BACKOFF_SECONDS)

    return []


def generate_tka_studio(
    *,
    jenjang: str,
    mapel: str,
    mapel_type: str = "Wajib",
    image_ids: list[str] | None = None,
    auto_select_images: bool = False,
    count: int = TKA_GENERATION_QUESTIONS,
    owner_key: str | None = None,
) -> list[dict]:
    jenjang = normalize_tka_jenjang(jenjang)
    mapel = tka_mapel_name(mapel)
    count = int(count or TKA_GENERATION_QUESTIONS)
    if count not in (15, 20, 25):
        print(f"[TKA STUDIO] Jumlah {count} tidak didukung; gunakan 15, 20, atau 25.")
        return []

    policy = tka_stimulus_policy(jenjang, mapel, mapel_type)
    max_images = int(policy["max_images"])
    selected = list(dict.fromkeys(str(x) for x in (image_ids or []) if x))[:max_images]

    # Untuk teks-penuh, abaikan ID gambar dari state/UI secara tegas.
    if policy["mode"] == "TEXT_ONLY":
        selected = []
    elif policy["mode"] == "MAPPED_IMAGES":
        # Pastikan ID terpilih benar-benar milik mata uji sumber yang ditetapkan.
        valid_source_images = {
            str(row["image_id"]) for row in list_tka_images(
                source_type=None, owner_key=owner_key,
                jenjang=policy["source_jenjang"], mapel=policy["source_mapel"], limit=200,
            )
        }
        selected = [image_id for image_id in selected if image_id in valid_source_images][:max_images]
        if not selected and auto_select_images:
            selected = [
                str(row["image_id"]) for row in list_tka_images(
                    source_type=None, owner_key=owner_key,
                    jenjang=policy["source_jenjang"],
                    mapel=policy["source_mapel"], limit=max_images,
                )
            ][:max_images]
    elif not selected and auto_select_images:
        selected = [
            str(row["image_id"]) for row in list_tka_images(
                source_type="SYSTEM", jenjang=jenjang, mapel=mapel, limit=max_images,
            )
        ][:max_images]

    image_records = []
    for image_id in selected:
        record = get_tka_image(image_id)
        if record:
            # Guard kedua agar metadata asset tidak bocor lintas mapel/jenjang.
            if policy["mode"] == "MAPPED_IMAGES":
                if normalize_tka_jenjang(record.get("jenjang", "")) != policy["source_jenjang"]:
                    continue
                if _mapel_key(record.get("mapel", "")) != _mapel_key(policy["source_mapel"]):
                    continue
            image_records.append(record)
    image_records = image_records[:max_images]

    # Dukungan jumlah Studio 15/20/25: distribusi tipe seimbang, bukan aturan resmi.
    if count == 15:
        batch_plan = [("PG", 5), ("MCMA", 5), ("KATEGORI", 5)]
    elif count == 20:
        batch_plan = [("PG", 7), ("MCMA", 7), ("KATEGORI", 6)]
    else:
        batch_plan = [("PG", 9), ("MCMA", 8), ("KATEGORI", 8)]

    print(
        f"[TKA STUDIO] mulai {count} soal mapel={mapel}, jenjang={jenjang}, "
        f"policy={policy['mode']}, stimulus={len(image_records)}/{max_images}, "
        f"batch={batch_plan}."
    )
    all_questions: list[dict] = []
    for question_type, target in batch_plan:
        # Pecah setiap target menjadi sub-batch maksimal 5 untuk mengurangi timeout.
        pending = target
        type_questions: list[dict] = []
        while pending > 0:
            size = min(TKA_STUDIO_BATCH_SIZE, pending)
            batch = generate_tka_questions_batch(
                jenjang=jenjang, mapel=mapel, question_type=question_type,
                count=size, image_records=image_records,
            )
            if len(batch) != size:
                print(f"[TKA STUDIO] batch {question_type} {size} gagal; mencoba pecahan kecil.")
                if size > 2:
                    left = size // 2
                    right = size - left
                    first = generate_tka_questions_batch(
                        jenjang=jenjang, mapel=mapel, question_type=question_type,
                        count=left, image_records=image_records,
                    )
                    second = generate_tka_questions_batch(
                        jenjang=jenjang, mapel=mapel, question_type=question_type,
                        count=right, image_records=image_records,
                    ) if len(first) == left else []
                    if len(first) == left and len(second) == right:
                        batch = first + second
                if len(batch) != size:
                    print(f"[TKA STUDIO] gagal total pada {question_type}: {len(batch)}/{size}; hasil parsial dibatalkan.")
                    return []
            type_questions.extend(batch)
            pending -= size
        all_questions.extend(type_questions)

    if len(all_questions) != count:
        print(f"[TKA STUDIO] jumlah akhir tidak sesuai: {len(all_questions)}/{count}.")
        return []
    for idx, question in enumerate(all_questions, 1):
        question["id"] = idx
    print(f"[TKA STUDIO] BERHASIL: {len(all_questions)}/{count} soal.")
    return all_questions


def generate_tka_30(
    *,
    jenjang: str,
    mapel: str,
    mapel_type: str = "Wajib",
    image_ids: list[str] | None = None,
    auto_select_images: bool = True,
) -> list[dict]:
    """Kompatibilitas nama lama; portal menghasilkan TKA_TOTAL_QUESTIONS (15) soal."""
    jenjang = normalize_tka_jenjang(jenjang)
    mapel = tka_mapel_name(mapel)
    policy = tka_stimulus_policy(jenjang, mapel, mapel_type)
    max_images = int(policy["max_images"])
    selected = list(dict.fromkeys(str(x) for x in (image_ids or []) if x))[:max_images]

    if policy["mode"] == "TEXT_ONLY":
        selected = []
    elif policy["mode"] == "MAPPED_IMAGES":
        if not selected and auto_select_images:
            selected = [
                str(row["image_id"]) for row in list_tka_images(
                    source_type="SYSTEM", jenjang=policy["source_jenjang"],
                    mapel=policy["source_mapel"], limit=max_images,
                )
            ][:max_images]
        valid_ids = {
            str(row["image_id"]) for row in list_tka_images(
                source_type="SYSTEM", jenjang=policy["source_jenjang"],
                mapel=policy["source_mapel"], limit=200,
            )
        }
        selected = [x for x in selected if x in valid_ids][:max_images]
    elif not selected and auto_select_images:
        selected = [
            str(row["image_id"]) for row in list_tka_images(
                source_type="SYSTEM", jenjang=jenjang, mapel=mapel, limit=max_images,
            )
        ][:max_images]

    image_records = []
    for image_id in selected:
        record = get_tka_image(image_id)
        if not record:
            continue
        if policy["mode"] == "MAPPED_IMAGES":
            if normalize_tka_jenjang(record.get("jenjang", "")) != policy["source_jenjang"]:
                continue
            if _mapel_key(record.get("mapel", "")) != _mapel_key(policy["source_mapel"]):
                continue
        image_records.append(record)
    image_records = image_records[:max_images]

    # Latihan Mandiri mata uji pilihan memakai jalur batch yang sama dengan Studio.
    if policy["is_elective"]:
        batches = []
        for qtype in TKA_STUDIO_BATCH_TYPES:
            batch = generate_tka_questions_batch(
                jenjang=jenjang, mapel=mapel, question_type=qtype,
                count=5, image_records=image_records,
            )
            if len(batch) != 5:
                print(f"[TKA MANDIRI] batch {qtype} gagal ({len(batch)}/5); paket dibatalkan.")
                return []
            batches.extend(batch)
        if len(batches) != TKA_TOTAL_QUESTIONS:
            return []
        for idx, question in enumerate(batches, 1):
            question["id"] = idx
        return batches

    # Jalur mapel wajib dipertahankan agar tidak mengubah perilaku selain mata uji pilihan.
    batch = generate_tka_questions_batch(
        jenjang=jenjang, mapel=mapel, question_type="MIXED",
        count=TKA_TOTAL_QUESTIONS, image_records=image_records,
    )
    if len(batch) != TKA_TOTAL_QUESTIONS:
        return []
    for idx, question in enumerate(batch, 1):
        question["id"] = idx
    return batch


def validate_tka_questions(
    questions: list[dict],
    jenjang: str,
    expected_count: int = TKA_TOTAL_QUESTIONS,
) -> tuple[bool, str]:

    if (
        not isinstance(questions, list)
        or len(questions) != expected_count
    ):
        return (
            False,
            f"Paket harus tepat {expected_count} soal.",
        )

    labels = tka_option_labels(jenjang)
    label_set = set(labels)

    counts = {
        x: 0
        for x in TKA_QUESTION_TYPES
    }

    for idx, q in enumerate(questions, 1):
        if (
            not isinstance(q, dict)
            or not str(q.get("question", "")).strip()
        ):
            return (False, f"Soal nomor {idx} tidak valid.")

        qtype = _normalize_question_type(q.get("question_type"))
        counts[qtype] += 1

        if qtype in {"PG", "MCMA"}:
            options = q.get("options")

            if not isinstance(options, list) or len(options) != len(labels):
                return (
                    False,
                    f"Soal nomor {idx} harus memiliki tepat "
                    f"{len(labels)} opsi ({'/'.join(labels)}).",
                )

            normalized_labels = {
                (_split_option_label(str(o), 0)[0] or "").upper()
                for o in options
            }

            if normalized_labels != label_set:
                return (
                    False,
                    f"Opsi soal nomor {idx} harus berlabel "
                    f"{', '.join(labels)}.",
                )

            answers = q.get("correct_answers")
            if not isinstance(answers, list):
                answers = [q.get("correct_answer")] if q.get("correct_answer") else []

            answers = [str(x).strip().upper() for x in answers if str(x).strip()]

            if qtype == "PG" and len(answers) != 1:
                return (False, f"PG nomor {idx} harus memiliki tepat satu jawaban benar.")

            if qtype == "MCMA" and len(set(answers)) < 2:
                return (False, f"MCMA nomor {idx} harus memiliki minimal dua jawaban benar.")

            if any(x not in label_set for x in answers):
                return (False, f"Kunci soal nomor {idx} tidak sesuai label opsi.")

        else:
            items = q.get("category_items")
            answers = q.get("correct_answers")

            if not isinstance(items, list) or not 3 <= len(items) <= 5:
                return (
                    False,
                    f"Soal kategori nomor {idx} harus memiliki 3-5 pernyataan.",
                )

            if not isinstance(answers, list) or len(answers) != len(items):
                return (False, f"Kunci kategori nomor {idx} tidak lengkap.")

            for pos, item in enumerate(items, 1):
                if not isinstance(item, dict) or not str(item.get("statement", "")).strip():
                    return (False, f"Pernyataan kategori nomor {idx}.{pos} tidak valid.")

                choices = item.get("options")
                correct = str(item.get("correct_response") or "").strip()

                if not isinstance(choices, list) or len(choices) < 2 or correct not in choices:
                    return (False, f"Respons kategori nomor {idx}.{pos} tidak valid.")

        if not q.get("topic"):
            return (False, f"Topik soal nomor {idx} kosong.")

    missing = [qtype for qtype in TKA_QUESTION_TYPES if counts.get(qtype, 0) < 1]
    if missing:
        return (
            False,
            "Paket TKA harus memuat semua bentuk soal: "
            + ", ".join(missing)
            + " belum ada.",
        )

    return (
        True,
        f"OK • PG {counts['PG']} • MCMA {counts['MCMA']} • Kategori {counts['KATEGORI']}",
    )


def validate_tka_30(
    questions: list[dict],
    jenjang: str,
) -> tuple[bool, str]:
    """Backward-compatible strict validator for student/published 30-question TKA."""
    return validate_tka_questions(questions, jenjang, TKA_TOTAL_QUESTIONS)


def publish_tka_to_db(
    kode_tka: str,
    config: dict,
    questions: list[dict],
) -> bool:

    # KOREKSI 5: Validasi saat Publish tidak lagi dikunci statis 30 soal
    expected_count = int(config.get("generation_count") or len(questions) or TKA_TOTAL_QUESTIONS)

    ok, reason = validate_tka_questions(
        questions,
        config.get("jenjang", "MTs"),
        expected_count=expected_count,
    )

    if not ok:
        print(f"[TKA PUBLISH] {reason}")
        return False

    code = re.sub(r"[^A-Z0-9_-]", "", str(kode_tka or "").upper())[:40]
    if not code:
        return False

    active_from = config.get("active_from") or _now_wib_naive().isoformat()
    active_until = config.get("active_until") or (
        _now_wib_naive() + timedelta(hours=TKA_DEFAULT_ACTIVE_HOURS)
    ).isoformat()

    cfg = {
        **config,
        "jenis": "TKA",
        "total_soal": expected_count,
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
            s.execute(
                text(
                    """
                    INSERT INTO tka_custom
                    (
                        kode_tka,
                        config,
                        tka_data,
                        created_at,
                        updated_at
                    )
                    VALUES
                    (
                        :code,
                        :cfg,
                        :data,
                        NOW() AT TIME ZONE 'Asia/Jakarta',
                        NOW() AT TIME ZONE 'Asia/Jakarta'
                    )
                    ON CONFLICT (kode_tka)
                    DO UPDATE SET
                        config = EXCLUDED.config,
                        tka_data = EXCLUDED.tka_data,
                        updated_at = NOW() AT TIME ZONE 'Asia/Jakarta'
                    """
                ),
                {
                    "code": code,
                    "cfg": json.dumps(cfg, default=str),
                    "data": json.dumps(questions, default=str),
                },
            )
            s.commit()
        return True
    except Exception as exc:
        print(f"[TKA PUBLISH] {exc}")
        return False


def get_tka_from_db(
    kode_tka: str,
) -> dict | None:

    conn = init_db_connection()

    if not conn:
        return None

    try:
        with conn.session as s:
            row = (
                s.execute(
                    text(
                        """
                        SELECT
                            config,
                            tka_data
                        FROM tka_custom
                        WHERE
                            UPPER(kode_tka)
                            =
                            UPPER(:code)
                        LIMIT 1
                        """
                    ),
                    {"code": str(kode_tka).strip()},
                )
                .mappings()
                .first()
            )

        if not row:
            return None

        return {
            "config": _json(row["config"], {}),
            "tka": _json(row["tka_data"], []),
        }

    except Exception as exc:
        print(f"[TKA GET] {exc}")
        return None


def update_tka_progress(
    *,
    session_id: str,
    nama: str,
    jenjang: str,
    mapel: str,
    soal_sekarang: int,
    detail_jawaban: list,
    status: str = "BERJALAN",
    user_answers: dict | None = None,
    questions: list | None = None,
    anti_cheat: dict | None = None,
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
        "user_answers": (user_answers or {}),
        "quiz_data": (questions or []),
    }

    if anti_cheat is not None:
        payload["anti_cheat"] = anti_cheat

    mapel_db = mapel if "(TKA)" in mapel else f"{mapel} (TKA)"

    query = """
    INSERT INTO sesi_ujian
      (
        id_sesi,
        nama_siswa,
        jenjang,
        mapel,
        soal_sekarang,
        detail_jawaban,
        jumlah_benar,
        jumlah_salah,
        nilai_akhir,
        status,
        created_at,
        updated_at
      )
    VALUES
      (
        :id,
        :nama,
        :jenjang,
        :mapel,
        :soal,
        :detail,
        :benar,
        :salah,
        :nilai,
        :status,
        NOW() AT TIME ZONE 'Asia/Jakarta',
        NOW() AT TIME ZONE 'Asia/Jakarta'
      )
    ON CONFLICT (id_sesi)
    DO UPDATE SET
      nama_siswa = EXCLUDED.nama_siswa,
      jenjang = EXCLUDED.jenjang,
      mapel = EXCLUDED.mapel,
      soal_sekarang = EXCLUDED.soal_sekarang,
      detail_jawaban = EXCLUDED.detail_jawaban,
      jumlah_benar = EXCLUDED.jumlah_benar,
      jumlah_salah = EXCLUDED.jumlah_salah,
      nilai_akhir = EXCLUDED.nilai_akhir,
      status =
        CASE
          WHEN sesi_ujian.status IN ('SELESAI', 'TRIAL', 'ARCHIVED')
          THEN sesi_ujian.status
          ELSE EXCLUDED.status
        END,
      created_at = sesi_ujian.created_at,
      updated_at =
        CASE
          WHEN sesi_ujian.status IN ('SELESAI', 'TRIAL', 'ARCHIVED')
          THEN sesi_ujian.updated_at
          ELSE NOW() AT TIME ZONE 'Asia/Jakarta'
        END
    """

    try:
        with conn.session as s:
            s.execute(
                text(query),
                {
                    "id": session_id,
                    "nama": nama,
                    "jenjang": normalize_tka_jenjang(jenjang),
                    "mapel": mapel_db,
                    "soal": int(soal_sekarang or 1),
                    "detail": json.dumps(payload, default=str),
                    "benar": benar,
                    "salah": salah,
                    "nilai": nilai,
                    "status": status,
                },
            )
            s.commit()
        return True

    except Exception as exc:
        print(f"[TKA PROGRESS] {exc}")
        return False


def touch_tka_heartbeat(
    session_id: str,
) -> bool:

    conn = init_db_connection()
    if not conn:
        return False

    try:
        with conn.session as s:
            s.execute(
                text(
                    """
                    UPDATE sesi_ujian
                    SET updated_at = NOW() AT TIME ZONE 'Asia/Jakarta'
                    WHERE id_sesi = :id AND status = 'BERJALAN'
                    """
                ),
                {"id": session_id},
            )
            s.commit()
        return True

    except Exception:
        return False
