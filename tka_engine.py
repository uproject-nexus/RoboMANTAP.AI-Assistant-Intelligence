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

TKA_TOTAL_QUESTIONS = 30
# Generator Studio dibuat ringan: satu batch hanya 5 soal.
# Ini TIDAK mengubah requirement portal siswa yang tetap 30 soal.
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
            # Query SQL di atas sudah memastikan image_id ditemukan di tka_data.
            # Tidak perlu mengambil/mem-parse seluruh JSON tka_data lagi di Python.
            config = _json(
                row.get("config"),
                {},
            )

            active_from = config.get("active_from")
            active_until = config.get("active_until")

            # TKA Studio menggunakan active_until sebagai batas aman
            # penghapusan stimulus. Baseline ini belum menyimpan relasi
            # langsung antara kode TKA dan sesi_ujian aktif, sehingga
            # kita tidak berpura-pura mengetahui status sesi per siswa.
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
                    # Waktu tidak dapat dipastikan -> fail-safe: anggap aktif.
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

    # Semua paket yang pernah memakai gambar sudah melewati active_until.
    # Stimulus boleh dikeluarkan dari Library aktif tanpa menunggu selamanya.
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

    # Jika UI sudah melakukan pengecekan usage saat tombol Hapus ditekan,
    # gunakan hasil tersebut agar tombol konfirmasi tidak melakukan query kedua.
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
    """Build a compact image part for AI generation.

    Stimulus asli dapat berukuran beberapa MB. Untuk generation kita tidak
    perlu mengirim resolusi penuh; thumbnail AI menjaga detail cukup untuk
    diagram/teks sambil mengurangi upload latency dan token/input cost.
    """
    try:
        from google.genai import types

        try:
            from PIL import Image
            import io

            src = Image.open(io.BytesIO(data))
            src.thumbnail((1600, 1600), Image.Resampling.LANCZOS)

            buf = io.BytesIO()
            # JPEG jauh lebih kecil untuk stimulus foto/diagram.
            # Untuk PNG transparan, gunakan RGB dengan latar putih agar aman.
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

    qtype = _normalize_question_type(
        question_type
    )

    if qtype == "MIXED":

        type_rules = "\n".join(
            [
                "BENTUK: CAMPURAN TKA",
                "- Gunakan ketiga bentuk: PG, MCMA, dan KATEGORI.",
                "- Tidak ada rasio resmi yang boleh diasumsikan; distribusi boleh bervariasi secara wajar.",
                "- Wajib ada minimal satu butir dari masing-masing bentuk dalam batch.",
                f"- Untuk PG: satu jawaban benar. Untuk MCMA: minimal dua jawaban benar. Untuk KATEGORI: 3-5 pernyataan dengan respons masing-masing.",
                f"- options wajib tepat {len(labels)} pilihan untuk PG/MCMA.",
            ]
        )

        schema = (
            '"options": [],\n'
            '      "correct_answer": [],\n'
            '      "correct_answers": [],\n'
            '      "category_items": []'
        )

    elif qtype == "PG":

        type_rules = f"""
BENTUK: PILIHAN GANDA (PG)
- Tepat satu jawaban benar.
- options wajib tepat {len(labels)} pilihan dengan label {', '.join(labels)}.
- correct_answer adalah SATU label, misalnya "B".
"""

        schema = f"""
"options": ["{labels[0]}. ...", "{labels[1]}. ...", ...],
      "correct_answer": "B",
      "correct_answers": []
"""

    elif qtype == "MCMA":

        type_rules = f"""
BENTUK: PILIHAN GANDA KOMPLEKS - MCMA
- Tepat {len(labels)} pilihan tersedia dengan label {', '.join(labels)}.
- Dua atau lebih jawaban harus benar; jangan hanya satu.
- correct_answers berisi 2 atau lebih LABEL unik, misalnya ["A", "C"].
- correct_answer harus sama dengan correct_answers untuk kompatibilitas.
"""

        schema = f"""
"options": ["{labels[0]}. ...", "{labels[1]}. ...", ...],
      "correct_answer": ["A", "C"],
      "correct_answers": ["A", "C"]
"""

    else:

        type_rules = """
BENTUK: PILIHAN GANDA KOMPLEKS - KATEGORI
- Buat 3-5 pernyataan yang semuanya berkaitan dengan satu stimulus/konsep.
- Setiap pernyataan memiliki kategori/respons sendiri.
- Kategori boleh Benar/Salah, Setuju/Tidak Setuju, atau kategori lain yang jelas ditentukan oleh soal.
- Setiap pernyataan hanya memiliki satu correct_response.
"""

        schema = """
"options": [],
      "correct_answer": ["Benar", "Salah", "Benar"],
      "correct_answers": ["Benar", "Salah", "Benar"],
      "category_items": [
        {
          "statement": "...",
          "options": ["Benar", "Salah"],
          "correct_response": "Benar"
        }
      ]
"""

    return f'''
Anda adalah Question Architect TKA RoboMANTAP untuk jenjang {jenjang}, mata uji {mapel}.
Buat tepat {count} butir bertipe {qtype}.

ATURAN TKA YANG WAJIB:
- TKA MTs: mata uji Bahasa Indonesia dan Matematika.
- TKA MA: mata uji wajib Bahasa Indonesia, Matematika, Bahasa Inggris; mata uji pilihan hanya jika dipilih guru.
- Bentuk soal yang didukung portal: PG, PG Kompleks-MCMA, dan PG Kompleks-Kategori.
- Jangan membuat matching/menjodohkan, isian, atau uraian.
- Stimulus TIDAK WAJIB berupa gambar.
- Stimulus dapat berupa teks, puisi, pidato, dialog, tabel, grafik, diagram, gambar, atau kombinasi yang relevan dengan mapel.
- Jika gambar diberikan, gunakan hanya fakta yang benar-benar tampak.
- Jangan memaksa setiap butir memakai gambar.
- Satu stimulus dapat dipakai bersama oleh beberapa butir melalui stimulus_group yang sama.
- Soal matematika boleh berupa perhitungan biasa tanpa gambar.
- Soal Bahasa Indonesia/Bahasa Inggris/Bahasa Arab boleh berupa teks polos tanpa gambar.
- Utamakan penalaran, literasi/numerasi, analisis, interpretasi, dan pemecahan masalah sesuai materi.
- level kognitif ditulis C4-C6 bila memang sesuai, jangan dipaksakan.
- Gunakan LaTeX $...$ hanya untuk rumus/pecahan/akar/variabel matematika.
- Jangan menaruh teks biasa di dalam delimiter matematika.
- Setiap butir wajib memiliki topic, cognitive_level, solution_basis.

{type_rules}

Jika tidak ada gambar, image_id harus null.
Jika memakai gambar, image_id WAJIB salah satu dari daftar IMAGE_ID yang diberikan.
Jika memakai stimulus teks, stimulus_text harus memuat teks stimulus yang diperlukan oleh siswa dan stimulus_group harus konsisten untuk butir yang memakai stimulus yang sama.
Jika memakai gambar yang tersedia, image_id harus berisi ID gambar yang relevan dan stimulus_text boleh kosong jika gambar sudah cukup.

IMAGE_ID yang tersedia:
{", ".join(str(x) for x in (image_ids or [])) or "(tidak ada)"}

OUTPUT JSON MURNI:
{{
  "questions": [
    {{
      "id": 1,
      "question_type": "{"PG|MCMA|KATEGORI" if qtype == "MIXED" else qtype}",
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
'''


