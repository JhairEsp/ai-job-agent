"""Acciones rápidas sobre una oferta: 🤖 Analizar, ⭐ Guardar, ❌ Ignorar."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import job_views
from app.database.repositories import (
    JobRepository,
    job_row_to_analysis,
    job_row_to_posting,
)
from app.models.job import ApplicationStatus
from app.portals import registry

logger = logging.getLogger(__name__)


async def _load(context, job_id: int, user_id: int):
    repo = JobRepository(context.bot_data["db"])
    row = repo.get(job_id, user_id)
    if not row:
        return None, None, None
    return row, job_row_to_posting(row), job_row_to_analysis(row)


async def analyze_job_action(update: Update, context: ContextTypes.DEFAULT_TYPE, job_id: int) -> None:
    query = update.callback_query
    service = context.bot_data["search_service"]
    user_id = update.effective_user.id

    row, job, analysis = await _load(context, job_id, user_id)
    if row is None:
        await query.answer("Esta oferta ya no está disponible.", show_alert=True)
        return

    # Enriquecer con la descripción real si falta y hay navegador disponible.
    if not job.description and job.portal:
        browser = context.bot_data.get("browser")
        portal = registry.create_portal(job.portal)
        if portal is not None and browser is not None and browser.available:
            try:
                await query.answer("Leyendo la descripción de la oferta…")
                description = await portal.fetch_description(browser, job)
                if description:
                    JobRepository(context.bot_data["db"]).update_description(job_id, description)
                    job.description = description
            except Exception as exc:
                logger.info("No se pudo leer la descripción: %s", type(exc).__name__)

    if context.bot_data.get("groq") is None:
        await query.answer("La IA no está configurada (GROQ_API_KEY).", show_alert=True)
        return

    await query.answer("Analizando con IA…")
    analysis = await service.analyze(user_id, job_id)
    if analysis is None:
        await query.edit_message_text(
            "⚠️ No pude analizar esta oferta ahora. Inténtalo de nuevo más tarde.",
            parse_mode="HTML",
        )
        return

    repo = JobRepository(context.bot_data["db"])
    if row["status"] == ApplicationStatus.FOUND.value:
        repo.set_status(job_id, ApplicationStatus.ANALYZED)

    await query.edit_message_text(
        job_views.analysis_detail(job, analysis),
        parse_mode="HTML",
        reply_markup=job_views.job_keyboard(job_id, job, analyzed=True),
    )


async def save_job_action(update: Update, context: ContextTypes.DEFAULT_TYPE, job_id: int) -> None:
    query = update.callback_query
    JobRepository(context.bot_data["db"]).set_status(job_id, ApplicationStatus.SAVED)
    await query.answer("⭐ Oferta guardada en tu lista.")


async def ignore_job_action(update: Update, context: ContextTypes.DEFAULT_TYPE, job_id: int) -> None:
    query = update.callback_query
    JobRepository(context.bot_data["db"]).set_status(job_id, ApplicationStatus.IGNORED)
    await query.answer("🚫 Oferta ignorada.")
    try:
        await query.edit_message_text(
            f"🚫 <s>{query.message.text_html}</s>",
            parse_mode="HTML",
        )
    except Exception:
        pass


async def job_action_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Despacha job:<id>:<acción> (excepto apply, que vive en su conversación)."""
    data = update.callback_query.data
    _, job_id_str, action = data.split(":", 2)
    job_id = int(job_id_str)

    if action == "analyze":
        await analyze_job_action(update, context, job_id)
    elif action == "save":
        await save_job_action(update, context, job_id)
    elif action == "ignore":
        await ignore_job_action(update, context, job_id)
