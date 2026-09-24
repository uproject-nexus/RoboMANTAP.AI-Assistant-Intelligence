"""Database connection lifecycle.

The connection layer knows how to create a SQLAlchemy connection or fall back
to Streamlit's PostgreSQL connection. It does not know quiz business rules.
"""
from __future__ import annotations
from typing import Any
import os

import pandas as pd

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
except ImportError:  # pragma: no cover
    create_engine = None
    text = None
    sessionmaker = None

_conn_cache: Any = None


class DBWrapper:
    def __init__(self, engine):
        self.engine = engine
        self.SessionMaker = sessionmaker(bind=engine)

    @property
    def session(self):
        return self.SessionMaker()

    def query(self, sql_query: str, ttl: int = 0):
        with self.engine.connect() as connection:
            return pd.read_sql(text(sql_query), connection)


def _streamlit_secret(name: str):
    try:
        import streamlit as st
        if hasattr(st, "secrets") and name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return None


def get_database_url() -> str | None:
    return os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or _streamlit_secret("DATABASE_URL")


def init_db_connection():
    global _conn_cache
    if _conn_cache is not None:
        return _conn_cache

    db_url = get_database_url()
    if db_url and create_engine is not None:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        try:
            _conn_cache = DBWrapper(create_engine(db_url, pool_pre_ping=True))
            return _conn_cache
        except Exception:
            pass

    try:
        import streamlit as st
        _conn_cache = st.connection("postgresql", type="sql")
        return _conn_cache
    except Exception:
        return None


def reset_db_connection_cache() -> None:
    global _conn_cache
    _conn_cache = None