def _option_map(options: list[str]) -> dict[str, str]:
    result = {}

    for opt in options:
        label, _ = _split_option_label(
            str(opt),
            0,
        )

        if label:
            result[label.upper()] = str(
                opt
            ).strip()

    return result


def _normalize_tka_questions(
    raw_questions: Any,
    jenjang: str,
    default_image_ids: list[str] | None = None,
) -> list[dict]:

    labels = tka_option_labels(jenjang)
    label_set = set(labels)

    if not isinstance(raw_questions, list):
        return []

    out = []

    default_image_ids = [
        str(x)
        for x in (default_image_ids or [])
        if x
    ]

    for idx, item in enumerate(
        raw_questions,
        1,
    ):

        if not isinstance(item, dict):
            return []

        question = str(
            item.get("question", "")
        ).strip()

        if not question:
            return []

        qtype = _normalize_question_type(
            item.get("question_type")
            or item.get("type")
        )

        stimulus_text, stimulus_group, image_id = (
            _normalize_stimulus(item)
        )

        if (
            image_id
            and default_image_ids
            and image_id not in default_image_ids
        ):
            return []

        topic = str(
            item.get("topic")
            or "TKA"
        ).strip()[:120]

        cognitive = str(
            item.get("cognitive_level")
            or "C4"
        ).strip()[:10]

        solution = str(
            item.get("solution_basis")
            or ""
        ).strip()

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

            raw_options = item.get(
                "options",
                [],
            )

            if not isinstance(
                raw_options,
                list,
            ):
                return []

            options, _ = normalize_quiz_options(
                raw_options,
                jenjang,
            )

            if len(options) != len(labels):
                return []

            optmap = _option_map(options)

            if set(optmap) != label_set:
                return []

            raw_answers = item.get(
                "correct_answers"
            )

            if raw_answers is None:
                raw_answers = item.get(
                    "correct_answer"
                )

            if isinstance(
                raw_answers,
                str,
            ):

                answers = [
                    x.strip().upper()
                    for x in re.split(
                        r"[,;|]",
                        raw_answers,
                    )
                    if x.strip()
                ]

            elif isinstance(
                raw_answers,
                list,
            ):

                answers = []

                for value in raw_answers:
                    label, _ = _split_option_label(
                        str(value),
                        0,
                    )

                    candidate = (
                        label.upper()
                        if label
                        else str(
                            value
                        ).strip().upper()
                    )

                    if candidate in label_set:
                        answers.append(
                            candidate
                        )

            else:
                answers = []

            answers = list(
                dict.fromkeys(answers)
            )

            if qtype == "PG" and len(answers) != 1:
                return []

            if qtype == "MCMA" and len(answers) < 2:
                return []

            base["options"] = options
            base["correct_answers"] = answers
            base["correct_answer"] = (
                answers[0]
                if qtype == "PG"
                else answers
            )
            base["category_items"] = []

        else:

            raw_items = item.get(
                "category_items",
                [],
            )

            if (
                not isinstance(
                    raw_items,
                    list,
                )
                or not 3 <= len(raw_items) <= 5
            ):
                return []

            category_items = []
            answers = []

            for cat in raw_items:

                if not isinstance(
                    cat,
                    dict,
                ):
                    return []

                statement = str(
                    cat.get("statement")
                    or ""
                ).strip()

                choices = cat.get(
                    "options"
                )

                correct_response = str(
                    cat.get("correct_response")
                    or cat.get("correct_answer")
                    or ""
                ).strip()

                if (
                    not statement
                    or not isinstance(
                        choices,
                        list,
                    )
                    or len(choices) < 2
                    or not correct_response
                ):
                    return []

                choices = [
                    str(x).strip()
                    for x in choices
                    if str(x).strip()
                ]

                if correct_response not in choices:
                    return []

                category_items.append(
                    {
                        "statement": statement,
                        "options": choices,
                        "correct_response": correct_response,
                    }
                )

                answers.append(
                    correct_response
                )

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
    """Generate one bounded AI batch.

    This function is intentionally small: Studio calls it with 5 questions
    per request instead of asking Gemini for all 15 questions at once.
    generate_tka_30() remains unchanged and may still request 30 questions.
    """
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

    # Fallback sengaja berganti model, bukan mengulang model pertama terus.
    # Urutan: model utama -> model fallback -> key kedua/model utama.
    # Ini penting untuk kondisi 503 high demand pada model utama.
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

    # KATEGORI membutuhkan output lebih panjang daripada PG/MCMA, tetapi
    # tetap jauh lebih kecil daripada request campuran 15 soal.
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
) -> list[dict]:
    """Generate exactly 15 Studio questions using three internal 5-question batches.

    IMPORTANT:
    - User-visible result is always exactly 15 questions.
    - 15 is split internally into 5 PG + 5 MCMA + 5 KATEGORI.
    - A partial result is NEVER returned.
    - 75-minute duration is controlled elsewhere by
      TKA_DEFAULT_DURATION_SECONDS and is not changed here.
    - generate_tka_30() is intentionally untouched for the student portal.
    """
    jenjang = normalize_tka_jenjang(jenjang)
    mapel = tka_mapel_name(mapel)

    # Studio requirement is fixed at exactly 15. Do not silently downgrade
    # to 5 or 10 if an old UI/API caller sends another value.
    requested_count = int(count or TKA_GENERATION_QUESTIONS)
    if requested_count != TKA_GENERATION_QUESTIONS:
        print(
            f"[TKA STUDIO] count={requested_count} diabaikan; "
            f"Studio dikunci tepat {TKA_GENERATION_QUESTIONS} soal."
        )
    count = TKA_GENERATION_QUESTIONS

    selected = list(
        dict.fromkeys(
            str(x) for x in (image_ids or []) if x
        )
    )[:TKA_GENERATION_MAX_IMAGES]

    if not selected and auto_select_images:
        selected = [
            str(x["image_id"])
            for x in list_tka_images(
                source_type="SYSTEM",
                jenjang=jenjang,
                mapel=mapel,
                limit=TKA_GENERATION_MAX_IMAGES,
            )
        ]

    image_records = []
    for image_id in selected:
        record = get_tka_image(image_id)
        if record:
            image_records.append(record)

    print(
        f"[TKA STUDIO] mulai generate tepat {count} soal: "
        f"3 batch x {TKA_STUDIO_BATCH_SIZE} "
        f"({', '.join(TKA_STUDIO_BATCH_TYPES)}), "
        f"gambar={len(image_records)}."
    )

    all_questions: list[dict] = []

    # Semua batch wajib berhasil. Kalau satu saja gagal, return [] agar tidak
    # ada penyimpanan/publish parsial yang tampak seperti kuis lengkap.
    for question_type in TKA_STUDIO_BATCH_TYPES:
        # Jalur utama: 5 soal sekaligus. Jika 5 masih terkena 503/504 atau
        # output invalid, pecah hanya batch internal tersebut menjadi 3 + 2.
        # Hasil Studio tetap wajib 15 soal; 3/2 bukan jumlah yang ditampilkan.
        batch = generate_tka_questions_batch(
            jenjang=jenjang,
            mapel=mapel,
            question_type=question_type,
            count=TKA_STUDIO_BATCH_SIZE,
            image_records=image_records,
        )

        if len(batch) != TKA_STUDIO_BATCH_SIZE:
            print(
                f"[TKA STUDIO] batch {question_type} 5 soal gagal; "
                "fallback internal 3 + 2 soal."
            )
            batch_3 = generate_tka_questions_batch(
                jenjang=jenjang,
                mapel=mapel,
                question_type=question_type,
                count=3,
                image_records=image_records,
            )
            if len(batch_3) == 3:
                batch_2 = generate_tka_questions_batch(
                    jenjang=jenjang,
                    mapel=mapel,
                    question_type=question_type,
                    count=2,
                    image_records=image_records,
                )
            else:
                batch_2 = []

            if len(batch_3) == 3 and len(batch_2) == 2:
                batch = batch_3 + batch_2
                print(
                    f"[TKA STUDIO] fallback {question_type} berhasil: 3 + 2 = 5 soal."
                )
            else:
                print(
                    f"[TKA STUDIO] GAGAL: batch {question_type} hanya "
                    f"{len(batch_3) + len(batch_2)}/5 setelah fallback. "
                    "Tidak mengembalikan hasil parsial."
                )
                return []

        all_questions.extend(batch)
        print(
            f"[TKA STUDIO] batch {question_type} selesai: "
            f"{len(batch)}/{TKA_STUDIO_BATCH_SIZE}; "
            f"total sementara {len(all_questions)}/{count}."
        )

    if len(all_questions) != count:
        print(
            f"[TKA STUDIO] GAGAL validasi jumlah akhir: "
            f"{len(all_questions)}/{count}."
        )
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

    jenjang = normalize_tka_jenjang(
        jenjang
    )

    mapel = tka_mapel_name(
        mapel
    )

    selected = list(
        dict.fromkeys(
            str(x)
            for x in (image_ids or [])
            if x
        )
    )[:5]

    if not selected and auto_select_images:
        selected = [
            str(x["image_id"])
            for x in list_tka_images(
                source_type="SYSTEM",
                jenjang=jenjang,
                mapel=mapel,
                limit=5,
            )
        ]

    if not selected and auto_select_images:
        selected = [
            str(x["image_id"])
            for x in list_tka_images(
                source_type="SYSTEM",
                jenjang=jenjang,
                limit=5,
            )
        ]

    image_records = []

    for image_id in selected:
        record = get_tka_image(
            image_id
        )

        if record:
            image_records.append(
                record
            )

    image_records = image_records[:5]

    batch = generate_tka_questions_batch(
        jenjang=jenjang,
        mapel=mapel,
        question_type="MIXED",
        count=TKA_TOTAL_QUESTIONS,
        image_records=image_records,
    )

    if len(batch) != TKA_TOTAL_QUESTIONS:
        return []

    for idx, question in enumerate(
        batch,
        1,
    ):
        question["id"] = idx

    return batch


