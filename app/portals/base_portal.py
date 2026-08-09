"""
Contrato base para los portales laborales.

Cada portal hereda de BasePortal.

Reglas:

- Sesión del navegador persistente y local.
- Nunca se solicitan ni almacenan contraseñas.
- El usuario inicia sesión manualmente.
- Ante CAPTCHA/verificación humana, se permite intervención manual.
- No se intenta evadir ningún CAPTCHA.
- Se respetan las condiciones de uso de cada portal.
"""

from __future__ import annotations

import asyncio
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


# ================================================================
# DETECCIÓN DE VERIFICACIÓN
# ================================================================

CAPTCHA_TEXT_MARKERS = (
    "are you a robot",
    "verify you are human",
    "verifica que eres humano",
    "security check",
    "human verification",
    "verificación humana",
    "verificación adicional requerida",
    "additional verification required",
    "captcha required",
    "complete the captcha",
    "complete el captcha",
)


CAPTCHA_URL_MARKERS = (
    "/challenge",
    "/captcha",
    "/verify",
    "/verification",
    "challenge.",
    "captcha.",
)


CAPTCHA_TITLE_MARKERS = (
    "verify",
    "verification",
    "verificación",
    "captcha",
    "security check",
    "human verification",
)


class BasePortal(ABC):
    """Interfaz base para todos los portales laborales."""

    name: str = "base"
    display_name: str = "Portal"

    home_url: str = ""
    login_url: str = ""

    requires_login: bool = True
    supports_apply: bool = False

    session_active_markers: tuple[str, ...] = ()

    # ============================================================
    # MÉTODOS ABSTRACTOS
    # ============================================================

    @abstractmethod
    def build_search_url(
        self,
        query: str,
        location: str,
    ) -> str:
        """Construye la URL de búsqueda."""

        raise NotImplementedError

    @abstractmethod
    def parse_search_results(
        self,
        html: str,
    ) -> list[JobPosting]:
        """Extrae ofertas desde el HTML."""

        raise NotImplementedError

    @abstractmethod
    def parse_description(
        self,
        html: str,
    ) -> str:
        """Extrae la descripción de una oferta."""

        raise NotImplementedError

    # ============================================================
    # URLS DE BÚSQUEDA
    # ============================================================

    def search_urls(
        self,
        preferences: SearchPreferences,
    ) -> list[str]:
        """
        Genera las URLs de búsqueda.

        IMPORTANTE:

        La ubicación NO se combina con el puesto.

        Ejemplo:

            positions = [
                "Analista de sistemas junior",
                "Analista de sistemas",
            ]

            locations = [
                "Lima",
            ]

        Antes se generaba:

            Analista de sistemas junior + Lima

        Ahora se genera:

            Analista de sistemas junior

        La ubicación queda disponible en `preferences`
        para el ranking/filtro posterior.

        Esto permite obtener más resultados del portal.
        """

        positions = [
            position.strip()
            for position in preferences.positions
            if position and position.strip()
        ]

        # Si el usuario no indicó puestos, hacemos una
        # búsqueda general.
        if not positions:
            positions = [""]

        # El límite se aplica solamente a los términos.
        positions = positions[:MAX_SEARCH_URLS]

        urls: list[str] = []

        for position in positions:

            try:
                url = self.build_search_url(
                    position,
                    "",
                )
            except Exception as exc:

                logger.warning(
                    "%s: no se pudo construir URL "
                    "para '%s': %s",
                    self.display_name,
                    position,
                    type(exc).__name__,
                )

                continue

            if url:
                urls.append(url)

        return urls[:MAX_SEARCH_URLS]

    # ============================================================
    # DETECCIÓN DE CAPTCHA
    # ============================================================

    def _looks_like_verification_page(
        self,
        html: str,
        *,
        url: str = "",
        title: str = "",
        body_text: str = "",
    ) -> bool:

        html_lower = (html or "").lower()
        url_lower = (url or "").lower()
        title_lower = (title or "").lower()
        body_lower = (body_text or "").lower()

        # --------------------------------------------------------
        # URL
        # --------------------------------------------------------

        if any(
            marker in url_lower
            for marker in CAPTCHA_URL_MARKERS
        ):
            return True

        # --------------------------------------------------------
        # TÍTULO
        # --------------------------------------------------------

        if any(
            marker in title_lower
            for marker in CAPTCHA_TITLE_MARKERS
        ):
            return True

        # --------------------------------------------------------
        # TEXTO VISIBLE
        # --------------------------------------------------------

        if any(
            marker in body_lower
            for marker in CAPTCHA_TEXT_MARKERS
        ):
            return True

        # --------------------------------------------------------
        # Cloudflare / Turnstile
        # --------------------------------------------------------

        challenge_markers = (
            "cf-chl-widget",
            "cf-chl-turnstile",
            "challenge-platform",
            "cf-turnstile",
        )

        if any(
            marker in html_lower
            for marker in challenge_markers
        ):
            return True

        return False

    def check_blocked(
        self,
        html: str,
        *,
        url: str = "",
        title: str = "",
        body_text: str = "",
    ) -> None:
        """Lanza HumanInterventionRequired si detecta verificación."""

        if self._looks_like_verification_page(
            html,
            url=url,
            title=title,
            body_text=body_text,
        ):
            raise HumanInterventionRequired(
                f"{self.display_name} está solicitando "
                "una verificación humana."
            )

    # ============================================================
    # UTILIDADES
    # ============================================================

    def absolutize(
        self,
        href: str,
    ) -> str:

        return urljoin(
            self.home_url or self.login_url,
            href,
        )

    @staticmethod
    def _first_text(
        soup: BeautifulSoup,
        selectors: tuple[str, ...],
        base=None,
    ) -> str:

        scope = (
            base
            if base is not None
            else soup
        )

        for selector in selectors:

            found = scope.select_one(
                selector
            )

            if not found:
                continue

            text = found.get_text(
                " ",
                strip=True,
            )

            if text:
                return text

        return ""

    # ============================================================
    # ESTADO DE PÁGINA
    # ============================================================

    async def _get_page_state(
        self,
        page,
    ) -> tuple[str, str, str, str]:

        current_url = ""
        title = ""
        body_text = ""
        html = ""

        try:
            current_url = page.url or ""
        except Exception:
            pass

        try:
            title = await page.title()
        except Exception:
            pass

        try:
            body_text = await page.locator(
                "body"
            ).inner_text(
                timeout=3000
            )
        except Exception:
            pass

        try:
            html = await page.content()
        except Exception:
            pass

        return (
            current_url,
            title,
            body_text,
            html,
        )

    # ============================================================
    # BÚSQUEDA
    # ============================================================

    async def search(
        self,
        browser: BrowserManager,
        preferences: SearchPreferences,
    ) -> list[JobPosting]:
        """
        Busca ofertas utilizando el navegador.

        La página se mantiene abierta mientras el usuario
        completa manualmente cualquier verificación.
        """

        context = await browser.get_context(
            self.name,
            headless=False,
        )

        page = await context.new_page()

        results: list[JobPosting] = []
        seen: set[str] = set()

        try:

            urls = self.search_urls(
                preferences
            )

            logger.info(
                "%s: %d URLs de búsqueda generadas.",
                self.display_name,
                len(urls),
            )

            for index, url in enumerate(
                urls,
                start=1,
            ):

                logger.info(
                    "%s: búsqueda %d/%d: %s",
                    self.display_name,
                    index,
                    len(urls),
                    url,
                )

                # =================================================
                # NAVEGACIÓN
                # =================================================

                try:

                    await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=PAGE_TIMEOUT_MS,
                    )

                    await asyncio.sleep(2)

                except Exception as exc:

                    logger.warning(
                        "%s: error cargando %s: %s",
                        self.name,
                        url,
                        type(exc).__name__,
                    )

                    continue

                # =================================================
                # ESTADO
                # =================================================

                (
                    current_url,
                    title,
                    body_text,
                    html,
                ) = await self._get_page_state(
                    page
                )

                # =================================================
                # CAPTCHA / VERIFICACIÓN
                # =================================================

                try:

                    self.check_blocked(
                        html,
                        url=current_url,
                        title=title,
                        body_text=body_text,
                    )

                except HumanInterventionRequired:

                    logger.warning(
                        "%s: verificación humana detectada.",
                        self.display_name,
                    )

                    logger.warning(
                        "Completa la verificación manualmente "
                        "en la ventana del navegador.",
                    )

                    try:

                        await self._wait_for_human_verification(
                            page
                        )

                    except HumanInterventionRequired as exc:

                        logger.error(
                            "%s: verificación no completada: %s",
                            self.display_name,
                            exc,
                        )

                        continue

                    # ------------------------------------------------
                    # IMPORTANTE:
                    #
                    # Aquí NO hacemos goto().
                    # Aquí NO hacemos reload().
                    #
                    # Simplemente leemos la página actual.
                    # ------------------------------------------------

                    (
                        current_url,
                        title,
                        body_text,
                        html,
                    ) = await self._get_page_state(
                        page
                    )

                    logger.info(
                        "%s: página posterior a "
                        "verificación: %s",
                        self.display_name,
                        current_url,
                    )

                    # ------------------------------------------------
                    # Comprobación final
                    # ------------------------------------------------

                    try:

                        self.check_blocked(
                            html,
                            url=current_url,
                            title=title,
                            body_text=body_text,
                        )

                    except HumanInterventionRequired:

                        logger.warning(
                            "%s: la verificación "
                            "sigue activa.",
                            self.display_name,
                        )

                        continue

                # =================================================
                # PARSER
                # =================================================

                try:

                    parsed_jobs = (
                        self.parse_search_results(
                            html
                        )
                    )

                except HumanInterventionRequired:

                    logger.warning(
                        "%s: parser detectó "
                        "verificación humana.",
                        self.display_name,
                    )

                    try:

                        await self._wait_for_human_verification(
                            page
                        )

                    except HumanInterventionRequired as exc:

                        logger.error(
                            "%s: no se completó "
                            "la verificación: %s",
                            self.display_name,
                            exc,
                        )

                        continue

                    (
                        current_url,
                        title,
                        body_text,
                        html,
                    ) = await self._get_page_state(
                        page
                    )

                    parsed_jobs = (
                        self.parse_search_results(
                            html
                        )
                    )

                # =================================================
                # RESULTADOS
                # =================================================

                page_count = 0

                for job in parsed_jobs:

                    key = (
                        job.url
                        or job.dedupe_key(),
                        job.dedupe_key(),
                    )

                    if key in seen:
                        continue

                    seen.add(key)

                    job.portal = self.name

                    results.append(job)

                    page_count += 1

                logger.info(
                    "%s: %d ofertas encontradas "
                    "en esta búsqueda.",
                    self.display_name,
                    page_count,
                )

        finally:

            try:

                if not page.is_closed():
                    await page.close()

            except Exception:

                logger.debug(
                    "%s: página ya estaba cerrada.",
                    self.display_name,
                )

        logger.info(
            "%s: %d ofertas extraídas en total.",
            self.display_name,
            len(results),
        )

        return results

    # ============================================================
    # ESPERAR VERIFICACIÓN HUMANA
    # ============================================================

    async def _wait_for_human_verification(
        self,
        page,
    ) -> None:
        """
        Espera a que el usuario complete manualmente
        la verificación.

        NO:

        - resuelve CAPTCHA;
        - pulsa CAPTCHA;
        - recarga la página;
        - navega a otra URL;
        - intenta evadir Cloudflare.

        Simplemente observa la misma página.
        """

        logger.warning(
            "%s requiere intervención humana.",
            self.display_name,
        )

        logger.warning(
            "Completa la verificación en el navegador.",
        )

        logger.warning(
            "NO cierres ni recargues la página.",
        )

        max_wait_seconds = 300
        poll_interval_seconds = 2

        stable_required = 5
        stable_count = 0

        elapsed = 0

        last_url = ""

        while elapsed < max_wait_seconds:

            # ----------------------------------------------------
            # Página cerrada
            # ----------------------------------------------------

            try:

                if page.is_closed():

                    raise HumanInterventionRequired(
                        f"{self.display_name}: la página "
                        "fue cerrada durante la verificación."
                    )

            except HumanInterventionRequired:
                raise

            except Exception:
                pass

            # ----------------------------------------------------
            # Estado
            # ----------------------------------------------------

            try:

                (
                    current_url,
                    title,
                    body_text,
                    html,
                ) = await self._get_page_state(
                    page
                )

            except Exception as exc:

                logger.debug(
                    "%s: no se pudo leer "
                    "el estado: %s",
                    self.display_name,
                    type(exc).__name__,
                )

                stable_count = 0

                await asyncio.sleep(
                    poll_interval_seconds
                )

                elapsed += poll_interval_seconds

                continue

            # ----------------------------------------------------
            # URL
            # ----------------------------------------------------

            if current_url != last_url:

                if last_url:

                    logger.info(
                        "%s: URL cambió:",
                        self.display_name,
                    )

                    logger.info(
                        "Anterior: %s",
                        last_url,
                    )

                    logger.info(
                        "Actual: %s",
                        current_url,
                    )

                last_url = current_url

            # ----------------------------------------------------
            # Verificación
            # ----------------------------------------------------

            verification_active = (
                self._looks_like_verification_page(
                    html,
                    url=current_url,
                    title=title,
                    body_text=body_text,
                )
            )

            # ----------------------------------------------------
            # CAPTCHA ACTIVO
            # ----------------------------------------------------

            if verification_active:

                if stable_count > 0:

                    logger.info(
                        "%s: la verificación reapareció.",
                        self.display_name,
                    )

                stable_count = 0

            # ----------------------------------------------------
            # CAPTCHA NO DETECTADO
            # ----------------------------------------------------

            else:

                stable_count += 1

                logger.info(
                    "%s: verificación no detectada "
                    "(%d/%d).",
                    self.display_name,
                    stable_count,
                    stable_required,
                )

                if stable_count >= stable_required:

                    # --------------------------------------------
                    # Esperamos un poco más SIN tocar la página.
                    # --------------------------------------------

                    await asyncio.sleep(3)

                    (
                        final_url,
                        final_title,
                        final_body,
                        final_html,
                    ) = await self._get_page_state(
                        page
                    )

                    final_blocked = (
                        self._looks_like_verification_page(
                            final_html,
                            url=final_url,
                            title=final_title,
                            body_text=final_body,
                        )
                    )

                    if final_blocked:

                        logger.info(
                            "%s: la verificación "
                            "reapareció.",
                            self.display_name,
                        )

                        stable_count = 0

                    else:

                        logger.info(
                            "%s: verificación confirmada.",
                            self.display_name,
                        )

                        return

            # ----------------------------------------------------
            # Próximo ciclo
            # ----------------------------------------------------

            await asyncio.sleep(
                poll_interval_seconds
            )

            elapsed += poll_interval_seconds

        raise HumanInterventionRequired(
            f"{self.display_name}: la verificación "
            "no se completó dentro de los "
            "5 minutos permitidos."
        )

    # ============================================================
    # DESCRIPCIÓN
    # ============================================================

    async def fetch_description(
        self,
        browser: BrowserManager,
        job: JobPosting,
    ) -> str:

        if not job.url:
            return ""

        context = await browser.get_context(
            self.name,
            headless=False,
        )

        page = await context.new_page()

        try:

            await page.goto(
                job.url,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT_MS,
            )

            (
                current_url,
                title,
                body_text,
                html,
            ) = await self._get_page_state(
                page
            )

            self.check_blocked(
                html,
                url=current_url,
                title=title,
                body_text=body_text,
            )

            return self.parse_description(
                html
            )

        finally:

            try:

                if not page.is_closed():
                    await page.close()

            except Exception:

                logger.debug(
                    "%s: página de descripción "
                    "ya estaba cerrada.",
                    self.name,
                )

    # ============================================================
    # SESIÓN
    # ============================================================

    async def is_session_active(
        self,
        browser: BrowserManager,
    ) -> bool:

        if not self.requires_login:
            return True

        context = await browser.get_context(
            self.name,
            headless=False,
        )

        page = await context.new_page()

        try:

            await page.goto(
                self.home_url
                or self.login_url,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT_MS,
            )

            for selector in (
                self.session_active_markers
            ):

                if await page.query_selector(
                    selector
                ):
                    return True

            return False

        finally:

            try:

                if not page.is_closed():
                    await page.close()

            except Exception:

                logger.debug(
                    "%s: página de sesión "
                    "ya estaba cerrada.",
                    self.name,
                )

    # ============================================================
    # POSTULACIÓN
    # ============================================================

    async def apply(
        self,
        browser: BrowserManager,
        job: JobPosting,
        applicant: dict,
        answers: dict[str, str],
    ) -> str:

        return "assisted"