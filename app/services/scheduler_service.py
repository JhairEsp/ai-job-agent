"""🤖 AUTO SEARCH: búsquedas programadas y notificaciones proactivas.

Usa el JobQueue de python-telegram-bot. Cuando una búsqueda automática
encuentra ofertas nuevas con match >= umbral del usuario, las notifica
con sus botones de acción.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from telegram.ext import Application

from app.database.repositories import UserRepository
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)

JOB_PREFIX = "auto-search-"


def _job_name(user_id: int) -> str:
    return f"{JOB_PREFIX}{user_id}"


def reschedule(app: Application, user_id: int, interval_hours: int) -> None:
    """Reprograma el auto-search de un usuario (0 = desactivado)."""
    if app.job_queue is None:
        logger.warning("JobQueue no disponible; auto-search desactivado.")
        return

    for job in app.job_queue.get_jobs_by_name(_job_name(user_id)):
        job.schedule_removal()

    if interval_hours <= 0:
        return

    app.job_queue.run_repeating(
        _auto_search_job,
        interval=timedelta(hours=interval_hours),
        first=timedelta(hours=interval_hours),
        name=_job_name(user_id),
        chat_id=user_id,
        data={"user_id": user_id},
    )
    logger.info("Auto-search programado para %s cada %s h", user_id, interval_hours)


async def _auto_search_job(context) -> None:
    user_id = context.job.data["user_id"]
    service: SearchService = context.application.bot_data["search_service"]
    repo = UserRepository(context.application.bot_data["db"])
    preferences = repo.get_preferences(user_id)
    if preferences is None or preferences.auto_search_interval_hours <= 0:
        return

    result = await service.search_for_user(user_id)
    threshold = preferences.auto_search_min_score
    strong = [
        r for r in result.new_jobs
        if r.analysis is not None and r.analysis.score >= threshold
    ][:5]
    if not strong:
        return

    from app.bot import job_views  # importación tardía (evita ciclo)

    for ranked in strong:
        text, markup = job_views.job_card(
            ranked.job_id, ranked.job, ranked.analysis, prefix="🔔 NUEVA OFERTA\n\n"
        )
        try:
            await context.bot.send_message(
                chat_id=user_id, text=text, parse_mode="HTML", reply_markup=markup
            )
        except Exception as exc:
            logger.warning("No pude notificar a %s: %s", user_id, type(exc).__name__)


def restore_schedules(app: Application) -> None:
    """Tras reiniciar el bot, reprograma el auto-search de todos los usuarios."""
    repo = UserRepository(app.bot_data["db"])
    for user_id in repo.get_all_user_ids():
        preferences = repo.get_preferences(user_id)
        if preferences and preferences.auto_search_interval_hours > 0:
            reschedule(app, user_id, preferences.auto_search_interval_hours)
