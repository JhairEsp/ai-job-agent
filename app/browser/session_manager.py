"""Gestor de navegador Playwright con sesiones persistentes por portal.

Diseño de seguridad:
- Un perfil de navegador aislado por portal: data/browser_profiles/<portal>/
- El usuario inicia sesión MANUALMENTE en el navegador; nunca se capturan,
  envían ni guardan contraseñas.
- Ante CAPTCHA o verificación humana, el sistema se detiene y avisa.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class BrowserUnavailableError(RuntimeError):
    """Playwright o los navegadores no están instalados en este equipo."""


class HumanInterventionRequired(RuntimeError):
    """La página exige CAPTCHA/2FA/acción manual. Nunca se intenta evadir."""


class BrowserManager:
    """Orquesta los contextos persistentes de Chromium."""

    def __init__(self, profiles_dir: Path, *, headless_search: bool = True):
        self.profiles_dir = Path(profiles_dir)
        self.headless_search = headless_search
        self._pw = None
        self._contexts: dict[str, object] = {}

    @property
    def available(self) -> bool:
        try:
            import playwright  # noqa: F401
        except ImportError:
            return False
        return True

    async def _ensure_started(self):
        if not self.available:
            raise BrowserUnavailableError(
                "Playwright no está instalado: pip install playwright && "
                "playwright install chromium"
            )
        if self._pw is None:
            from playwright.async_api import async_playwright

            self._pw = await async_playwright().start()

    def _profile_dir(self, portal_name: str) -> Path:
        path = self.profiles_dir / portal_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def get_context(self, portal_name: str, *, headless: bool | None = None):
        """Contexto persistente del portal (reutiliza la sesión guardada)."""
        await self._ensure_started()
        key = portal_name
        if key in self._contexts:
            return self._contexts[key]

        try:
            context = await self._pw.chromium.launch_persistent_context(
                user_data_dir=str(self._profile_dir(portal_name)),
                headless=self.headless_search if headless is None else headless,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 900},
                locale="es-PE",
            )
        except Exception as exc:
            msg = str(exc)
            if "Executable doesn't exist" in msg or "playwright install" in msg:
                raise BrowserUnavailableError(
                    "Chromium no está instalado. Ejecuta: playwright install chromium"
                ) from exc
            raise

        self._contexts[key] = context
        return context

    async def open_login(self, portal_name: str, url: str) -> None:
        """Abre el navegador VISIBLE para que el usuario inicie sesión a mano.

        El contexto queda abierto hasta `close_portal()`.
        """
        context = await self.get_context(portal_name, headless=False)
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)

    async def close_portal(self, portal_name: str) -> None:
        context = self._contexts.pop(portal_name, None)
        if context is not None:
            try:
                await context.close()
            except Exception:
                logger.debug("Contexto de %s ya estaba cerrado", portal_name)

    async def stop(self) -> None:
        for name in list(self._contexts):
            await self.close_portal(name)
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None
