"""Small, dependency-light Streamlit session-state helpers."""
from __future__ import annotations
from typing import Any


def _state():
    import streamlit as st
    return st.session_state


def get_state(key: str, default: Any = None) -> Any:
    return _state().get(key, default)


def set_state(key: str, value: Any) -> None:
    _state()[key] = value


def has_state(key: str) -> bool:
    return key in _state()


def pop_state(key: str, default: Any = None) -> Any:
    return _state().pop(key, default)


def set_defaults(values: dict[str, Any]) -> None:
    state = _state()
    for key, value in values.items():
        state.setdefault(key, value)
