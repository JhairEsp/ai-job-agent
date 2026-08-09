"""Smoke test: la aplicación completa debe ensamblarse sin errores ni red."""
from pathlib import Path

import pytest

from app.config import Settings, ensure_directories
from main import create_application


def test_application_builds_with_dummy_credentials(tmp_path: Path):
    settings = Settings(
        telegram_bot_token="123456:dummy-token-for-tests",
        groq_api_key=None,
        base_dir=tmp_path,
    )
    ensure_directories(settings)

    app = create_application(settings)

    assert app.bot_data["settings"] is settings
    assert app.bot_data["db"] is not None
    assert app.bot_data["cv_manager"] is not None
    assert app.bot_data["groq"] is None  # sin API key → IA deshabilitada

    # La plantilla de CV se crea automáticamente si no existe.
    cv_file = tmp_path / "data" / "profile" / "cv.md"
    assert cv_file.exists()

    # La BD queda inicializada con todas las tablas del producto final.
    tables = {
        row[0]
        for row in app.bot_data["db"]
        .raw()
        .execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"users", "profile", "search_preferences", "portals", "jobs", "applications"} <= tables


def test_application_builds_with_groq_client(tmp_path: Path):
    from app.ai.groq_client import GroqClient

    settings = Settings(
        telegram_bot_token="123456:dummy-token-for-tests",
        groq_api_key="gsk_dummy_key_for_offline_tests",
        base_dir=tmp_path,
    )
    ensure_directories(settings)
    app = create_application(settings)
    assert isinstance(app.bot_data["groq"], GroqClient)


def test_groq_client_requires_api_key():
    with pytest.raises(ValueError):
        from app.ai.groq_client import GroqClient

        GroqClient(api_key="")
