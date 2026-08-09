"""📋 Tracker de postulaciones: listado y cambio de estado."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.bot import keyboards
from app.database.repositories import ApplicationRepository, JobRepository
from app.models.job import STATUS_LABELS, ApplicationStatus

TRACK_STATUSES = (
    ApplicationStatus.INTERVIEW,
    ApplicationStatus.REJECTED,
    ApplicationStatus.OFFER,
    ApplicationStatus.WITHDRAWN,
)


def _format_date(raw: str) -> str:
    try:
        yyyy, mm, dd = raw[:10].split("-")
        return f"{dd}/{mm}/{yyyy}"
    except (ValueError, AttributeError):
        return raw[:10]


def _line(row: dict) -> str:
    emoji, label = STATUS_LABELS.get(ApplicationStatus(row["status"]), ("•", row["status"]))
    score = f"\n⭐ {row['score']}%" if row.get("score") is not None else ""
    return (
        f"{emoji} <b>{row['title']}</b> — {row['company']}\n"
        f"🌐 {row['portal']} · 📅 {_format_date(row['sent_at'])}{score}\n"
        f"Estado: <b>{label}</b>"
    )


def _detail_keyboard(job_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🎤 Entrevista", callback_data=f"appst:{job_id}:INTERVIEW"),
            InlineKeyboardButton("🏆 Oferta", callback_data=f"appst:{job_id}:OFFER"),
        ],
        [
            InlineKeyboardButton("🔴 Rechazada", callback_data=f"appst:{job_id}:REJECTED"),
            InlineKeyboardButton("⚪ Retirada", callback_data=f"appst:{job_id}:WITHDRAWN"),
        ],
        [InlineKeyboardButton("🔙 Menú principal", callback_data="menu:home")],
    ]
    return InlineKeyboardMarkup(rows)


async def list_applications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    repo = ApplicationRepository(context.bot_data["db"])
    rows = repo.list_for_user(update.effective_user.id, limit=10)

    if not rows:
        text = (
            "📋 <b>MIS POSTULACIONES</b>\n\n"
            "Aún no tienes postulaciones registradas.\n"
            "Cuando postules a una oferta aparecerá aquí."
        )
        markup = keyboards.back_to_menu()
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        else:
            await update.effective_message.reply_html(text, reply_markup=markup)
        return

    if update.callback_query:
        await update.callback_query.answer()

    first = rows[0]
    text, markup = (
        f"📋 <b>MIS POSTULACIONES</b> — {len(rows)} más recientes\n\n{_line(first)}",
        _detail_keyboard(first["job_id"]),
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.effective_message.reply_html(text, reply_markup=markup)

    for row in rows[1:]:
        await update.effective_message.reply_html(
            _line(row), reply_markup=_detail_keyboard(row["job_id"])
        )


async def change_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    _, job_id_str, status_value = query.data.split(":", 2)
    try:
        new_status = ApplicationStatus(status_value)
    except ValueError:
        await query.answer("Estado no válido.", show_alert=True)
        return

    repo = JobRepository(context.bot_data["db"])
    repo.set_status(int(job_id_str), new_status)
    emoji, label = STATUS_LABELS[new_status]
    await query.answer(f"Estado actualizado: {label}")
    try:
        await query.edit_message_text(
            f"{query.message.text_html}\n\n➡️ Estado actualizado: <b>{emoji} {label}</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass
