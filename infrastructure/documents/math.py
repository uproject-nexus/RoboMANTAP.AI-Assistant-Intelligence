"""Document math boundary.

Stage 2 exposes the normalization primitive only. Full OMML rendering remains
untouched in legacy until the dedicated document migration stage.
"""
from utils.math import clean_math_string, clean_math_text

__all__ = ["clean_math_string", "clean_math_text"]
