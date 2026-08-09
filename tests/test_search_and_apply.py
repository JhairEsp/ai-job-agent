"""Integración offline: búsqueda (portal demo) + análisis (Groq falso) + tracker."""
import asyncio
from pathlib import Path

import pytest

from app.browser.session_manager import BrowserManager
from app.cv.cv_manager import CVManager
from app.database.db import Database
from app.database.repositories import (
    ApplicationRepository,
    JobRepository,
    PortalRepository,
    UserRepository,
)
from app.models.job import ApplicationStatus
from app.models.profile import SearchPreferences, UserProfile
from app.services.search_service import SearchService


class FakeGroq:
    """Simula las llamadas de análisis sin red ni credenciales reales."""

    model = "fake-model"

    async def complete_structured(self, system_prompt: str, user_prompt: str) -> str:
        return (
            '{"score": 88, "recommendation": "APPLY", "reason": "Coincide con el perfil.",'
            ' "matching_skills": ["SQL"], "missing_skills": ["Power BI"],'
            ' "experience_match": "adecuada", "location_match": true, "salary_match": true}'
        )

    async def chat(self, messages, **kwargs) -> str:
        return "Respuesta falsa basada solo en el CV."


@pytest.fixture()
def stack(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    db.init()
    cv_dir = tmp_path / "profile"
    cv_dir.mkdir()
    (cv_dir / "cv.md").write_text(
        "# Jhair Espinoza\n\n## Skills\n\n- Python\n- SQL\n- Excel\n", encoding="utf-8"
    )
    user_repo = UserRepository(db)
    user_repo.upsert_user(1, "jhair", "Jhair")
    user_repo.set_onboarded(1)
    user_repo.save_profile(1, UserProfile(full_name="Jhair Espinoza", city="Lima", country="Perú"))
    user_repo.save_preferences(
        1,
        SearchPreferences(
            locations=["Lima"], positions=["Practicante"], modalities=[], min_salary=None
        ),
    )
    service = SearchService(
        db,
        CVManager(cv_dir / "cv.md"),
        FakeGroq(),
        BrowserManager(tmp_path / "profiles"),
    )
    return db, service, PortalRepository(db)


def test_search_demo_chain(stack):
    db, service, portals_repo = stack
    portals_repo.ensure_defaults(1, ["demo"], demo_enabled="demo")

    result = asyncio.run(service.search_for_user(1))

    assert result.portals_used == ["demo"]
    assert result.new_jobs, "debe encontrar ofertas del portal demo"
    assert all(r.job.portal == "demo" for r in result.new_jobs)

    # Las mejores tienen análisis de IA persistido.
    analyzed = [r for r in result.new_jobs if r.analysis is not None]
    assert analyzed
    assert analyzed[0].analysis.score == 88

    # Segunda búsqueda: no duplica ofertas.
    result2 = asyncio.run(service.search_for_user(1))
    assert result2.new_jobs == []


def test_tracker_flow(stack):
    db, service, portals_repo = stack
    portals_repo.ensure_defaults(1, ["demo"], demo_enabled="demo")
    result = asyncio.run(service.search_for_user(1))
    job_id = result.new_jobs[0].job_id

    jobs = JobRepository(db)
    apps = ApplicationRepository(db)

    jobs.set_status(job_id, ApplicationStatus.READY)
    apps.record(1, job_id, answers="respuesta", method="manual")
    jobs.set_status(job_id, ApplicationStatus.APPLIED)

    rows = apps.list_for_user(1)
    assert len(rows) == 1
    assert rows[0]["status"] == ApplicationStatus.APPLIED.value
    assert rows[0]["title"]


def test_portal_repository_toggle(stack):
    db, _, portals_repo = stack
    portals_repo.ensure_defaults(1, ["demo", "linkedin"], demo_enabled="demo")
    assert portals_repo.enabled_names(1) == ["demo"]

    portals_repo.set_enabled(1, "linkedin", True)
    assert set(portals_repo.enabled_names(1)) == {"demo", "linkedin"}

    portals_repo.set_enabled(1, "linkedin", False)
    assert portals_repo.enabled_names(1) == ["demo"]
