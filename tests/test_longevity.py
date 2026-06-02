"""Relative-longevity context: validated demographic baseline + calibration-pending phenotype band."""
import pytest

from centenarian_phenotype import population_baseline, relative_longevity, score, list_countries


def test_population_baseline_is_real_demography():
    jp_f = population_baseline("Japan", sex="F", age=65, target=100)
    us_m = population_baseline("USA", sex="M", age=65, target=100)
    # Japanese women reach 100 from 65 far more often than US men — a known demographic fact.
    assert jp_f["p_reach_target"] > us_m["p_reach_target"]
    assert jp_f["source"].startswith("Human Mortality Database")
    assert jp_f["target_age"] == 100 and jp_f["from_age"] == 65


def test_country_alias_and_code_resolution():
    assert population_baseline("United States", sex="female")["country_code"] == "USA"
    assert population_baseline("USA", sex="female")["country_code"] == "USA"
    assert population_baseline("uk", sex="male")["country_code"] == "GBR"


def test_unknown_country_returns_none():
    assert population_baseline("Atlantis", sex="F") is None


def test_age_selects_the_right_anchor():
    young = population_baseline("Sweden", sex="F", age=65, target=100)
    old = population_baseline("Sweden", sex="F", age=82, target=100)
    assert young["from_age"] == 65 and old["from_age"] == 80


def test_relative_longevity_separates_validated_from_pending():
    hi = relative_longevity(90, country="Japan", sex="F", age=65)
    lo = relative_longevity(40, country="Japan", sex="F", age=65)
    assert hi["phenotype_band"] == "exceptional"
    assert lo["phenotype_band"] == "below_typical"
    # population baseline is identical (it's demography, not the phenotype)
    assert hi["population_baseline"]["p_reach_target"] == lo["population_baseline"]["p_reach_target"]
    assert hi["calibration"] == "phenotype_to_survival_mapping_uncalibrated"


def test_no_personal_odds_unless_opted_in():
    default = relative_longevity(90, country="Japan", sex="F")
    assert "illustrative_relative_odds" not in default
    opted = relative_longevity(90, country="Japan", sex="F", allow_uncalibrated_odds=True)
    assert opted["illustrative_relative_odds"]["status"] == "illustrative_not_validated"


def test_biological_age_context():
    r = relative_longevity(80, country="Italy", sex="F", bio_age_delta=-6)
    assert r["biological_age_context"]["delta_years"] == -6.0
    assert "younger" in r["biological_age_context"]["interpretation"]


def test_score_attaches_longevity_context_without_changing_score():
    base = score(1, {"q_smoking": 0, "q_family": 0, "q_social": 0})
    withctx = score(1, {"q_smoking": 0, "q_family": 0, "q_social": 0},
                    context={"country": "USA", "sex": "F", "age": 65})
    assert withctx["score_pct"] == base["score_pct"]          # score unchanged
    assert withctx["longevity_context"]["population_baseline"]["country_code"] == "USA"
    assert "longevity_context" not in base


def test_list_countries_nonempty():
    cs = list_countries()
    assert len(cs) >= 40 and all("country_code" in c for c in cs)
