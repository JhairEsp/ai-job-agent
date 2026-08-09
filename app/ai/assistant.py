"""Asistente conversacional con personalidad, apoyado en Groq.

Hace que el bot "converse" de forma natural con el usuario, pero siempre
anclado a la verdad: solo conoce lo que dicen el perfil y el cv.md.
"""
from __future__ import annotations

import logging

from app.ai.groq_client import GroqClient
from app.models.profile import SearchPreferences, UserProfile

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """Eres "AI Job Agent", el asistente laboral personal de {name}. Conversas por Telegram.

PERSONALIDAD:
- Cercano, natural y profesional: como un mentor de carrera, no como un formulario.
- Respuestas cortas y concretas (máximo ~120 palabras), en español, con un emoji ocasional.
- Proactivo: cuando sea útil, menciona que puede usar /start para el menú, /cv para su CV
  o ⚙️ Preferencias para ajustar su búsqueda.

CONTEXTO DEL USUARIO (úNICA fuente de verdad; no inventes nada fuera de esto):
{context}

REGLAS INVIOLABLES:
- No inventes experiencia, estudios, certificaciones, habilidades ni datos del usuario.
- Nunca pidas contraseñas, tarjetas ni datos bancarios.
- Tu especialidad es empleo y carrera profesional. Si te hablan de otro tema,
  responde con brevedad y redirige con amabilidad.
- No uses formato Markdown complejo: texto plano con saltos de línea."""

MAX_HISTORY_MESSAGES = 24  # ~12 intercambios


class Assistant:
    """Mantiene la personalidad del bot y conversa con el usuario vía Groq."""

    def __init__(self, client: GroqClient):
        self._client = client

    @staticmethod
    def build_context(
        profile: UserProfile | None,
        preferences: SearchPreferences | None,
        cv_summary: str,
    ) -> str:
        parts: list[str] = []
        if profile and profile.full_name:
            parts.append(
                f"Perfil: {profile.full_name} — {profile.location_label}"
            )
        if preferences:
            parts.append("Preferencias de búsqueda:\n" + preferences.summary())
        if cv_summary:
            parts.append("CV (resumen):\n" + cv_summary)
        return "\n\n".join(parts) if parts else "(el usuario aún no configura su perfil)"

    @staticmethod
    def trim_history(history: list[dict]) -> list[dict]:
        """Conserva solo los últimos intercambios para no inflar el contexto."""
        if len(history) > MAX_HISTORY_MESSAGES:
            del history[: len(history) - MAX_HISTORY_MESSAGES]
        return history

    async def reply(
        self,
        user_text: str,
        *,
        profile: UserProfile | None,
        preferences: SearchPreferences | None,
        cv_summary: str,
        history: list[dict],
    ) -> str:
        name = profile.full_name if profile and profile.full_name else "el usuario"
        system = SYSTEM_TEMPLATE.format(
            name=name,
            context=self.build_context(profile, preferences, cv_summary),
        )
        messages = [
            {"role": "system", "content": system},
            *self.trim_history(history),
            {"role": "user", "content": user_text},
        ]
        return await self._client.chat(messages, temperature=0.7, max_tokens=400)
