"""Pruebas de las nuevas funciones: carga de CV y asistente conversacional."""
from pathlib import Path

from app.ai.assistant import Assistant
from app.cv.cv_manager import CVManager
from app.models.profile import SearchPreferences, UserProfile

OLD_CV = "# CV Antiguo\n\n## Skills\n\n- Python\n"
NEW_CV = "# Jhair Espinoza\n\n## Skills\n\n- Python\n- SQL\n"


def test_replace_with_backup_creates_bak(tmp_path: Path):
    cv_file = tmp_path / "cv.md"
    cv_file.write_text(OLD_CV, encoding="utf-8")
    manager = CVManager(cv_file)

    backup = manager.replace_with_backup(NEW_CV)

    assert backup is not None and backup.exists()
    assert backup.read_text(encoding="utf-8") == OLD_CV
    assert cv_file.read_text(encoding="utf-8") == NEW_CV
    # El resumen refleja el nuevo contenido.
    assert manager.parse().title == "Jhair Espinoza"


def test_replace_without_previous_cv_returns_none(tmp_path: Path):
    manager = CVManager(tmp_path / "cv.md")
    backup = manager.replace_with_backup(NEW_CV)
    assert backup is None
    assert manager.exists()


def test_assistant_context_uses_only_real_data():
    profile = UserProfile(full_name="Jhair Espinoza", city="Lima", country="Perú")
    prefs = SearchPreferences(locations=["Lima"], positions=["Practicante BI"])
    context = Assistant.build_context(profile, prefs, "Título: Jhair Espinoza")

    assert "Jhair Espinoza" in context
    assert "Practicante BI" in context
    # No se inyecta información inventada:
    assert "años de experiencia" not in context.lower()


def test_assistant_context_empty_when_no_profile():
    assert "aún no configura" in Assistant.build_context(None, None, "")


def test_history_trimming_keeps_recent_messages():
    history = [{"role": "user", "content": str(i)} for i in range(40)]
    trimmed = Assistant.trim_history(history)
    assert len(trimmed) == 24
    assert trimmed[0]["content"] == "16"  # se descartaron los más antiguos
