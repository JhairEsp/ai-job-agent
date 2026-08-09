"""Configuración central de la aplicación.

Toda la configuración se carga desde variables de entorno (archivo .env).
Nunca incluir secretos directamente en el código.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


@dataclass(frozen=True)
class Settings:
    """Configuración inmutable de la aplicación, cargada una sola vez."""

    telegram_bot_token: str | None = None
    groq_api_key: str | None = None
    groq_model: str = DEFAULT_GROQ_MODEL
    environment: str = "development"
    base_dir: Path = BASE_DIR

    # ------------------------------------------------------------------ paths
    @property
    def data_dir(self) -> Path:
        return self.base_dir / "data"

    @property
    def cv_path(self) -> Path:
        return self.data_dir / "profile" / "cv.md"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "ai_job_agent.db"

    @property
    def browser_profiles_dir(self) -> Path:
        return self.data_dir / "browser_profiles"

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def applications_dir(self) -> Path:
        return self.data_dir / "applications"

    @property
    def logs_dir(self) -> Path:
        return self.base_dir / "logs"

    @property
    def prompts_dir(self) -> Path:
        return self.base_dir / "prompts"

    # ------------------------------------------------------------- utilidades
    @property
    def has_groq(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def masked_groq_key(self) -> str:
        """Versión enmascarada de la API key, segura para mostrar en logs/UI."""
        if not self.groq_api_key:
            return "no configurada"
        key = self.groq_api_key
        if len(key) <= 12:
            return "••••••••"
        return f"{key[:6]}…{key[-4:]}"

    @property
    def masked_telegram_token(self) -> str:
        if not self.telegram_bot_token:
            return "no configurado"
        token = self.telegram_bot_token
        if len(token) <= 12:
            return "••••••••"
        return f"{token[:6]}…{token[-4:]}"

    def missing_required(self) -> list[str]:
        """Variables imprescindibles para arrancar el bot."""
        errors: list[str] = []
        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN no está definido en el archivo .env")
        return errors

    @classmethod
    def load(cls, base_dir: Path | None = None) -> "Settings":
        """Carga la configuración desde `.env` y variables de entorno."""
        base = base_dir or BASE_DIR
        load_dotenv(base / ".env")
        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
            groq_api_key=os.getenv("GROQ_API_KEY") or None,
            groq_model=os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL),
            environment=os.getenv("ENVIRONMENT", "development"),
            base_dir=base,
        )


def ensure_directories(settings: Settings) -> None:
    """Crea la estructura de directorios de datos si no existe."""
    for directory in (
        settings.data_dir,
        settings.data_dir / "profile",
        settings.browser_profiles_dir,
        settings.jobs_dir,
        settings.applications_dir,
        settings.logs_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
