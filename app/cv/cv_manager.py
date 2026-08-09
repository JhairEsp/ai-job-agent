"""Lectura y estructuración del CV del candidato.

El archivo `data/profile/cv.md` es la ÚNICA fuente de verdad sobre el
perfil profesional del usuario. La IA solo puede usar lo que exista aquí:
nunca se debe inventar experiencia, estudios, certificaciones ni skills.

REGLA: este módulo solo LEE el CV. La ÚNICA forma de modificar `cv.md`
es `replace_with_backup()` (usado exclusivamente cuando el usuario sube
su CV voluntariamente desde Telegram), que siempre crea un respaldo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


@dataclass
class CVSection:
    name: str
    level: int
    content: list[str] = field(default_factory=list)


@dataclass
class StructuredCV:
    """CV convertido a una estructura navegable (equivalente JSON interno)."""

    title: str = ""
    sections: list[CVSection] = field(default_factory=list)
    raw: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "sections": [
                {"name": s.name, "level": s.level, "content": list(s.content)}
                for s in self.sections
            ],
        }

    def find_sections(self, keyword: str) -> list[CVSection]:
        keyword = keyword.lower()
        return [s for s in self.sections if keyword in s.name.lower()]

    def bullets(self, section_keyword: str | None = None) -> list[str]:
        """Devuelve los ítems con viñeta (habilidades, idiomas, etc.)."""
        result: list[str] = []
        sections = (
            self.find_sections(section_keyword) if section_keyword else self.sections
        )
        for section in sections:
            for line in section.content:
                stripped = line.lstrip()
                if stripped.startswith(("- ", "• ", "* ")):
                    result.append(stripped[2:].strip())
        return result


class CVManager:
    """Gestor del CV. Solo lectura: jamás escribe sobre `cv.md`."""

    def __init__(self, cv_path: Path):
        self.cv_path = Path(cv_path)

    def exists(self) -> bool:
        return self.cv_path.exists()

    def replace_with_backup(self, content: str) -> Path | None:
        """Reemplaza el CV creando antes un respaldo (cv.md.bak).

        Solo se debe invocar con autorización explícita del usuario
        (por ejemplo, cuando sube su CV desde Telegram).
        Devuelve la ruta del respaldo, o None si no había CV previo.
        """
        backup: Path | None = None
        if self.exists() and self.raw_text().strip():
            backup = self.cv_path.with_name(self.cv_path.name + ".bak")
            backup.write_text(self.raw_text(), encoding="utf-8")
        self.cv_path.parent.mkdir(parents=True, exist_ok=True)
        self.cv_path.write_text(content, encoding="utf-8")
        return backup

    def raw_text(self) -> str:
        if not self.exists():
            return ""
        return self.cv_path.read_text(encoding="utf-8")

    def parse(self) -> StructuredCV:
        """Convierte el Markdown del CV a una estructura interna."""
        text = self.raw_text()
        structured = StructuredCV(raw=text)
        current: CVSection | None = None

        for line in text.splitlines():
            heading = _HEADING_RE.match(line)
            if heading:
                level = len(heading.group(1))
                name = heading.group(2).strip()
                if level == 1 and not structured.title:
                    structured.title = name
                    current = None
                    continue
                current = CVSection(name=name, level=level)
                structured.sections.append(current)
            elif line.strip():
                if current is None:
                    current = CVSection(name="_intro", level=2)
                    structured.sections.append(current)
                current.content.append(line.strip())

        return structured

    def summary(self) -> str:
        """Resumen corto y legible del CV para mostrar en Telegram."""
        if not self.exists():
            return "⚠️ No se encontró `data/profile/cv.md`."
        cv = self.parse()
        skills = cv.bullets("skill") or cv.bullets("programación")
        languages = cv.bullets("idioma")
        return (
            f"Título: {cv.title or '—'}\n"
            f"Secciones: {len(cv.sections)}\n"
            f"Habilidades detectadas: {len(skills)}\n"
            f"Idiomas: {', '.join(languages) if languages else '—'}"
        )
