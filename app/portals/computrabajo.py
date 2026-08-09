"""Portal: Computrabajo Perú.

Implementación experimental.
Los selectores pueden cambiar con frecuencia.
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from app.models.job import JobPosting
from app.portals.base_portal import BasePortal


class CompuTrabajoPortal(BasePortal):
    name = "computrabajo"
    display_name = "Computrabajo"

    home_url = "https://pe.computrabajo.com"
    login_url = "https://pe.computrabajo.com/login"

    requires_login = False
    supports_apply = False

    session_active_markers = (
        "[data-testid='user-menu']",
        ".user-menu",
    )

    # ============================================================
    # URL DE BÚSQUEDA
    # ============================================================

    def build_search_url(
        self,
        query: str,
        location: str,
    ) -> str:

        query = query.strip()
        location = location.strip()

        if not query:
            return self.home_url

        query_slug = re.sub(
            r"\s+",
            "-",
            query.lower(),
        )

        query_slug = re.sub(
            r"[^a-z0-9áéíóúüñ-]",
            "",
            query_slug,
        )

        # --------------------------------------------------------
        # IMPORTANTE:
        #
        # Si el usuario pone ubicación, la usamos.
        # Si no, buscamos solamente por puesto.
        # --------------------------------------------------------

        if location:

            location_slug = re.sub(
                r"\s+",
                "-",
                location.lower(),
            )

            location_slug = re.sub(
                r"[^a-z0-9áéíóúüñ-]",
                "",
                location_slug,
            )

            return (
                "https://pe.computrabajo.com/"
                f"trabajo-de-{quote_plus(query_slug)}"
                f"-en-{quote_plus(location_slug)}"
            )

        return (
            "https://pe.computrabajo.com/"
            f"trabajo-de-{quote_plus(query_slug)}"
        )

    # ============================================================
    # PARSER
    # ============================================================

    def parse_search_results(
        self,
        html: str,
    ) -> list[JobPosting]:

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        jobs: list[JobPosting] = []

        # --------------------------------------------------------
        # Computrabajo suele utilizar enlaces hacia /ofertas-de-
        # trabajo/oferta-de-trabajo-de-...
        #
        # También dejamos selectores alternativos.
        # --------------------------------------------------------

        links = soup.select(
            "a[href*='/ofertas-de-trabajo/'], "
            "a[href*='/oferta-de-trabajo/'], "
            "a[href*='/trabajo/']"
        )

        seen_urls: set[str] = set()

        for link in links:

            href = link.get("href")

            if not href:
                continue

            url = self.absolutize(
                str(href)
            )

            if not url:
                continue

            # ----------------------------------------------------
            # Evitar duplicados
            # ----------------------------------------------------

            normalized_url = url.split("?")[0]

            if normalized_url in seen_urls:
                continue

            # ----------------------------------------------------
            # TÍTULO
            # ----------------------------------------------------

            title = self._extract_title(
                link
            )

            if not title:
                continue

            if len(title.strip()) < 4:
                continue

            title_lower = title.lower()

            ignored_titles = {
                "ver oferta",
                "ver empleo",
                "postular",
                "postularme",
                "ver más",
                "más información",
                "leer más",
                "detalle",
            }

            if title_lower in ignored_titles:
                continue

            # ----------------------------------------------------
            # CONTENEDOR
            # ----------------------------------------------------

            container = link.find_parent(
                [
                    "article",
                    "li",
                    "div",
                ]
            )

            company = ""
            location = ""
            salary = ""
            modality = ""

            if container is not None:

                company = self._extract_company(
                    container
                )

                location = self._extract_location(
                    container
                )

                salary = self._extract_salary(
                    container
                )

                modality = self._extract_modality(
                    container
                )

            # ----------------------------------------------------
            # CREAR OFERTA
            # ----------------------------------------------------

            job = JobPosting(
                title=title,
                company=company,
                location=location,
                salary=salary,
                modality=modality,
                url=url,
                portal=self.name,
            )

            seen_urls.add(
                normalized_url
            )

            jobs.append(job)

        return jobs

    # ============================================================
    # TÍTULO
    # ============================================================

    @staticmethod
    def _extract_title(
        link,
    ) -> str:

        selectors = (
            "h1",
            "h2",
            "h3",
            "h4",
            "[data-testid*='title']",
            "[class*='title']",
            "[class*='Title']",
        )

        for selector in selectors:

            try:
                element = link.select_one(
                    selector
                )
            except Exception:
                continue

            if not element:
                continue

            text = element.get_text(
                " ",
                strip=True,
            )

            if 4 <= len(text) <= 180:
                return text

        # aria-label

        aria_label = link.get(
            "aria-label"
        )

        if aria_label:

            text = str(
                aria_label
            ).strip()

            if 4 <= len(text) <= 180:
                return text

        # title attribute

        attribute_title = link.get(
            "title"
        )

        if attribute_title:

            text = str(
                attribute_title
            ).strip()

            if 4 <= len(text) <= 180:
                return text

        # texto directo

        text = link.get_text(
            " ",
            strip=True,
        )

        if 4 <= len(text) <= 180:
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
            "[data-testid*='company']",
            "[data-testid*='empresa']",
            "[class*='company']",
            "[class*='Company']",
            "[class*='empresa']",
            "[class*='Empresa']",
            "h3",
            "h4",
        )

        for selector in selectors:

            try:
                element = container.select_one(
                    selector
                )
            except Exception:
                continue

            if not element:
                continue

            text = element.get_text(
                " ",
                strip=True,
            )

            if not text:
                continue

            # Evitar devolver el mismo título
            if len(text) > 150:
                continue

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
            "[data-testid*='location']",
            "[data-testid*='ubicacion']",
            "[class*='location']",
            "[class*='Location']",
            "[class*='ubicacion']",
            "[class*='Ubicacion']",
        )

        for selector in selectors:

            try:
                element = container.select_one(
                    selector
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
        # Fallback
        # --------------------------------------------------------

        text = container.get_text(
            " ",
            strip=True,
        )

        locations = (
            "Lima",
            "Callao",
            "Arequipa",
            "Trujillo",
            "Piura",
            "Cusco",
            "Chiclayo",
            "Ica",
            "Perú",
        )

        for location in locations:

            if location.lower() in text.lower():
                return location

        return ""

    # ============================================================
    # SALARIO
    # ============================================================

    @staticmethod
    def _extract_salary(
        container,
    ) -> str:

        selectors = (
            "[data-testid*='salary']",
            "[data-testid*='salario']",
            "[class*='salary']",
            "[class*='Salary']",
            "[class*='sueldo']",
            "[class*='Sueldo']",
            "[class*='salario']",
            "[class*='Salario']",
        )

        for selector in selectors:

            try:
                element = container.select_one(
                    selector
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

        text = container.get_text(
            " ",
            strip=True,
        )

        salary_pattern = re.compile(
            r"(?:S\/\.?|S\/|PEN)\s*"
            r"[\d.,]+"
            r"(?:\s*[-–]\s*"
            r"(?:S\/\.?|S\/|PEN)?\s*"
            r"[\d.,]+)?",
            re.IGNORECASE,
        )

        match = salary_pattern.search(
            text
        )

        if match:
            return match.group(
                0
            ).strip()

        return ""

    # ============================================================
    # MODALIDAD
    # ============================================================

    @staticmethod
    def _extract_modality(
        container,
    ) -> str:

        text = container.get_text(
            " ",
            strip=True,
        ).lower()

        if "remoto" in text:
            return "Remoto"

        if "híbrido" in text or "hibrido" in text:
            return "Híbrido"

        if "presencial" in text:
            return "Presencial"

        return ""

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
            "[data-testid*='description']",
            "[data-testid*='descripcion']",
            "[class*='description']",
            "[class*='Description']",
            "[class*='descripcion']",
            "[class*='Descripcion']",
            ".description",
            ".box_detail",
            "article",
        )

        for selector in selectors:

            try:
                element = soup.select_one(
                    selector
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