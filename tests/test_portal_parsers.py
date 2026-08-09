"""Los parseadores HTML de cada portal funcionan sin navegador ni red."""
from pathlib import Path

import pytest

from app.portals.computrabajo import CompuTrabajoPortal
from app.portals.indeed import IndeedPortal
from app.portals.linkedin import LinkedInPortal
from app.browser.session_manager import HumanInterventionRequired

FIXTURES = Path(__file__).parent / "fixtures"


def test_linkedin_parse():
    html = (FIXTURES / "linkedin_search.html").read_text(encoding="utf-8")
    jobs = LinkedInPortal().parse_search_results(html)

    assert len(jobs) == 2
    assert jobs[0].title == "Practicante BI"
    assert jobs[0].company == "Claro Perú"
    assert jobs[0].location == "Lima, Perú"
    # URL limpia sin parámetros de tracking
    assert jobs[0].url == "https://pe.linkedin.com/jobs/view/123456"


def test_computrabajo_parse():
    html = (FIXTURES / "computrabajo_search.html").read_text(encoding="utf-8")
    jobs = CompuTrabajoPortal().parse_search_results(html)

    assert len(jobs) == 2
    assert jobs[0].title == "Practicante de Sistemas"
    assert jobs[0].company == "TechAndina"
    assert jobs[0].salary.startswith("S/")
    assert jobs[0].url.startswith("https://pe.computrabajo.com/")


def test_indeed_parse():
    html = (FIXTURES / "indeed_search.html").read_text(encoding="utf-8")
    jobs = IndeedPortal().parse_search_results(html)

    assert len(jobs) == 2
    assert jobs[0].title == "Practicante de Business Intelligence"
    assert jobs[1].location == "Remoto"


def test_captcha_detection_stops_search():
    portal = LinkedInPortal()
    with pytest.raises(HumanInterventionRequired):
        portal.check_blocked("<html><body><div class='g-recaptcha'></div></body></html>")


def test_search_urls_combine_positions_and_locations():
    from app.models.profile import SearchPreferences

    portal = IndeedPortal()
    urls = portal.search_urls(
        SearchPreferences(locations=["Lima", "Remoto"], positions=["BI", "Sistemas"])
    )
    assert len(urls) == 4
    assert all(u.startswith("https://pe.indeed.com/jobs") for u in urls)


def test_demo_portal_search_filters_by_positions():
    import asyncio

    from app.models.profile import SearchPreferences
    from app.portals.demo import DemoPortal

    jobs = asyncio.run(
        DemoPortal().search(None, SearchPreferences(positions=["Practicante BI"], locations=[]))
    )
    assert jobs, "el portal demo debe devolver ofertas"
    assert all("practicante" in j.title.lower() or "bi" in j.title.lower() for j in jobs)
