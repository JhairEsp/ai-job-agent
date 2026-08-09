"""Generación de respuestas personalizadas para postulaciones (Fase 6).

Usa EXCLUSIVAMENTE información del CV del usuario (anti-alucinación).
Toda respuesta generada se muestra al usuario antes de usarse: nunca se
envía nada automáticamente.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.ai.groq_client import GroqClient
from app.models.job import JobPosting

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

_FALLBACK_PROMPT = (
    "Genera una respuesta de postulación usando ÚNICAMENTE los datos del CV "
    "adjunto. Prohibido inventar experiencia, estudios, certificaciones o "
    "habilidades. Tono profesional, primera persona, máximo 120 palabras."
)

COVER_QUESTION = (
    "Cuéntanos por qué te interesa este puesto y qué puedes aportar a la empresa."
)


def _load_prompt() -> str:
    try:
        return (PROMPTS_DIR / "generate_answer.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return _FALLBACK_PROMPT


async def generate_answer(
    client: GroqClient,
    *,
    question: str,
    job: JobPosting,
    cv_markdown: str,
) -> str:
    """Genera UNA respuesta para una pregunta concreta de postulación."""
    user_prompt = f"""CV DEL CANDIDATO:
---
{cv_markdown}
---

OFERTA:
Puesto: {job.title}
Empresa: {job.company or '—'}
Descripción: {job.description or '—'}

PREGUNTA DEL FORMULARIO:
{question}

Escribe SOLO la respuesta (sin comillas ni encabezados)."""
    return await client.chat(
        messages=[
            {"role": "system", "content": _load_prompt()},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=400,
    )


async def generate_cover_message(
    client: GroqClient, *, job: JobPosting, cv_markdown: str
) -> str:
    """Mensaje de presentación genérico para la postulación."""
    return await generate_answer(
        client, question=COVER_QUESTION, job=job, cv_markdown=cv_markdown
    )
