"""Quiz application service boundary.
AI and persistence dependencies are now modular; legacy quiz-package helpers remain lazy compatibility hooks until Stage 4.
"""
from infrastructure.ai.quiz import generate_quiz_batch, generate_custom_quiz_ai, get_ai_hint_stream, get_ai_solution_stream
from infrastructure.ai.validation import validate_and_repair_quiz
from infrastructure.ai.policy import (normalize_quiz_options, option_labels_for_jenjang, option_count_for_jenjang,
    normalize_custom_timer_config, build_language_guidance)
from infrastructure.database.quiz import publish_custom_quiz_to_db, get_custom_quiz_from_db

def create_5_quiz_packages(*args, **kwargs):
    from legacy.app import create_5_quiz_packages as fn
    return fn(*args, **kwargs)

def get_or_create_student_quiz_order(*args, **kwargs):
    from legacy.app import get_or_create_student_quiz_order as fn
    return fn(*args, **kwargs)

__all__ = ['generate_quiz_batch','generate_custom_quiz_ai','get_ai_hint_stream','get_ai_solution_stream','validate_and_repair_quiz','publish_custom_quiz_to_db','get_custom_quiz_from_db','normalize_quiz_options','option_labels_for_jenjang','option_count_for_jenjang','normalize_custom_timer_config','build_language_guidance','create_5_quiz_packages','get_or_create_student_quiz_order']
