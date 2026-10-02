"""SQLite migrations and small transaction boundaries for background runs.

One connection per operation avoids sharing connections between request threads
and the worker. WAL allows readers to inspect progress while writes checkpoint.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def json_dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(str(self.path), timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    title TEXT NOT NULL, description TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    name TEXT NOT NULL COLLATE NOCASE, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, UNIQUE(user_id, name)
                );
                CREATE TABLE IF NOT EXISTS profile_versions (
                    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL, criteria TEXT NOT NULL, changelog TEXT NOT NULL,
                    source TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(profile_id, version)
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    mode TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL,
                    iteration INTEGER NOT NULL DEFAULT 0, max_iterations INTEGER NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    input_json TEXT NOT NULL, state_json TEXT NOT NULL,
                    result_json TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id),
                    stage TEXT NOT NULL, message TEXT NOT NULL, iteration INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS iterations (
                    run_id TEXT NOT NULL REFERENCES runs(id), iteration INTEGER NOT NULL,
                    html TEXT NOT NULL, report_json TEXT NOT NULL, reward REAL NOT NULL,
                    created_at TEXT NOT NULL, PRIMARY KEY(run_id, iteration)
                );
                CREATE TABLE IF NOT EXISTS rate_limits (
                    bucket TEXT PRIMARY KEY, attempts INTEGER NOT NULL, reset_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(user_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_events_run ON run_events(run_id, id);
                PRAGMA user_version=1;
            ''')

    def one(self, sql, parameters=()):
        with self.connection() as connection:
            row = connection.execute(sql, parameters).fetchone()
        return dict(row) if row else None

    def all(self, sql, parameters=()):
        with self.connection() as connection:
            return [dict(row) for row in connection.execute(sql, parameters).fetchall()]

    def execute(self, sql, parameters=()):
        with self.connection() as connection:
            connection.execute(sql, parameters)
