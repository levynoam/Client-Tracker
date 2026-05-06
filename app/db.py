"""SQLite connection and schema management."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import Flask, current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL UNIQUE,
    archived  INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clients (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id  INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    rate        REAL NOT NULL CHECK (rate >= 0),
    archived    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (profile_id, name)
);
CREATE INDEX IF NOT EXISTS idx_clients_profile ON clients(profile_id);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id  INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    client_id   INTEGER NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    date        TEXT NOT NULL,             -- YYYY-MM-DD (local date)
    hours       REAL NOT NULL CHECK (hours > 0) DEFAULT 1,
    rate        REAL NOT NULL CHECK (rate >= 0),  -- snapshot at creation
    notes       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sessions_profile_date ON sessions(profile_id, date);
CREATE INDEX IF NOT EXISTS idx_sessions_client ON sessions(client_id);

CREATE TABLE IF NOT EXISTS billing_status (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id    INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    client_id     INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    year          INTEGER NOT NULL,
    month         INTEGER NOT NULL,
    invoice_sent  INTEGER NOT NULL DEFAULT 0,
    invoice_paid  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (profile_id, client_id, year, month)
);
CREATE INDEX IF NOT EXISTS idx_billing_status_lookup
    ON billing_status(profile_id, year, month);
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        g.db = conn
    return g.db


def close_db(_e=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()


def init_app(app: Flask) -> None:
    app.teardown_appcontext(close_db)

    # Ensure DB & schema exist at startup.
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    with app.app_context():
        init_db()
