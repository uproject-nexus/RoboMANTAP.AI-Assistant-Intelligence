"""Material bundle persistence repository."""
from __future__ import annotations
import json
from infrastructure.database.connection import init_db_connection
try:
    from sqlalchemy import text
except Exception:
    text = None
def save_material_bundle_to_db(bundle_code: str, bundle: dict, config: dict | None = None) -> bool:
    conn = init_db_connection()
    if not conn:
        return False
    query = """
    INSERT INTO material_hub (bundle_code, config, bundle_data, created_at, updated_at)
    VALUES (:code, :cfg, :data, NOW() AT TIME ZONE 'Asia/Jakarta', NOW() AT TIME ZONE 'Asia/Jakarta')
    ON CONFLICT (bundle_code) DO UPDATE SET
        config = EXCLUDED.config,
        bundle_data = EXCLUDED.bundle_data,
        updated_at = NOW() AT TIME ZONE 'Asia/Jakarta';
    """
    try:
        with conn.session as session:
            session.execute(text(query), {
                "code": bundle_code.strip().upper(),
                "cfg": json.dumps(config or {}, ensure_ascii=False, default=str),
                "data": json.dumps(bundle, ensure_ascii=False, default=str),
            })
            session.commit()
        return True
    except Exception as exc:
        print(f"Error save_material_bundle_to_db: {exc}")
        return False


def get_material_bundle_from_db(bundle_code: str):
    conn = init_db_connection()
    if not conn:
        return None
    try:
        with conn.session as session:
            row = session.execute(
                text("SELECT bundle_data, config FROM material_hub WHERE UPPER(bundle_code)=UPPER(:code)"),
                {"code": bundle_code.strip()},
            ).fetchone()
        if not row:
            return None
        bundle = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        config = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
        bundle["config"] = config
        bundle["bundle_code"] = bundle_code.strip().upper()
        return bundle
    except Exception as exc:
        print(f"Error get_material_bundle_from_db: {exc}")
        return None
