import os
from pathlib import Path

from app.config import Settings


def test_load_reads_env_file(tmp_path: Path, monkeypatch):
    (tmp_path / ".env").write_text(
        "TELEGRAM_BOT_TOKEN=123456:abc\nGROQ_API_KEY=gsk_test_key_1234567890\n",
        encoding="utf-8",
    )
    for var in ("TELEGRAM_BOT_TOKEN", "GROQ_API_KEY", "GROQ_MODEL", "ENVIRONMENT"):
        monkeypatch.delenv(var, raising=False)

    settings = Settings.load(base_dir=tmp_path)

    assert settings.telegram_bot_token == "123456:abc"
    assert settings.groq_api_key == "gsk_test_key_1234567890"
    assert settings.groq_model == "llama-3.3-70b-versatile"
    assert settings.missing_required() == []


def test_missing_token_is_reported(tmp_path: Path, monkeypatch):
    for var in ("TELEGRAM_BOT_TOKEN", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    settings = Settings.load(base_dir=tmp_path)
    assert any("TELEGRAM_BOT_TOKEN" in e for e in settings.missing_required())
    assert not settings.has_groq


def test_masked_keys_never_expose_full_secret():
    settings = Settings(
        telegram_bot_token="123456789:super-secret-token-value",
        groq_api_key="gsk_1234567890abcdefghijklmnop",
    )
    assert "super-secret" not in settings.masked_telegram_token
    assert "1234567890abcdef" not in settings.masked_groq_key
    assert settings.masked_groq_key.startswith("gsk_12")

    empty = Settings()
    assert empty.masked_groq_key == "no configurada"


def test_paths_derive_from_base_dir(tmp_path: Path):
    settings = Settings(base_dir=tmp_path)
    assert settings.cv_path == tmp_path / "data" / "profile" / "cv.md"
    assert str(os.fspath(settings.db_path)).endswith("data/ai_job_agent.db")
