from pathlib import Path

from app.cv.cv_manager import CVManager

SAMPLE = """# Jhair Espinoza

## Perfil

Estudiante de Ingeniería de Sistemas.

## Skills

### Programación

- Python
- Java

### Bases de datos

- MySQL

## Idiomas

- Español
- Inglés
"""


def test_parse_extracts_title_and_sections(tmp_path: Path):
    cv_file = tmp_path / "cv.md"
    cv_file.write_text(SAMPLE, encoding="utf-8")
    manager = CVManager(cv_file)

    cv = manager.parse()

    assert cv.title == "Jhair Espinoza"
    assert {s.name for s in cv.sections} >= {"Perfil", "Skills", "Idiomas"}
    assert cv.to_dict()["sections"]


def test_bullets_collect_only_list_items(tmp_path: Path):
    cv_file = tmp_path / "cv.md"
    cv_file.write_text(SAMPLE, encoding="utf-8")
    manager = CVManager(cv_file)
    cv = manager.parse()

    assert cv.bullets("programación") == ["Python", "Java"]
    assert cv.bullets("idiomas") == ["Español", "Inglés"]


def test_missing_cv_is_handled_gracefully(tmp_path: Path):
    manager = CVManager(tmp_path / "no-existe.md")
    assert not manager.exists()
    assert manager.raw_text() == ""
    assert "No se encontró" in manager.summary()


def test_summary_reports_counts(tmp_path: Path):
    cv_file = tmp_path / "cv.md"
    cv_file.write_text(SAMPLE, encoding="utf-8")
    summary = CVManager(cv_file).summary()

    assert "Jhair Espinoza" in summary
    assert "Idiomas: Español, Inglés" in summary
