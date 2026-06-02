"""Centenarian Longevity Phenotype Model — deployable scoring package.

A similarity score, NOT a lifespan predictor: output is "X% similar to verified centenarians".
See `scoring.score` for the public entry point.
"""
from .scoring import score, get_quiz, load_model, MODEL_VERSIONS, CONSTRUCT_MAP
from .validation import ValidationError
from .mappers import map_value, map_panel, MAPPERS

__all__ = ["score", "get_quiz", "load_model", "MODEL_VERSIONS", "CONSTRUCT_MAP",
           "ValidationError", "map_value", "map_panel", "MAPPERS"]
__version__ = "0.2.0"
