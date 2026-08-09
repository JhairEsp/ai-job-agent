"""Presentación de ofertas y análisis en Telegram."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.models.job import JobAnalysis, JobPosting

RECOMMENDATION_LABELS = {
    "APPLY": "🟢 RECOMENDADO",
    "CONSIDER": "🟡 VALE LA PENA CONSIDERARLO",
    "SKIP": "🔴 NO RECOMENDADO",
}


def match_label(analysis: JobAnalysis | None, heuristic: int = 0) -> str:
    if analysis is not None:
        return f"⭐ Match: {analysis.score}% ({analysis.classification})"
    if heuristic:
        return f"⭐ Coincidencia estimada: ~{heuristic}%"
    return "⭐ Sin analizar"


def job_keyboard(job_id: int, job: JobPosting, analyzed: bool = True) -> InlineKeyboardMarkup:
    row1 = [InlineKeyboardButton("🔗 Ver oferta", url=job.url)] if job.url else []
    row2 = [
        InlineKeyboardButton("🤖 Analizar", callback_data=f"job:{job_id}:analyze"),
        InlineKeyboardButton("🚀 Postular", callback_data=f"job:{job_id}:apply"),
    ]
    if analyzed:
        row2 = [b for b in row2 if not b.callback_data.endswith("analyze")]
    row3 = [
        InlineKeyboardButton("⭐ Guardar", callback_data=f"job:{job_id}:save"),
        InlineKeyboardButton("❌ Ignorar", callback_data=f"job:{job_id}:ignore"),
    ]
    rows = [r for r in (row1, row2, row3) if r]
    return InlineKeyboardMarkup(rows)


def _meta_line(job: JobPosting) -> str:
    parts = []
    if job.location:
        parts.append(f"📍 {job.location}")
    if job.modality:
        modality_icon = "🏠" if "remot" in job.modality.lower() else "🌎"
        parts.append(f"{modality_icon} {job.modality}")
    if job.salary:
        parts.append(f"💰 {job.salary}")
    return " · ".join(parts) if parts else ""


def job_card(
    job_id: int,
    job: JobPosting,
    analysis: JobAnalysis | None,
    *,
    heuristic: int = 0,
    prefix: str = "",
) -> tuple[str, InlineKeyboardMarkup]:
    text = prefix
    text += f"<b>{job.title}</b>\n🏢 {job.company or '—'}"
    meta = _meta_line(job)
    if meta:
        text += f"\n{meta}"
    text += f"\n{match_label(analysis, heuristic)}"
    return text, job_keyboard(job_id, job, analyzed=analysis is not None)


def analysis_detail(job: JobPosting, analysis: JobAnalysis) -> str:
    strengths = "\n".join(f"✓ {s}" for s in analysis.matching_skills) or "✓ (no detectadas)"
    gaps = "\n".join(f"⚠ {s}" for s in analysis.missing_skills) or "⚠ (no detectadas)"
    recommendation = RECOMMENDATION_LABELS.get(analysis.recommendation, analysis.recommendation)
    return (
        "🤖 <b>ANÁLISIS DE COMPATIBILIDAD</b>\n\n"
        f"<b>PUESTO</b>\n{job.title}\n\n"
        f"<b>EMPRESA</b>\n{job.company or '—'}\n\n"
        f"<b>MATCH</b>\n{analysis.score}% — {analysis.classification}\n\n"
        f"<b>FORTALEZAS</b>\n{strengths}\n\n"
        f"<b>BRECHAS</b>\n{gaps}\n\n"
        f"<b>EXPERIENCIA</b>\n{analysis.experience_match or '—'}\n\n"
        f"<b>UBICACIÓN</b>: {'✅ coincide' if analysis.location_match else '⚠️ no coincide'} · "
        f"<b>SALARIO</b>: {'✅ acorde' if analysis.salary_match else '⚠️ por debajo o desconocido'}\n\n"
        f"<b>RECOMENDACIÓN</b>\n{recommendation}\n\n"
        f"<b>Motivo:</b>\n{analysis.reason or '—'}"
    )


def top_matches_summary(items: list) -> str:
    """Encabezado 🔥 TOP MATCHES con una línea por oferta.

    `items`: lista de RankedJob (del servicio de búsqueda).
    """
    lines = ["🔥 <b>TOP MATCHES</b>\n"]
    for index, ranked in enumerate(items, start=1):
        job = ranked.job
        score = match_label(ranked.analysis, ranked.heuristic)
        meta = _meta_line(job)
        entry = f"<b>{index}. {job.title}</b> — {job.company}"
        if meta:
            entry += f"\n{meta}"
        entry += f"\n{score}"
        lines.append(entry)
    return "\n\n".join(lines)
