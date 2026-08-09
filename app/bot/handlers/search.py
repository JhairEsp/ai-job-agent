"""Handlers de búsqueda de ofertas y listado de jobs."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import job_views, keyboards
from app.portfolio_errors import PORTAL_ERROR_MESSAGES
from app.services.search_service import SearchResult

logger = logging.getLogger(__name__)

MAX_CARDS = 6


async def _send_result(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, markup=None) -> None:
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.effective_message.reply_html(text, reply_markup=markup)


async def run_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service = context.bot_data["search_service"]
    user_id = update.effective_user.id

    if update.callback_query:
        await update.callback_query.answer()
    await _send_result(update, context, "⏳ <b>Buscando ofertas en tus portales activos…</b>")

    result: SearchResult = await service.search_for_user(user_id)

    if not result.portals_used:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                "🌐 No tienes portales activos.\n\n"
                "Activa al menos uno en /portals para poder buscar."
            ),
            reply_markup=keyboards.back_to_menu(),
        )
        return

    if not result.new_jobs:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=_no_results_text(result),
            parse_mode="HTML",
            reply_markup=keyboards.back_to_menu(),
        )
        return

    top = sorted(
        result.new_jobs,
        key=lambda r: (r.analysis.score if r.analysis else -1, r.heuristic),
        reverse=True,
    )[:5]

    # Encabezado + detalle por oferta (cada una con sus botones).
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=_summary_text(result, job_views.top_matches_summary(top)),
        parse_mode="HTML",
        reply_markup=keyboards.back_to_menu(),
    )
    for ranked in top[:MAX_CARDS]:
        card, markup = job_views.job_card(
            ranked.job_id, ranked.job, ranked.analysis, heuristic=ranked.heuristic
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=card, parse_mode="HTML", reply_markup=markup
        )


def _summary_text(result: SearchResult, matches_block: str) -> str:
    portals = ", ".join(result.portals_used)
    errors_block = ""
    if result.portal_errors:
        details = "\n".join(
            f"• {name}: {PORTAL_ERROR_MESSAGES.get(code, code)}"
            for name, code in result.portal_errors.items()
        )
        errors_block = f"\n\n⚠️ <b>Portales con inconvenientes:</b>\n{details}"
    return (
        f"🔎 <b>BÚSQUEDA COMPLETADA</b>\n\n"
        f"Portales: {portals}\n"
        f"Ofertas revisadas: {result.sought}\n"
        f"Nuevas: {len(result.new_jobs)}"
        f"{errors_block}\n\n{matches_block}"
    )


def _no_results_text(result: SearchResult) -> str:
    errors_block = ""
    if result.portal_errors:
        details = "\n".join(
            f"• {name}: {PORTAL_ERROR_MESSAGES.get(code, code)}"
            for name, code in result.portal_errors.items()
        )
        errors_block = f"\n\n⚠️ Detalle:\n{details}"
    return (
        "🔎 <b>Búsqueda completada</b>\n\n"
        "No encontré ofertas nuevas con tus preferencias actuales. "
        "Prueba ajustar tus puestos o ubicaciones en ⚙️ Preferencias."
        f"{errors_block}"
    )


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_search(update, context)


async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista las ofertas guardadas/encontradas más recientes del usuario."""
    service = context.bot_data["search_service"]
    ranked = service.ranked_saved_jobs(update.effective_user.id, limit=8)
    if not ranked:
        await update.effective_message.reply_html(
            "💼 <b>Mis ofertas</b>\n\nTodavía no hay ofertas guardadas. "
            "Usa 🔎 <b>Buscar trabajos</b> para encontrarlas.",
            reply_markup=keyboards.back_to_menu(),
        )
        return
    await update.effective_message.reply_html(
        "💼 <b>MIS OFERTAS</b> (más recientes)", reply_markup=keyboards.back_to_menu()
    )
    for item in ranked[:6]:
        card, markup = job_views.job_card(item.job_id, item.job, item.analysis)
        await update.effective_message.reply_html(card, reply_markup=markup)
