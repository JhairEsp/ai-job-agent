"""Portal: Computrabajo Perú.

⚠️ Selectores sujetos a cambios del sitio: si deja de devolver
resultados, revisa `parse_search_results`.
"""
from __future__ import annotations

import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from app.models.job import JobPosting
from app.portals.base_portal import BasePortal

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    text = text.lower().replace("á", "a").replace("é", "e").replace("í", "i")
    text = text.replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    return _SLUG_RE.sub("-", text).strip("-")


class CompuTrabajoPortal(BasePortal):
    name = "computrabajo"
    display_name = "Computrabajo"
    home_url = "https://pe.computrabajo.com"
    login_url = "https://pe.computrabajo.com/auth/login"
    requires_login = False
    supports_apply = True
    session_active_markers = ("[data-cy='header-user-menu']",)

    def build_search_url(self, query: str, location: str) -> str:
        base = f"https://pe.computrabajo.com/trabajo-de-{_slug(query)}"
        if location and _slug(location) != "peru":
            base += f"-en-{_slug(location)}"
        return base + "?by=publicationtime"

    def parse_search_results(self, html: str) -> list[JobPosting]:
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[JobPosting] = []
        for card in soup.select("article.box_offer"):
            link = card.select_one("a.js-o-link") or card.select_one("a[href*='/ofertas-de-trabajo/']")
            if not link or not link.get("href"):
                continue
            title = link.get_text(strip=True)
            company = self._first_text(soup, ("a[title]", "p.fc_1"), base=card)
            location = self._first_text(soup, ("p.fc_2", "span.color_custom5"), base=card)
            salary = self._first_text(soup, ("span.tag-base-salary",), base=card)
            modality = self._first_text(
                soup, ("span.tag-base:contains('emoto')",), base=card
            ) or ""
            if not title:
                continue
            jobs.append(
                JobPosting(
                    title=title,
                    company=company,
                    location=location,
                    salary=salary,
                    modality="Remoto" if "remot" in card.get_text(" ", strip=True).lower() else modality,
                    url=self.absolutize(link["href"]),
                    portal=self.name,
                )
            )
        return jobs

    def parse_description(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        return self._first_text(
            soup,
            ("div.box_detail div.container", "div#props_offre", "div.bWord"),
        )

    async def apply(self, browser, job, applicant, answers) -> str:
        """CompuTrabajo suele permitir postulación en 1-2 pasos cuando hay sesión.

        Estrategia conservadora: abrir la oferta, rellenar campos de texto
        conocidos y dejar que el USUARIO revise y confirme el envío final
        en el navegador (cumple la regla de no evadir controles humanos).
        """
        if not job.url:
            return "assisted"
        context = await browser.get_context(self.name, headless=False)
        page = await context.new_page()
        try:
            await page.goto(job.url, wait_until="domcontentloaded", timeout=45_000)
            self.check_blocked(await page.content())
            for label, value in (
                ("nombre", applicant.get("full_name", "")),
                ("email", applicant.get("email", "")),
                ("correo", applicant.get("email", "")),
                ("teléfono", applicant.get("phone", "")),
                ("telefono", applicant.get("phone", "")),
            ):
                if not value:
                    continue
                try:
                    field = page.get_by_label(re.compile(label, re.IGNORECASE))
                    if await field.count():
                        await field.first.fill(value)
                except Exception:
                    continue
            for selector, key in (("textarea", "cover_letter"),):
                if answers.get(key):
                    try:
                        textarea = page.locator(selector).first
                        if await textarea.count():
                            await textarea.fill(answers[key])
                    except Exception:
                        continue
            # Se detiene aquí: el usuario revisa y confirma el envío final.
            return "assisted"
        finally:
            await page.close()
