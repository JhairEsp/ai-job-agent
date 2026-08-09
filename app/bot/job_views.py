"""Presentación de ofertas y análisis en Telegram."""

from __future__ import annotations

from html import escape

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from app.models.job import (
    JobAnalysis,
    JobPosting,
)


# ============================================================
# RECOMENDACIONES
# ============================================================

RECOMMENDATION_LABELS = {
    "APPLY": "🟢 RECOMENDADO",
    "CONSIDER": "🟡 VALE LA PENA CONSIDERAR",
    "SKIP": "🔴 NO RECOMENDADO",
}


# ============================================================
# MATCH
# ============================================================

def match_label(
    analysis: JobAnalysis | None,
    heuristic: int = 0,
) -> str:

    if analysis is not None:

        score = analysis.score

        if score >= 90:
            icon = "🟢"

        elif score >= 80:
            icon = "🟡"

        elif score >= 70:
            icon = "🔵"

        elif score >= 60:
            icon = "🟠"

        else:
            icon = "🔴"

        return (
            f"{icon} <b>Compatibilidad IA: "
            f"{score}%</b> "
            f"({escape(analysis.classification)})"
        )

    if heuristic:

        return (
            f"⭐ Coincidencia preliminar: "
            f"~{heuristic}%"
        )

    return (
        "🤖 <b>Sin analizar todavía</b>"
    )


# ============================================================
# BOTONES
# ============================================================

def job_keyboard(
    job_id: int,
    job: JobPosting,
    analyzed: bool = True,
) -> InlineKeyboardMarkup:

    rows = []

    # --------------------------------------------------------
    # VER OFERTA
    # --------------------------------------------------------

    if job.url:

        rows.append(
            [
                InlineKeyboardButton(
                    "🔗 Ver oferta",
                    url=job.url,
                )
            ]
        )

    # --------------------------------------------------------
    # IA / POSTULAR
    # --------------------------------------------------------

    action_row = []

    if not analyzed:

        action_row.append(
            InlineKeyboardButton(
                "🤖 Analizar",
                callback_data=(
                    f"job:{job_id}:analyze"
                ),
            )
        )

    action_row.append(
        InlineKeyboardButton(
            "🚀 Postular",
            callback_data=(
                f"job:{job_id}:apply"
            ),
        )
    )

    if action_row:

        rows.append(
            action_row
        )

    # --------------------------------------------------------
    # GUARDAR / IGNORAR
    # --------------------------------------------------------

    rows.append(
        [
            InlineKeyboardButton(
                "⭐ Guardar",
                callback_data=(
                    f"job:{job_id}:save"
                ),
            ),
            InlineKeyboardButton(
                "❌ Ignorar",
                callback_data=(
                    f"job:{job_id}:ignore"
                ),
            ),
        ]
    )

    return InlineKeyboardMarkup(
        rows
    )


# ============================================================
# METADATA
# ============================================================

def _meta_line(
    job: JobPosting,
) -> str:

    parts = []

    # --------------------------------------------------------
    # UBICACIÓN
    # --------------------------------------------------------

    if job.location:

        parts.append(
            f"📍 {escape(job.location)}"
        )

    # --------------------------------------------------------
    # MODALIDAD
    # --------------------------------------------------------

    if job.modality:

        modality_lower = (
            job.modality.lower()
        )

        if (
            "remot" in modality_lower
            or "home" in modality_lower
        ):
            icon = "🏠"

        elif (
            "híbr" in modality_lower
            or "hibr" in modality_lower
        ):
            icon = "🔄"

        else:
            icon = "🏢"

        parts.append(
            f"{icon} "
            f"{escape(job.modality)}"
        )

    # --------------------------------------------------------
    # SALARIO
    # --------------------------------------------------------

    if job.salary:

        parts.append(
            f"💰 {escape(job.salary)}"
        )

    return (
        " · ".join(parts)
        if parts
        else ""
    )


# ============================================================
# TARJETA DE OFERTA
# ============================================================

