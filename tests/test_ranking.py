from app.models.job import JobPosting
from app.models.profile import SearchPreferences
from app.services.ranking import heuristic_score, parse_salary


def prefs() -> SearchPreferences:
    return SearchPreferences(
        locations=["Lima", "Remoto"],
        positions=["Practicante BI", "Practicante de Sistemas"],
        modalities=["Híbrido", "Remoto"],
        job_type="Cualquiera",
        min_salary=1000,
    )


def test_parse_salary_variants():
    assert parse_salary("S/ 1,200 al mes") == 1200
    assert parse_salary("S/.1,000") == 1000
    assert parse_salary("") is None
    assert parse_salary("a convenir") is None


def test_strong_match_scores_high():
    job = JobPosting(
        title="Practicante BI",
        company="Claro",
        location="Lima",
        salary="S/ 1,200",
        modality="Híbrido",
        description="Practicante de BI con SQL y Excel.",
    )
    assert heuristic_score(job, prefs()) >= 85


def test_irrelevant_job_scores_low():
    job = JobPosting(
        title="Desarrollador Backend Senior (5+ años)",
        company="X",
        location="Arequipa",
        salary="S/ 800",
        modality="Presencial",
        description="Se requieren 5 años de experiencia en Java.",
    )
    assert heuristic_score(job, prefs()) < 60


def test_salary_below_minimum_penalized():
    job_low = JobPosting(title="Practicante BI", company="X", location="Lima", modality="Híbrido", salary="S/ 700")
    job_ok = JobPosting(title="Practicante BI", company="X", location="Lima", modality="Híbrido", salary="S/ 1,100")
    assert heuristic_score(job_ok, prefs()) > heuristic_score(job_low, prefs())
