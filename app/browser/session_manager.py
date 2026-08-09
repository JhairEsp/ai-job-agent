"""Gestor de navegador Playwright con sesiones persistentes por portal.

Diseño de seguridad:

- Un perfil de navegador aislado por portal:
  data/browser_profiles/<portal>
- El usuario inicia sesión MANUALMENTE.
- Nunca se capturan, envían ni almacenan contraseñas.
- Ante CAPTCHA/Cloudflare/2FA se permite intervención manual.
- No se intenta evadir ningún mecanismo de seguridad.
- Los contextos persistentes se mantienen durante la ejecución.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class BrowserUnavailableError(RuntimeError):
    """Playwright o Chromium no están instalados."""


class HumanInterventionRequired(RuntimeError):
    """La página exige CAPTCHA/2FA/acción manual."""


class BrowserManager:
    """Orquesta los contextos persistentes de Chromium."""

    def __init__(
        self,
        profiles_dir: Path,
        *,
        headless_search: bool = False,
    ):
        self.profiles_dir = Path(
            profiles_dir
        )

        self.headless_search = (
            headless_search
        )

        self._pw: Any | None = None

        self._contexts: dict[
            str,
            Any,
        ] = {}

    # ============================================================
    # DISPONIBILIDAD
    # ============================================================

    @property
    def available(self) -> bool:
        """Comprueba si Playwright está instalado."""

        try:
            import playwright  # noqa: F401

        except ImportError:
            return False

        return True

    # ============================================================
    # INICIAR PLAYWRIGHT
    # ============================================================

    async def _ensure_started(
        self,
    ) -> None:

        if not self.available:

            raise BrowserUnavailableError(
                "Playwright no está instalado. "
                "Ejecuta: pip install playwright && "
                "playwright install chromium"
            )

        if self._pw is None:

            from playwright.async_api import (
                async_playwright,
            )

            self._pw = (
                await async_playwright().start()
            )

            logger.info(
                "Playwright iniciado correctamente."
            )

    # ============================================================
    # PERFIL
    # ============================================================

    def _profile_dir(
        self,
        portal_name: str,
    ) -> Path:
        """Obtiene el directorio persistente del portal."""

        path = (
            self.profiles_dir
            / portal_name
        )

        path.mkdir(
            parents=True,
            exist_ok=True,
        )

        return path

    # ============================================================
    # CONTEXTO PERSISTENTE
    # ============================================================

    async def get_context(
        self,
        portal_name: str,
        *,
        headless: bool | None = None,
    ):
        """Obtiene un contexto persistente por portal.

        El mismo contexto se reutiliza durante la ejecución,
        manteniendo cookies, localStorage y sesión del perfil.
        """

        await self._ensure_started()

        key = portal_name

        # --------------------------------------------------------
        # Si ya existe, reutilizamos el contexto.
        # --------------------------------------------------------

        existing = self._contexts.get(
            key
        )

        if existing is not None:

            try:

                if not existing.is_closed():

                    return existing

            except Exception:

                logger.debug(
                    "No se pudo comprobar el estado "
                    "del contexto %s.",
                    portal_name,
                )

            # Si estaba cerrado, lo eliminamos
            # del registro.

            self._contexts.pop(
                key,
                None,
            )

        # --------------------------------------------------------
        # Determinar modo visible/headless.
        # --------------------------------------------------------

        use_headless = (
            self.headless_search
            if headless is None
            else headless
        )

        profile_dir = (
            self._profile_dir(
                portal_name
            )
        )

        logger.info(
            "Abriendo perfil persistente de %s: %s",
            portal_name,
            profile_dir,
        )

        # --------------------------------------------------------
        # Lanzar Chromium persistente.
        # --------------------------------------------------------

        try:

            context = (
                await self._pw.chromium.launch_persistent_context(
                    user_data_dir=str(
                        profile_dir
                    ),
                    headless=use_headless,
                    viewport={
                        "width": 1280,
                        "height": 900,
                    },
                    locale="es-PE",
                    timezone_id="America/Lima",
                    accept_downloads=True,
                )
            )

        except Exception as exc:

            message = str(
                exc
            ).lower()

            if (
                "executable doesn't exist"
                in message
                or "playwright install"
                in message
            ):

                raise BrowserUnavailableError(
                    "Chromium no está instalado. "
                    "Ejecuta: playwright install chromium"
                ) from exc

            raise

        # --------------------------------------------------------
        # Guardar contexto.
        # --------------------------------------------------------

        self._contexts[key] = context

        logger.info(
            "Contexto persistente de %s iniciado.",
            portal_name,
        )

        return context

    # ============================================================
    # ABRIR LOGIN
    # ============================================================

    async def open_login(
        self,
        portal_name: str,
        url: str,
    ) -> None:
        """Abre el navegador visible para login manual."""

        context = await self.get_context(
            portal_name,
            headless=False,
        )

        page = await context.new_page()

        try:

            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60_000,
            )

        except Exception:

            # No cerramos el contexto.
            # El usuario puede necesitar interactuar
            # manualmente con el navegador.

            logger.exception(
                "Error abriendo login de %s.",
                portal_name,
            )

            raise

    # ============================================================
    # CERRAR PORTAL
    # ============================================================

    async def close_portal(
        self,
        portal_name: str,
    ) -> None:
        """Cierra el contexto persistente del portal."""

        context = self._contexts.pop(
            portal_name,
            None,
        )

        if context is None:
            return

        try:

            await context.close()

        except Exception:

            logger.debug(
                "Contexto de %s ya estaba cerrado.",
                portal_name,
            )

    # ============================================================
    # DETENER TODO
    # ============================================================

    async def stop(
        self,
    ) -> None:
        """Cierra todos los contextos y Playwright."""

        for name in list(
            self._contexts
        ):

            await self.close_portal(
                name
            )

        if self._pw is not None:

            try:

                await self._pw.stop()

            finally:

                self._pw = None

        logger.info(
            "BrowserManager detenido."
        )