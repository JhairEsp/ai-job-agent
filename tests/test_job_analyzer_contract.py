import json

import pytest

from app.ai.job_analyzer import AnalysisParseError, parse_analysis

VALID = {
    "score": 87,
    "recommendation": "apply",
    "reason": "Coinciden skills de sistemas.",
    "matching_skills": ["Python", "SQL"],
    "missing_skills": ["Power BI"],
    "experience_match": "Sin experiencia previa requerida",
    "location_match": True,
    "salary_match": False,
}


def test_parse_valid_payload_from_json_string():
    analysis = parse_analysis(json.dumps(VALID))
    assert analysis.score == 87
    assert analysis.recommendation == "APPLY"  # normalizado a mayúsculas
    assert analysis.matching_skills == ["Python", "SQL"]
    assert analysis.location_match is True
    assert analysis.classification == "Muy buena"


def test_parse_valid_payload_from_dict():
    analysis = parse_analysis(dict(VALID))
    assert analysis.salary_match is False


def test_score_out_of_range_is_rejected():
    with pytest.raises(AnalysisParseError):
        parse_analysis({**VALID, "score": 140})


def test_score_missing_is_rejected():
    payload = {k: v for k, v in VALID.items() if k != "score"}
    with pytest.raises(AnalysisParseError):
        parse_analysis(payload)


def test_non_list_skills_become_empty():
    analysis = parse_analysis({**VALID, "matching_skills": "Python"})
    assert analysis.matching_skills == []
