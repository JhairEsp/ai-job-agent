"""
Portal: LinkedIn Jobs.

Implementación experimental y asistida.

Reglas:

- No intenta evadir CAPTCHA.
- No intenta saltarse login.
- No automatiza mecanismos anti-bot.
- Usa la sesión persistente del navegador.
- El usuario inicia sesión manualmente.
- No captura ni almacena contraseñas.
- La extracción depende de los selectores actuales de LinkedIn.

El perfil persistente se encuentra en:

data/browser_profiles/linkedin
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from app.models.job import JobPosting
from app.portals.base_portal import BasePortal


# ============================================================
# CONFIGURACIÓN
# ============================================================

MAX_RESULTS = 6


class LinkedInPortal(BasePortal):

    name = "linkedin"
    display_name = "LinkedIn"

    home_url = (
        "https://www.linkedin.com"
    )

    login_url = (
        "https://www.linkedin.com/login"
    )

    requires_login = True
    supports_apply = False

    # --------------------------------------------------------
    # Selectores que pueden indicar que hay sesión.
    #
    # No dependemos únicamente de uno.
    # --------------------------------------------------------

    session_active_markers = (
        "img.global-nav__me-photo",
        ".global-nav__me",
        ".global-nav__primary-link-me",
        ".feed-identity-module",
        "[data-control-name='nav.settings_and_privacy']",
        "[data-test-global-nav-link='profile']",
        "button[aria-label*='Yo']",
        "button[aria-label*='Me']",
        "a[href*='/in/']",
    )

    # ============================================================
    # URL DE BÚSQUEDA
    # ============================================================

    def build_search_url(
        self,
        query: str,
        location: str,
    ) -> str:

        query = (
            query
            or ""
        ).strip()

        location = (
            location
            or ""
        ).strip()

        # --------------------------------------------------------
        # Si no hay puesto, abrir Jobs.
        # --------------------------------------------------------

        if not query:

            return (
                f"{self.home_url}/jobs/"
            )

        params = [
            "f_TPR=r86400",
            f"keywords={quote_plus(query)}",
        ]

        # --------------------------------------------------------
        # IMPORTANTE:
        #
        # Solo agregar ubicación si realmente existe.
        #
        # Si location == "":
        #
        # LinkedIn busca:
        #
        # Analista de Sistemas
        #
        # sin forzar Lima.
        # --------------------------------------------------------

        if location:

            params.append(
                "location="
                + quote_plus(
                    location
                )
            )

        return (
            f"{self.home_url}/jobs/search?"
            + "&".join(params)
        )

    # ============================================================
    # PARSER DE RESULTADOS
    # ============================================================

    def parse_search_results(
        self,
        html: str,
    ) -> list[JobPosting]:

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        jobs: list[
            JobPosting
        ] = []

        seen_urls: set[str] = set()

        # --------------------------------------------------------
        # Primero: tarjetas actuales.
        # --------------------------------------------------------

        containers = soup.select(
            "li.jobs-search-results__list-item, "
            "li[data-occludable-job-id], "
            ".job-card-container, "
            ".jobs-search-results__list-item, "
            ".base-card"
        )

        for container in containers:

            if len(jobs) >= MAX_RESULTS:
                break

            title = (
                self._extract_title(
                    container
                )
            )

            if not title:
                continue

            company = (
                self._extract_company(
                    container
                )
            )

            location = (
                self._extract_location(
                    container
                )
            )

            salary = (
                self._extract_salary(
                    container
                )
            )

            url = (
                self._extract_url(
                    container
                )
            )

            if not url:
                continue

            # ----------------------------------------------------
            # Normalizar URL.
            # ----------------------------------------------------

            url = self._normalize_job_url(
                url
            )

            if not url:
                continue

            if url in seen_urls:
                continue

            jobs.append(
                JobPosting(
                    title=title,
                    company=company,
                    location=location,
                    salary=salary,
                    url=url,
                    portal=self.name,
                )
            )

            seen_urls.add(
                url
            )

        # ========================================================
        # FALLBACK
        # ========================================================

        if len(jobs) < MAX_RESULTS:

            links = soup.select(
                "a[href*='/jobs/view/'], "
                "a[href*='/jobs-guest/jobs/api/']"
            )

            for link in links:

                if len(jobs) >= MAX_RESULTS:
                    break

                href = (
                    link.get(
                        "href"
                    )
                )

                if not href:
                    continue

                url = self.absolutize(
                    str(href)
                )

                url = (
                    self._normalize_job_url(
                        url
                    )
                )

                if not url:
                    continue

                if url in seen_urls:
                    continue

                title = (
                    self._extract_link_title(
                        link
                    )
                )

                if not title:
                    continue

                parent = (
                    link.find_parent(
                        [
                            "li",
                            "article",
                            "div",
                        ]
                    )
                )

                company = ""
                location = ""
                salary = ""

                if parent:

                    company = (
                        self._extract_company(
                            parent
                        )
                    )

                    location = (
                        self._extract_location(
                            parent
                        )
                    )

                    salary = (
                        self._extract_salary(
                            parent
                        )
                    )

                jobs.append(
                    JobPosting(
                        title=title,
                        company=company,
                        location=location,
                        salary=salary,
                        url=url,
                        portal=self.name,
                    )
                )

                seen_urls.add(
                    url
                )

        return jobs[:MAX_RESULTS]

    # ============================================================
    # TÍTULO
    # ============================================================

    @staticmethod
    def _extract_title(
        container,
    ) -> str:

        selectors = (
            "h3.base-search-card__title",
            ".base-search-card__title",
            ".job-card-list__title",
            ".job-card-container__link",
            ".job-card-container__primary-description",
            "h3",
            "h2",
        )

        for selector in selectors:

            try:

                element = (
                    container.select_one(
                        selector
                    )
                )

            except Exception:

                continue

            if not element:
                continue

            text = element.get_text(
                " ",
                strip=True,
            )

            if 4 <= len(text) <= 200:

                return text

        return ""

    # ============================================================
    # TÍTULO DESDE LINK
    # ============================================================

    @staticmethod
    def _extract_link_title(
        link,
    ) -> str:

        # aria-label

        aria = link.get(
            "aria-label"
        )

        if aria:

            text = str(
                aria
            ).strip()

            if len(text) >= 4:

                return text

        # title

        title = link.get(
            "title"
        )

        if title:

            text = str(
                title
            ).strip()

            if len(text) >= 4:

                return text

        # texto

        text = link.get_text(
            " ",
            strip=True,
        )

        if 4 <= len(text) <= 200:

            return text

        return ""

    # ============================================================
    # EMPRESA
    # ============================================================

    @staticmethod
    def _extract_company(
        container,
    ) -> str:

        selectors = (
            ".base-search-card__subtitle",
            ".job-card-container__company-name",
            ".job-card-container__primary-description",
            ".job-card-container__company-name",
            "[class*='company-name']",
            "[class*='Company']",
        )

        for selector in selectors:

            try:

                element = (
                    container.select_one(
                        selector
                    )
                )

            except Exception:

                continue

            if not element:
                continue

            text = element.get_text(
                " ",
                strip=True,
            )

            if text:

                return text

        # --------------------------------------------------------
        # Fallback.
        #
        # Buscar elementos típicos de empresa.
        # --------------------------------------------------------

        for element in container.select(
            "a[href*='/company/']"
        ):

            text = element.get_text(
                " ",
                strip=True,
            )

            if text:

                return text

        return ""

    # ============================================================
    # UBICACIÓN
    # ============================================================

    @staticmethod
    def _extract_location(
        container,
    ) -> str:

        selectors = (
            ".job-search-card__location",
            ".base-search-card__metadata",
            ".job-card-container__metadata-item",
            ".job-card-container__metadata-wrapper",
            "[class*='location']",
            "[class*='Location']",
        )

        for selector in selectors:

            try:

                element = (
                    container.select_one(
                        selector
                    )
                )

            except Exception:

                continue

            if not element:
                continue

            text = element.get_text(
                " ",
                strip=True,
            )

            if text:

                return text

        return ""

    # ============================================================
    # SALARIO
    # ============================================================

    @staticmethod
    def _extract_salary(
        container,
    ) -> str:

        selectors = (
            ".job-search-card__salary-info",
            ".salary",
            "[class*='salary']",
            "[class*='Salary']",
        )

        for selector in selectors:

            try:

                element = (
                    container.select_one(
                        selector
                    )
                )

            except Exception:

                continue

            if not element:
                continue

            text = element.get_text(
                " ",
                strip=True,
            )

            if text:

                return text

        # --------------------------------------------------------
        # Fallback por texto.
        # --------------------------------------------------------

        text = container.get_text(
            " ",
            strip=True,
        )

        salary_pattern = re.compile(
            r"(?:S\/\.?|S\/|PEN|\$)\s*"
            r"[\d.,]+"
            r"(?:\s*[-–]\s*"
            r"(?:S\/\.?|S\/|PEN|\$)?\s*"
            r"[\d.,]+)?",
            re.IGNORECASE,
        )

        match = (
            salary_pattern.search(
                text
            )
        )

        if match:

            return (
                match.group(
                    0
                ).strip()
            )

        return ""

    # ============================================================
    # URL DE OFERTA
    # ============================================================

    def _extract_url(
        self,
        container,
    ) -> str:

        links = container.select(
            "a[href]"
        )

        for link in links:

            href = link.get(
                "href"
            )

            if not href:
                continue

            href = str(
                href
            )

            if (
                "/jobs/view/"
                in href
            ):

                return self.absolutize(
                    href
                )

        # --------------------------------------------------------
        # Fallback por data-*
        # --------------------------------------------------------

        job_id = (
            container.get(
                "data-job-id"
            )
            or container.get(
                "data-occludable-job-id"
            )
        )

        if job_id:

            return (
                f"{self.home_url}"
                f"/jobs/view/{job_id}/"
            )

        return ""

    # ============================================================
    # NORMALIZAR URL
    # ============================================================

    @staticmethod
    def _normalize_job_url(
        url: str,
    ) -> str:

        if not url:
            return ""

        url = (
            url
            .split("?")[0]
            .strip()
        )

        if "/jobs/view/" not in url:

            return ""

        # --------------------------------------------------------
        # Aseguramos slash final opcional.
        # --------------------------------------------------------

        return url

    # ============================================================
    # DESCRIPCIÓN
    # ============================================================

    def parse_description(
        self,
        html: str,
    ) -> str:

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        selectors = (
            ".show-more-less-html__markup",
            ".jobs-description__content",
            ".jobs-box__html-content",
            ".description__text",
            ".jobs-description-content__text",
            "[class*='description']",
            "[class*='Description']",
            "article",
        )

        for selector in selectors:

            try:

                element = (
                    soup.select_one(
                        selector
                    )
                )

            except Exception:

                continue

            if not element:
                continue

            text = element.get_text(
                "\n",
                strip=True,
            )

            if len(text) >= 50:

                return text

        return ""

    # ============================================================
    # SESIÓN DE LINKEDIN
    # ============================================================

    async def is_session_active(
        self,
        browser,
    ) -> bool:

        """
        Comprueba si LinkedIn parece tener una sesión activa.

        IMPORTANTE:

        No depende exclusivamente de un selector.

        Se comprueban:

        1. URL actual.
        2. Redirección a login.
        3. Elementos del navbar.
        4. Elementos de perfil.
        5. Cookies de LinkedIn.
        """

        context = await browser.get_context(
            self.name,
            headless=False,
        )

        # --------------------------------------------------------
        # Reutilizar página existente si existe.
        # --------------------------------------------------------

        page = None

        try:

            for existing_page in context.pages:

                try:

                    if (
                        "linkedin.com"
                        in existing_page.url
                    ):

                        page = existing_page
                        break

                except Exception:

                    continue

            if page is None:

                page = (
                    await context.new_page()
                )

            # ----------------------------------------------------
            # Ir a LinkedIn.
            # ----------------------------------------------------

            await page.goto(
                self.home_url,
                wait_until="domcontentloaded",
                timeout=60_000,
            )

            await page.wait_for_timeout(
                3000
            )

            current_url = (
                page.url
                or ""
            ).lower()

            # ----------------------------------------------------
            # Si LinkedIn nos mandó al login,
            # claramente no hay sesión.
            # ----------------------------------------------------

            if (
                "/login"
                in current_url
                or "/signup"
                in current_url
                or "/authwall"
                in current_url
            ):

                return False

            # ----------------------------------------------------
            # Comprobar selectores.
            # ----------------------------------------------------

            for selector in (
                self.session_active_markers
            ):

                try:

                    locator = page.locator(
                        selector
                    )

                    count = (
                        await locator.count()
                    )

                    if count > 0:

                        return True

                except Exception:

                    continue

            # ----------------------------------------------------
            # Comprobar cookies.
            #
            # No almacenamos valores.
            # Solo comprobamos si existen cookies
            # relacionadas con una sesión.
            # ----------------------------------------------------

            try:

                cookies = (
                    await context.cookies(
                        [
                            "https://www.linkedin.com"
                        ]
                    )
                )

                cookie_names = {
                    str(
                        cookie.get(
                            "name",
                            ""
                        )
                    ).lower()
                    for cookie in cookies
                }

                session_cookie_names = {
                    "li_at",
                    "jsessionid",
                    "liap",
                }

                if (
                    cookie_names
                    & session_cookie_names
                ):

                    return True

            except Exception:

                pass

            # ----------------------------------------------------
            # Comprobar texto del navbar.
            # ----------------------------------------------------

            try:

                body_text = (
                    await page.locator(
                        "body"
                    ).inner_text(
                        timeout=5000
                    )
                )

                body_lower = (
                    body_text.lower()
                )

                # Si aparece "iniciar sesión",
                # probablemente no está autenticado.

                login_markers = (
                    "iniciar sesión",
                    "inicia sesión",
                    "sign in",
                    "join now",
                )

                if any(
                    marker in body_lower
                    for marker in login_markers
                ):

                    return False

            except Exception:

                pass

            # ----------------------------------------------------
            # Si no hay login y estamos en LinkedIn,
            # permitimos continuar.
            #
            # Esto evita falsos negativos por cambios
            # de selectores del frontend.
            # ----------------------------------------------------

            if (
                "linkedin.com"
                in current_url
                and "/login"
                not in current_url
            ):

                return True

            return False

        finally:

            # ----------------------------------------------------
            # No cerramos una página que pudiera estar siendo
            # utilizada manualmente por el usuario.
            #
            # Tampoco cerramos el contexto.
            # ----------------------------------------------------

            pass