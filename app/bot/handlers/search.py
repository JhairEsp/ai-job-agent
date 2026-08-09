"""Handlers de búsqueda de ofertas y listado de jobs.

La búsqueda:
- muestra cuántas ofertas encontró;
- recibe el ranking generado por Groq;
- muestra primero las mejores coincidencias;
- cada tarjeta contiene puesto, empresa, ubicación, salario y match;
- no limita artificialmente la búsqueda a 6 resultados.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import job_views, keyboards
from app.portfolio_errors import PORTAL_ERROR_MESSAGES
from app.services.search_service import SearchResult

logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURACIÓN DE TELEGRAM
# ============================================================

# Score mínimo que consideramos una coincidencia útil.
#
# 90-100 = Excelente
# 80-89  = Muy buena
# 70-79  = Buena
#
# Las ofertas por debajo de 70 no se muestran en el bloque
# principal de recomendaciones.
#
# IMPORTANTE:
# La búsqueda NO está limitada a este número.
# Groq analiza todas.
MIN_RECOMMENDATION_SCORE = 70


# Máximo de mensajes de ofertas que Telegram enviará
# individualmente en una sola búsqueda.
#
# Esto es SOLO para evitar inundar Telegram.
#
# Si quieres absolutamente todas, puedes subirlo.
TELEGRAM_MAX_RESULTS = 30


# ============================================================
# UTILIDADES
# ============================================================

async def _send_result(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    markup=None,
) -> None:

    if update.callback_query:

        await update.callback_query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=markup,
        )

    else:

        await update.effective_message.reply_html(
            text,
            reply_markup=markup,
        )


def _analysis_score(ranked) -> int:
    if ranked.analysis is not None:
        return ranked.analysis.score

    return ranked.heuristic or 0


def _recommendations(
    result: SearchResult,
):
    """Devuelve las ofertas que realmente califican."""

    analyzed = [
        item
        for item in result.new_jobs
        if item.analysis is not None
    ]

    good = [
        item
        for item in analyzed
        if item.analysis.score
        >= MIN_RECOMMENDATION_SCORE
    ]

    return sorted(
        good,
        key=lambda item: (
            item.analysis.score,
            item.heuristic,
        ),
        reverse=True,
    )


# ============================================================
# /SEARCH
# ============================================================

async def run_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    service = context.bot_data[
        "search_service"
    ]

    user_id = (
        update.effective_user.id
    )

    # --------------------------------------------------------
    # ACK CALLBACK
    # --------------------------------------------------------

    if update.callback_query:

        await update.callback_query.answer()

    # --------------------------------------------------------
    # MENSAJE INICIAL
    # --------------------------------------------------------

    await _send_result(
        update,
        context,
        (
            "⏳ <b>Buscando ofertas...</b>\n\n"
            "🔎 Revisando tus portales.\n"
            "📄 Leyendo los anuncios.\n"
            "🤖 Después Groq analizará cada oferta "
            "contra tu CV.\n\n"
            "Esto puede tardar unos minutos si hay "
            "muchas ofertas."
        ),
    )

    # --------------------------------------------------------
    # BÚSQUEDA
    # --------------------------------------------------------

    result: SearchResult = (
        await service.search_for_user(
            user_id
        )
    )

    # --------------------------------------------------------
    # SIN PORTALES
    # --------------------------------------------------------

    if not result.portals_used:

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                "🌐 <b>No tienes portales activos.</b>\n\n"
                "Activa al menos uno desde /portals "
                "para poder buscar."
            ),
            parse_mode="HTML",
            reply_markup=keyboards.back_to_menu(),
        )

        return

    # --------------------------------------------------------
    # RECOMENDACIONES
    # --------------------------------------------------------

    recommendations = _recommendations(
        result
    )

    # --------------------------------------------------------
    # SI NO HAY BUENOS MATCHES
    # --------------------------------------------------------

    if not recommendations:

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=_no_results_text(
                result
            ),
            parse_mode="HTML",
            reply_markup=keyboards.back_to_menu(),
        )

        return

    # --------------------------------------------------------
    # RESUMEN
    # --------------------------------------------------------

    summary = _summary_text(
        result,
        recommendations,
    )

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=summary,
        parse_mode="HTML",
        reply_markup=keyboards.back_to_menu(),
    )

    # --------------------------------------------------------
    # TARJETAS
    # --------------------------------------------------------

    shown = 0

    for ranked in recommendations:

        if shown >= TELEGRAM_MAX_RESULTS:
            break

        card, markup = (
            job_views.job_card(
                ranked.job_id,
                ranked.job,
                ranked.analysis,
                heuristic=ranked.heuristic,
            )
        )

        try:

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=card,
                parse_mode="HTML",
                reply_markup=markup,
            )

            shown += 1

        except Exception as exc:

            logger.warning(
                "No se pudo enviar tarjeta "
                "del job %s: %s",
                ranked.job_id,
                type(exc).__name__,
            )

    # --------------------------------------------------------
    # AVISO SI HAY MÁS
    # --------------------------------------------------------

    if len(recommendations) > shown:

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                f"📚 Hay <b>{len(recommendations) - shown}</b> "
                "matches adicionales que no se enviaron "
                "para no saturar el chat.\n\n"
                "Puedes revisar tus ofertas desde /jobs."
            ),
            parse_mode="HTML",
            reply_markup=keyboards.back_to_menu(),
        )


# ============================================================
# RESUMEN
# ============================================================

def _summary_text(
    result: SearchResult,
    recommendations,
) -> str:

    portals = ", ".join(
        result.portals_used
    )

    analyzed_count = sum(
        1
        for item in result.new_jobs
        if item.analysis is not None
    )

    excellent = sum(
        1
        for item in recommendations
        if item.analysis
        and item.analysis.score >= 90
    )

    very_good = sum(
        1
        for item in recommendations
        if item.analysis
        and 80 <= item.analysis.score < 90
    )

    good = sum(
        1
        for item in recommendations
        if item.analysis
        and 70 <= item.analysis.score < 80
    )

    lines = [
        "🔎 <b>BÚSQUEDA COMPLETADA</b>",
        "",
        f"🌐 <b>Portales:</b> {portals}",
        f"📥 <b>Ofertas encontradas:</b> {result.sought}",
        f"🆕 <b>Ofertas nuevas:</b> {len(result.new_jobs)}",
        f"🤖 <b>Analizadas por IA:</b> {analyzed_count}",
        "",
        "🔥 <b>MATCHES ENCONTRADOS</b>",
        "",
        f"🟢 Excelente: <b>{excellent}</b>",
        f"🟡 Muy buena: <b>{very_good}</b>",
        f"🔵 Buena: <b>{good}</b>",
        "",
        f"📊 Mostrando ofertas con match ≥ "
        f"<b>{MIN_RECOMMENDATION_SCORE}%</b>",
    ]

    # --------------------------------------------------------
    # ERRORES
    # --------------------------------------------------------

    if result.portal_errors:

        details = "\n".join(
            (
                f"• {name}: "
                f"{PORTAL_ERROR_MESSAGES.get(code, code)}"
            )
            for name, code
            in result.portal_errors.items()
        )

        lines.extend(
            [
                "",
                "⚠️ <b>Portales con inconvenientes:</b>",
                details,
            ]
        )

    return "\n".join(
        lines
    )


# ============================================================
# SIN RESULTADOS
# ============================================================

def _no_results_text(
    result: SearchResult,
) -> str:

    analyzed_count = sum(
        1
        for item in result.new_jobs
        if item.analysis is not None
    )

    lines = [
        "🔎 <b>BÚSQUEDA COMPLETADA</b>",
        "",
        f"📥 Ofertas encontradas: "
        f"<b>{result.sought}</b>",
        f"🤖 Analizadas por IA: "
        f"<b>{analyzed_count}</b>",
        "",
        (
            "No encontré ofertas con una compatibilidad "
            f"de al menos <b>{MIN_RECOMMENDATION_SCORE}%</b> "
            "con tu perfil."
        ),
        "",
        (
            "Esto no significa que no existan ofertas. "
            "Significa que Groq determinó que las encontradas "
            "no son suficientemente compatibles con tu CV."
        ),
    ]

    if result.portal_errors:

        details = "\n".join(
            (
                f"• {name}: "
                f"{PORTAL_ERROR_MESSAGES.get(code, code)}"
            )
            for name, code
            in result.portal_errors.items()
        )

        lines.extend(
            [
                "",
                "⚠️ <b>Detalle:</b>",
                details,
            ]
        )

    return "\n".join(
        lines
    )


# ============================================================
# COMANDO SEARCH
# ============================================================

async def search_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    await run_search(
        update,
        context,
    )


# ============================================================
# /JOBS
# ============================================================

async def jobs_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    """Lista las ofertas guardadas/encontradas."""

    service = context.bot_data[
        "search_service"
    ]

    ranked = service.ranked_saved_jobs(
        update.effective_user.id,
        limit=30,
    )

    if not ranked:

        await update.effective_message.reply_html(
            (
                "💼 <b>MIS OFERTAS</b>\n\n"
                "Todavía no hay ofertas guardadas.\n\n"
                "Usa 🔎 <b>Buscar trabajos</b> "
                "para encontrarlas."
            ),
            reply_markup=keyboards.back_to_menu(),
        )

        return

    # --------------------------------------------------------
    # Ordenar por IA
    # --------------------------------------------------------

    ranked = sorted(
        ranked,
        key=lambda item: (
            item.analysis.score
            if item.analysis
            else -1
        ),
        reverse=True,
    )

    await update.effective_message.reply_html(
        (
            "💼 <b>MIS OFERTAS</b>\n\n"
            f"Encontradas: <b>{len(ranked)}</b>\n"
            "Ordenadas por compatibilidad IA."
        ),
        reply_markup=keyboards.back_to_menu(),
    )

    # --------------------------------------------------------
    # MOSTRAR
    # --------------------------------------------------------

    for item in ranked:

        card, markup = (
            job_views.job_card(
                item.job_id,
                item.job,
                item.analysis,
                heuristic=item.heuristic,
            )
        )

        try:

            await update.effective_message.reply_html(
                card,
                reply_markup=markup,
            )

        except Exception as exc:

            logger.warning(
                "No se pudo mostrar job %s: %s",
                item.job_id,
                type(exc).__name__,
            )