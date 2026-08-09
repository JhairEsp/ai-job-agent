"""Portal: LinkedIn.

⚠️ Los selectores CSS de LinkedIn cambian con frecuencia y el sitio es
estricto con la automatización. La búsqueda usa la vista pública de
empleos; si pide verificación, el sistema se detiene y avisa (regla de
anti-CAPTCHA).
"""
from __future__ import annotations

from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from app.models.job import JobPosting
from app.portals.base_portal import BasePortal


class LinkedInPortal(BasePortal):
    name = "linkedin"
    display_name = "LinkedIn"
    home_url = "https://www.linkedin.com"
    login_url = "https://www.linkedin.com/login"
    requires_login = True
    supports_apply = False
    session_active_markers = ("div.global-nav__me", "img.global-nav__me-photo")

    def build_search_url(self, query: str, location: str) -> str:
        loc = quote_plus(location or "Perú")
        return (
            "https://www.linkedin.com/jobs/search/"
            f"?keywords={quote_plus(query)}&location={loc}&f_E=1%2C2"
        )

    def parse_search_results(self, html: str) -> list[JobPosting]:
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[JobPosting] = []
        for card in soup.select("div.job-search-card"):
            link = card.select_one("a.base-card__full-link")
            if not link or not link.get("href"):
                continue
            title = self._first_text(soup, ("h3.base-search-card__title",), base=card)
            company = self._first_text(soup, ("h4.base-search-card__subtitle",), base=card)
            location = self._first_text(soup, ("span.job-search-card__location",), base=card)
            if not title:
                continue
            jobs.append(
                JobPosting(
                    title=title,
                    company=company,
                    location=location,
                    url=self.absolutize(link["href"].split("?")[0]),
                    portal=self.name,
                )
            )
        return jobs

    def parse_description(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        return self._first_text(
            soup,
            (
                "div.show-more-less-html__markup",
                "div.description__text",
                "section.description",
            ),
        )
