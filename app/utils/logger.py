"""Configuración de logging.

Los logs nunca deben contener información sensible (tokens, API keys,
contraseñas). Cualquier excepción que pueda incluir credenciales debe
registrarse sanitizada.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(logs_dir: Path, level: int = logging.INFO) -> logging.Logger:
    """Configura logging a consola y archivo rotativo."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger()
    if logger.handlers:
        return logging.getLogger("ai_job_agent")
    logger.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(console)

    file_handler = RotatingFileHandler(
        logs_dir / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(file_handler)

    # Reducir ruido de librerías externas
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    return logging.getLogger("ai_job_agent")