def validate_tka_questions(
    questions: list[dict],
    jenjang: str,
    expected_count: int = TKA_TOTAL_QUESTIONS,
) -> tuple[bool, str]:

    if (
        not isinstance(questions, list)
        or len(questions)
        != expected_count
    ):
        return (
            False,
            f"Paket harus tepat {expected_count} soal.",
        )

    labels = tka_option_labels(
        jenjang
    )

    label_set = set(labels)

    counts = {
        x: 0
        for x in TKA_QUESTION_TYPES
    }

    for idx, q in enumerate(
        questions,
        1,
    ):

        if (
            not isinstance(q, dict)
            or not str(
                q.get("question", "")
            ).strip()
        ):
            return (
                False,
                f"Soal nomor {idx} tidak valid.",
            )

        qtype = _normalize_question_type(
            q.get("question_type")
        )

        counts[qtype] += 1

        if qtype in {"PG", "MCMA"}:

            options = q.get(
                "options"
            )

            if (
                not isinstance(
                    options,
                    list,
                )
                or len(options)
                != len(labels)
            ):
                return (
                    False,
                    f"Soal nomor {idx} harus memiliki tepat "
                    f"{len(labels)} opsi "
                    f"({'/'.join(labels)}).",
                )

            normalized_labels = {
                (
                    _split_option_label(
                        str(o),
                        0,
                    )[0]
                    or ""
                ).upper()
                for o in options
            }

            if normalized_labels != label_set:
                return (
                    False,
                    f"Opsi soal nomor {idx} harus berlabel "
                    f"{', '.join(labels)}.",
                )

            answers = q.get(
                "correct_answers"
            )

            if not isinstance(
                answers,
                list,
            ):
                answers = (
                    [q.get("correct_answer")]
                    if q.get("correct_answer")
                    else []
                )

            answers = [
                str(x).strip().upper()
                for x in answers
                if str(x).strip()
            ]

            if (
                qtype == "PG"
                and len(answers) != 1
            ):
                return (
                    False,
                    f"PG nomor {idx} harus memiliki "
                    "tepat satu jawaban benar.",
                )

            if (
                qtype == "MCMA"
                and len(set(answers)) < 2
            ):
                return (
                    False,
                    f"MCMA nomor {idx} harus memiliki "
                    "minimal dua jawaban benar.",
                )

            if any(
                x not in label_set
                for x in answers
            ):
                return (
                    False,
                    f"Kunci soal nomor {idx} "
                    "tidak sesuai label opsi.",
                )

        else:

            items = q.get(
                "category_items"
            )

            answers = q.get(
                "correct_answers"
            )

            if (
                not isinstance(
                    items,
                    list,
                )
                or not 3 <= len(items) <= 5
            ):
                return (
                    False,
                    f"Soal kategori nomor {idx} "
                    "harus memiliki 3-5 pernyataan.",
                )

            if (
                not isinstance(
                    answers,
                    list,
                )
                or len(answers) != len(items)
            ):
                return (
                    False,
                    f"Kunci kategori nomor {idx} "
                    "tidak lengkap.",
                )

            for pos, item in enumerate(
                items,
                1,
            ):

                if (
                    not isinstance(
                        item,
                        dict,
                    )
                    or not str(
                        item.get("statement", "")
                    ).strip()
                ):
                    return (
                        False,
                        f"Pernyataan kategori "
                        f"nomor {idx}.{pos} "
                        "tidak valid.",
                    )

                choices = item.get(
                    "options"
                )

                correct = str(
                    item.get(
                        "correct_response"
                    )
                    or ""
                ).strip()

                if (
                    not isinstance(
                        choices,
                        list,
                    )
                    or len(choices) < 2
                    or correct not in choices
                ):
                    return (
                        False,
                        f"Respons kategori "
                        f"nomor {idx}.{pos} "
                        "tidak valid.",
                    )

        if not q.get("topic"):
            return (
                False,
                f"Topik soal nomor {idx} kosong.",
            )

    missing = [
        qtype
        for qtype in TKA_QUESTION_TYPES
        if counts.get(qtype, 0) < 1
    ]

    if missing:
        return (
            False,
            "Paket TKA harus memuat semua "
            "bentuk soal: "
            + ", ".join(missing)
            + " belum ada.",
        )

    return (
        True,
        f"OK • PG {counts['PG']} • "
        f"MCMA {counts['MCMA']} • "
        f"Kategori {counts['KATEGORI']}",
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

    ok, reason = validate_tka_30(
        questions,
        config.get(
            "jenjang",
            "MTs",
        ),
    )

    if not ok:
        print(
            f"[TKA PUBLISH] {reason}"
        )
        return False

    code = re.sub(
        r"[^A-Z0-9_-]",
        "",
        str(kode_tka or "").upper(),
    )[:40]

    if not code:
        return False

    active_from = (
        config.get("active_from")
        or _now_wib_naive().isoformat()
    )

    active_until = (
        config.get("active_until")
        or (
            _now_wib_naive()
            + timedelta(
                hours=TKA_DEFAULT_ACTIVE_HOURS
            )
        ).isoformat()
    )

    cfg = {
        **config,
        "jenis": "TKA",
        "total_soal": TKA_TOTAL_QUESTIONS,
        "jenjang": normalize_tka_jenjang(
            config.get(
                "jenjang",
                "MTs",
            )
        ),
        "mapel": tka_mapel_name(
            config.get(
                "mapel",
                "Matematika",
            )
        ),
        "timer_seconds": int(
            config.get(
                "timer_seconds"
            )
            or TKA_DEFAULT_DURATION_SECONDS
        ),
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
                        NOW()
                            AT TIME ZONE 'Asia/Jakarta',
                        NOW()
                            AT TIME ZONE 'Asia/Jakarta'
                    )
                    ON CONFLICT (kode_tka)
                    DO UPDATE SET
                        config =
                            EXCLUDED.config,
                        tka_data =
                            EXCLUDED.tka_data,
                        updated_at =
                            NOW()
                            AT TIME ZONE 'Asia/Jakarta'
                    """
                ),
                {
                    "code": code,
                    "cfg": json.dumps(
                        cfg,
                        default=str,
                    ),
                    "data": json.dumps(
                        questions,
                        default=str,
                    ),
                },
            )

            s.commit()

        return True

    except Exception as exc:
        print(
            f"[TKA PUBLISH] {exc}"
        )
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
                    {
                        "code": str(
                            kode_tka
                        ).strip()
                    },
                )
                .mappings()
                .first()
            )

        if not row:
            return None

        return {
            "config": _json(
                row["config"],
                {},
            ),
            "tka": _json(
                row["tka_data"],
                [],
            ),
        }

    except Exception as exc:
        print(
            f"[TKA GET] {exc}"
        )
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

    detail = (
        detail_jawaban
        if isinstance(
            detail_jawaban,
            list,
        )
        else []
    )

    total = len(detail) or (
        len(questions)
        if isinstance(
            questions,
            list,
        )
        else TKA_TOTAL_QUESTIONS
    )

    benar = sum(
        1
        for x in detail
        if x is True
    )

    salah = sum(
        1
        for x in detail
        if x is False
    )

    nilai = (
        int(
            round(
                benar
                / total
                * 100
            )
        )
        if total
        else 0
    )

    payload = {
        "activity_type": "TKA",
        "detail_boolean": detail,
        "user_answers": (
            user_answers or {}
        ),
        "quiz_data": (
            questions or []
        ),
    }

    if anti_cheat is not None:
        payload["anti_cheat"] = anti_cheat

    mapel_db = (
        mapel
        if "(TKA)" in mapel
        else f"{mapel} (TKA)"
    )

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
        NOW()
            AT TIME ZONE 'Asia/Jakarta',
        NOW()
            AT TIME ZONE 'Asia/Jakarta'
      )
    ON CONFLICT (id_sesi)
    DO UPDATE SET
      nama_siswa =
        EXCLUDED.nama_siswa,
      jenjang =
        EXCLUDED.jenjang,
      mapel =
        EXCLUDED.mapel,
      soal_sekarang =
        EXCLUDED.soal_sekarang,
      detail_jawaban =
        EXCLUDED.detail_jawaban,
      jumlah_benar =
        EXCLUDED.jumlah_benar,
      jumlah_salah =
        EXCLUDED.jumlah_salah,
      nilai_akhir =
        EXCLUDED.nilai_akhir,
      status =
        CASE
          WHEN sesi_ujian.status
            IN (
              'SELESAI',
              'TRIAL',
              'ARCHIVED'
            )
          THEN sesi_ujian.status
          ELSE EXCLUDED.status
        END,
      created_at =
        sesi_ujian.created_at,
      updated_at =
        CASE
          WHEN sesi_ujian.status
            IN (
              'SELESAI',
              'TRIAL',
              'ARCHIVED'
            )
          THEN sesi_ujian.updated_at
          ELSE
            NOW()
            AT TIME ZONE 'Asia/Jakarta'
        END
    """

    try:
        with conn.session as s:
            s.execute(
                text(query),
                {
                    "id": session_id,
                    "nama": nama,
                    "jenjang": normalize_tka_jenjang(
                        jenjang
                    ),
                    "mapel": mapel_db,
                    "soal": int(
                        soal_sekarang or 1
                    ),
                    "detail": json.dumps(
                        payload,
                        default=str,
                    ),
                    "benar": benar,
                    "salah": salah,
                    "nilai": nilai,
                    "status": status,
                },
            )

            s.commit()

        return True

    except Exception as exc:
        print(
            f"[TKA PROGRESS] {exc}"
        )
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
                    SET
                        updated_at =
                            NOW()
                            AT TIME ZONE 'Asia/Jakarta'
                    WHERE
                        id_sesi = :id
                        AND status = 'BERJALAN'
                    """
                ),
                {
                    "id": session_id
                },
            )

            s.commit()

        return True

    except Exception:
        return False
