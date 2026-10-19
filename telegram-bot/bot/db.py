"""Хранилище заявок в SQLite (стандартный модуль sqlite3, без ORM)."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    username   TEXT,
    name       TEXT NOT NULL,
    phone      TEXT NOT NULL,
    task       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_user_time ON leads (user_id, created_at);
"""


@dataclass(frozen=True)
class Lead:
    id: int
    user_id: int
    username: str | None
    name: str
    phone: str
    task: str
    created_at: datetime  # UTC


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class LeadRepo:
    def __init__(self, path: str):
        self.path = path
        with closing(self._connect()) as conn, conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _to_lead(row: sqlite3.Row) -> Lead:
        return Lead(
            id=row["id"],
            user_id=row["user_id"],
            username=row["username"],
            name=row["name"],
            phone=row["phone"],
            task=row["task"],
            created_at=_parse(row["created_at"]),
        )

    def add(
        self,
        user_id: int,
        username: str | None,
        name: str,
        phone: str,
        task: str,
        created_at: datetime | None = None,
    ) -> Lead:
        created = (created_at or _now()).astimezone(timezone.utc)
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "INSERT INTO leads (user_id, username, name, phone, task, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, username, name, phone, task, created.isoformat()),
            )
            row = conn.execute("SELECT * FROM leads WHERE id = ?", (cur.lastrowid,)).fetchone()
        return self._to_lead(row)

    def all(self) -> list[Lead]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM leads ORDER BY id").fetchall()
        return [self._to_lead(r) for r in rows]

    def count(self) -> int:
        with closing(self._connect()) as conn:
            return conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]

    def last_lead_time(self, user_id: int) -> datetime | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT created_at FROM leads WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        return _parse(row["created_at"]) if row else None

    def flood_wait(self, user_id: int, minutes: int, now: datetime | None = None) -> timedelta | None:
        """Сколько ещё ждать до новой заявки; None, если можно отправлять."""
        if minutes <= 0:
            return None
        last = self.last_lead_time(user_id)
        if last is None:
            return None
        remaining = last + timedelta(minutes=minutes) - (now or _now())
        return remaining if remaining > timedelta(0) else None
