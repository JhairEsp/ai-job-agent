"""Portal: Indeed Perú.

Indeed puede mostrar CAPTCHAs o verificaciones humanas con frecuencia.
En ese caso el sistema se detiene y solicita intervención humana.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from app.models.job import JobPosting
from app.portals.base_portal import BasePortal
from app.browser.session_manager import HumanInterventionRequired


class IndeedPortal(BasePortal):
    name = "indeed"
    display_name = "Indeed"
    home_url = "https://pe.indeed.com"
    login_url = "https://secure.indeed.com/auth"

    requires_login = False
    supports_apply = True

    session_active_markers = (
        "[data-gnav='AccountMenu']",
    )

    def build_search_url(self, query: str, location: str) -> str:
        """Construye la URL de búsqueda de Indeed Perú."""
        return (
            "https://pe.indeed.com/jobs"
            f"?q={quote_plus(query)}"
            f"&l={quote_plus(location)}"
            "&sort=date"
        )

    def parse_search_results(self, html: str) -> list[JobPosting]:
        """Extrae ofertas de una página de resultados de Indeed.

        Indeed cambia frecuentemente sus clases/selectores HTML, por lo que
        se prueban varias estructuras conocidas.
        """

        soup = BeautifulSoup(html, "html.parser")
        jobs: list[JobPosting] = []

        # -------------------------------------------------------------
        # 1. Detectar CAPTCHA / verificación humana
        # -------------------------------------------------------------
        body_text = soup.get_text(" ", strip=True).lower()

        captcha_markers = (
            "captcha",
            "verify you are human",
            "verify that you are human",
            "verifica que eres humano",
            "verifica que eres una persona",
            "i'm not a robot",
            "im not a robot",
            "no soy un robot",
            "human verification",
            "unusual traffic",
        )

        if any(marker in body_text for marker in captcha_markers):
            raise HumanInterventionRequired(
                "Indeed requiere completar una verificación humana."
            )

        # -------------------------------------------------------------
        # 2. Localizar tarjetas de ofertas
        # -------------------------------------------------------------
        card_selectors = (
            "div.job_seen_beacon",
            "div.jobsearch-ResultsList > div",
            "div[data-testid='slider_item']",
            "td.resultContent",
            "div.cardOutline",
        )

        cards = []
        seen_cards: set[int] = set()

        for selector in card_selectors:
            for card in soup.select(selector):
                marker = id(card)

                if marker in seen_cards:
                    continue

                seen_cards.add(marker)
                cards.append(card)

        # -------------------------------------------------------------
        # 3. Procesar cada oferta
        # -------------------------------------------------------------
        for card in cards:

            # ---------------------------------------------------------
            # Título + enlace
            # ---------------------------------------------------------
            link = (
                card.select_one("h2.jobTitle a")
                or card.select_one("a.jcs-JobTitle")
                or card.select_one("a[data-jk]")
                or card.select_one("h2 a")
            )

            if not link:
                continue

            title = link.get_text(" ", strip=True)

            if not title:
                continue

            # ---------------------------------------------------------
            # Empresa
            # ---------------------------------------------------------
            company = self._first_text(
                card,
                (
                    "[data-testid='company-name']",
                    "span[data-testid='company-name']",
                    "span.companyName",
                    "div.companyName",
                ),
            )

            # ---------------------------------------------------------
            # Ubicación
            # ---------------------------------------------------------
            location = self._first_text(
                card,
                (
                    "[data-testid='text-location']",
                    "div.companyLocation",
                    "span.companyLocation",
                ),
            )

            # ---------------------------------------------------------
            # Salario
            # ---------------------------------------------------------
            salary = self._first_text(
                card,
                (
                    "[data-testid='attribute_snippet_testid']",
                    "div.salary-snippet-container",
                    "span.salary-snippet",
                    "div[data-testid='attribute_snippet_testid']",
                ),
            )

            # ---------------------------------------------------------
            # URL
            # ---------------------------------------------------------
            href = link.get("href", "")

            if not href:
                continue

            url = (
                href
                if href.startswith("http")
                else self.absolutize(href)
            )

            # ---------------------------------------------------------
            # Crear JobPosting
            # ---------------------------------------------------------
            job = JobPosting(
                title=title,
                company=company,
                location=location,
                salary=salary,
                url=url,
                portal=self.name,
            )

            jobs.append(job)

        # -------------------------------------------------------------
        # 4. Eliminar duplicados
        # -------------------------------------------------------------
        unique_jobs: dict[str, JobPosting] = {}

        for job in jobs:
            unique_jobs[job.dedupe_key()] = job

        jobs = list(unique_jobs.values())

        # -------------------------------------------------------------
        # 5. Si encontramos ofertas, devolverlas
        # -------------------------------------------------------------
        if jobs:
            return jobs

        # -------------------------------------------------------------
        # 6. Determinar si realmente no existen resultados
        # -------------------------------------------------------------
        no_results_markers = (
            "no jobs found",
            "no results",
            "no se encontraron empleos",
            "no encontramos empleos",
            "no encontramos ofertas",
            "sin resultados",
            "no hay resultados",
            "no hay ofertas",
        )

        if any(marker in body_text for marker in no_results_markers):
            return []

        # -------------------------------------------------------------
        # 7. Si la página cargó pero no reconocemos las ofertas,
        #    considerarlo error del scraper.
        # -------------------------------------------------------------
        raise RuntimeError(
            "Indeed cargó correctamente, pero el scraper no reconoció "
            "la estructura de las ofertas."
        )

    def parse_description(self, html: str) -> str:
        """Extrae la descripción de una oferta de Indeed."""

        soup = BeautifulSoup(html, "html.parser")

        return self._first_text(
            soup,
            (
                "#jobDescriptionText",
                "div#jobDescriptionText",
                "[data-testid='jobDescriptionText']",
                "div.jobsearch-JobComponent-description",
                "div.jobsearch-jobDescriptionText",
            ),
        )