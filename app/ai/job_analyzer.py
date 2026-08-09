"""Análisis de ofertas de trabajo con Groq (score 0-100).

Contrato JSON documentado en prompts/analyze_job.txt. Reglas inviolables:
- La IA NO inventa experiencia, estudios, certificaciones, habilidades,
  salarios, empresas, puestos ni años de experiencia.
- Lo que no esté en cv.md se considera inexistente o desconocido.
- Las respuestas de postulación jamás mienten.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.ai.groq_client import GroqClient
from app.models.job import JobAnalysis, JobPosting

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

CLASSIFICATIONS = (
    (90, "Excelente"),
    (80, "Muy buena"),
    (70, "Buena"),
    (60, "Regular"),
    (0, "Baja"),
)

JOB_ANALYSIS_JSON_SCHEMA: dict[str, Any] = {
    "score": "int 0-100",
    "recommendation": "APPLY | CONSIDER | SKIP",
    "reason": "str",
    "matching_skills": ["str"],
    "missing_skills": ["str"],
    "experience_match": "str",
    "location_match": "bool",
    "salary_match": "bool",
}

_FALLBACK_SYSTEM = (
    "Eres un analista laboral estricto. Responde SOLO JSON válido. "
    "Nunca inventes datos del candidato: todo lo que no esté en el CV "
    "se considera inexistente."
)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


class AnalysisParseError(ValueError):
    """La respuesta de la IA no cumple el contrato esperado."""


def _load_system_prompt() -> str:
    try:
        return (PROMPTS_DIR / "analyze_job.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return _FALLBACK_SYSTEM


def parse_analysis(payload: str | dict) -> JobAnalysis:
    """Parsea y valida la respuesta JSON de Groq hacia un JobAnalysis."""
    if isinstance(payload, str):
        match = _JSON_BLOCK_RE.search(payload)
        if not match:
            raise AnalysisParseError("La respuesta no contiene JSON")
        data = json.loads(match.group(0))
    else:
        data = dict(payload)

    try:
        score = int(data["score"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AnalysisParseError(f"score inválido: {data.get('score')!r}") from exc
    if not 0 <= score <= 100:
        raise AnalysisParseError(f"score fuera de rango: {score}")

    def _list(value: Any) -> list[str]:
        return [str(v) for v in value] if isinstance(value, list) else []

    return JobAnalysis(
        score=score,
        recommendation=str(data.get("recommendation", "CONSIDER")).upper(),
        reason=str(data.get("reason", "")),
        matching_skills=_list(data.get("matching_skills")),
        missing_skills=_list(data.get("missing_skills")),
        experience_match=str(data.get("experience_match", "")),
        location_match=bool(data.get("location_match", False)),
        salary_match=bool(data.get("salary_match", False)),
    )


def _build_user_prompt(job: JobPosting, cv_markdown: str, preferences: dict | None) -> str:
    prefs_block = json.dumps(preferences, ensure_ascii=False) if preferences else "{}"
    return f"""CV DEL CANDIDATO (fuente única de verdad):
---
{cv_markdown}
---

PREFERENCIAS DEL CANDIDATO:
{prefs_block}

OFERTA A EVALUAR:
- Puesto: {job.title}
- Empresa: {job.company or '—'}
- Ubicación: {job.location or '—'}
- Modalidad: {job.modality or '—'}
- Salario: {job.salary or '—'}
- Descripción: {job.description or '(sin descripción disponible; evalúa solo con los datos anteriores)'}
"""


async def analyze_job(
    client: GroqClient,
    job: JobPosting,
    cv_markdown: str,
    preferences: dict | None = None,
) -> JobAnalysis:
    """Evalúa la compatibilidad oferta↔CV con Groq y valida el resultado."""
    raw = await client.complete_structured(
        _load_system_prompt(), _build_user_prompt(job, cv_markdown, preferences)
    )
    analysis = parse_analysis(raw)
    if analysis.recommendation not in ("APPLY", "CONSIDER", "SKIP"):
        analysis.recommendation = "CONSIDER"
    return analysis
