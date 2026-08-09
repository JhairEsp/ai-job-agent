"""Servicio de búsqueda y análisis de ofertas.

Flujo:
1. Lee preferencias y portales activos del usuario.
2. Busca en paralelo en los portales (Playwright o fuente interna).
3. Desduplica y persiste las ofertas nuevas.
4. Ordena con heurística y envía las mejores N a Groq para su score.
5. Devuelve el ranking final para mostrarlo en Telegram.
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

ANALYZE_TOP_K = 8


@dataclass
class RankedJob:
    job_id: int
    job: JobPosting
    analysis: JobAnalysis | None
    heuristic: int


@dataclass
class SearchResult:
    sought: int = 0
    new_jobs: list[RankedJob] = field(default_factory=list)
    portal_errors: dict[str, str] = field(default_factory=dict)
    portals_used: list[str] = field(default_factory=list)


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

    # ---------------------------------------------------------------- portales
    def _active_portals(self, user_id: int) -> list:
        repo = PortalRepository(self._db)
        repo.ensure_defaults(user_id, registry.portal_names(), demo_enabled=registry.DEFAULT_ENABLED)
        portals = []
        for name in repo.enabled_names(user_id):
            portal = registry.create_portal(name)
            if portal is not None:
                portals.append(portal)
        return portals

    @staticmethod
    async def _search_one(portal, browser, preferences) -> list[JobPosting]:
        return await portal.search(browser, preferences)

    async def _collect(self, portals, preferences) -> tuple[list[JobPosting], dict[str, str]]:
        tasks = [self._search_one(p, self._browser, preferences) for p in portals]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        jobs: list[JobPosting] = []
        errors: dict[str, str] = {}
        for portal, outcome in zip(portals, outcomes):
            if isinstance(outcome, HumanInterventionRequired):
                errors[portal.name] = "captcha"
                logger.warning("%s pide intervención humana", portal.name)
            elif isinstance(outcome, BrowserUnavailableError):
                errors[portal.name] = "browser"
            elif isinstance(outcome, Exception):
                errors[portal.name] = type(outcome).__name__
                logger.warning("%s falló: %s", portal.name, type(outcome).__name__)
            else:
                jobs.extend(outcome)
        return jobs, errors

    # -------------------------------------------------------------- análisis
    async def analyze(self, user_id: int, job_id: int) -> JobAnalysis | None:
        """Analiza (o re-analiza) una oferta concreta con Groq y la persiste."""
        repo = JobRepository(self._db)
        row = repo.get(job_id, user_id)
        if not row:
            return None
        cached = job_row_to_analysis(row)
        if cached and row["status"] != "FOUND":
            return cached
        if self._groq is None:
            return None

        job = job_row_to_posting(row)
        preferences = UserRepository(self._db).get_preferences(user_id)
        try:
            analysis = await job_analyzer.analyze_job(
                self._groq,
                job,
                self._cv.raw_text(),
                preferences.to_dict() if preferences else None,
            )
        except (job_analyzer.AnalysisParseError, ValueError) as exc:
            logger.warning("Análisis inválido para job %s: %s", job_id, exc)
            return None
        repo.update_analysis(job_id, analysis)
        return analysis

    # -------------------------------------------------------------- búsqueda
    async def search_for_user(self, user_id: int) -> SearchResult:
        user_repo = UserRepository(self._db)
        preferences = user_repo.get_preferences(user_id)
        result = SearchResult()

        portals = self._active_portals(user_id)
        if not portals:
            return result
        result.portals_used = [p.name for p in portals]

        raw_jobs, errors = await self._collect(
            portals, preferences or type("P", (), {"positions": [], "locations": []})
        )
        result.portal_errors = errors
        result.sought = len(raw_jobs)

        # Desduplicar entre portales y persistir solo las nuevas.
        job_repo = JobRepository(self._db)
        seen: set[str] = set()
        new: list[tuple[int, JobPosting]] = []
        for job in raw_jobs:
            key = job.dedupe_key()
            if key in seen:
                continue
            seen.add(key)
            job_id = job_repo.add_job(user_id, job)
            if job_id is not None:
                new.append((job_id, job))

        # Ranking heurístico + análisis con IA de las mejores candidatas.
        prefs = preferences or type("P", (), {
            "positions": [], "locations": [], "modalities": [],
            "job_type": "Cualquiera", "min_salary": None,
        })
        scored = sorted(
            ((job_id, job, heuristic_score(job, prefs)) for job_id, job in new),
            key=lambda item: item[2],
            reverse=True,
        )
        for job_id, job, heuristic in scored[:ANALYZE_TOP_K]:
            analysis = None
            if self._groq is not None:
                analysis = await self.analyze(user_id, job_id)
            result.new_jobs.append(RankedJob(job_id, job, analysis, heuristic))
        for job_id, job, heuristic in scored[ANALYZE_TOP_K:]:
            result.new_jobs.append(RankedJob(job_id, job, None, heuristic))

        logger.info(
            "Búsqueda para %s: %d vistas, %d nuevas, errores: %s",
            user_id, result.sought, len(result.new_jobs), errors,
        )
        return result

    # ----------------------------------------------------------------- listas
    def ranked_saved_jobs(self, user_id: int, limit: int = 25) -> list[RankedJob]:
        """Todas las ofertas vigentes del usuario (score IA si existe)."""
        job_repo = JobRepository(self._db)
        rows = job_repo.list_for_user(user_id, limit=limit)
        ranked: list[RankedJob] = []
        for row in rows:
            ranked.append(
                RankedJob(
                    job_id=row["id"],
                    job=job_row_to_posting(row),
                    analysis=job_row_to_analysis(row),
                    heuristic=0,
                )
            )
        return ranked
