"""Portal: Bumeran Perú.

Implementación experimental.
Los selectores de Bumeran pueden cambiar con frecuencia.

Objetivos:
- Buscar por puesto.
- No obligar a incluir ubicación en la URL.
- Extraer la mayor cantidad posible de ofertas.
- Extraer título y empresa de forma robusta.
- Mantener URL, ubicación y salario cuando estén disponibles.
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup, Tag

from app.models.job import JobPosting
from app.portals.base_portal import BasePortal


class BumeranPortal(BasePortal):
    name = "bumeran"
    display_name = "Bumeran"

    home_url = "https://www.bumeran.com.pe"
    login_url = "https://www.bumeran.com.pe/login"

    requires_login = False
    supports_apply = False

    session_active_markers = (
        "[data-testid='user-menu']",
    )

    # ============================================================
    # URL DE BÚSQUEDA
    # ============================================================

    def build_search_url(
        self,
        query: str,
        location: str,
    ) -> str:
        """Construye la URL de búsqueda.

        Importante:
        La ubicación NO se fuerza dentro de la búsqueda.

        El agente puede recibir:
            Analista de sistemas
            Lima

        pero Bumeran buscará principalmente:
            Analista de sistemas

        Esto evita reducir artificialmente los resultados.
        """

        query = (query or "").strip()

        if not query:
            return self.home_url

        # Normalizar espacios.
        query = re.sub(
            r"\s+",
            " ",
            query,
        )

        # Bumeran funciona mejor con slug.
        slug = query.lower()

        # Mantener letras, números, espacios y guiones.
        slug = re.sub(
            r"[^a-z0-9áéíóúüñ\s-]",
            "",
            slug,
        )

        slug = re.sub(
            r"\s+",
            "-",
            slug,
        )

        slug = re.sub(
            r"-+",
            "-",
            slug,
        ).strip("-")

        return (
            "https://www.bumeran.com.pe/"
            f"empleos-busqueda-{quote_plus(slug)}.html"
        )

    # ============================================================
    # PARSER PRINCIPAL
    # ============================================================

    def parse_search_results(
        self,
        html: str,
    ) -> list[JobPosting]:
        """Extrae ofertas de la página de resultados."""

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        jobs: list[JobPosting] = []
        seen_urls: set[str] = set()

        # --------------------------------------------------------
        # Primero buscamos enlaces que tengan apariencia de
        # publicación laboral.
        # --------------------------------------------------------

        links = soup.select(
            "a[href*='/empleos/'], "
            "a[href*='/empleo/'], "
            "a[href*='/aviso/'], "
            "a[href*='/job/'], "
            "a[href*='jobId'], "
            "a[data-testid*='job'], "
            "a[data-testid*='offer'], "
            "a[class*='job'], "
            "a[class*='Job']"
        )

        # --------------------------------------------------------
        # Algunos sitios renderizan las ofertas sin clases
        # predecibles. Como fallback buscamos enlaces internos
        # que parezcan URLs de ofertas.
        # --------------------------------------------------------

        if not links:
            links = soup.find_all(
                "a",
                href=True,
            )

        for link in links:

            if not isinstance(link, Tag):
                continue

            href = link.get(
                "href"
            )

            if not href:
                continue

            href = str(href).strip()

            # ----------------------------------------------------
            # Ignorar enlaces que claramente NO son ofertas.
            # ----------------------------------------------------

            if self._is_navigation_link(
                href
            ):
                continue

            url = self.absolutize(
                href
            )

            if not url:
                continue

            if url in seen_urls:
                continue

            # ----------------------------------------------------
            # Buscar contenedor de la oferta.
            # ----------------------------------------------------

            container = self._find_job_container(
                link
            )

            # ----------------------------------------------------
            # Extraer título.
            # ----------------------------------------------------

            title = self._extract_title(
                link,
                container,
            )

            if not title:
                continue

            if not self._looks_like_job_title(
                title
            ):
                continue

            # ----------------------------------------------------
            # Extraer empresa.
            # ----------------------------------------------------

            company = self._extract_company(
                link,
                container,
            )

            # ----------------------------------------------------
            # Extraer ubicación.
            # ----------------------------------------------------

            location = self._extract_location(
                link,
                container,
            )

            # ----------------------------------------------------
            # Extraer salario.
            # ----------------------------------------------------

            salary = self._extract_salary(
                link,
                container,
            )

            # ----------------------------------------------------
            # Crear oferta.
            # ----------------------------------------------------

            job = JobPosting(
                title=title,
                company=company,
                location=location,
                salary=salary,
                url=url,
                portal=self.name,
            )

            jobs.append(job)
            seen_urls.add(url)

        return self._deduplicate_jobs(
            jobs
        )

    # ============================================================
    # CONTENEDOR DE OFERTA
    # ============================================================

    @staticmethod
    def _find_job_container(
        link: Tag,
    ) -> Tag | None:
        """Busca el contenedor más probable de una oferta."""

        # Primero buscamos ancestros semánticos.
        for parent in link.parents:

            if not isinstance(parent, Tag):
                continue

            if parent.name in (
                "article",
                "li",
            ):
                return parent

            classes = " ".join(
                parent.get("class", [])
            ).lower()

            data_testid = str(
                parent.get(
                    "data-testid",
                    ""
                )
            ).lower()

            # Indicadores de una card de empleo.
            indicators = (
                "job",
                "offer",
                "aviso",
                "vacancy",
                "listing",
                "card",
                "search-result",
                "resultado",
                "empleo",
            )

            if any(
                indicator in classes
                for indicator in indicators
            ):
                return parent

            if any(
                indicator in data_testid
                for indicator in indicators
            ):
                return parent

            # Evitar subir demasiado.
            if parent.name == "body":
                break

        return None

    # ============================================================
    # TÍTULO
    # ============================================================

    @classmethod
    def _extract_title(
        cls,
        link: Tag,
        container: Tag | None,
    ) -> str:
        """Extrae únicamente el título de la oferta."""

        # --------------------------------------------------------
        # 1. Atributos explícitos del enlace.
        # --------------------------------------------------------

        for attribute in (
            "data-title",
            "data-job-title",
            "data-offer-title",
            "aria-label",
            "title",
        ):

            value = link.get(
                attribute
            )

            if value:

                text = cls._clean_text(
                    str(value)
                )

                if cls._looks_like_job_title(
                    text
                ):
                    return text

        # --------------------------------------------------------
        # 2. Selectores de título dentro del enlace.
        # --------------------------------------------------------

        title_selectors = (
            "[data-testid='job-title']",
            "[data-testid*='job-title']",
            "[data-testid*='title']",
            "[class*='job-title']",
            "[class*='JobTitle']",
            "[class*='jobTitle']",
            "[class*='offer-title']",
            "[class*='OfferTitle']",
            "[class*='title']",
            "[class*='Title']",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
        )

        for selector in title_selectors:

            try:
                element = link.select_one(
                    selector
                )
            except Exception:
                continue

            if not element:
                continue

            text = cls._clean_text(
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            if cls._looks_like_job_title(
                text
            ):
                return text

        # --------------------------------------------------------
        # 3. Buscar el título dentro del contenedor.
        # --------------------------------------------------------

        if container is not None:

            for selector in title_selectors:

                try:
                    element = container.select_one(
                        selector
                    )
                except Exception:
                    continue

                if not element:
                    continue

                text = cls._clean_text(
                    element.get_text(
                        " ",
                        strip=True,
                    )
                )

                if cls._looks_like_job_title(
                    text
                ):
                    return text

        # --------------------------------------------------------
        # 4. Texto directo del enlace.
        #
        # IMPORTANTE:
        # No usamos el texto de toda la tarjeta.
        # --------------------------------------------------------

        direct_text = cls._direct_text(
            link
        )

        if cls._looks_like_job_title(
            direct_text
        ):
            return direct_text

        # --------------------------------------------------------
        # 5. Último fallback: texto del enlace.
        # --------------------------------------------------------

        text = cls._clean_text(
            link.get_text(
                " ",
                strip=True,
            )
        )

        if cls._looks_like_job_title(
            text
        ):
            return text

        return ""

    # ============================================================
    # EMPRESA
    # ============================================================

    @classmethod
    def _extract_company(
        cls,
        link: Tag,
        container: Tag | None,
    ) -> str:
        """Extrae la empresa de la oferta."""

        scopes: list[Tag] = [
            link
        ]

        if container is not None:
            scopes.append(
                container
            )

        selectors = (
            "[data-testid='company']",
            "[data-testid*='company']",
            "[data-testid*='employer']",
            "[data-testid*='business']",
            "[class*='company']",
            "[class*='Company']",
            "[class*='employer']",
            "[class*='Employer']",
            "[class*='empresa']",
            "[class*='Empresa']",
            "[class*='business']",
            "[class*='Business']",
            "[itemprop='hiringOrganization']",
            "[itemprop='name']",
        )

        for scope in scopes:

            for selector in selectors:

                try:
                    elements = scope.select(
                        selector
                    )
                except Exception:
                    continue

                for element in elements:

                    text = cls._clean_text(
                        element.get_text(
                            " ",
                            strip=True,
                        )
                    )

                    if cls._looks_like_company(
                        text
                    ):
                        return text

                    # Si el elemento tiene content.
                    content = element.get(
                        "content"
                    )

                    if content:

                        text = cls._clean_text(
                            str(content)
                        )

                        if cls._looks_like_company(
                            text
                        ):
                            return text

        # --------------------------------------------------------
        # Buscar atributos de empresa.
        # --------------------------------------------------------

        attributes = (
            "data-company",
            "data-company-name",
            "data-employer",
            "data-employer-name",
        )

        for scope in scopes:

            for attribute in attributes:

                value = scope.get(
                    attribute
                )

                if value:

                    text = cls._clean_text(
                        str(value)
                    )

                    if cls._looks_like_company(
                        text
                    ):
                        return text

        # --------------------------------------------------------
        # Microdatos.
        # --------------------------------------------------------

        if container is not None:

            organization = container.select_one(
                "[itemtype*='Organization']"
            )

            if organization:

                element = organization.select_one(
                    "[itemprop='name']"
                )

                if element:

                    text = cls._clean_text(
                        element.get_text(
                            " ",
                            strip=True,
                        )
                    )

                    if text:
                        return text

        return ""

    # ============================================================
    # UBICACIÓN
    # ============================================================

    @classmethod
    def _extract_location(
        cls,
        link: Tag,
        container: Tag | None,
    ) -> str:
        """Extrae la ubicación."""

        scopes: list[Tag] = [
            link
        ]

        if container is not None:
            scopes.append(
                container
            )

        selectors = (
            "[data-testid='location']",
            "[data-testid*='location']",
            "[data-testid*='city']",
            "[class*='location']",
            "[class*='Location']",
            "[class*='ubicacion']",
            "[class*='Ubicacion']",
            "[class*='city']",
            "[class*='City']",
            "[itemprop='jobLocation']",
            "[itemprop='addressLocality']",
        )

        for scope in scopes:

            for selector in selectors:

                try:
                    element = scope.select_one(
                        selector
                    )
                except Exception:
                    continue

                if not element:
                    continue

                text = cls._clean_text(
                    element.get_text(
                        " ",
                        strip=True,
                    )
                )

                if text:
                    return text

                content = element.get(
                    "content"
                )

                if content:
                    return cls._clean_text(
                        str(content)
                    )

        # --------------------------------------------------------
        # Fallback por ciudades.
        # --------------------------------------------------------

        text = ""

        if container is not None:
            text = container.get_text(
                " ",
                strip=True,
            )
        else:
            text = link.get_text(
                " ",
                strip=True,
            )

        location_patterns = (
            "Lima",
            "Callao",
            "Arequipa",
            "Trujillo",
            "Piura",
            "Cusco",
            "Chiclayo",
            "Ica",
            "Tacna",
            "Huancayo",
            "Perú",
            "Peru",
        )

        for pattern in location_patterns:

            if re.search(
                rf"\b{re.escape(pattern)}\b",
                text,
                re.IGNORECASE,
            ):
                return pattern

        return ""

    # ============================================================
    # SALARIO
    # ============================================================

    @classmethod
    def _extract_salary(
        cls,
        link: Tag,
        container: Tag | None,
    ) -> str:
        """Extrae salario si aparece."""

        scopes: list[Tag] = [
            link
        ]

        if container is not None:
            scopes.append(
                container
            )

        selectors = (
            "[data-testid='salary']",
            "[data-testid*='salary']",
            "[data-testid*='sueldo']",
            "[class*='salary']",
            "[class*='Salary']",
            "[class*='sueldo']",
            "[class*='Sueldo']",
            "[class*='remuneracion']",
            "[class*='Remuneracion']",
        )

        for scope in scopes:

            for selector in selectors:

                try:
                    element = scope.select_one(
                        selector
                    )
                except Exception:
                    continue

                if not element:
                    continue

                text = cls._clean_text(
                    element.get_text(
                        " ",
                        strip=True,
                    )
                )

                if text:
                    return text

        # --------------------------------------------------------
        # Fallback por regex.
        # --------------------------------------------------------

        if container is not None:
            text = container.get_text(
                " ",
                strip=True,
            )
        else:
            text = link.get_text(
                " ",
                strip=True,
            )

        salary_pattern = re.compile(
            r"(?:S\/\.?|S\/|PEN|USD|\$)\s*"
            r"[\d.,]+"
            r"(?:\s*[-–]\s*"
            r"(?:S\/\.?|S\/|PEN|USD|\$)?\s*"
            r"[\d.,]+)?",
            re.IGNORECASE,
        )

        match = salary_pattern.search(
            text
        )

        if match:
            return cls._clean_text(
                match.group(0)
            )

        return ""

    # ============================================================
    # VALIDACIÓN DEL TÍTULO
    # ============================================================

    @staticmethod
    def _looks_like_job_title(
        text: str,
    ) -> bool:
        if not text:
            return False

        text = text.strip()

        if len(text) < 4:
            return False

        if len(text) > 180:
            return False

        lowered = text.lower()

        ignored = {
            "ver oferta",
            "ver empleo",
            "ver más",
            "ver mas",
            "leer más",
            "leer mas",
            "postular",
            "postularme",
            "aplicar",
            "apply",
            "buscar",
            "iniciar sesión",
            "iniciar sesion",
            "registrarse",
            "ingresar",
        }

        if lowered in ignored:
            return False

        # Textos que son claramente navegación.
        navigation = (
            "inicio",
            "contacto",
            "privacidad",
            "términos",
            "terminos",
            "cookies",
            "mi cuenta",
        )

        if lowered in navigation:
            return False

        return True

    # ============================================================
    # VALIDACIÓN DE EMPRESA
    # ============================================================

    @staticmethod
    def _looks_like_company(
        text: str,
    ) -> bool:
        if not text:
            return False

        text = text.strip()

        if len(text) < 2:
            return False

        if len(text) > 150:
            return False

        lowered = text.lower()

        invalid = {
            "empresa",
            "company",
            "empleador",
            "employer",
            "ver oferta",
            "postular",
            "postularme",
            "aplicar",
            "salario",
            "ubicación",
            "ubicacion",
        }

        if lowered in invalid:
            return False

        return True

    # ============================================================
    # ENLACES NO VÁLIDOS
    # ============================================================

    @staticmethod
    def _is_navigation_link(
        href: str,
    ) -> bool:
        lowered = href.lower()

        ignored = (
            "/login",
            "/registro",
            "/registrate",
            "/contacto",
            "/ayuda",
            "/privacidad",
            "/terminos",
            "/cookies",
            "javascript:",
            "mailto:",
            "#",
        )

        return lowered.startswith(
            ignored
        )

    # ============================================================
    # TEXTO DIRECTO
    # ============================================================

    @staticmethod
    def _direct_text(
        element: Tag,
    ) -> str:
        """Obtiene solamente texto directamente perteneciente
        al elemento, evitando en lo posible texto de hijos grandes.
        """

        texts: list[str] = []

        for child in element.children:

            if isinstance(child, str):

                value = child.strip()

                if value:
                    texts.append(
                        value
                    )

        return " ".join(
            texts
        ).strip()

    # ============================================================
    # LIMPIEZA
    # ============================================================

    @staticmethod
    def _clean_text(
        value: str,
    ) -> str:
        if not value:
            return ""

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        return value.strip()

    # ============================================================
    # DEDUPLICACIÓN
    # ============================================================

    @staticmethod
    def _deduplicate_jobs(
        jobs: list[JobPosting],
    ) -> list[JobPosting]:
        """Elimina duplicados manteniendo el primer resultado."""

        unique: dict[str, JobPosting] = {}

        for job in jobs:

            if not job.url:
                continue

            if job.url not in unique:
                unique[job.url] = job

        return list(
            unique.values()
        )

    # ============================================================
    # DESCRIPCIÓN
    # ============================================================

    def parse_description(
        self,
        html: str,
    ) -> str:
        """Extrae la descripción completa de la oferta."""

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        selectors = (
            "#ficha-detalle",
            ".aviso_description",
            "section.detail",
            "[data-testid*='description']",
            "[data-testid*='job-description']",
            "[class*='description']",
            "[class*='Description']",
            "[class*='descripcion']",
            "[class*='Descripcion']",
            "[itemprop='description']",
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

            text = re.sub(
                r"\n{3,}",
                "\n\n",
                text,
            )

            if len(text) >= 50:
                return text

        return ""