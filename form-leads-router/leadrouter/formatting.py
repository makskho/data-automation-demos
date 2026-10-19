"""Human-readable renderings of a lead: Telegram text, email body, spreadsheet row."""
from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from .normalize import Lead

SOURCE_LABEL = {"tilda": "Tilda", "form": "Форма на сайте", "json": "Форма на сайте (JSON)"}
SHEET_HEADER = ["Дата", "Имя", "Телефон", "Email", "Сообщение", "Источник", "Форма",
                "Страница", "Доп. поля", "ID заявки"]
TELEGRAM_LIMIT = 4096


def local_time(lead: Lead, tz: str) -> datetime:
    return datetime.fromisoformat(lead.created_at).astimezone(ZoneInfo(tz))


def _lines(lead: Lead, tz: str) -> list[tuple[str, str]]:
    pairs = [
        ("Имя", lead.name), ("Телефон", lead.phone), ("Email", lead.email),
        ("Сообщение", lead.message), ("Источник", SOURCE_LABEL.get(lead.source, lead.source)),
        ("Форма", lead.form), ("Страница", lead.page),
    ]
    pairs += [(k, v) for k, v in lead.extra.items()]
    pairs.append(("Время", local_time(lead, tz).strftime("%d.%m.%Y %H:%M")))
    return [(k, v) for k, v in pairs if v]


def telegram_text(lead: Lead, tz: str) -> str:
    body = "\n".join(f"{escape(k)}: {escape(v)}" for k, v in _lines(lead, tz))
    text = "<b>Новая заявка с сайта</b>\n" + body
    return text if len(text) <= TELEGRAM_LIMIT else text[: TELEGRAM_LIMIT - 1] + "…"


def email_subject(lead: Lead) -> str:
    who = lead.name or lead.phone or lead.email
    return f"Новая заявка с сайта: {who}"


def email_body(lead: Lead, tz: str) -> str:
    return "Новая заявка с сайта\n\n" + "\n".join(f"{k}: {v}" for k, v in _lines(lead, tz)) + "\n"


def sheet_row(lead: Lead, tz: str) -> list[str]:
    extra = "; ".join(f"{k}={v}" for k, v in lead.extra.items())
    return [
        local_time(lead, tz).strftime("%Y-%m-%d %H:%M:%S"), lead.name, lead.phone, lead.email,
        lead.message, SOURCE_LABEL.get(lead.source, lead.source), lead.form, lead.page,
        extra, lead.id,
    ]
