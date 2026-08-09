"""Carga del CV del usuario en formato Markdown.

Flujo: botón "⬆️ Subir nuevo CV (.md)" → el usuario envía un archivo .md
(o pega el contenido como texto) → se valida → se guarda reemplazando el
anterior, del que se crea un respaldo automático (cv.md.bak).

Esta es la ÚNICA vía por la que el sistema escribe sobre cv.md, y siempre
es a petición explícita del usuario.
"""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot import keyboards

logger = logging.getLogger(__name__)

AWAIT_CV = 0
MAX_CV_BYTES = 64 * 1024  # 64 KB es más que suficiente para un CV en Markdown

ASK_FILE = (
    "📤 <b>Subir nuevo CV</b>\n\n"
    "Envíame tu CV como archivo <b>.md</b> (Markdown)\n"
    "o pega el contenido directamente como mensaje.\n\n"
    "💡 Se creará un respaldo del CV actual antes de reemplazarlo."
)

INVALID_FILE = (
    "⚠️ El archivo debe tener extensión <b>.md</b>.\n"
    "Envíalo de nuevo o toca <b>❌ Cancelar</b>."
)


def _cv_manager(context: ContextTypes.DEFAULT_TYPE):
    return context.bot_data["cv_manager"]


def _cancel_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancelar", callback_data="cv:upload_cancel")]]
    )


async def ask_for_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        ASK_FILE, parse_mode="HTML", reply_markup=_cancel_markup()
    )
    return AWAIT_CV


async def _save_and_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, content: str) -> int:
    content = content.strip()
    if not content or "#" not in content:
        await update.effective_message.reply_html(
            "⚠️ El contenido no parece un CV en Markdown válido "
            "(debe incluir al menos un encabezado con <code>#</code>).\n"
            "Inténtalo de nuevo o cancela."
        )
        return AWAIT_CV

    manager = _cv_manager(context)
    backup = manager.replace_with_backup(content)
    logger.info(
        "CV actualizado por el usuario %s (respaldo: %s)",
        update.effective_user.id,
        backup.name if backup else "no existía CV previo",
    )

    backup_note = f"\n💾 Respaldo creado: <code>{backup.name}</code>" if backup else ""
    await update.effective_message.reply_html(
        f"✅ <b>CV actualizado correctamente.</b>{backup_note}\n\n"
        f"{manager.summary()}",
        reply_markup=keyboards.cv_actions(),
    )
    return ConversationHandler.END


async def receive_cv_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    document = update.message.document

    if not document.file_name or not document.file_name.lower().endswith(".md"):
        await update.message.reply_html(INVALID_FILE, reply_markup=_cancel_markup())
        return AWAIT_CV
    if document.file_size and document.file_size > MAX_CV_BYTES:
        await update.message.reply_html(
            f"⚠️ El archivo supera el límite de {MAX_CV_BYTES // 1024} KB.\n"
            "Envíame un .md más ligero o pega el contenido como texto.",
            reply_markup=_cancel_markup(),
        )
        return AWAIT_CV

    try:
        tlg_file = await document.get_file()
        data = bytes(await tlg_file.download_to_memory())
        content = data.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("No se pudo descargar el CV: %s", type(exc).__name__)
        await update.message.reply_html(
            "⚠️ No pude descargar el archivo. Inténtalo de nuevo.",
            reply_markup=_cancel_markup(),
        )
        return AWAIT_CV

    return await _save_and_confirm(update, context, content)


async def receive_cv_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Permite pegar el CV directamente como mensaje de texto."""
    return await _save_and_confirm(update, context, update.message.text)


async def cancel_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "📄 Carga de CV cancelada.",
            reply_markup=keyboards.cv_actions(),
        )
    else:
        await update.effective_message.reply_html("📄 Carga de CV cancelada.")
    return ConversationHandler.END


def build_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_for_cv, pattern=r"^cv:upload$")],
        states={
            AWAIT_CV: [
                MessageHandler(filters.Document.ALL, receive_cv_document),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_cv_text),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_upload, pattern=r"^cv:upload_cancel$"),
            CommandHandler("cancel", cancel_upload),
        ],
        allow_reentry=True,
    )
