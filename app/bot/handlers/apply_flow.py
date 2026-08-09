"""Flujo guiado de postulación con confirmaciones explícitas.

    [🚀 Postular] → confirmar → (IA genera respuesta) → revisar/editar
                  → ⚠️ REVISIÓN FINAL → [🚀 ENVIAR] → registro en tracker.

Nada se envía sin que el usuario presione ENVIAR. Las respuestas de la IA
solo usan información real del CV (nunca inventan).
"""
from __future__ import annotations

import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.ai import answer_generator
from app.bot import job_views
from app.database.repositories import (
    ApplicationRepository,
    JobRepository,
    UserRepository,
    job_row_to_posting,
)
from app.models.job import ApplicationStatus, JobPosting
from app.portals import registry

logger = logging.getLogger(__name__)

CONFIRM, DRAFT, EDIT, REVIEW = range(4)
MAX_REGENERATIONS = 3


def _store(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data.setdefault("apply", {"job_id": None, "draft": "", "rounds": 0})


def _reset(context: ContextTypes.DEFAULT_TYPE) -> dict:
    store = _store(context)
    store.update({"job_id": None, "draft": "", "rounds": 0})
    return store


def _kbd(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([list(r) for r in rows if r])


async def ask_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    job_id = int(query.data.split(":")[1])
    repo = JobRepository(context.bot_data["db"])
    row = repo.get(job_id, update.effective_user.id)
    if row is None:
        await query.answer("Esta oferta ya no está disponible.", show_alert=True)
        return ConversationHandler.END

    _reset(context)["job_id"] = job_id
    await query.answer()
    await query.edit_message_text(
        "🚀 <b>POSTULACIÓN</b>\n\n"
        f"Puesto: <b>{row['title']}</b>\n"
        f"Empresa: <b>{row['company']}</b>\n\n"
        "¿Quieres postular a esta oferta?",
        parse_mode="HTML",
        reply_markup=_kbd(
            [InlineKeyboardButton("✅ Sí, preparar postulación", callback_data="af:yes")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="af:cancel")],
        ),
    )
    return CONFIRM


async def _generate_draft(context: ContextTypes.DEFAULT_TYPE, user_id: int, job: JobPosting) -> str:
    groq = context.bot_data.get("groq")
    if groq is None:
        return ""
    cv_manager = context.bot_data["cv_manager"]
    try:
        return await answer_generator.generate_cover_message(
            groq, job=job, cv_markdown=cv_manager.raw_text()
        )
    except Exception as exc:
        logger.warning("No se pudo generar la respuesta: %s", type(exc).__name__)
        return ""


async def _show_draft(query, context: ContextTypes.DEFAULT_TYPE, job: JobPosting) -> int:
    store = _store(context)
    draft = store["draft"]
    if draft:
        body = f"📝 <b>RESPUESTA GENERADA</b>\n\n<blockquote>{draft}</blockquote>"
    else:
        body = (
            "⚠️ La IA no está disponible (o no pudo generar una respuesta).\n"
            "Puedes escribir tu propia respuesta con <b>✏️ Editar</b>."
        )
    await query.edit_message_text(
        f"🚀 <b>POSTULACIÓN</b> — {job.title} @ {job.company}\n\n{body}\n\n"
        "<i>Solo se usó información real de tu CV. Nada es inventado.</i>",
        parse_mode="HTML",
        reply_markup=_kbd(
            [
                InlineKeyboardButton("✅ Usar respuesta", callback_data="af:use"),
                InlineKeyboardButton("✏️ Editar", callback_data="af:edit"),
            ],
            [InlineKeyboardButton("🔄 Generar otra", callback_data="af:regen")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="af:cancel")],
        ),
    )
    return DRAFT


async def confirm_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("Generando una respuesta personalizada…")
    repo = JobRepository(context.bot_data["db"])
    row = repo.get(_store(context)["job_id"], update.effective_user.id)
    job = job_row_to_posting(row)
    repo.set_status(row["id"], ApplicationStatus.READY)
    store = _store(context)
    store["rounds"] += 1
    store["draft"] = await _generate_draft(context, update.effective_user.id, job)
    return await _show_draft(query, context, job)


async def regenerate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    store = _store(context)
    if store["rounds"] >= MAX_REGENERATIONS:
        await query.answer(
            "Ya generé varias versiones. Puedes editar el texto a tu gusto con ✏️.",
            show_alert=True,
        )
        return DRAFT
    repo = JobRepository(context.bot_data["db"])
    row = repo.get(store["job_id"], update.effective_user.id)
    job = job_row_to_posting(row)
    await query.answer("Generando otra versión…")
    store["rounds"] += 1
    store["draft"] = await _generate_draft(context, update.effective_user.id, job)
    return await _show_draft(query, context, job)


async def ask_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✏️ <b>Edita la respuesta</b>\n\n"
        "Envíame el texto final que quieres usar en la postulación.",
        parse_mode="HTML",
        reply_markup=_kbd(
            [InlineKeyboardButton("❌ Cancelar", callback_data="af:cancel")],
        ),
    )
    return EDIT


