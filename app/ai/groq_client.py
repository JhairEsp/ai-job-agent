"""Cliente exclusivo para la API de Groq.

Responsabilidad única: comunicación con Groq. La API key proviene de
`.env` (GROQ_API_KEY) y jamás se registra en logs ni se expone en la UI.

REGLA DE SEGURIDAD: nunca enviar credenciales, contraseñas ni tokens
del usuario en los prompts hacia Groq. Solo datos del CV y de ofertas.
"""
from __future__ import annotations

import asyncio
import logging

from groq import Groq

logger = logging.getLogger(__name__)


class GroqClient:
    """Wrapper async mínimo sobre el SDK oficial de Groq."""

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        timeout: float = 30.0,
    ):
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY no configurada. Define el valor en el archivo .env"
            )
        self.model = model
        self._client = Groq(api_key=api_key, timeout=timeout)

    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> str:
        """Envía una conversación a Groq y devuelve el texto de respuesta."""
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        logger.debug("Llamando a Groq (model=%s, json_mode=%s)", self.model, json_mode)
        response = await asyncio.to_thread(
            lambda: self._client.chat.completions.create(**kwargs)
        )
        choice = response.choices[0]
        return (choice.message.content or "").strip()

    async def health_check(self) -> dict:
        """Verifica conectividad con Groq sin consumir tokens de chat."""
        models = await asyncio.to_thread(self._client.models.list)
        available = {m.id for m in models.data}
        return {
            "ok": True,
            "model": self.model,
            "model_available": self.model in available,
            "models_count": len(available),
        }

    async def complete_structured(self, system_prompt: str, user_prompt: str) -> str:
        """Atajo para respuestas JSON (usado por el analizador, Fase 2)."""
        return await self.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            json_mode=True,
        )
