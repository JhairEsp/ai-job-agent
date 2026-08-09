"""Handlers comunes: menú principal, ayuda y enrutado de secciones."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import keyboards, menu, messages
from app.bot.handlers import applications as applications_handler
from app.bot.handlers import portals as portals_handler
from app.bot.handlers import search as search_handler


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_html(
        messages.HELP_TEXT, reply_markup=keyboards.back_to_menu()
    )


async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Despacha los botones simples del menú principal."""
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]

    if action == "home":
        await menu.show_main_menu(update, context)
    elif action == "help":
        await query.edit_message_text(
            messages.HELP_TEXT, parse_mode="HTML", reply_markup=keyboards.back_to_menu()
        )
    elif action in ("search", "jobs"):
        await search_handler.run_search(update, context)
    elif action == "applications":
        await applications_handler.list_applications(update, context)
    elif action == "portals":
        await portals_handler.show_portals(update, context)
