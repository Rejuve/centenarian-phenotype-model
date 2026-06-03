"""
HTTP service for the Centenarian Phenotype Model.

Each layer can be deployed **independently** so the surfaces can be hosted separately with
different access controls:

  - Layer 1  -> public web widget / ads        (create_app([1]))
  - Layer 2  -> in-app OR web survey           (create_app([2]))
  - Layer 3  -> Rejuve app exclusively (premium, clinical: labs + genome)  (create_app([3]))

`create_app(layers)` returns a FastAPI app exposing ONLY the chosen layers' routes (and 404s the
rest), so an L1-only deployment cannot be used to hit L3, etc. Pre-built apps + Lambda handlers are
provided for the common shapes; the all-in-one `app` is the default for single-service hosting.

Run locally (all layers):    uvicorn centenarian_phenotype.api:app --reload
Run just the widget:         uvicorn "centenarian_phenotype.api:app_widget" --reload
AWS Lambda handlers:         centenarian_phenotype.api.handler          (all)
                             centenarian_phenotype.api.handler_widget   (L1 only)
                             centenarian_phenotype.api.handler_app       (L2 + L3)

CORS: set CENTENARIAN_CORS_ORIGINS (comma-separated). The public Layer-1 widget may default to "*";
**Layer 2/3 deployments must NOT default to wildcard** — if no explicit origins are configured for a
deployment that serves L2 or L3, CORS defaults to deny (empty allow-list) and a warning is logged.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import __version__
from .scoring import MODEL_VERSIONS, get_quiz, score
from .validation import ValidationError

log = logging.getLogger(__name__)


class ScoreRequest(BaseModel):
    answers: dict[str, int] = Field(default_factory=dict,
                                    description="question_id -> chosen option index (0-based)")
    clinical: Optional[dict[str, float]] = Field(
        None, description="Layer 3 only: measured feature -> alignment in [0,1]")
    strict: bool = Field(True, description="reject unknown/out-of-range inputs (422) vs warn")
    context: Optional[dict[str, Any]] = Field(
        None, description="optional {country, sex, age, bio_age_delta} for a relative-longevity "
                          "context (validated population baseline + calibration-pending band)")
    # NOTE: Naive Bayes prior/likelihood overrides (posterior_kwargs) are intentionally NOT exposed
    # on the HTTP API — a client could manipulate posterior outputs. They remain available only in
    # the Python `score()` for research use.


def _resolve_origins(layers: tuple[int, ...], cors_origins: Optional[list[str]]) -> list[str]:
    """Resolve CORS allow-list. Explicit arg > env. L2/L3 never silently default to wildcard."""
    if cors_origins is not None:
        return cors_origins
    env = [x.strip() for x in os.getenv("CENTENARIAN_CORS_ORIGINS", "").split(",") if x.strip()]
    if env:
        return env
    if layers == (1,):
        return ["*"]  # public widget / ads may be permissive
    log.warning("No CENTENARIAN_CORS_ORIGINS set for a deployment serving layers %s; "
                "defaulting to DENY (empty allow-list). Set explicit origins for app deployments.",
                layers)
    return []


def create_app(layers=(1, 2, 3), cors_origins: Optional[list[str]] = None,
               title: Optional[str] = None) -> FastAPI:
    """Build a FastAPI app exposing only the given layer(s). 404s any layer not in the set."""
    layers = tuple(sorted(set(layers)))
    app = FastAPI(
        title=title or f"Centenarian Phenotype Model (layers {','.join(map(str, layers))})",
        version=__version__,
        description="Similarity-to-centenarians scoring (NOT a lifespan predictor).",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_resolve_origins(layers, cors_origins),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.state.layers = layers

    @app.get("/v1/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "package_version": __version__,
                "layers": list(layers), "model_versions": MODEL_VERSIONS}

    @app.get("/v1/quiz/{layer}", tags=["quiz"])
    def quiz(layer: int) -> dict[str, Any]:
        if layer not in layers:
            raise HTTPException(status_code=404, detail=f"layer {layer} not served by this deployment")
        try:
            return get_quiz(layer)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    def _score(layer: int, body: ScoreRequest) -> dict[str, Any]:
        try:
            return score(layer, body.answers, clinical=body.clinical, strict=body.strict,
                         context=body.context)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail={"error": "input validation failed",
                                                         "report": e.report})
        except (KeyError, IndexError) as e:
            raise HTTPException(status_code=422, detail=f"invalid answers/clinical payload: {e}")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    if 1 in layers:
        @app.post("/v1/score/layer1", tags=["score"])
        def score_layer1(body: ScoreRequest):
            """Layer 1 — HTML teaser widget (web / ads)."""
            return _score(1, body)

    if 2 in layers:
        @app.post("/v1/score/layer2", tags=["score"])
        def score_layer2(body: ScoreRequest):
            """Layer 2 — app or web survey."""
            return _score(2, body)

    if 3 in layers:
        @app.post("/v1/score/layer3", tags=["score"])
        def score_layer3(body: ScoreRequest):
            """Layer 3 — Rejuve app exclusively (Layer-2 answers + `clinical` labs/genome)."""
            return _score(3, body)

    return app


# Pre-built apps for the common deployment shapes -----------------------------
app = create_app([1, 2, 3])                       # all-in-one (single service)
app_widget = create_app([1])                      # public web widget / ads
app_survey = create_app([2])                      # standalone web/app survey
app_app = create_app([2, 3])                      # Rejuve app backend (survey + clinical)


# AWS Lambda adapters (optional; only if mangum is installed) ------------------
try:
    from mangum import Mangum

    handler = Mangum(app)
    handler_widget = Mangum(app_widget)
    handler_survey = Mangum(app_survey)
    handler_app = Mangum(app_app)
except ImportError:
    handler = handler_widget = handler_survey = handler_app = None
