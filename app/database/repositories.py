"""Repositorios de acceso a datos (patrón repository).

Aíslan SQL del resto de la aplicación para que los modelos de dominio
y los handlers de Telegram no conozcan detalles de persistencia.
"""
from __future__ import annotations

import json

from app.database.db import Database
from app.models.job import ApplicationStatus, JobAnalysis, JobPosting
from app.models.profile import SearchPreferences, UserProfile


class UserRepository:
    def __init__(self, db: Database):
        self._db = db

    # ----------------------------------------------------------- usuarios
    def upsert_user(self, telegram_id: int, username: str | None, first_name: str | None) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)",
            (telegram_id, username, first_name),
        )
        self._db.execute(
            "UPDATE users SET username = ?, first_name = ? WHERE telegram_id = ?",
            (username, first_name, telegram_id),
        )

    def get_user(self, telegram_id: int) -> dict | None:
        return self._db.fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))

    def get_all_user_ids(self) -> list[int]:
        """IDs de todos los usuarios conocidos (notificaciones de arranque, auto-search)."""
        rows = self._db.fetchall("SELECT telegram_id FROM users")
        return [row["telegram_id"] for row in rows]

    def is_onboarded(self, telegram_id: int) -> bool:
        row = self.get_user(telegram_id)
        return bool(row and row["onboarding_completed"])

    def set_onboarded(self, telegram_id: int) -> None:
        self._db.execute(
            "UPDATE users SET onboarding_completed = 1 WHERE telegram_id = ?",
            (telegram_id,),
        )

    def reset_onboarding(self, telegram_id: int) -> None:
        self._db.execute(
            "UPDATE users SET onboarding_completed = 0 WHERE telegram_id = ?",
            (telegram_id,),
        )

    # ------------------------------------------------------------ perfil
    def save_profile(self, telegram_id: int, profile: UserProfile) -> None:
        self._db.execute(
            """
            INSERT INTO profile (user_id, data, updated_at) VALUES (?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET data = excluded.data,
                                               updated_at = datetime('now')
            """,
            (telegram_id, json.dumps(profile.to_dict(), ensure_ascii=False)),
        )

    def get_profile(self, telegram_id: int) -> UserProfile | None:
        row = self._db.fetchone("SELECT data FROM profile WHERE user_id = ?", (telegram_id,))
        if not row:
            return None
        return UserProfile.from_dict(json.loads(row["data"]))

    # -------------------------------------------------------- preferencias
    def save_preferences(self, telegram_id: int, preferences: SearchPreferences) -> None:
        self._db.execute(
            """
            INSERT INTO search_preferences (user_id, data, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET data = excluded.data,
                                               updated_at = datetime('now')
            """,
            (telegram_id, json.dumps(preferences.to_dict(), ensure_ascii=False)),
        )

    def get_preferences(self, telegram_id: int) -> SearchPreferences | None:
        row = self._db.fetchone(
            "SELECT data FROM search_preferences WHERE user_id = ?", (telegram_id,)
        )
        if not row:
            return None
        return SearchPreferences.from_dict(json.loads(row["data"]))


class PortalRepository:
    """Estado por usuario de cada portal (activado/conectado)."""

    def __init__(self, db: Database):
        self._db = db

    def ensure_defaults(self, user_id: int, portal_names: list[str], demo_enabled: str | None = None) -> None:
        for name in portal_names:
            enabled = 1 if name == demo_enabled else 0
            self._db.execute(
                "INSERT OR IGNORE INTO portals (user_id, name, enabled) VALUES (?, ?, ?)",
                (user_id, name, enabled),
            )

    def set_enabled(self, user_id: int, name: str, enabled: bool) -> None:
        self._db.execute(
            "UPDATE portals SET enabled = ? WHERE user_id = ? AND name = ?",
            (int(enabled), user_id, name),
        )

    def set_connected(self, user_id: int, name: str, connected: bool) -> None:
        self._db.execute(
            """
            UPDATE portals SET connected = ?, connected_at = datetime('now')
            WHERE user_id = ? AND name = ?
            """,
            (int(connected), user_id, name),
        )

    def get(self, user_id: int, name: str) -> dict | None:
        return self._db.fetchone(
            "SELECT * FROM portals WHERE user_id = ? AND name = ?", (user_id, name)
        )

    def all(self, user_id: int) -> dict[str, dict]:
        rows = self._db.fetchall("SELECT * FROM portals WHERE user_id = ?", (user_id,))
        return {row["name"]: row for row in rows}

    def enabled_names(self, user_id: int) -> list[str]:
        rows = self._db.fetchall(
            "SELECT name FROM portals WHERE user_id = ? AND enabled = 1", (user_id,)
        )
        return [row["name"] for row in rows]


