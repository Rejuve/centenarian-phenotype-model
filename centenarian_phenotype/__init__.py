"""Centenarian Longevity Phenotype Model — deployable scoring package.

A similarity score, NOT a lifespan predictor: output is "X% similar to verified centenarians".
See `scoring.score` for the public entry point.
"""
from .scoring import score, get_quiz, load_model, MODEL_VERSIONS, CONSTRUCT_MAP

__all__ = ["score", "get_quiz", "load_model", "MODEL_VERSIONS", "CONSTRUCT_MAP"]
__version__ = "0.1.0"
