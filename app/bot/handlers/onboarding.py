"""Onboarding progresivo de nuevos usuarios.

Flujo conversacional (ConversationHandler):

    /start ──► nombre ──► ciudad ──► país ──► distrito
        ──► ubicaciones (multi) ──► puestos (multi) ──► salario mínimo
        ──► modalidad (multi) ──► jornada ──► ✅ listo

Puede reiniciarse desde "✏️ Editar perfil" o entrar solo a las
preferencias desde "🎯 Editar preferencias".
"""
from __future__ import annotations

import logging
import re

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot import keyboards, menu, messages
from app.database.repositories import UserRepository
from app.models.profile import SearchPreferences, UserProfile

logger = logging.getLogger(__name__)

(NAME, CITY, COUNTRY, DISTRICT, LOCATIONS, POSITIONS, SALARY, MODALITIES, JOB_TYPE) = range(9)

TEXT = filters.TEXT & ~filters.COMMAND

ASK_NAME = "👤 <b>Datos personales</b> — paso 1/4\n\n¿Cuál es tu <b>nombre completo</b>?"
ASK_CITY = "👤 <b>Datos personales</b> — paso 2/4\n\n¿En qué <b>ciudad</b> vives?"
ASK_COUNTRY = (
    "👤 <b>Datos personales</b> — paso 3/4\n\n¿En qué <b>país</b> vives?\n"
    "<i>Elige una opción o escribe otro país.</i>"
)
ASK_DISTRICT = (
    "👤 <b>Datos personales</b> — paso 4/4\n\n¿En qué <b>zona o distrito</b> vives?"
)

LOCATIONS_PROMPT = (
    "📍 <b>¿En qué ubicación quieres buscar trabajo?</b>\n\n"
    "Puedes elegir varias opciones o escribir otra ubicación.\n"
    "Cuando termines, toca <b>✔️ Continuar</b>."
)
POSITIONS_PROMPT = (
    "💼 <b>¿Qué puestos estás buscando?</b>\n\n"
    "Elige de la lista o escribe tu propio puesto.\n"
    "Cuando termines, toca <b>✔️ Continuar</b>."
)
SALARY_PROMPT = (
    "💰 <b>¿Cuál es tu salario mínimo esperado?</b>\n\n"
    "Elige una opción o toca <b>✏️ Personalizado</b> para escribir el monto."
)
MODALITY_PROMPT = (
    "🏠 <b>¿Qué modalidad prefieres?</b>\n\n"
    "Puedes elegir varias. Cuando termines, toca <b>✔️ Continuar</b>."
)
JOB_TYPE_PROMPT = "🕐 <b>¿Qué tipo de jornada buscas?</b>"


# ------------------------------------------------------------------ helpers
def _repo(context: ContextTypes.DEFAULT_TYPE) -> UserRepository:
    return UserRepository(context.bot_data["db"])


