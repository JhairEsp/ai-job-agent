"""Configuración general: IA (Groq) y 🤖 AUTO SEARCH."""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.bot import keyboards
from app.database.repositories import UserRepository
from app.services import scheduler_service

logger = logging.getLogger(__name__)

AUTO_INTERVALS = [(0, "Manual"), (6, "Cada 6 h"), (12, "Cada 12 h"), (24, "Diario")]
AUTO_THRESHOLDS = [70, 80, 90]


def _ai_text(settings, status: str = "") -> str:
    groq_status = "🟢 API key configurada" if settings.has_groq else "🔴 API key no configurada"
    block = (
        "🤖 <b>CONFIGURACIÓN DE IA</b>\n\n"
        f"• Proveedor: <b>Groq</b>\n"
        f"• Modelo: <code>{settings.groq_model}</code>\n"
        f"• API key: <code>{settings.masked_groq_key}</code>\n"
        f"• Estado: {groq_status}"
    )
    if status:
        block += f"\n\n{status}"
    return block


def _settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔍 Probar conexión Groq", callback_data="ai:test")],
            [InlineKeyboardButton("🤖 AUTO SEARCH", callback_data="auto:show")],
            [InlineKeyboardButton("🎯 Editar preferencias", callback_data="prefs:edit")],
            [InlineKeyboardButton("🔙 Menú principal", callback_data="menu:home")],
        ]
    )


def _auto_text(preferences) -> str:
    return (
        "🤖 <b>AUTO SEARCH</b>\n\n"
        f"Frecuencia: <b>{preferences.auto_search_label}</b>\n"
        f"Notificar ofertas nuevas con match ≥ <b>{preferences.auto_search_min_score}%</b>\n\n"
        "El bot buscará automáticamente con tus preferencias y solo te "
        "avisará de los matches fuertes."
    )


def _auto_keyboard(preferences) -> InlineKeyboardMarkup:
    interval_row = []
    for hours, label in AUTO_INTERVALS:
        mark = "✅ " if preferences.auto_search_interval_hours == hours else ""
        interval_row.append(
            InlineKeyboardButton(f"{mark}{label}", callback_data=f"auto:hours:{hours}")
        )
    threshold_row = []
    for score in AUTO_THRESHOLDS:
        mark = "✅ " if preferences.auto_search_min_score == score else ""
        threshold_row.append(
            InlineKeyboardButton(f"{mark}≥ {score}", callback_data=f"auto:score:{score}")
        )
    return InlineKeyboardMarkup(
        [interval_row, threshold_row, [InlineKeyboardButton("🔙 Volver", callback_data="ai:show")]]
    )


def _get_preferences(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    repo = UserRepository(context.bot_data["db"])
    prefs = repo.get_preferences(user_id)
    if prefs is None:
        from app.models.profile import SearchPreferences

        prefs = SearchPreferences()
    return repo, prefs


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.bot_data["settings"]
    await update.effective_message.reply_html(
        _ai_text(settings), reply_markup=_settings_keyboard()
    )


async def show_ai_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.bot_data["settings"]
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        _ai_text(settings), parse_mode="HTML", reply_markup=_settings_keyboard()
    )


async def show_auto_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, prefs = _get_preferences(context, update.effective_user.id)
    await query.edit_message_text(
        _auto_text(prefs), parse_mode="HTML", reply_markup=_auto_keyboard(prefs)
    )


async def set_auto_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    repo, prefs = _get_preferences(context, update.effective_user.id)
    _, _, kind, raw_value = query.data.split(":", 3)
    value = int(raw_value)

    if kind == "hours":
        prefs.auto_search_interval_hours = value
        action = f"Frecuencia: {prefs.auto_search_label}"
    else:
        prefs.auto_search_min_score = value
        action = f"Umbral de match: ≥ {value}"

    repo.save_preferences(update.effective_user.id, prefs)
    scheduler_service.reschedule(context.application, update.effective_user.id, prefs.auto_search_interval_hours)
    await query.answer(f"✅ {action}")
    await query.edit_message_text(
        _auto_text(prefs), parse_mode="HTML", reply_markup=_auto_keyboard(prefs)
    )


async def test_groq_connection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.bot_data["settings"]
    client = context.bot_data.get("groq")
    query = update.callback_query

    if client is None:
        await query.answer("Groq no está configurado.", show_alert=True)
        await query.edit_message_text(
            _ai_text(settings, "❌ Define <code>GROQ_API_KEY</code> en tu archivo .env y reinicia."),
            parse_mode="HTML",
            reply_markup=_settings_keyboard(),
        )
        return

    await query.answer("Consultando a Groq…")
    try:
        health = await client.health_check()
    except Exception as exc:  # sin exponer secretos: solo tipo de error
        logger.warning("Falló el health check de Groq: %s", type(exc).__name__)
        await query.edit_message_text(
            _ai_text(settings, f"❌ Error de conexión: <code>{type(exc).__name__}</code>"),
            parse_mode="HTML",
            reply_markup=_settings_keyboard(),
        )
        return

    model_flag = "✅" if health["model_available"] else "⚠️"
    status = (
        f"✅ <b>Conexión exitosa con Groq.</b>\n"
        f"{model_flag} Modelo <code>{health['model']}</code> "
        f"{'disponible' if health['model_available'] else 'no listado'} "
        f"({health['models_count']} modelos disponibles)"
    )
    await query.edit_message_text(
        _ai_text(settings, status), parse_mode="HTML", reply_markup=_settings_keyboard()
    )
