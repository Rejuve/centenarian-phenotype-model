"""Four-class Naive Bayes posterior layer for the Centenarian Phenotype Model.

WHAT THIS IS (and is not)
-------------------------
The deployed **v1 score** (`scoring.score` -> `evidence_weighted_similarity`) is an
evidence-weighted mean of per-feature alignment. THIS module is the **planned v2 probabilistic
layer**, implemented and exposed now as a *derived* output so the surfaces and PLN integration can
consume posteriors, but it is **NOT a model trained on labelled four-class data**.

It is a genuine Naive Bayes computation:

    P(class | evidence)  ∝  P(class) · ∏_i  L(alignment_i | class) ^ eff_weight_i

over the four reference classes. What is *not* yet data-calibrated is the **likelihood model**:
each class is given an explicit alignment centroid (`MU`) and shared spread (`SIGMA`) — a declared,
monotone, auditable parameterisation, NOT estimated from labelled nonagenarian/centenarian/
supercentenarian feature distributions (the corpus has no cleanly-named 90–99 subjects; subject age
is floored at 100 — see METHODS "Nonagenarian floor"). The centroids are ordered
general < nonagenarian < centenarian < supercentenarian, so higher alignment moves posterior mass
toward the longevity classes. When labelled multi-class feature distributions become available, only
`MU`/`SIGMA` change — the math and the public contract stay fixed.

Because of this, the user-facing number remains `evidence_weighted_similarity`. Posteriors are
reported as `class_posteriors` / `centenarian_posterior` / `supercentenarian_posterior` and are
flagged `calibration: "heuristic_pending"` in the model card.
"""
from __future__ import annotations

import math

# Ordered reference classes (low -> high longevity). Order is load-bearing: MU must be monotone.
CLASSES = (
    "general_population",
    "nonagenarian_90_99",
    "centenarian_100_109",
    "supercentenarian_110_plus",
)

# Default priors. Ordered by population base rate (most people are general population; reaching 90,
# 100, 110 is progressively rarer), but deliberately *mildly* informative rather than the true
# demographic base rates (~1e-4 centenarian) so the posterior expresses **resemblance**, not raw
# incidence — a strongly centenarian-like profile should be able to accrue meaningful centenarian
# mass. Overridable per call (see `class_posteriors(priors=...)`).
DEFAULT_PRIORS = {
    "general_population": 0.70,
    "nonagenarian_90_99": 0.20,
    "centenarian_100_109": 0.08,
    "supercentenarian_110_plus": 0.02,
}

# Declared (calibration-pending) likelihood model: the alignment a feature is *expected* to take
# under each class. Monotone increasing — this is the only assumption the layer makes.
MU = {
    "general_population": 0.45,
    "nonagenarian_90_99": 0.62,
    "centenarian_100_109": 0.78,
    "supercentenarian_110_plus": 0.88,
}
SIGMA = 0.18  # shared spread of the per-class alignment likelihood

LIKELIHOOD_CALIBRATION = "heuristic_pending"


def _log_gaussian(x: float, mu: float, sigma: float) -> float:
    # Drop the normalising constant: it is identical across classes (shared sigma) and so cancels
    # in the softmax. Posteriors depend only on (x - mu_c)^2 / sigma^2.
    return -((x - mu) ** 2) / (2.0 * sigma * sigma)


def class_posteriors(items, priors=None, mu=None, sigma=None):
    """Compute P(class | evidence) over the four reference classes.

    `items` is the list of scored features the engine already built — each a dict with
    ``alignment`` (0..1) and ``eff_weight`` (>=0). Higher-weight features count more, exactly as in
    the evidence-weighted score (weighted Naive Bayes via the eff_weight exponent).

    Returns a dict {class_name: posterior}, summing to 1.0. With no items, returns the priors.
    """
    priors = priors or DEFAULT_PRIORS
    mu = mu or MU
    sigma = sigma if sigma is not None else SIGMA
    if sigma <= 0:
        raise ValueError("sigma must be > 0")

    logp = {}
    for c in CLASSES:
        lp = math.log(priors[c]) if priors.get(c, 0) > 0 else -math.inf
        for it in items:
            lp += it.get("eff_weight", it.get("weight", 1.0)) * _log_gaussian(
                it["alignment"], mu[c], sigma)
        logp[c] = lp

    m = max(logp.values())
    exps = {c: math.exp(lp - m) for c, lp in logp.items()}
    z = sum(exps.values()) or 1.0
    return {c: exps[c] / z for c in CLASSES}


def posterior_summary(items, priors=None, mu=None, sigma=None):
    """Posteriors plus the two product-relevant marginals, JSON-serialisable and rounded."""
    post = class_posteriors(items, priors=priors, mu=mu, sigma=sigma)
    return {
        "class_posteriors": {c: round(post[c], 4) for c in CLASSES},
        "centenarian_posterior": round(post["centenarian_100_109"], 4),
        "supercentenarian_posterior": round(post["supercentenarian_110_plus"], 4),
        "calibration": LIKELIHOOD_CALIBRATION,
    }
