"""🌐 Gestión de portales: activar/desactivar y conectar cuentas.

NUNCA se piden contraseñas por Telegram: la conexión abre un navegador
Playwright para que el usuario inicie sesión a mano; solo se conserva la
sesión local del navegador.
"""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.bot import keyboards
from app.browser.session_manager import BrowserUnavailableError
from app.database.repositories import PortalRepository
from app.portals import registry

logger = logging.getLogger(__name__)


def _repo(context: ContextTypes.DEFAULT_TYPE) -> PortalRepository:
    return PortalRepository(context.bot_data["db"])


def _states(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> dict[str, dict]:
    repo = _repo(context)
    repo.ensure_defaults(user_id, registry.portal_names(), demo_enabled=registry.DEFAULT_ENABLED)
    return repo.all(user_id)


def portals_keyboard(states: dict[str, dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for name, portal_cls in registry.PORTAL_CLASSES.items():
        state = states.get(name, {})
        enabled = bool(state.get("enabled"))
        connected = bool(state.get("connected"))
        toggle = "🟢" if enabled else "⚪"
        label = f"{portal_cls.display_name} {toggle}"
        buttons = [InlineKeyboardButton(label, callback_data=f"portal:{name}:toggle")]
        if enabled and portal_cls.requires_login:
            btn = "🟢 Sesión activa" if connected else "🔐 Conectar"
            buttons.append(InlineKeyboardButton(btn, callback_data=f"portal:{name}:connect"))
        rows.append(buttons)
    rows.append([InlineKeyboardButton("🔙 Menú principal", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


HEADER = (
    "🌐 <b>PORTALES LABORALES</b>\n\n"
    "Activa los portales donde quieres buscar.\n"
    "En los que requieren sesión, conéctalos una vez: el navegador se abre "
    "para que <b>tú</b> inicies sesión. <b>JAMÁS te pediremos tu contraseña "
    "por Telegram</b> ni la guardaremos en ningún sitio."
)


async def show_portals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    states = _states(context, update.effective_user.id)
    markup = portals_keyboard(states)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            HEADER, parse_mode="HTML", reply_markup=markup
        )
    else:
        await update.effective_message.reply_html(HEADER, reply_markup=markup)


async def toggle_portal(update: Update, context: ContextTypes.DEFAULT_TYPE, name: str) -> None:
    repo = _repo(context)
    user_id = update.effective_user.id
    current = repo.get(user_id, name)
    new_value = not bool(current and current["enabled"])
    repo.set_enabled(user_id, name, new_value)
    await update.callback_query.answer(
        f"{'✅ Activado' if new_value else '⏸ Desactivado'}"
    )
    states = _states(context, user_id)
    await update.callback_query.edit_message_text(
        HEADER, parse_mode="HTML", reply_markup=portals_keyboard(states)
    )


async def connect_portal(update: Update, context: ContextTypes.DEFAULT_TYPE, name: str) -> None:
    query = update.callback_query
    user_id = update.effective_user.id
    portal = registry.create_portal(name)
    browser = context.bot_data.get("browser")

    if portal is None:
        await query.answer("Portal desconocido.", show_alert=True)
        return
    if browser is None or not browser.available:
        await query.answer(
            "El navegador no está disponible. Instala Chromium:\n"
            "playwright install chromium",
            show_alert=True,
        )
        return

    await query.answer(f"Abriendo {portal.display_name} en el navegador…")
    try:
        await browser.open_login(portal.name, portal.login_url or portal.home_url)
    except BrowserUnavailableError as exc:
        await query.edit_message_text(
            f"⚠️ {exc}", reply_markup=keyboards.back_to_menu()
        )
        return

    await query.edit_message_text(
        f"🌐 <b>{portal.display_name}</b>\n\n"
        "Se abrió una ventana del navegador.\n"
        "1️⃣ Inicia sesión normalmente en el portal.\n"
        "2️⃣ Cuando termines, vuelve aquí y toca <b>✅ Ya inicié sesión</b>.\n\n"
        "<i>No capturamos ni guardamos tu contraseña: la sesión queda solo "
        "en tu equipo.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Ya inicié sesión", callback_data=f"portal:{name}:verify")],
                [InlineKeyboardButton("❌ Cancelar", callback_data=f"portal:{name}:abort")],
            ]
        ),
    )


async def verify_portal(update: Update, context: ContextTypes.DEFAULT_TYPE, name: str) -> None:
    query = update.callback_query
    user_id = update.effective_user.id
    portal = registry.create_portal(name)
    browser = context.bot_data.get("browser")
    await query.answer("Verificando la sesión…")

    active = False
    try:
        if browser is not None and browser.available:
            active = await portal.is_session_active(browser)
    except Exception as exc:
        logger.warning("No se pudo verificar la sesión de %s: %s", name, type(exc).__name__)

    repo = _repo(context)
    repo.set_connected(user_id, name, active)

    if active:
        await query.edit_message_text(
            f"✅ <b>{portal.display_name} conectado.</b>\n\n"
            "Sesión guardada localmente. Nunca mostramos ni almacenamos tu contraseña.",
            parse_mode="HTML",
            reply_markup=keyboards.back_to_menu(),
        )
    else:
        await query.edit_message_text(
            f"⚠️ No pude confirmar la sesión de <b>{portal.display_name}</b>.\n"
            "Asegúrate de haber iniciado sesión en la ventana del navegador e "
            "inténtalo de nuevo.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🔄 Verificar de nuevo", callback_data=f"portal:{name}:verify")],
                    [InlineKeyboardButton("🔙 Volver", callback_data="menu:portals")],
                ]
            ),
        )


async def abort_connect(update: Update, context: ContextTypes.DEFAULT_TYPE, name: str) -> None:
    query = update.callback_query
    browser = context.bot_data.get("browser")
    if browser is not None:
        await browser.close_portal(name)
    await query.answer("Conexión cancelada.")
    await show_portals(update, context)


async def portal_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _, name, action = update.callback_query.data.split(":", 2)
    if action == "toggle":
        await toggle_portal(update, context, name)
    elif action == "connect":
        await connect_portal(update, context, name)
    elif action == "verify":
        await verify_portal(update, context, name)
    elif action == "abort":
        await abort_connect(update, context, name)
