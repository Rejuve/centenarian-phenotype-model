"""Smoke tests for the HTTP service (skipped if fastapi/httpx are absent)."""
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from centenarian_phenotype.api import app  # noqa: E402

client = TestClient(app)


def test_health():
    r = client.get("/v1/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_quiz_layers():
    assert len(client.get("/v1/quiz/1").json()["questions"]) == 12
    assert len(client.get("/v1/quiz/2").json()["questions"]) == 32
    assert client.get("/v1/quiz/3").status_code == 404  # layer 3 is not a quiz


def test_quiz_does_not_leak_internal_scoring_fields():
    q = client.get("/v1/quiz/1").json()
    opt = q["questions"][0]["options"][0]
    assert set(opt) == {"index", "label"}  # no alignment/basis/weight exposed


def test_score_routes():
    r1 = client.post("/v1/score/layer1", json={"answers": {"q_smoking": 0, "q_family": 0}})
    assert r1.status_code == 200 and r1.json()["completeness_pct"] == 30
    r2 = client.post("/v1/score/layer2", json={"answers": {"q_diabetes": 0}})
    assert r2.json()["completeness_pct"] == 50
    r3 = client.post("/v1/score/layer3",
                     json={"answers": {"q_smoking": 0}, "clinical": {"rs2069837": 1.0}})
    assert r3.json()["completeness_pct"] == 80
    assert r3.json()["gwas_corroborated_weight_share_pct"] > 0


def test_invalid_payload_returns_422():
    r = client.post("/v1/score/layer1", json={"answers": {"q_smoking": 99}})
    assert r.status_code == 422


def test_unknown_question_returns_structured_422():
    r = client.post("/v1/score/layer1", json={"answers": {"q_bogus": 0, "q_smoking": 0}})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error"] == "input validation failed"
    assert "q_bogus" in detail["report"]["unknown_inputs"]


def test_unknown_clinical_feature_returns_422():
    r = client.post("/v1/score/layer3",
                    json={"answers": {"q_smoking": 0}, "clinical": {"not_a_marker": 0.9}})
    assert r.status_code == 422


def test_empty_answers_returns_422():
    r = client.post("/v1/score/layer2", json={"answers": {}})
    assert r.status_code == 422


def test_non_strict_request_is_permissive():
    r = client.post("/v1/score/layer1",
                    json={"answers": {"q_smoking": 0, "q_bogus": 0}, "strict": False})
    assert r.status_code == 200
    assert "q_bogus" in r.json()["warnings"]["unknown_inputs"]


def test_score_returns_posteriors_and_product_fields():
    r = client.post("/v1/score/layer1",
                    json={"answers": {"q_smoking": 0, "q_family": 0, "q_social": 0}}).json()
    assert "class_posteriors" in r and "centenarian_posterior" in r
    assert "domain_scores" in r and "missing_high_value_inputs" in r


def test_layer_scoped_apps_are_independent():
    from centenarian_phenotype.api import create_app

    # widget = Layer 1 only: serves L1, refuses L2/L3
    w = TestClient(create_app([1]))
    assert w.get("/v1/quiz/1").status_code == 200
    assert w.post("/v1/score/layer1", json={"answers": {"q_smoking": 0}}).status_code == 200
    assert w.get("/v1/quiz/2").status_code == 404           # layer not served
    assert w.post("/v1/score/layer2", json={"answers": {}}).status_code == 404  # route absent
    assert w.post("/v1/score/layer3", json={"answers": {}}).status_code == 404

    # app backend = Layers 2+3: serves survey + clinical, refuses L1
    a = TestClient(create_app([2, 3]))
    assert a.get("/v1/quiz/2").status_code == 200
    assert a.post("/v1/score/layer3",
                  json={"answers": {"q_smoking": 0}, "clinical": {"rs2069837": 1.0}}).status_code == 200
    assert a.post("/v1/score/layer1", json={"answers": {}}).status_code == 404
    assert a.get("/v1/health").json()["layers"] == [2, 3]
