"""Conexión y esquema de la base de datos SQLite.

Tablas: users, profile, search_preferences (config), portals (estado por
usuario), jobs (ofertas con score/estado) y applications (postulaciones).

NUNCA se almacenan contraseñas de portales en la base de datos.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id          INTEGER PRIMARY KEY,
    username             TEXT,
    first_name           TEXT,
    onboarding_completed INTEGER NOT NULL DEFAULT 0,
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS profile (
    user_id    INTEGER PRIMARY KEY REFERENCES users(telegram_id),
    data       TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS search_preferences (
    user_id    INTEGER PRIMARY KEY REFERENCES users(telegram_id),
    data       TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS portals (
    user_id      INTEGER NOT NULL REFERENCES users(telegram_id),
    name         TEXT NOT NULL,
    enabled      INTEGER NOT NULL DEFAULT 0,
    connected    INTEGER NOT NULL DEFAULT 0,
    connected_at TEXT,
    PRIMARY KEY (user_id, name)
);

CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(telegram_id),
    dedupe_key  TEXT NOT NULL,
    portal      TEXT NOT NULL,
    title       TEXT NOT NULL,
    company     TEXT NOT NULL,
    location    TEXT NOT NULL DEFAULT '',
    salary      TEXT NOT NULL DEFAULT '',
    modality    TEXT NOT NULL DEFAULT '',
    url         TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    score       INTEGER,
    analysis    TEXT,
    status      TEXT NOT NULL DEFAULT 'FOUND',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, dedupe_key)
);

CREATE TABLE IF NOT EXISTS applications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(telegram_id),
    job_id       INTEGER NOT NULL REFERENCES jobs(id),
    answers      TEXT NOT NULL DEFAULT '',
    method       TEXT NOT NULL DEFAULT 'assisted',
    confirmation TEXT NOT NULL DEFAULT '',
    sent_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class Database:
    """Wrapper mínimo y thread-safe sobre sqlite3."""

    def __init__(self, path: str | Path):
        self._path = str(path)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")

    def init(self) -> None:
        self.connect()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Ejecuta una sentencia (con commit) y devuelve el cursor."""
        self.connect()
        with self._lock:
            cursor = self._conn.execute(query, params)
            self._conn.commit()
            return cursor

    def execute_returning(self, query: str, params: tuple = ()) -> list[tuple]:
        """INSERT/UPDATE con cláusula RETURNING.

        Es necesario consumir las filas ANTES de confirmar, o SQLite falla
        con "cannot commit transaction - SQL statements in progress".
        """
        self.connect()
        with self._lock:
            cursor = self._conn.execute(query, params)
            rows = cursor.fetchall()
            self._conn.commit()
            return rows

    def fetchone(self, query: str, params: tuple = ()) -> dict | None:
        self.connect()
        with self._lock:
            row = self._conn.execute(query, params).fetchone()
        return dict(row) if row else None

    def fetchall(self, query: str, params: tuple = ()) -> list[dict]:
        self.connect()
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # Conveniencia para pruebas
    def raw(self) -> sqlite3.Connection:
        self.connect()
        return self._conn

