"""Strict input validation for the scoring engine.

Production callers should use ``strict=True`` (the default in ``scoring.score``): unknown question
IDs, unknown clinical features, out-of-range option indices, clinical alignments outside [0, 1], and
empty/insufficient input all raise :class:`ValidationError` instead of silently degrading the score.
Research/debug callers may pass ``strict=False`` to downgrade these to structured warnings.

The structured report (also attached to the exception) groups issues so the API can return a clean
422 body and the app can prompt the user:

    unknown_inputs        — question IDs / clinical features not in the model
    ignored_inputs        — inputs dropped from scoring (only in non-strict mode)
    invalid_inputs        — wrong type / un-parseable
    missing_required_inputs — too little to produce a usable score
    out_of_range_values   — option index out of range, or alignment not in [0, 1]
"""
from __future__ import annotations


class ValidationError(ValueError):
    """Raised in strict mode when inputs cannot be scored safely. Carries a structured report."""

    def __init__(self, report: dict):
        self.report = report
        problems = {k: v for k, v in report.items() if v and k != "ignored_inputs"}
        super().__init__(f"input validation failed: {problems}")


def _empty_report() -> dict:
    return {
        "unknown_inputs": [],
        "ignored_inputs": [],
        "invalid_inputs": [],
        "missing_required_inputs": [],
        "out_of_range_values": [],
    }


def validate_quiz_answers(answers, question_index, report) -> dict:
    """Validate {question_id: option_index} against the model's questions. Returns clean answers."""
    clean = {}
    if not isinstance(answers, dict):
        report["invalid_inputs"].append({"answers": "must be an object of question_id -> option index"})
        return clean
    for qid, oi in answers.items():
        q = question_index.get(qid)
        if q is None:
            report["unknown_inputs"].append(qid)
            report["ignored_inputs"].append(qid)
            continue
        if not isinstance(oi, int) or isinstance(oi, bool):
            report["invalid_inputs"].append({qid: f"option index must be an integer, got {oi!r}"})
            continue
        if not (0 <= oi < len(q["options"])):
            report["out_of_range_values"].append(
                {qid: f"option index {oi} out of range 0..{len(q['options']) - 1}"})
            continue
        clean[qid] = oi
    return clean


def validate_clinical(clinical, feature_defs, report) -> dict:
    """Validate {feature: alignment} for Layer 3. alignment must be a float in [0, 1]. Returns clean."""
    clean = {}
    if clinical is None:
        return clean
    if not isinstance(clinical, dict):
        report["invalid_inputs"].append({"clinical": "must be an object of feature -> alignment in [0,1]"})
        return clean
    for feat, al in clinical.items():
        if feat not in feature_defs:
            report["unknown_inputs"].append(feat)
            report["ignored_inputs"].append(feat)
            continue
        if isinstance(al, bool) or not isinstance(al, (int, float)):
            report["invalid_inputs"].append({feat: f"alignment must be a number in [0,1], got {al!r}"})
            continue
        if not (0.0 <= float(al) <= 1.0):
            report["out_of_range_values"].append({feat: f"alignment {al} outside [0,1]"})
            continue
        clean[feat] = float(al)
    return clean


def finalize(report, scored_count, strict, min_items=1):
    """Flag insufficient input and, in strict mode, raise if anything is wrong.

    Returns the (possibly mutated) report so non-strict callers can attach it as `warnings`.
    """
    if scored_count < min_items:
        report["missing_required_inputs"].append(
            f"need at least {min_items} valid scored item(s); got {scored_count}")
        # A score with no scoreable inputs is meaningless (weighted mean over an empty set), so this is
        # a hard error even in non-strict mode — never return a hollow score with a degenerate CI.
        raise ValidationError(report)
    if strict:
        hard = ("unknown_inputs", "invalid_inputs", "out_of_range_values", "missing_required_inputs")
        if any(report[k] for k in hard):
            raise ValidationError(report)
    return report
