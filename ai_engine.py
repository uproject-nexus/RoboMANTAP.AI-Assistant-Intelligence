"""Compatibility facade for the staged modular AI layer.

New code must import from infrastructure.ai, infrastructure.database, or feature services.
Legacy-only symbols are intentionally resolved lazily from legacy.ai_engine during migration.
"""
from infrastructure.ai import *
from infrastructure.database import *

def __getattr__(name):
    from legacy import ai_engine as _legacy
    return getattr(_legacy, name)
