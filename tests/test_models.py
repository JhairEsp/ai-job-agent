from app.models.job import JobAnalysis, JobPosting
from app.models.profile import SearchPreferences, UserProfile


def test_profile_roundtrip():
    profile = UserProfile(full_name="Jhair Espinoza", city="Lima", country="Perú", district="SJL")
    restored = UserProfile.from_dict(profile.to_dict())
    assert restored == profile
    assert restored.location_label == "SJL, Lima, Perú"


def test_preferences_roundtrip_and_summary():
    prefs = SearchPreferences(
        locations=["Lima", "Remoto"],
        positions=["Practicante BI", "Soporte TI"],
        modalities=["Remoto", "Híbrido"],
        job_type="Prácticas",
        min_salary=1000,
        salary_label="S/ 1 000",
    )
    restored = SearchPreferences.from_dict(prefs.to_dict())
    assert restored == prefs
    summary = restored.summary()
    assert "Practicante BI" in summary
    assert "Prácticas" in summary


def test_from_dict_ignores_unknown_keys():
    profile = UserProfile.from_dict({"full_name": "X", "hack": "y"})
    assert profile.full_name == "X"
    assert not hasattr(profile, "hack")


def test_job_dedupe_key_normalizes_case_and_spaces():
    a = JobPosting(title="  Practicante BI ", company="CLARO")
    b = JobPosting(title="practicante bi", company="claro")
    assert a.dedupe_key() == b.dedupe_key()


def test_analysis_classification_thresholds():
    assert JobAnalysis(score=95, recommendation="APPLY", reason="").classification == "Excelente"
    assert JobAnalysis(score=85, recommendation="APPLY", reason="").classification == "Muy buena"
    assert JobAnalysis(score=75, recommendation="CONSIDER", reason="").classification == "Buena"
    assert JobAnalysis(score=65, recommendation="CONSIDER", reason="").classification == "Regular"
    assert JobAnalysis(score=30, recommendation="SKIP", reason="").classification == "Baja"
