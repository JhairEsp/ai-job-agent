"""Registro de portales disponibles."""
from __future__ import annotations

from app.portals.base_portal import BasePortal
from app.portals.bumeran import BumeranPortal
from app.portals.computrabajo import CompuTrabajoPortal
from app.portals.demo import DemoPortal
from app.portals.indeed import IndeedPortal
from app.portals.linkedin import LinkedInPortal

PORTAL_CLASSES: dict[str, type[BasePortal]] = {
    cls.name: cls
    for cls in (DemoPortal, LinkedInPortal, CompuTrabajoPortal, IndeedPortal, BumeranPortal)
}

#: Portal habilitado por defecto para nuevos usuarios.
DEFAULT_ENABLED = DemoPortal.name


def create_portal(name: str) -> BasePortal | None:
    cls = PORTAL_CLASSES.get(name)
    return cls() if cls else None


def portal_names() -> list[str]:
    return list(PORTAL_CLASSES)
