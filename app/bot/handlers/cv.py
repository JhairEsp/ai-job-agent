"""Visualización del CV del candidato (data/profile/cv.md).

El CV solo se edita manualmente por el usuario (o con su autorización
explícita en fases futuras). Este módulo únicamente lee y resume.
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import keyboards

logger = logging.getLogger(__name__)

MAX_CHUNK = 3800

NO_CV = (
    "📄 <b>Mi CV</b>\n\n"
    "No se encontró el archivo <code>data/profile/cv.md</code>.\n"
    "Crea ese archivo con tu información profesional para que la IA "
    "pueda analizar ofertas con tu perfil real."
)

CV_NOTE = (
    "\n\n🔒 <i>El CV es tu fuente de verdad: la IA nunca inventará "
    "experiencia ni habilidades que no estén aquí. Puedes actualizarlo "
    "editando <code>data/profile/cv.md</code> o con el botón "
    "<b>⬆️ Subir nuevo CV</b>.</i>"
)


def _cv_manager(context: ContextTypes.DEFAULT_TYPE):
    return context.bot_data["cv_manager"]


async def show_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    manager = _cv_manager(context)
    text = NO_CV if not manager.exists() else (
        f"📄 <b>MI CV</b>\n\n{manager.summary()}{CV_NOTE}"
    )

    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            text, parse_mode="HTML", reply_markup=keyboards.cv_actions()
        )
    else:
        await update.effective_message.reply_html(text, reply_markup=keyboards.cv_actions())


async def show_full_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    manager = _cv_manager(context)
    query = update.callback_query
    if not manager.exists():
        await query.answer("No hay CV disponible.", show_alert=True)
        return

    await query.answer()
    raw = manager.raw_text()
    for offset in range(0, len(raw), MAX_CHUNK):
        await query.message.reply_text(raw[offset : offset + MAX_CHUNK])
    await query.message.reply_html(
        f"📄 <b>Resumen</b>\n\n{manager.summary()}",
        reply_markup=keyboards.cv_actions(),
    )