class JobRepository:
    """Ofertas encontradas, con score, análisis y estado del tracker."""

    def __init__(self, db: Database):
        self._db = db

    def add_job(self, user_id: int, job: JobPosting) -> int | None:
        """Inserta una oferta si no es duplicada. Devuelve el id o None.

        Usa RETURNING: si el INSERT fue ignorado (duplicado) no devuelve fila.
        """
        rows = self._db.execute_returning(
            """
            INSERT OR IGNORE INTO jobs
                (user_id, dedupe_key, portal, title, company, location,
                 salary, modality, url, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                user_id, job.dedupe_key(), job.portal, job.title, job.company,
                job.location, job.salary, job.modality, job.url, job.description,
            ),
        )
        return int(rows[0][0]) if rows else None

    def get(self, job_id: int, user_id: int | None = None) -> dict | None:
        if user_id is None:
            return self._db.fetchone("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return self._db.fetchone(
            "SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user_id)
        )

    def update_analysis(self, job_id: int, analysis: JobAnalysis) -> None:
        self._db.execute(
            "UPDATE jobs SET score = ?, analysis = ? WHERE id = ?",
            (analysis.score, json.dumps(analysis.to_dict(), ensure_ascii=False), job_id),
        )

    def update_description(self, job_id: int, description: str) -> None:
        self._db.execute(
            "UPDATE jobs SET description = ? WHERE id = ?", (description, job_id)
        )

    def set_status(self, job_id: int, status: ApplicationStatus) -> None:
        self._db.execute(
            "UPDATE jobs SET status = ? WHERE id = ?", (status.value, job_id)
        )

    def list_for_user(
        self,
        user_id: int,
        *,
        statuses: list[ApplicationStatus] | None = None,
        limit: int = 50,
    ) -> list[dict]:
        query = "SELECT * FROM jobs WHERE user_id = ?"
        params: list = [user_id]
        if statuses:
            query += f" AND status IN ({','.join('?' for _ in statuses)})"
            params += [s.value for s in statuses]
        query += " ORDER BY score IS NULL, score DESC, id DESC LIMIT ?"
        params.append(limit)
        return self._db.fetchall(query, tuple(params))

    def unanalyzed(self, user_id: int, limit: int = 50) -> list[dict]:
        return self._db.fetchall(
            "SELECT * FROM jobs WHERE user_id = ? AND score IS NULL "
            "AND status != 'IGNORED' ORDER BY id LIMIT ?",
            (user_id, limit),
        )


class ApplicationRepository:
    """Registro de postulaciones enviadas."""

    def __init__(self, db: Database):
        self._db = db

    def record(
        self,
        user_id: int,
        job_id: int,
        *,
        answers: str = "",
        method: str = "assisted",
        confirmation: str = "",
    ) -> int:
        rows = self._db.execute_returning(
            """
            INSERT INTO applications (user_id, job_id, answers, method, confirmation)
            VALUES (?, ?, ?, ?, ?)
            RETURNING id
            """,
            (user_id, job_id, answers, method, confirmation),
        )
        return int(rows[0][0])

    def list_for_user(self, user_id: int, limit: int = 50) -> list[dict]:
        return self._db.fetchall(
            """
            SELECT a.id AS application_id, a.sent_at, a.method, a.answers,
                   j.id AS job_id, j.title, j.company, j.portal, j.url, j.score, j.status
            FROM applications a
            JOIN jobs j ON j.id = a.job_id
            WHERE a.user_id = ?
            ORDER BY a.id DESC LIMIT ?
            """,
            (user_id, limit),
        )


def job_row_to_posting(row: dict) -> JobPosting:
    return JobPosting(
        title=row["title"],
        company=row["company"],
        location=row.get("location", ""),
        salary=row.get("salary", ""),
        modality=row.get("modality", ""),
        url=row.get("url", ""),
        portal=row.get("portal", ""),
        description=row.get("description", ""),
    )


def job_row_to_analysis(row: dict) -> JobAnalysis | None:
    if not row.get("analysis"):
        return None
    try:
        return JobAnalysis.from_dict(json.loads(row["analysis"]))
    except (ValueError, TypeError):
        return None
