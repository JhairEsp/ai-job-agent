"""AI Job Agent — punto de entrada de la aplicación.

Uso:
    python main.py
"""
from __future__ import annotations

import sys

from app.ai.groq_client import GroqClient
from app.bot.bot import build_bot
from app.browser.session_manager import BrowserManager
from app.config import Settings, ensure_directories
from app.cv.cv_manager import CVManager
from app.database.db import Database
from app.services.search_service import SearchService
from app.utils.logger import setup_logging


def create_application(settings: Settings):
    """Ensambla las dependencias y construye la aplicación de Telegram."""
    ensure_directories(settings)

    db = Database(settings.db_path)
    db.init()

    cv_manager = CVManager(settings.cv_path)
    if not cv_manager.exists():
        # Plantilla mínima para que el usuario la complete a mano.
        cv_manager.cv_path.parent.mkdir(parents=True, exist_ok=True)
        cv_manager.cv_path.write_text(
            "# Tu Nombre\n\n## Perfil\n\nCompleta este archivo con tu información profesional.\n",
            encoding="utf-8",
        )

    groq_client = (
        GroqClient(api_key=settings.groq_api_key, model=settings.groq_model)
        if settings.has_groq
        else None
    )

    browser = BrowserManager(settings.browser_profiles_dir)
    search_service = SearchService(db, cv_manager, groq_client, browser)

    return build_bot(settings, db, cv_manager, groq_client, browser, search_service)


def main() -> int:
    settings = Settings.load()
    ensure_directories(settings)
    logger = setup_logging(settings.logs_dir)

    missing = settings.missing_required()
    if missing:
        for error in missing:
            logger.error("%s", error)
        logger.error(
            "Copia .env.example a .env, completa los valores y vuelve a intentar."
        )
        return 1

    if not settings.has_groq:
        logger.warning(
            "GROQ_API_KEY no configurada: las funciones de IA estarán deshabilitadas."
        )

    application = create_application(settings)
    logger.info("🤖 AI Job Agent iniciado. Esperando mensajes en Telegram…")
    application.run_polling(drop_pending_updates=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
