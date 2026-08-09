"""Chat libre con el asistente (Groq).

Cualquier mensaje de texto que no sea comando ni parte del onboarding
se responde de forma conversacional con contexto del perfil y del CV.
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from app.ai.assistant import Assistant
from app.database.repositories import UserRepository

logger = logging.getLogger(__name__)

GROQ_NOT_CONFIGURED = (
    "🤖 Todavía no tengo configurada la IA.\n"
    "Define GROQ_API_KEY en tu archivo .env y reiníciame. "
    "Mientras tanto, puedes usar /start para el menú."
)


async def chat_with_assistant(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    client = context.bot_data.get("groq")
    if client is None:
        await update.message.reply_text(GROQ_NOT_CONFIGURED)
        return

    repo = UserRepository(context.bot_data["db"])
    tg_id = update.effective_user.id
    profile = repo.get_profile(tg_id)
    preferences = repo.get_preferences(tg_id)

    cv_manager = context.bot_data["cv_manager"]
    cv_summary = cv_manager.summary() if cv_manager.exists() else "(sin CV cargado)"

    history = context.user_data.setdefault("chat_history", [])

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )
    try:
        answer = await Assistant(client).reply(
            update.message.text,
            profile=profile,
            preferences=preferences,
            cv_summary=cv_summary,
            history=history,
        )
    except Exception as exc:  # nunca registrar contenido sensible del error
        logger.warning("Error al conversar con Groq: %s", type(exc).__name__)
        await update.message.reply_text(
            "⚠️ Tuve un problema al hablar con la IA. Inténtalo de nuevo en unos "
            "segundos. Si persiste, revisa la conexión en /settings."
        )
        return

    history.append({"role": "user", "content": update.message.text})
    history.append({"role": "assistant", "content": answer})
    Assistant.trim_history(history)

    # Texto plano: la IA habla con naturalidad, sin formato forzado.
    await update.message.reply_text(answer)