def _draft(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data.setdefault("draft_profile", {})


def _prefs(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data.setdefault(
        "draft_prefs",
        {
            "locations": [],
            "positions": [],
            "modalities": [],
            "min_salary": None,
            "salary_label": "Sin mínimo",
            "job_type": "Cualquiera",
        },
    )


def _toggle(options: list[str], option: str) -> None:
    if option in options:
        options.remove(option)
    else:
        options.append(option)


async def _next(update: Update, text: str, markup=None) -> None:
    """Avanza la conversación editando el mensaje (si hay callback) o respondiendo."""
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=markup
        )
    else:
        await update.effective_message.reply_html(text, reply_markup=markup)


# -------------------------------------------------------------- entry /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.effective_user
    repo = _repo(context)
    repo.upsert_user(tg_user.id, tg_user.username, tg_user.first_name)

    if repo.is_onboarded(tg_user.id):
        await menu.show_main_menu(update, context)
        return ConversationHandler.END

    context.user_data.pop("draft_profile", None)
    context.user_data.pop("draft_prefs", None)

    await update.effective_message.reply_html(messages.ONBOARDING_WELCOME)
    await update.effective_message.reply_html(ASK_NAME)
    return NAME


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("draft_profile", None)
    context.user_data.pop("draft_prefs", None)
    await update.effective_message.reply_html(
        "⏸ Configuración en pausa. Usa /start cuando quieras continuar."
    )
    return ConversationHandler.END


# ------------------------------------------------------------ datos personales
async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _draft(context)["full_name"] = update.message.text.strip()
    await update.message.reply_html(ASK_CITY)
    return CITY


async def receive_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _draft(context)["city"] = update.message.text.strip()
    await update.message.reply_html(ASK_COUNTRY, reply_markup=keyboards.country_keyboard())
    return COUNTRY


async def receive_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        _draft(context)["country"] = update.callback_query.data.split(":", 2)[2]
    else:
        _draft(context)["country"] = update.message.text.strip()
    await _next(update, ASK_DISTRICT, keyboards.skip_keyboard("ob:district"))
    return DISTRICT


async def receive_district(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        _draft(context)["district"] = ""
    else:
        _draft(context)["district"] = update.message.text.strip()
    prefs = _prefs(context)
    await _next(
        update,
        LOCATIONS_PROMPT,
        keyboards.multiselect_keyboard(keyboards.LOCATION_OPTIONS, prefs["locations"], prefix="ob:loc"),
    )
    return LOCATIONS


# ----------------------------------------------------------------- ubicaciones
async def toggle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 3)[2]
    prefs = _prefs(context)

    if action == "done":
        await query.edit_message_text(
            POSITIONS_PROMPT,
            parse_mode="HTML",
            reply_markup=keyboards.multiselect_keyboard(
                keyboards.POSITION_EXAMPLES, prefs["positions"], prefix="ob:pos"
            ),
        )
        return POSITIONS

    _toggle(prefs["locations"], query.data.split(":", 3)[3])
    await query.edit_message_reply_markup(
        reply_markup=keyboards.multiselect_keyboard(
            keyboards.LOCATION_OPTIONS, prefs["locations"], prefix="ob:loc"
        )
    )
    return LOCATIONS


async def custom_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    prefs = _prefs(context)
    value = update.message.text.strip()
    if value and value not in prefs["locations"]:
        prefs["locations"].append(value)
    await update.message.reply_html(
        f"➕ Ubicación agregada: <b>{value}</b>",
        reply_markup=keyboards.multiselect_keyboard(
            keyboards.LOCATION_OPTIONS, prefs["locations"], prefix="ob:loc"
        ),
    )
    return LOCATIONS


# --------------------------------------------------------------------- puestos
async def toggle_position(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 3)[2]
    prefs = _prefs(context)

    if action == "done":
        await query.edit_message_text(
            SALARY_PROMPT, parse_mode="HTML", reply_markup=keyboards.salary_keyboard()
        )
        return SALARY

    _toggle(prefs["positions"], query.data.split(":", 3)[3])
    await query.edit_message_reply_markup(
        reply_markup=keyboards.multiselect_keyboard(
            keyboards.POSITION_EXAMPLES, prefs["positions"], prefix="ob:pos"
        )
    )
    return POSITIONS


async def custom_position(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    prefs = _prefs(context)
    value = update.message.text.strip()
    if value and value not in prefs["positions"]:
        prefs["positions"].append(value)
    await update.message.reply_html(
        f"➕ Puesto agregado: <b>{value}</b>",
        reply_markup=keyboards.multiselect_keyboard(
            keyboards.POSITION_EXAMPLES, prefs["positions"], prefix="ob:pos"
        ),
    )
    return POSITIONS


# --------------------------------------------------------------------- salario
async def receive_salary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    prefs = _prefs(context)

    if query is not None:
        await query.answer()
        choice = query.data.split(":", 2)[2]
        if choice == "custom":
            await query.edit_message_text(
                "💰 Escribe tu salario mínimo esperado <b>solo el número en soles</b> "
                "(ejemplo: <code>1200</code>). Envía <code>0</code> si no tienes mínimo.",
                parse_mode="HTML",
            )
            return SALARY
        if choice == "none":
            prefs["min_salary"], prefs["salary_label"] = None, "Sin mínimo"
        else:
            prefs["min_salary"] = int(choice)
            prefs["salary_label"] = f"S/ {int(choice):,}".replace(",", " ")
    else:
        digits = re.sub(r"\D", "", update.message.text)
        amount = int(digits) if digits else 0
        prefs["min_salary"] = amount or None
        prefs["salary_label"] = f"S/ {amount:,}".replace(",", " ") if amount else "Sin mínimo"

    await _next(
        update,
        MODALITY_PROMPT,
        keyboards.multiselect_keyboard(keyboards.MODALITY_OPTIONS, prefs["modalities"], prefix="ob:mod"),
    )
    return MODALITIES


# ------------------------------------------------------------------- modalidad
async def toggle_modality(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 3)[2]
    prefs = _prefs(context)

    if action == "done":
        await query.edit_message_text(
            JOB_TYPE_PROMPT, parse_mode="HTML", reply_markup=keyboards.job_type_keyboard()
        )
        return JOB_TYPE

    _toggle(prefs["modalities"], query.data.split(":", 3)[3])
    await query.edit_message_reply_markup(
        reply_markup=keyboards.multiselect_keyboard(
            keyboards.MODALITY_OPTIONS, prefs["modalities"], prefix="ob:mod"
        )
    )
    return MODALITIES


# --------------------------------------------------------------------- jornada
async def receive_job_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    prefs = _prefs(context)
    prefs["job_type"] = query.data.split(":", 2)[2]

    tg_id = update.effective_user.id
    repo = _repo(context)
    profile = UserProfile.from_dict(_draft(context))
    preferences = SearchPreferences.from_dict(prefs)
    repo.save_profile(tg_id, profile)
    repo.save_preferences(tg_id, preferences)
    repo.set_onboarded(tg_id)
    logger.info("Onboarding completado para el usuario %s", tg_id)

    await query.edit_message_text(
        messages.ONBOARDING_DONE.format(
            name=profile.full_name,
            location=profile.location_label,
            prefs=preferences.summary(),
        ),
        parse_mode="HTML",
    )
    await query.message.reply_html(
        messages.MAIN_MENU.format(name=profile.full_name),
        reply_markup=keyboards.main_menu(),
    )
    context.user_data.pop("draft_profile", None)
    context.user_data.pop("draft_prefs", None)
    return ConversationHandler.END


# ------------------------------------------------------ edición posterior
async def edit_full_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Re-ejecuta el onboarding completo desde el principio."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("draft_profile", None)
    context.user_data.pop("draft_prefs", None)
    await query.edit_message_text(ASK_NAME, parse_mode="HTML")
    return NAME


async def edit_preferences(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entra al onboarding directamente en la sección de preferencias."""
    query = update.callback_query
    await query.answer()

    repo = _repo(context)
    current = repo.get_preferences(update.effective_user.id)
    if current:
        context.user_data["draft_prefs"] = current.to_dict()
    profile = repo.get_profile(update.effective_user.id)
    context.user_data["draft_profile"] = profile.to_dict() if profile else {}

    prefs = _prefs(context)
    await query.edit_message_text(
        LOCATIONS_PROMPT,
        parse_mode="HTML",
        reply_markup=keyboards.multiselect_keyboard(
            keyboards.LOCATION_OPTIONS, prefs["locations"], prefix="ob:loc"
        ),
    )
    return LOCATIONS


# -------------------------------------------------------------------- builder
def build_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(edit_full_profile, pattern=r"^profile:edit$"),
            CallbackQueryHandler(edit_preferences, pattern=r"^prefs:edit$"),
        ],
        states={
            NAME: [MessageHandler(TEXT, receive_name)],
            CITY: [MessageHandler(TEXT, receive_city)],
            COUNTRY: [
                CallbackQueryHandler(receive_country, pattern=r"^ob:country:"),
                MessageHandler(TEXT, receive_country),
            ],
            DISTRICT: [
                CallbackQueryHandler(receive_district, pattern=r"^ob:district:"),
                MessageHandler(TEXT, receive_district),
            ],
            LOCATIONS: [
                CallbackQueryHandler(toggle_location, pattern=r"^ob:loc:"),
                MessageHandler(TEXT, custom_location),
            ],
            POSITIONS: [
                CallbackQueryHandler(toggle_position, pattern=r"^ob:pos:"),
                MessageHandler(TEXT, custom_position),
            ],
            SALARY: [
                CallbackQueryHandler(receive_salary, pattern=r"^ob:sal:"),
                MessageHandler(TEXT, receive_salary),
            ],
            MODALITIES: [CallbackQueryHandler(toggle_modality, pattern=r"^ob:mod:")],
            JOB_TYPE: [CallbackQueryHandler(receive_job_type, pattern=r"^ob:job:")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )
