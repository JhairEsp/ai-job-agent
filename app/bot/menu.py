"""Renderizado del menú principal."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import keyboards, messages
from app.database.repositories import UserRepository


def display_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Nombre del usuario: prioriza el perfil guardado sobre Telegram."""
    repo = UserRepository(context.bot_data["db"])
    profile = repo.get_profile(update.effective_user.id)
    if profile and profile.full_name:
        return profile.full_name
    return update.effective_user.first_name or "candidato"


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el menú principal, editando el mensaje si viene de un botón."""
    text = messages.MAIN_MENU.format(name=display_name(update, context))
    markup = keyboards.main_menu()
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=markup
        )
    else:
        await update.effective_message.reply_html(text, reply_markup=markup)
