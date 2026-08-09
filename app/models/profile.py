"""Modelos de perfil de usuario y preferencias de búsqueda."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class UserProfile:
    """Datos personales del candidato."""

    full_name: str = ""
    city: str = ""
    country: str = ""
    district: str = ""
    email: str = ""
    phone: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "UserProfile":
        if not data:
            return cls()
        valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid)

    @property
    def location_label(self) -> str:
        parts = [p for p in (self.district, self.city, self.country) if p]
        return ", ".join(parts) if parts else "—"


@dataclass
class SearchPreferences:
    """Preferencias laborales usadas para buscar y rankear ofertas."""

    locations: list[str] = field(default_factory=list)
    positions: list[str] = field(default_factory=list)
    modalities: list[str] = field(default_factory=list)
    job_type: str = "Cualquiera"
    min_salary: int | None = None
    salary_label: str = "Sin mínimo"
    # 🤖 AUTO SEARCH (horas entre búsquedas; 0 = manual) y umbral de match
    auto_search_interval_hours: int = 0
    auto_search_min_score: int = 80

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "SearchPreferences":
        if not data:
            return cls()
        valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid)

    @property
    def auto_search_label(self) -> str:
        return {0: "Manual", 6: "Cada 6 horas", 12: "Cada 12 horas", 24: "Diario"}.get(
            self.auto_search_interval_hours, f"Cada {self.auto_search_interval_hours} h"
        )

    def summary(self) -> str:
        auto = (
            f"\n• Auto búsqueda: {self.auto_search_label} (match ≥ {self.auto_search_min_score})"
            if self.auto_search_interval_hours
            else ""
        )
        return (
            f"• Puestos: {', '.join(self.positions) or '—'}\n"
            f"• Ubicaciones: {', '.join(self.locations) or '—'}\n"
            f"• Modalidad: {', '.join(self.modalities) or 'Cualquiera'}\n"
            f"• Jornada: {self.job_type}\n"
            f"• Salario mínimo: {self.salary_label}"
            f"{auto}"
        )
