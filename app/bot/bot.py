"""Construcción de la aplicación de Telegram con todos los handlers."""
from __future__ import annotations

import logging

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.bot.handlers import (
    apply_flow,
    applications,
    chat,
    common,
    cv as cv_handler,
    cv_upload,
    job_actions,
    onboarding,
    portals,
    profile,
    search as search_handler,
    settings as settings_handler,
)
from app.database.repositories import UserRepository
from app.services import scheduler_service

logger = logging.getLogger(__name__)

STARTUP_MESSAGE = (
    "🟢 AI Job Agent está en línea.\n"
    "Escribe /start para abrir el menú principal."
)


async def _post_init(app: Application) -> None:
    """Al arrancar: avisar a usuarios conocidos y restaurar auto-searches."""
    repo = UserRepository(app.bot_data["db"])
    for user_id in repo.get_all_user_ids():
        try:
            await app.bot.send_message(chat_id=user_id, text=STARTUP_MESSAGE)
        except Exception as exc:  # usuario bloqueó el bot, chat inexistente, etc.
            logger.warning("No se pudo notificar a %s: %s", user_id, type(exc).__name__)
    scheduler_service.restore_schedules(app)


async def _post_shutdown(app: Application) -> None:
    browser = app.bot_data.get("browser")
    if browser is not None:
        await browser.stop()


def build_bot(settings, db, cv_manager, groq_client, browser, search_service) -> Application:
    """Crea y configura la Application de python-telegram-bot."""
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )

    # Dependencias compartidas, accesibles desde todos los handlers.
    app.bot_data["settings"] = settings
    app.bot_data["db"] = db
    app.bot_data["cv_manager"] = cv_manager
    app.bot_data["groq"] = groq_client
    app.bot_data["browser"] = browser
    app.bot_data["search_service"] = search_service

    # 1) Conversaciones guiadas (tienen prioridad sobre el chat libre).
    app.add_handler(onboarding.build_conversation())
    app.add_handler(cv_upload.build_conversation())
    app.add_handler(apply_flow.build_conversation())

    # 2) Comandos.
    app.add_handler(CommandHandler("help", common.help_command))
    app.add_handler(CommandHandler("profile", profile.show_profile))
    app.add_handler(CommandHandler("cv", cv_handler.show_cv))
    app.add_handler(CommandHandler("search", search_handler.run_search))
    app.add_handler(CommandHandler("jobs", search_handler.jobs_command))
    app.add_handler(CommandHandler("applications", applications.list_applications))
    app.add_handler(CommandHandler("portals", portals.show_portals))
    app.add_handler(CommandHandler("settings", settings_handler.settings_command))

    # 3) Botones inline.
    app.add_handler(CallbackQueryHandler(job_actions.job_action_router, pattern=r"^job:\d+:(analyze|save|ignore)$"))
    app.add_handler(CallbackQueryHandler(applications.change_status, pattern=r"^appst:"))
    app.add_handler(CallbackQueryHandler(portals.portal_router, pattern=r"^portal:"))
    app.add_handler(CallbackQueryHandler(common.menu_router, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(profile.show_profile, pattern=r"^profile:show$"))
    app.add_handler(CallbackQueryHandler(profile.show_preferences, pattern=r"^prefs:show$"))
    app.add_handler(CallbackQueryHandler(cv_handler.show_cv, pattern=r"^cv:show$"))
    app.add_handler(CallbackQueryHandler(cv_handler.show_full_cv, pattern=r"^cv:full$"))
    app.add_handler(CallbackQueryHandler(settings_handler.show_ai_settings, pattern=r"^ai:show$"))
    app.add_handler(CallbackQueryHandler(settings_handler.test_groq_connection, pattern=r"^ai:test$"))
    app.add_handler(CallbackQueryHandler(settings_handler.show_auto_search, pattern=r"^auto:show$"))
    app.add_handler(CallbackQueryHandler(settings_handler.set_auto_search, pattern=r"^auto:(hours|score):"))

    # 4) Chat libre con IA (último: solo si ningún handler anterior procesó).
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, chat.chat_with_assistant)
    )

    return app
