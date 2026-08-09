from pathlib import Path

import pytest

from app.database.db import Database
from app.database.repositories import UserRepository
from app.models.profile import SearchPreferences, UserProfile


@pytest.fixture()
def repo(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.init()
    yield UserRepository(db)
    db.close()


def test_user_lifecycle(repo):
    repo.upsert_user(111, "jhair", "Jhair")
    assert repo.get_user(111)["first_name"] == "Jhair"
    assert not repo.is_onboarded(111)

    repo.set_onboarded(111)
    assert repo.is_onboarded(111)

    repo.reset_onboarding(111)
    assert not repo.is_onboarded(111)


def test_upsert_does_not_reset_onboarding(repo):
    repo.upsert_user(222, "user", "Nombre")
    repo.set_onboarded(222)
    repo.upsert_user(222, "user2", "Nombre 2")
    assert repo.is_onboarded(222)
    assert repo.get_user(222)["username"] == "user2"


def test_profile_persistence(repo):
    repo.upsert_user(333, "u", "U")
    profile = UserProfile(full_name="Jhair Espinoza", city="Lima", country="Perú")
    repo.save_profile(333, profile)

    restored = repo.get_profile(333)
    assert restored == profile

    # Actualización (upsert)
    profile.city = "Callao"
    repo.save_profile(333, profile)
    assert repo.get_profile(333).city == "Callao"


def test_preferences_persistence(repo):
    repo.upsert_user(444, "u", "U")
    prefs = SearchPreferences(
        locations=["Lima", "Remoto"],
        positions=["Practicante BI"],
        modalities=["Remoto"],
        job_type="Prácticas",
        min_salary=1000,
        salary_label="S/ 1 000",
    )
    repo.save_preferences(444, prefs)
    assert repo.get_preferences(444) == prefs


def test_get_profile_missing_returns_none(repo):
    assert repo.get_profile(999) is None
    assert repo.get_preferences(999) is None
