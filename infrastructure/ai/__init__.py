"""AI infrastructure public API."""
from .client import get_gemini_clients, reset_client_cache
from .service import call_gemini_with_rotation, stream_ai_text
from .policy import *
from .quiz import generate_quiz_batch, generate_custom_quiz_ai, get_ai_hint_stream, get_ai_solution_stream
from .validation import validate_and_repair_quiz
from .material import build_material_knowledge_pack, normalize_material_trigger
