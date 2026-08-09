"""Ranking heurístico previo a la IA.

Antes de gastar llamadas a Groq, ordenamos las ofertas nuevas con una
heurística determinista basada en las preferencias del usuario. La IA
refina luego el score de las mejores candidatas.
"""
from __future__ import annotations

import re

from app.models.job import JobPosting
from app.models.profile import SearchPreferences

_NUM_RE = re.compile(r"[\d]+(?:[.,]\d+)?")


def parse_salary(text: str) -> int | None:
    """Primer monto numérico encontrado en un texto de salario."""
    if not text:
        return None
    match = _NUM_RE.search(text.replace(" ", ""))
    if not match:
        return None
    value = float(match.group(0).replace(",", ""))
    return int(value)


def _modality_of(job: JobPosting) -> str:
    haystack = f"{job.modality} {job.location} {job.title} {job.description}".lower()
    if "remot" in haystack:
        return "remoto"
    if "híbrid" in haystack or "hibrid" in haystack:
        return "híbrido"
    if "presencial" in haystack:
        return "presencial"
    return job.modality.lower()


def heuristic_score(job: JobPosting, preferences: SearchPreferences) -> int:
    """Score 0-100 aproximado sin IA (para priorizar qué analizar con Groq)."""
    score = 0
    job_text = f"{job.title} {job.description}".lower()

    # 1) Compatibilidad de puesto (el criterio más fuerte)
    position_hit = any(
        token in job_text
        for position in preferences.positions
        for token in position.lower().split()
        if len(token) > 2
    )
    if position_hit or not preferences.positions:
        score += 45

    # 2) Ubicación
    haystack = f"{job.location} {job.modality} {job.title}".lower()
    location_hit = any(
        loc.lower() in haystack for loc in preferences.locations
    )
    if location_hit or not preferences.locations:
        score += 20

    # 3) Modalidad
    modality = _modality_of(job)
    if not preferences.modalities or any(m.lower() in modality for m in preferences.modalities):
        score += 15

    # 4) Salario
    salary = parse_salary(job.salary)
    if salary is not None:
        if preferences.min_salary is None or salary >= preferences.min_salary:
            score += 10
    else:
        score += 5  # dato desconocido: no castigamos del todo

    # 5) Experiencia: penalización suave si pide muchos años (sin inventar)
    description = job.description.lower()
    years = re.search(r"(\d+)\s*\+?\s*años", description)
    if years and int(years.group(1)) >= 3:
        score -= 25

    # 6) Tipo de jornada
    if preferences.job_type != "Cualquiera":
        if preferences.job_type.lower().rstrip("s") in job_text:
            score += 10

    return max(0, min(100, score))


def rank(jobs: list[tuple[int, JobPosting]], preferences: SearchPreferences) -> list[tuple[int, JobPosting, int]]:
    """Devuelve [(posición_final, job, heuristic_score)] ordenados."""
    scored = [(job_id, job, heuristic_score(job, preferences)) for job_id, job in jobs]
    return sorted(scored, key=lambda item: item[2], reverse=True)