async def receive_edited_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _store(context)["draft"] = update.message.text.strip()
    repo = JobRepository(context.bot_data["db"])
    row = repo.get(_store(context)["job_id"], update.effective_user.id)
    job = job_row_to_posting(row)
    await update.message.reply_text("✅ Respuesta actualizada.")
    store = _store(context)
    body = f"📝 <b>RESPUESTA GENERADA</b>\n\n<blockquote>{store['draft']}</blockquote>"
    await update.message.reply_html(
        f"🚀 <b>POSTULACIÓN</b> — {job.title} @ {job.company}\n\n{body}",
        reply_markup=_kbd(
            [
                InlineKeyboardButton("✅ Usar respuesta", callback_data="af:use"),
                InlineKeyboardButton("✏️ Editar", callback_data="af:edit"),
            ],
            [InlineKeyboardButton("🔄 Generar otra", callback_data="af:regen")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="af:cancel")],
        ),
    )
    return DRAFT


async def use_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    store = _store(context)
    repo = JobRepository(context.bot_data["db"])
    row = repo.get(store["job_id"], update.effective_user.id)
    job = job_row_to_posting(row)

    await query.edit_message_text(
        "⚠️ <b>REVISIÓN FINAL</b>\n\n"
        f"Puesto: <b>{job.title}</b>\n"
        f"Empresa: <b>{job.company}</b>\n"
        f"Respuestas: {'1' if store['draft'] else '0'}\n"
        "CV: <code>cv.md</code>\n\n"
        "¿Enviar postulación?",
        parse_mode="HTML",
        reply_markup=_kbd(
            [InlineKeyboardButton("🚀 ENVIAR", callback_data="af:send")],
            [InlineKeyboardButton("❌ CANCELAR", callback_data="af:cancel")],
        ),
    )
    return REVIEW


async def send_application(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    store = _store(context)
    user_id = update.effective_user.id
    job_id = store["job_id"]

    db = context.bot_data["db"]
    job_repo = JobRepository(db)
    row = job_repo.get(job_id, user_id)
    job = job_row_to_posting(row)

    await query.answer("Enviando…")

    # Perfil del postulante (solo datos reales).
    profile = UserRepository(db).get_profile(user_id)
    applicant = profile.to_dict() if profile else {}

    method = "manual"
    note = ""
    portal = registry.create_portal(job.portal) if job.portal else None
    browser = context.bot_data.get("browser")
    if portal is not None and portal.supports_apply and browser is not None and browser.available:
        try:
            method = await portal.apply(
                browser, job, applicant, {"cover_letter": store["draft"]}
            )
        except Exception as exc:
            logger.warning("Postulación automática falló: %s", type(exc).__name__)
            note = "\n⚠️ La automatización no pudo completarse; completa la postulación desde el enlace."

    app_repo = ApplicationRepository(db)
    app_repo.record(
        user_id,
        job_id,
        answers=store["draft"],
        method=method,
        confirmation=datetime.now().isoformat(timespec="seconds"),
    )
    job_repo.set_status(job_id, ApplicationStatus.APPLIED)
    logger.info("Postulación registrada: user=%s job=%s método=%s", user_id, job_id, method)

    result_line = (
        "✅ <b>Postulación completada y registrada.</b>"
        if method == "submitted"
        else "📋 <b>Postulación asistida registrada.</b>\n" \
             "Revisa el portal para confirmar el envío final."
    )
    link_line = f"\n🔗 {job.url}" if job.url else ""
    await query.edit_message_text(
        f"🚀 <b>POSTULACIÓN ENVIADA</b>\n\n"
        f"Puesto: <b>{job.title}</b>\nEmpresa: <b>{job.company}</b>\n\n"
        f"{result_line}{link_line}{note}\n\n"
        "La encontrarás en 📋 <b>Mis postulaciones</b>.",
        parse_mode="HTML",
    )
    _reset(context)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer("Postulación cancelada.")
        try:
            await update.callback_query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
    else:
        await update.effective_message.reply_text("Postulación cancelada.")
    _reset(context)
    return ConversationHandler.END


def build_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_confirm, pattern=r"^job:\d+:apply$")],
        states={
            CONFIRM: [
                CallbackQueryHandler(confirm_yes, pattern=r"^af:yes$"),
                CallbackQueryHandler(cancel, pattern=r"^af:cancel$"),
            ],
            DRAFT: [
                CallbackQueryHandler(use_draft, pattern=r"^af:use$"),
                CallbackQueryHandler(ask_edit, pattern=r"^af:edit$"),
                CallbackQueryHandler(regenerate, pattern=r"^af:regen$"),
                CallbackQueryHandler(cancel, pattern=r"^af:cancel$"),
            ],
            EDIT: [
                CallbackQueryHandler(cancel, pattern=r"^af:cancel$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edited_text),
            ],
            REVIEW: [
                CallbackQueryHandler(send_application, pattern=r"^af:send$"),
                CallbackQueryHandler(cancel, pattern=r"^af:cancel$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern=r"^af:cancel$")],
        allow_reentry=True,
    )
