"""Portal: Indeed Perú.

⚠️ Indeed muestra CAPTCHAs con frecuencia; en ese caso el sistema se
detiene y pide intervención humana (regla inviolable).
"""
from __future__ import annotations

from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from app.models.job import JobPosting
from app.portals.base_portal import BasePortal


class IndeedPortal(BasePortal):
    name = "indeed"
    display_name = "Indeed"
    home_url = "https://pe.indeed.com"
    login_url = "https://secure.indeed.com/auth"
    requires_login = False
    supports_apply = True
    session_active_markers = ("[data-gnav='AccountMenu']",)

    def build_search_url(self, query: str, location: str) -> str:
        return (
            "https://pe.indeed.com/jobs"
            f"?q={quote_plus(query)}&l={quote_plus(location)}&sort=date"
        )

    def parse_search_results(self, html: str) -> list[JobPosting]:
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[JobPosting] = []
        for card in soup.select("div.job_seen_beacon, td.resultContent"):
            link = card.select_one("h2.jobTitle a") or card.select_one("a.jcs-JobTitle")
            if not link:
                continue
            title = link.get_text(strip=True)
            company = self._first_text(
                soup, ("span[data-testid='company-name']", "span.companyName"), base=card
            )
            location = self._first_text(
                soup, ("div[data-testid='text-location']", "div.companyLocation"), base=card
            )
            salary = self._first_text(
                soup, ("div[data-testid='attribute_snippet_testid']", "div.salary-snippet-container"), base=card
            )
            href = link.get("href", "")
            jobs.append(
                JobPosting(
                    title=title,
                    company=company,
                    location=location,
                    salary=salary,
                    url=href if href.startswith("http") else self.absolutize(href),
                    portal=self.name,
                )
            )
        return jobs

    def parse_description(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        return self._first_text(soup, ("div#jobDescriptionText", "div.jobsearch-JobComponent-description"))
