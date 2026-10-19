"""Settings read from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


def _csv(value: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in value.split(",") if p.strip())


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key, "").strip()
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    db_path: str = "leads.db"
    webhook_secret: str = ""
    timezone: str = "Europe/Moscow"
    dedupe_window_sec: int = 600
    honeypot_fields: tuple[str, ...] = ("website", "hp", "botcheck", "_honeypot")
    max_attempts: int = 8
    backoff_base_sec: int = 30
    backoff_max_sec: int = 3600
    sheets_credentials_file: str = ""
    sheets_spreadsheet_id: str = ""
    sheets_worksheet: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_to: tuple[str, ...] = ()
    smtp_starttls: bool = True

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        g = lambda k, d="": env.get(k, d).strip()  # noqa: E731
        return cls(
            db_path=g("DB_PATH", "leads.db"),
            webhook_secret=g("WEBHOOK_SECRET"),
            timezone=g("TIMEZONE", "Europe/Moscow"),
            dedupe_window_sec=_int(env, "DEDUPE_WINDOW_SEC", 600),
            honeypot_fields=_csv(g("HONEYPOT_FIELDS", "website,hp,botcheck,_honeypot")),
            max_attempts=_int(env, "MAX_ATTEMPTS", 8),
            backoff_base_sec=_int(env, "BACKOFF_BASE_SEC", 30),
            backoff_max_sec=_int(env, "BACKOFF_MAX_SEC", 3600),
            sheets_credentials_file=g("SHEETS_CREDENTIALS_FILE"),
            sheets_spreadsheet_id=g("SHEETS_SPREADSHEET_ID"),
            sheets_worksheet=g("SHEETS_WORKSHEET"),
            telegram_bot_token=g("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=g("TELEGRAM_CHAT_ID"),
            smtp_host=g("SMTP_HOST"),
            smtp_port=_int(env, "SMTP_PORT", 587),
            smtp_user=g("SMTP_USER"),
            smtp_password=env.get("SMTP_PASSWORD", ""),
            smtp_from=g("SMTP_FROM"),
            smtp_to=_csv(g("SMTP_TO")),
            smtp_starttls=g("SMTP_STARTTLS", "1").lower() not in ("0", "false", "no", ""),
        )
