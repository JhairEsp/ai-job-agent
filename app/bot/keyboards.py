"""Teclados inline del bot."""
from __future__ import annotations

from typing import Iterable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ------------------------------------------------------------------ opciones
LOCATION_OPTIONS = ["Lima", "Callao", "Remoto", "Perú"]
POSITION_EXAMPLES = [
    "Practicante de Sistemas",
    "Practicante BI",
    "Analista de Sistemas Junior",
    "Soporte TI",
    "Desarrollador Junior",
]
SALARY_CHOICES = [
    ("Sin mínimo", "none"),
    ("S/ 800", "800"),
    ("S/ 1,000", "1000"),
    ("S/ 1,500", "1500"),
    ("S/ 2,000", "2000"),
    ("✏️ Personalizado", "custom"),
]
MODALITY_OPTIONS = ["Remoto", "Híbrido", "Presencial"]
JOB_TYPE_OPTIONS = ["Tiempo completo", "Medio tiempo", "Prácticas", "Freelance", "Cualquiera"]
COUNTRY_OPTIONS = ["Perú"]


# ------------------------------------------------------------------ helpers
def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_btn("🔎 Buscar trabajos", "menu:search")],
            [_btn("📋 Mis postulaciones", "menu:applications")],
            [_btn("👤 Mi perfil", "profile:show"), _btn("📄 Mi CV", "cv:show")],
            [_btn("⚙️ Preferencias", "prefs:show"), _btn("🌐 Portales", "menu:portals")],
            [_btn("🤖 Configurar IA", "ai:show"), _btn("❓ Ayuda", "menu:help")],
        ]
    )


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_btn("🔙 Menú principal", "menu:home")]])


def multiselect_keyboard(
    options: Iterable[str],
    selected: Iterable[str],
    *,
    prefix: str,
    done_label: str = "✔️ Continuar",
) -> InlineKeyboardMarkup:
    """Teclado de selección múltiple con marcas ✅ y botón de continuar.

    Las opciones personalizadas (escritas por el usuario) se muestran al
    final siempre marcadas.
    """
    chosen = list(dict.fromkeys(selected))
    chosen_set = set(chosen)

    rows: list[list[InlineKeyboardButton]] = []

    def _row(option: str) -> list[InlineKeyboardButton]:
        mark = "✅ " if option in chosen_set else ""
        return [_btn(f"{mark}{option}"[:64], f"{prefix}:t:{option}")]

    for opt in options:
        rows.append(_row(opt))
    for opt in chosen:
        if opt not in set(options):
            rows.append(_row(opt))

    rows.append([_btn(done_label, f"{prefix}:done")])
    return InlineKeyboardMarkup(rows)


def salary_keyboard() -> InlineKeyboardMarkup:
    rows = [[_btn(label, f"ob:sal:{value}")] for label, value in SALARY_CHOICES]
    return InlineKeyboardMarkup(rows)


def country_keyboard() -> InlineKeyboardMarkup:
    rows = [[_btn(f"🇵🇪 {c}", f"ob:country:{c}")] for c in COUNTRY_OPTIONS]
    return InlineKeyboardMarkup(rows)


def skip_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_btn("⏭ Omitir", f"{prefix}:skip")]])


def job_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[_btn(opt, f"ob:job:{opt}")] for opt in JOB_TYPE_OPTIONS]
    )


def profile_actions() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_btn("✏️ Editar perfil", "profile:edit"), _btn("🎯 Editar preferencias", "prefs:edit")],
            [_btn("🔙 Menú principal", "menu:home")],
        ]
    )


def preferences_actions() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_btn("✏️ Editar preferencias", "prefs:edit")],
            [_btn("🔙 Menú principal", "menu:home")],
        ]
    )


def cv_actions() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_btn("⬆️ Subir nuevo CV (.md)", "cv:upload")],
            [_btn("📄 Ver CV completo", "cv:full"), _btn("🔄 Recargar", "cv:show")],
            [_btn("🔙 Menú principal", "menu:home")],
        ]
    )


def ai_actions() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_btn("🔍 Probar conexión", "ai:test")],
            [_btn("🔙 Menú principal", "menu:home")],
        ]
    )
