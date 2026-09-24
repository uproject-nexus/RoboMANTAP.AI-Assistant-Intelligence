"""Generic model/key rotation primitive."""
from __future__ import annotations
from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")


def rotate_call(clients: Iterable[object], models: Iterable[str], call: Callable[[object, str], T]) -> T | None:
    for client in clients:
        for model in models:
            try:
                return call(client, model)
            except Exception:
                continue
    return None
