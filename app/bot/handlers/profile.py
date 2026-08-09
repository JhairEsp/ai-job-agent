"""Visualización del perfil y de las preferencias del usuario."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import keyboards
from app.database.repositories import UserRepository

NO_PROFILE = (
    "👤 <b>Mi perfil</b>\n\n"
    "Aún no has configurado tu perfil.\nUsa /start para comenzar el registro."
)


def _profile_text(profile, preferences) -> str:
    return (
        "👤 <b>MI PERFIL</b>\n\n"
        f"• Nombre: <b>{profile.full_name}</b>\n"
        f"• Ubicación: {profile.location_label}\n\n"
        "🎯 <b>Preferencias laborales</b>\n"
        f"{preferences.summary()}"
    )


def _prefs_text(preferences) -> str:
    return f"⚙️ <b>MIS PREFERENCIAS</b>\n\n{preferences.summary()}"


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    repo = UserRepository(context.bot_data["db"])
    tg_id = update.effective_user.id
    profile = repo.get_profile(tg_id)
    preferences = repo.get_preferences(tg_id)

    if not profile:
        text, markup = NO_PROFILE, keyboards.back_to_menu()
    else:
        text = _profile_text(profile, preferences)
        markup = keyboards.profile_actions()

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=markup
        )
    else:
        await update.effective_message.reply_html(text, reply_markup=markup)


async def show_preferences(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    repo = UserRepository(context.bot_data["db"])
    preferences = repo.get_preferences(update.effective_user.id)
    text = (
        _prefs_text(preferences)
        if preferences
        else "⚙️ Aún no tienes preferencias configuradas. Usa /start."
    )
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=keyboards.preferences_actions()
    )
