"""Modelos relacionados con ofertas de trabajo y postulaciones."""
from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


class ApplicationStatus(str, enum.Enum):
    # Estados internos previos a la postulación
    FOUND = "FOUND"
    IGNORED = "IGNORED"
    # Tracker oficial
    SAVED = "SAVED"
    ANALYZED = "ANALYZED"
    READY = "READY"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"
    WITHDRAWN = "WITHDRAWN"


STATUS_LABELS = {
    ApplicationStatus.FOUND: ("🆕", "Encontrada"),
    ApplicationStatus.IGNORED: ("🚫", "Ignorada"),
    ApplicationStatus.SAVED: ("⭐", "Guardada"),
    ApplicationStatus.ANALYZED: ("🔍", "Analizada"),
    ApplicationStatus.READY: ("✅", "Lista para postular"),
    ApplicationStatus.APPLIED: ("🟡", "POSTULADO"),
    ApplicationStatus.REJECTED: ("🔴", "Rechazada"),
    ApplicationStatus.INTERVIEW: ("🎤", "Entrevista"),
    ApplicationStatus.OFFER: ("🏆", "Oferta"),
    ApplicationStatus.WITHDRAWN: ("⚪", "Retirada"),
}


@dataclass
class JobPosting:
    """Representación normalizada de una oferta encontrada en un portal."""

    title: str
    company: str
    location: str = ""
    salary: str = ""
    modality: str = ""
    url: str = ""
    portal: str = ""
    description: str = ""

    def dedupe_key(self) -> str:
        """Clave heurística para evitar duplicados entre portales."""
        return f"{self.title.strip().lower()}::{self.company.strip().lower()}"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class JobAnalysis:
    """Resultado estructurado del análisis de compatibilidad (Groq)."""

    score: int
    recommendation: str
    reason: str
    matching_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    experience_match: str = ""
    location_match: bool = False
    salary_match: bool = False

    @property
    def classification(self) -> str:
        if self.score >= 90:
            return "Excelente"
        if self.score >= 80:
            return "Muy buena"
        if self.score >= 70:
            return "Buena"
        if self.score >= 60:
            return "Regular"
        return "Baja"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "JobAnalysis":
        valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid)


@dataclass
class Application:
    """Registro de una postulación enviada (tracker)."""

    job_id: int
    status: ApplicationStatus = ApplicationStatus.APPLIED
    answers: str = ""
    method: str = "assisted"  # "auto" | "assisted" | "manual"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