def job_card(
    job_id: int,
    job: JobPosting,
    analysis: JobAnalysis | None,
    *,
    heuristic: int = 0,
    prefix: str = "",
) -> tuple[
    str,
    InlineKeyboardMarkup,
]:

    title = escape(
        job.title or "Puesto no especificado"
    )

    company = escape(
        job.company
        or "Empresa no especificada"
    )

    text = ""

    if prefix:
        text += prefix

    # --------------------------------------------------------
    # CABECERA
    # --------------------------------------------------------

    text += (
        "💼 <b>"
        f"{title}"
        "</b>\n"
    )

    text += (
        "🏢 <b>Empresa:</b> "
        f"{company}\n"
    )

    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------

    meta = _meta_line(
        job
    )

    if meta:

        text += (
            f"{meta}\n"
        )

    # --------------------------------------------------------
    # PORTAL
    # --------------------------------------------------------

    if job.portal:

        text += (
            "🌐 <b>Portal:</b> "
            f"{escape(job.portal)}\n"
        )

    # --------------------------------------------------------
    # MATCH
    # --------------------------------------------------------

    text += "\n"

    text += match_label(
        analysis,
        heuristic,
    )

    # --------------------------------------------------------
    # RECOMENDACIÓN
    # --------------------------------------------------------

    if analysis is not None:

        recommendation = (
            RECOMMENDATION_LABELS.get(
                analysis.recommendation,
                analysis.recommendation,
            )
        )

        text += (
            "\n"
            f"🎯 <b>{escape(recommendation)}</b>"
        )

        # ----------------------------------------------------
        # MOTIVO CORTO
        # ----------------------------------------------------

        if analysis.reason:

            reason = (
                analysis.reason
                .strip()
            )

            # Telegram no necesita un párrafo gigante
            # en la tarjeta principal.
            if len(reason) > 350:

                reason = (
                    reason[:347]
                    + "..."
                )

            text += (
                "\n\n"
                "🧠 <b>Por qué:</b>\n"
                f"{escape(reason)}"
            )

    return (
        text,
        job_keyboard(
            job_id,
            job,
            analyzed=(
                analysis is not None
            ),
        ),
    )


# ============================================================
# DETALLE DE ANÁLISIS
# ============================================================

def analysis_detail(
    job: JobPosting,
    analysis: JobAnalysis,
) -> str:

    title = escape(
        job.title
        or "Puesto no especificado"
    )

    company = escape(
        job.company
        or "Empresa no especificada"
    )

    location = escape(
        job.location
        or "No especificada"
    )

    salary = escape(
        job.salary
        or "No especificado"
    )

    # --------------------------------------------------------
    # FORTALEZAS
    # --------------------------------------------------------

    strengths = "\n".join(
        f"✓ {escape(str(skill))}"
        for skill
        in analysis.matching_skills
    )

    if not strengths:

        strengths = (
            "✓ No se detectaron "
            "coincidencias específicas."
        )

    # --------------------------------------------------------
    # BRECHAS
    # --------------------------------------------------------

    gaps = "\n".join(
        f"⚠ {escape(str(skill))}"
        for skill
        in analysis.missing_skills
    )

    if not gaps:

        gaps = (
            "⚠ No se detectaron "
            "brechas importantes."
        )

    # --------------------------------------------------------
    # RECOMENDACIÓN
    # --------------------------------------------------------

    recommendation = (
        RECOMMENDATION_LABELS.get(
            analysis.recommendation,
            analysis.recommendation,
        )
    )

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    return (
        "🤖 <b>ANÁLISIS DE COMPATIBILIDAD</b>\n"
        "\n"
        "💼 <b>PUESTO</b>\n"
        f"{title}\n"
        "\n"
        "🏢 <b>EMPRESA</b>\n"
        f"{company}\n"
        "\n"
        "📍 <b>UBICACIÓN</b>\n"
        f"{location}\n"
        "\n"
        "💰 <b>SALARIO</b>\n"
        f"{salary}\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "⭐ <b>COMPATIBILIDAD</b>\n"
        f"{analysis.score}% — "
        f"{escape(analysis.classification)}\n"
        "\n"
        "💪 <b>FORTALEZAS</b>\n"
        f"{strengths}\n"
        "\n"
        "⚠️ <b>BRECHAS</b>\n"
        f"{gaps}\n"
        "\n"
        "🧑‍💻 <b>EXPERIENCIA</b>\n"
        f"{escape(analysis.experience_match or '—')}\n"
        "\n"
        "📍 <b>UBICACIÓN</b>: "
        f"{'✅ coincide' if analysis.location_match else '⚠️ no coincide o es desconocida'}\n"
        "\n"
        "💰 <b>SALARIO</b>: "
        f"{'✅ acorde' if analysis.salary_match else '⚠️ por debajo o desconocido'}\n"
        "\n"
        "🎯 <b>RECOMENDACIÓN</b>\n"
        f"{escape(recommendation)}\n"
        "\n"
        "🧠 <b>MOTIVO</b>\n"
        f"{escape(analysis.reason or '—')}"
    )


# ============================================================
# RESUMEN TOP MATCHES
# ============================================================

def top_matches_summary(
    items: list,
) -> str:

    lines = [
        "🔥 <b>TOP MATCHES</b>",
        "",
    ]

    for index, ranked in enumerate(
        items,
        start=1,
    ):

        job = ranked.job

        title = escape(
            job.title
            or "Puesto no especificado"
        )

        company = escape(
            job.company
            or "Empresa no especificada"
        )

        entry = (
            f"<b>{index}. "
            f"{title}</b>\n"
            f"🏢 {company}"
        )

        meta = _meta_line(
            job
        )

        if meta:

            entry += (
                f"\n{meta}"
            )

        entry += (
            "\n"
            f"{match_label(ranked.analysis, ranked.heuristic)}"
        )

        lines.append(
            entry
        )

    return "\n\n".join(
        lines
    )