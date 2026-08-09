"""
Servicio de búsqueda y análisis de ofertas.

Flujo:

1. Lee preferencias y portales activos del usuario.
2. Busca ofertas en todos los portales activos.
3. Desduplica las ofertas.
4. Guarda todas las ofertas nuevas.
5. Intenta obtener la descripción real del anuncio.
6. Envía las ofertas nuevas a Groq.
7. Si Groq responde RateLimitError:
   - espera
   - reintenta
   - aumenta progresivamente la espera
8. Ordena las ofertas por score de compatibilidad IA.
9. Devuelve el ranking completo para Telegram.

IMPORTANTE:

- No se limita el análisis a las primeras N ofertas.
- Groq analiza todas las ofertas nuevas.
- Las solicitudes a Groq son SECUENCIALES.
- RateLimitError se maneja con retry/backoff.
- Si una oferta falla definitivamente, no detiene las demás.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from app.ai import job_analyzer
from app.ai.groq_client import GroqClient
from app.browser.session_manager import (
    BrowserManager,
    BrowserUnavailableError,
    HumanInterventionRequired,
)
from app.cv.cv_manager import CVManager
from app.database.db import Database
from app.database.repositories import (
    JobRepository,
    PortalRepository,
    UserRepository,
    job_row_to_analysis,
    job_row_to_posting,
)
from app.models.job import JobAnalysis, JobPosting
from app.portals import registry
from app.services.ranking import heuristic_score

logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURACIÓN GROQ
# ============================================================

# Tiempo inicial cuando Groq responde RateLimit.
GROQ_INITIAL_RETRY_DELAY = 5

# Máximo de reintentos después de un RateLimit.
GROQ_MAX_RETRIES = 4

# Backoff:
#
# intento 1 -> 5 segundos
# intento 2 -> 10 segundos
# intento 3 -> 20 segundos
# intento 4 -> 40 segundos
#
GROQ_BACKOFF_MULTIPLIER = 2

# Pausa normal entre análisis exitosos.
#
# Esto ayuda a no bombardear Groq.
GROQ_DELAY_SECONDS = 2.0


# ============================================================
# MODELOS
# ============================================================


@dataclass
class RankedJob:
    job_id: int
    job: JobPosting
    analysis: JobAnalysis | None
    heuristic: int


@dataclass
class SearchResult:
    sought: int = 0
    new_jobs: list[RankedJob] = field(
        default_factory=list
    )
    portal_errors: dict[str, str] = field(
        default_factory=dict
    )
    portals_used: list[str] = field(
        default_factory=list
    )


# ============================================================
# SERVICIO
# ============================================================


class SearchService:

    def __init__(
        self,
        db: Database,
        cv_manager: CVManager,
        groq: GroqClient | None,
        browser: BrowserManager,
    ):
        self._db = db
        self._cv = cv_manager
        self._groq = groq
        self._browser = browser

    # ========================================================
    # PORTALES
    # ========================================================

    def _active_portals(
        self,
        user_id: int,
    ) -> list:

        repo = PortalRepository(
            self._db
        )

        repo.ensure_defaults(
            user_id,
            registry.portal_names(),
            demo_enabled=registry.DEFAULT_ENABLED,
        )

        portals = []

        for name in repo.enabled_names(
            user_id
        ):

            portal = registry.create_portal(
                name
            )

            if portal is not None:
                portals.append(
                    portal
                )

        return portals

    # ========================================================
    # BUSCAR UN PORTAL
    # ========================================================

    @staticmethod
    async def _search_one(
        portal,
        browser,
        preferences,
    ) -> list[JobPosting]:

        return await portal.search(
            browser,
            preferences,
        )

    # ========================================================
    # COLECTAR OFERTAS
    # ========================================================

    async def _collect(
        self,
        portals,
        preferences,
    ) -> tuple[
        list[JobPosting],
        dict[str, str],
    ]:

        tasks = [
            self._search_one(
                portal,
                self._browser,
                preferences,
            )
            for portal in portals
        ]

        outcomes = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        jobs: list[JobPosting] = []

        errors: dict[str, str] = {}

        for portal, outcome in zip(
            portals,
            outcomes,
        ):

            # ------------------------------------------------
            # CAPTCHA
            # ------------------------------------------------

            if isinstance(
                outcome,
                HumanInterventionRequired,
            ):

                errors[
                    portal.name
                ] = "captcha"

                logger.warning(
                    "⚠️ %s pide intervención humana: %s",
                    portal.name,
                    outcome,
                )

            # ------------------------------------------------
            # BROWSER
            # ------------------------------------------------

            elif isinstance(
                outcome,
                BrowserUnavailableError,
            ):

                errors[
                    portal.name
                ] = "browser"

                logger.error(
                    "❌ %s: navegador no disponible: %s",
                    portal.name,
                    outcome,
                )

            # ------------------------------------------------
            # ERROR GENERAL
            # ------------------------------------------------

            elif isinstance(
                outcome,
                Exception,
            ):

                errors[
                    portal.name
                ] = "scraper_error"

                logger.error(
                    "❌ %s falló durante la búsqueda.",
                    portal.name,
                    exc_info=(
                        type(outcome),
                        outcome,
                        outcome.__traceback__,
                    ),
                )

            # ------------------------------------------------
            # CORRECTO
            # ------------------------------------------------

            else:

                logger.info(
                    "✅ %s encontró %d ofertas.",
                    portal.name,
                    len(outcome),
                )

                jobs.extend(
                    outcome
                )

        return jobs, errors

    # ========================================================
    # OBTENER DESCRIPCIÓN
    # ========================================================

    async def _enrich_job_description(
        self,
        portal,
        job_id: int,
        job: JobPosting,
    ) -> JobPosting:

        # ----------------------------------------------------
        # Ya tenemos descripción
        # ----------------------------------------------------

        if job.description:

            return job

        # ----------------------------------------------------
        # No hay URL
        # ----------------------------------------------------

        if not job.url:

            logger.warning(
                "⚠️ Job %s no tiene URL para obtener descripción.",
                job_id,
            )

            return job

        try:

            logger.info(
                "📄 Entrando al anuncio: %s | %s",
                portal.name,
                job.title,
            )

            description = (
                await portal.fetch_description(
                    self._browser,
                    job,
                )
            )

            if description:

                job.description = (
                    description.strip()
                )

                JobRepository(
                    self._db
                ).update_description(
                    job_id,
                    job.description,
                )

                logger.info(
                    "✅ Descripción obtenida "
                    "para job %s (%d caracteres).",
                    job_id,
                    len(job.description),
                )

            else:

                logger.warning(
                    "⚠️ No se obtuvo descripción "
                    "para job %s.",
                    job_id,
                )

        except HumanInterventionRequired:

            logger.warning(
                "⚠️ %s requiere intervención humana "
                "para leer: %s",
                portal.name,
                job.title,
            )

        except Exception as exc:

            logger.warning(
                "⚠️ No se pudo obtener descripción "
                "del job %s: %s",
                job_id,
                type(exc).__name__,
            )

        return job

    # ========================================================
    # ANÁLISIS DIRECTO CON GROQ
    # ========================================================

    async def _analyze_once(
        self,
        user_id: int,
        job_id: int,
    ) -> JobAnalysis | None:

        repo = JobRepository(
            self._db
        )

        row = repo.get(
            job_id,
            user_id,
        )

        if not row:

            logger.warning(
                "⚠️ No se encontró job %s.",
                job_id,
            )

            return None

        # ----------------------------------------------------
        # Revisar análisis existente
        # ----------------------------------------------------

        cached = job_row_to_analysis(
            row
        )

        if (
            cached
            and row["status"] != "FOUND"
        ):

            logger.info(
                "♻️ Reutilizando análisis existente "
                "para job %s.",
                job_id,
            )

            return cached

        # ----------------------------------------------------
        # Groq no configurado
        # ----------------------------------------------------

        if self._groq is None:

            logger.warning(
                "⚠️ Groq no está configurado."
            )

            return None

        job = job_row_to_posting(
            row
        )

        preferences = (
            UserRepository(
                self._db
            ).get_preferences(
                user_id
            )
        )

        # ----------------------------------------------------
        # Información del job
        # ----------------------------------------------------

        logger.info(
            "🤖 Groq analizando "
            "job=%s | puesto=%s | empresa=%s",
            job_id,
            job.title,
            job.company or "—",
        )

        # ----------------------------------------------------
        # Llamada a Groq
        # ----------------------------------------------------

        analysis = await job_analyzer.analyze_job(
            self._groq,
            job,
            self._cv.raw_text(),
            (
                preferences.to_dict()
                if preferences
                else None
            ),
        )

        # ----------------------------------------------------
        # Guardar
        # ----------------------------------------------------

        repo.update_analysis(
            job_id,
            analysis,
        )

        logger.info(
            "✅ Groq terminó "
            "job=%s | score=%d/100 | %s",
            job_id,
            analysis.score,
            analysis.recommendation,
        )

        return analysis

    # ========================================================
    # ANÁLISIS CON RETRY
    # ========================================================

    async def _analyze_with_retry(
        self,
        user_id: int,
        job_id: int,
    ) -> JobAnalysis | None:

        # ----------------------------------------------------
        # Intentos
        # ----------------------------------------------------

        for attempt in range(
            GROQ_MAX_RETRIES + 1
        ):

            try:

                return await self._analyze_once(
                    user_id,
                    job_id,
                )

            # ------------------------------------------------
            # RATE LIMIT
            # ------------------------------------------------

            except Exception as exc:

                error_name = type(
                    exc
                ).__name__

                error_text = str(
                    exc
                ).lower()

                is_rate_limit = (
                    error_name
                    == "RateLimitError"
                    or "rate limit"
                    in error_text
                    or "429"
                    in error_text
                    or "too many requests"
                    in error_text
                )

                if not is_rate_limit:

                    logger.error(
                        "❌ Error de Groq "
                        "analizando job %s: %s",
                        job_id,
                        error_name,
                        exc_info=True,
                    )

                    return None

                # ------------------------------------------------
                # Último intento
                # ------------------------------------------------

                if attempt >= GROQ_MAX_RETRIES:

                    logger.error(
                        "❌ RateLimit persistente "
                        "para job %s después de %d reintentos.",
                        job_id,
                        GROQ_MAX_RETRIES,
                    )

                    return None

                # ------------------------------------------------
                # BACKOFF
                # ------------------------------------------------

                delay = (
                    GROQ_INITIAL_RETRY_DELAY
                    * (
                        GROQ_BACKOFF_MULTIPLIER
                        ** attempt
                    )
                )

                logger.warning(
                    "⏳ RateLimit de Groq "
                    "para job %s. "
                    "Reintento %d/%d en %d segundos...",
                    job_id,
                    attempt + 1,
                    GROQ_MAX_RETRIES,
                    delay,
                )

                await asyncio.sleep(
                    delay
                )

        return None

    # ========================================================
    # API PÚBLICA DE ANÁLISIS
    # ========================================================

    async def analyze(
        self,
        user_id: int,
        job_id: int,
    ) -> JobAnalysis | None:

        """
        Analiza una oferta concreta.

        Si Groq devuelve RateLimitError,
        se aplica retry/backoff automáticamente.
        """

        return await self._analyze_with_retry(
            user_id,
            job_id,
        )

    # ========================================================
    # BÚSQUEDA COMPLETA
    # ========================================================

    async def search_for_user(
        self,
        user_id: int,
    ) -> SearchResult:

        user_repo = UserRepository(
            self._db
        )

        preferences = (
            user_repo.get_preferences(
                user_id
            )
        )

        result = SearchResult()

        # ====================================================
        # PORTALES ACTIVOS
        # ====================================================

        portals = self._active_portals(
            user_id
        )

        if not portals:

            logger.warning(
                "⚠️ No hay portales activos "
                "para usuario %s",
                user_id,
            )

            return result

        result.portals_used = [
            portal.name
            for portal in portals
        ]

        logger.info(
            "🌐 Portales activos: %s",
            ", ".join(
                result.portals_used
            ),
        )

        # ====================================================
        # PREFERENCIAS DE BÚSQUEDA
        # ====================================================

        search_preferences = (
            preferences
            or type(
                "P",
                (),
                {
                    "positions": [],
                    "locations": [],
                },
            )()
        )

        # ====================================================
        # BUSCAR
        # ====================================================

        logger.info(
            "🔎 Iniciando búsqueda "
            "para usuario %s...",
            user_id,
        )

        raw_jobs, errors = (
            await self._collect(
                portals,
                search_preferences,
            )
        )

        result.portal_errors = errors

        result.sought = len(
            raw_jobs
        )

        logger.info(
            "🔎 Ofertas encontradas: %d",
            result.sought,
        )

        # ====================================================
        # DESDUPLICAR
        # ====================================================

        job_repo = JobRepository(
            self._db
        )

        seen: set[str] = set()

        new: list[
            tuple[int, JobPosting]
        ] = []

        for job in raw_jobs:

            key = job.dedupe_key()

            if key in seen:

                continue

            seen.add(
                key
            )

            job_id = job_repo.add_job(
                user_id,
                job,
            )

            if job_id is not None:

                new.append(
                    (
                        job_id,
                        job,
                    )
                )

        logger.info(
            "💾 Ofertas nuevas: %d",
            len(new),
        )

        # ====================================================
        # MAPA DE PORTALES
        # ====================================================

        portal_map = {
            portal.name: portal
            for portal in portals
        }

        # ====================================================
        # OBTENER DESCRIPCIONES
        # ====================================================

        enriched: list[
            tuple[int, JobPosting]
        ] = []

        total_new = len(
            new
        )

        for position, (
            job_id,
            job,
        ) in enumerate(
            new,
            start=1,
        ):

            logger.info(
                "📄 Descripción %d/%d | %s | %s",
                position,
                total_new,
                job.title,
                job.company or "—",
            )

            portal = portal_map.get(
                job.portal
            )

            if portal is not None:

                job = (
                    await self._enrich_job_description(
                        portal,
                        job_id,
                        job,
                    )
                )

            enriched.append(
                (
                    job_id,
                    job,
                )
            )

        # ====================================================
        # PREFERENCIAS PARA HEURÍSTICA
        # ====================================================

        prefs = (
            preferences
            or type(
                "P",
                (),
                {
                    "positions": [],
                    "locations": [],
                    "modalities": [],
                    "job_type": "Cualquiera",
                    "min_salary": None,
                },
            )()
        )

        # ====================================================
        # RANKING INICIAL
        # ====================================================

        scored = sorted(
            (
                (
                    job_id,
                    job,
                    heuristic_score(
                        job,
                        prefs,
                    ),
                )
                for job_id, job in enriched
            ),
            key=lambda item: item[2],
            reverse=True,
        )

        # ====================================================
        # ANALIZAR TODAS CON GROQ
        # ====================================================

        analyzed_jobs: list[
            RankedJob
        ] = []

        total = len(
            scored
        )

        for position, (
            job_id,
            job,
            heuristic,
        ) in enumerate(
            scored,
            start=1,
        ):

            logger.info(
                "🤖 IA %d/%d | %s | %s",
                position,
                total,
                job.title,
                job.company or "—",
            )

            analysis = None

            if self._groq is not None:

                analysis = (
                    await self._analyze_with_retry(
                        user_id,
                        job_id,
                    )
                )

                # ------------------------------------------------
                # Pausa normal después del análisis.
                #
                # Si hubo RateLimit, el retry ya esperó.
                # ------------------------------------------------

                if (
                    position < total
                ):

                    await asyncio.sleep(
                        GROQ_DELAY_SECONDS
                    )

            analyzed_jobs.append(
                RankedJob(
                    job_id=job_id,
                    job=job,
                    analysis=analysis,
                    heuristic=heuristic,
                )
            )

        # ====================================================
        # ORDEN FINAL
        # ====================================================

        analyzed_jobs.sort(
            key=lambda item: (
                (
                    item.analysis.score
                    if item.analysis is not None
                    else -1
                ),
                item.heuristic,
            ),
            reverse=True,
        )

        result.new_jobs = (
            analyzed_jobs
        )

        # ====================================================
        # ESTADÍSTICAS
        # ====================================================

        analyzed_count = sum(
            1
            for item in result.new_jobs
            if item.analysis is not None
        )

        failed_count = (
            len(result.new_jobs)
            - analyzed_count
        )

        logger.info(
            "=================================================="
        )

        logger.info(
            "🔎 BÚSQUEDA FINALIZADA"
        )

        logger.info(
            "Ofertas encontradas: %d",
            result.sought,
        )

        logger.info(
            "Ofertas nuevas: %d",
            len(result.new_jobs),
        )

        logger.info(
            "Ofertas analizadas por Groq: %d",
            analyzed_count,
        )

        logger.info(
            "Ofertas sin análisis: %d",
            failed_count,
        )

        if errors:

            logger.info(
                "Errores de portales: %s",
                errors,
            )

        logger.info(
            "=================================================="
        )

        return result

    # ========================================================
    # OFERTAS GUARDADAS
    # ========================================================

    def ranked_saved_jobs(
        self,
        user_id: int,
        limit: int = 25,
    ) -> list[RankedJob]:

        """
        Devuelve ofertas guardadas con su análisis,
        ordenadas por score IA.
        """

        job_repo = JobRepository(
            self._db
        )

        rows = job_repo.list_for_user(
            user_id,
            limit=limit,
        )

        ranked: list[
            RankedJob
        ] = []

        for row in rows:

            ranked.append(
                RankedJob(
                    job_id=row["id"],
                    job=job_row_to_posting(
                        row
                    ),
                    analysis=job_row_to_analysis(
                        row
                    ),
                    heuristic=0,
                )
            )

        ranked.sort(
            key=lambda item: (
                item.analysis.score
                if item.analysis
                else -1
            ),
            reverse=True,
        )

        return ranked