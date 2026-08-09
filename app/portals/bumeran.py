"""Portal: Bumeran Perú (experimental — selectores volátiles)."""
from __future__ import annotations

import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from app.models.job import JobPosting
from app.portals.base_portal import BasePortal


class BumeranPortal(BasePortal):
    name = "bumeran"
    display_name = "Bumeran"
    home_url = "https://www.bumeran.com.pe"
    login_url = "https://www.bumeran.com.pe/login"
    requires_login = False
    supports_apply = False
    session_active_markers = ("[data-testid='user-menu']",)

    def build_search_url(self, query: str, location: str) -> str:
        slug = re.sub(r"\s+", "-", query.strip().lower())
        area_slug = re.sub(r"\s+", "-", location.strip().lower()) if location else ""
        area = f"-en-{area_slug}" if area_slug else ""
        return f"https://www.bumeran.com.pe/empleos-busqueda-{quote_plus(slug)}{area}.html"

    def parse_search_results(self, html: str) -> list[JobPosting]:
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[JobPosting] = []
        for link in soup.select("a[href*='/empleos/']"):
            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            container = link.find_parent(["div", "article"])
            company = location = salary = ""
            if container:
                company = self._first_text(soup, ("h3", "h2"), base=container)
                salary = self._first_text(soup, ("span:contains('S/')",), base=container)
                location = self._first_text(soup, ("h4",), base=container)
            jobs.append(
                JobPosting(
                    title=title,
                    company=company,
                    location=location,
                    salary=salary,
                    url=self.absolutize(link.get("href", "")),
                    portal=self.name,
                )
            )
        # Quitar duplicados por URL
        unique: dict[str, JobPosting] = {j.url: j for j in jobs if j.url}
        return list(unique.values())

    def parse_description(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        return self._first_text(
            soup,
            ("div#ficha-detalle", "div.aviso_description", "section.detail"),
        )
