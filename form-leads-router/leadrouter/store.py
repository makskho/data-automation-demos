"""SQLite: duplicate keys, saved leads and the delivery outbox."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Iterator, Sequence

from .normalize import Lead

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY, created_at REAL NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT NOT NULL REFERENCES leads(id),
    sink TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | done | dead
    attempts INTEGER NOT NULL DEFAULT 0,
    next_at REAL NOT NULL,
    last_error TEXT NOT NULL DEFAULT '',
    updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS outbox_due ON outbox(status, next_at);
"""


@dataclass
class OutboxRow:
    id: int
    lead_id: str
    sink: str
    status: str
    attempts: int
    next_at: float
    last_error: str


class Store:
    def __init__(self, path: str):
        self.path = path
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # --- duplicates -------------------------------------------------
    def claim(self, keys: Sequence[str], now: float, window: float) -> bool:
        """Atomically: False if any key was seen within `window` seconds, else remember all."""
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                c.execute("DELETE FROM seen WHERE ts < ?", (now - window,))
                marks = ",".join("?" * len(keys))
                hit = c.execute(f"SELECT 1 FROM seen WHERE key IN ({marks}) LIMIT 1",
                                tuple(keys)).fetchone()
                if hit:
                    c.execute("COMMIT")
                    return False
                c.executemany("INSERT OR REPLACE INTO seen(key, ts) VALUES (?, ?)",
                              [(k, now) for k in keys])
                c.execute("COMMIT")
                return True
            except Exception:
                c.execute("ROLLBACK")
                raise

    # --- leads and outbox -------------------------------------------
    def add_lead(self, lead: Lead, sinks: Sequence[str], now: float) -> list[int]:
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                c.execute("INSERT INTO leads(id, created_at, payload) VALUES (?, ?, ?)",
                          (lead.id, now, json.dumps(asdict(lead), ensure_ascii=False)))
                ids = []
                for sink in sinks:
                    cur = c.execute(
                        "INSERT INTO outbox(lead_id, sink, next_at, updated_at) VALUES (?,?,?,?)",
                        (lead.id, sink, now, now))
                    ids.append(cur.lastrowid)
                c.execute("COMMIT")
                return ids
            except Exception:
                c.execute("ROLLBACK")
                raise

    def get_lead(self, lead_id: str) -> Lead:
        with self._conn() as c:
            row = c.execute("SELECT payload FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if row is None:
            raise KeyError(lead_id)
        return Lead(**json.loads(row["payload"]))

    def count_leads(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM leads").fetchone()[0]

    def get_outbox(self, row_id: int) -> OutboxRow:
        with self._conn() as c:
            row = c.execute("SELECT * FROM outbox WHERE id = ?", (row_id,)).fetchone()
        return _row(row)

    def due(self, now: float, force: bool = False) -> list[OutboxRow]:
        sql = "SELECT * FROM outbox WHERE status = 'pending'"
        args: tuple = ()
        if not force:
            sql += " AND next_at <= ?"
            args = (now,)
        with self._conn() as c:
            return [_row(r) for r in c.execute(sql + " ORDER BY id", args)]

    def list_outbox(self, status: str | None = None) -> list[OutboxRow]:
        sql, args = "SELECT * FROM outbox", ()
        if status:
            sql, args = sql + " WHERE status = ?", (status,)
        with self._conn() as c:
            return [_row(r) for r in c.execute(sql + " ORDER BY id", args)]

    def mark_done(self, row_id: int, now: float) -> None:
        with self._conn() as c:
            c.execute("UPDATE outbox SET status='done', attempts=attempts+1, last_error='',"
                      " updated_at=? WHERE id=?", (now, row_id))

    def mark_failed(self, row_id: int, error: str, next_at: float, dead: bool, now: float) -> None:
        with self._conn() as c:
            c.execute("UPDATE outbox SET status=?, attempts=attempts+1, last_error=?, next_at=?,"
                      " updated_at=? WHERE id=?",
                      ("dead" if dead else "pending", error[:500], next_at, now, row_id))

    def stats(self) -> dict[str, int]:
        with self._conn() as c:
            rows = c.execute("SELECT status, COUNT(*) AS n FROM outbox GROUP BY status")
            out = {"pending": 0, "done": 0, "dead": 0}
            out.update({r["status"]: r["n"] for r in rows})
            return out


def _row(r: sqlite3.Row) -> OutboxRow:
    return OutboxRow(r["id"], r["lead_id"], r["sink"], r["status"], r["attempts"],
                     r["next_at"], r["last_error"])
