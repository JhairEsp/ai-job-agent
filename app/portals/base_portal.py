"""Contrato base para los portales laborales.

Cada portal (linkedin.py, computrabajo.py, indeed.py, bumeran.py, demo.py)
hereda de BasePortal. Reglas inviolables:

- Sesión del navegador persistente y local (data/browser_profiles/<portal>/).
- NUNCA se solicitan ni almacenan contraseñas: el usuario inicia sesión
  manualmente en el navegador controlado.
- Ante CAPTCHA o verificación humana: detenerse y pedir intervención.
  Prohibido intentar evadirlos.
- Respetar las condiciones de uso de cada portal.

El parseo de HTML (`parse_search_results`, `parse_description`) es una
función pura sobre strings para poder probarla sin navegador ni red.
Nota: los selectores CSS de los portales cambian con el tiempo; si un
portal deja de devolver resultados, revisa sus selectores en su módulo.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.browser.session_manager import (
    BrowserManager,
    HumanInterventionRequired,
)
from app.models.job import JobPosting
from app.models.profile import SearchPreferences

logger = logging.getLogger(__name__)

MAX_SEARCH_URLS = 6
PAGE_TIMEOUT_MS = 45_000

# Marcadores genéricos de bloqueo/CAPTCHA (en minúsculas contra el HTML).
CAPTCHA_MARKERS = (
    "g-recaptcha",
    "hcaptcha",
    "cf-challenge",
    "captcha-delivery",
    "are you a robot",
    "verifica que eres humano",
    "security check",
)


class BasePortal(ABC):
    """Interfaz que todo portal laboral debe implementar."""

    name: str = "base"
    display_name: str = "Portal"
    home_url: str = ""
    login_url: str = ""
    #: Si el portal requiere sesión iniciada para buscar.
    requires_login: bool = True
    #: Si podemos intentar pre-llenado del formulario de postulación.
    supports_apply: bool = False
    #: Selectores que indican que la sesión sigue activa (CSS, primer match).
    session_active_markers: tuple[str, ...] = ()

    # ------------------------------------------------------------ búsqueda
    @abstractmethod
    def build_search_url(self, query: str, location: str) -> str:
        """URL de resultados para una combinación puesto/ubicación."""

    @abstractmethod
    def parse_search_results(self, html: str) -> list[JobPosting]:
        """Extrae ofertas del HTML de una página de resultados (función pura)."""

    @abstractmethod
    def parse_description(self, html: str) -> str:
        """Extrae la descripción de la página de detalle (función pura)."""

    def search_urls(self, preferences: SearchPreferences) -> list[str]:
        positions = preferences.positions[:3] or [""]
        locations = preferences.locations[:2] or [""]
        urls: list[str] = []
        for position in positions:
            for location in locations:
                urls.append(self.build_search_url(position, location))
        return urls[:MAX_SEARCH_URLS]

    # ----------------------------------------------------------- utilidades
    def check_blocked(self, html: str) -> None:
        lowered = html.lower()
        if any(marker in lowered for marker in CAPTCHA_MARKERS):
            raise HumanInterventionRequired(
                f"{self.display_name} está pidiendo un CAPTCHA/verificación. "
                "Abre el portal desde la app y resuélvelo manualmente."
            )

    def absolutize(self, href: str) -> str:
        return urljoin(self.home_url or self.login_url, href)

    @staticmethod
    def _first_text(soup: BeautifulSoup, selectors: tuple[str, ...], base=None) -> str:
        scope = base if base is not None else soup
        for selector in selectors:
            found = scope.select_one(selector)
            if found and found.get_text(strip=True):
                return found.get_text(strip=True)
        return ""

    # ------------------------------------------------- ciclo de vida activo
    async def search(
        self, browser: BrowserManager, preferences: SearchPreferences
    ) -> list[JobPosting]:
        """Navega las URLs de búsqueda y devuelve ofertas sin duplicados."""
        context = await browser.get_context(self.name)
        page = await context.new_page()
        results: list[JobPosting] = []
        seen: set[str] = set()
        try:
            for url in self.search_urls(preferences):
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
                    await page.wait_for_timeout(1500)
                    html = await page.content()
                except Exception as exc:
                    logger.warning("%s: error cargando %s: %s", self.name, url, type(exc).__name__)
                    continue

                self.check_blocked(html)
                for job in self.parse_search_results(html):
                    key = (job.url or job.dedupe_key(), job.dedupe_key())
                    if key in seen:
                        continue
                    seen.add(key)
                    job.portal = self.name
                    results.append(job)
        finally:
            await page.close()
        logger.info("%s: %d ofertas extraídas", self.name, len(results))
        return results

    async def fetch_description(self, browser: BrowserManager, job: JobPosting) -> str:
        if not job.url:
            return ""
        context = await browser.get_context(self.name)
        page = await context.new_page()
        try:
            await page.goto(job.url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
            html = await page.content()
            self.check_blocked(html)
            return self.parse_description(html)
        finally:
            await page.close()

    async def is_session_active(self, browser: BrowserManager) -> bool:
        """True si el portal reconoce la sesión guardada."""
        if not self.requires_login:
            return True
        context = await browser.get_context(self.name)
        page = await context.new_page()
        try:
            await page.goto(
                self.home_url or self.login_url,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT_MS,
            )
            for selector in self.session_active_markers:
                if await page.query_selector(selector):
                    return True
            return False
        finally:
            await page.close()

    # ------------------------------------------------------------ postulación
    async def apply(
        self,
        browser: BrowserManager,
        job: JobPosting,
        applicant: dict,
        answers: dict[str, str],
    ) -> str:
        """Intenta automatizar la postulación.

        Devuelve "submitted" o "assisted" (cuando el usuario debe completar
        el envío a mano). La implementación genérica es 'assisted': los
        portales con formularios automatizables sobreescriben este método.
        NUNCA se envía nada sin que el usuario haya confirmado antes.
        """
        return "assisted"
