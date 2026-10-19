"""Delivery channels. Each sink has a `name` and `send(lead)`; any exception means 'not delivered'."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any, Callable, Protocol

import httpx

from . import formatting
from .config import Settings
from .normalize import Lead


class Sink(Protocol):
    name: str

    def send(self, lead: Lead) -> None: ...


class SheetsSink:
    """Append one row to a Google Sheet. `worksheet_provider` returns a gspread Worksheet."""

    name = "sheets"

    def __init__(self, worksheet_provider: Callable[[], Any], tz: str):
        self._provider = worksheet_provider
        self._tz = tz

    def send(self, lead: Lead) -> None:
        ws = self._provider()
        # RAW keeps "+7999..." as text instead of letting Sheets parse it as a formula/number.
        ws.append_row(formatting.sheet_row(lead, self._tz), value_input_option="RAW")


def gspread_worksheet_provider(credentials_file: str, spreadsheet_id: str,
                               worksheet: str = "") -> Callable[[], Any]:
    """Lazy, cached connection through a service-account JSON (imports gspread on first use)."""
    cache: dict[str, Any] = {}

    def provider() -> Any:
        if "ws" not in cache:
            import gspread

            client = gspread.service_account(filename=credentials_file)
            book = client.open_by_key(spreadsheet_id)
            ws = book.worksheet(worksheet) if worksheet else book.sheet1
            if not ws.get_values("A1:A1"):
                ws.append_row(formatting.SHEET_HEADER, value_input_option="RAW")
            cache["ws"] = ws
        return cache["ws"]

    return provider


class TelegramSink:
    name = "telegram"

    def __init__(self, token: str, chat_id: str, tz: str, client: httpx.Client | None = None):
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._chat_id = chat_id
        self._tz = tz
        self._client = client or httpx.Client(timeout=10.0)

    def send(self, lead: Lead) -> None:
        payload = {"chat_id": self._chat_id, "text": formatting.telegram_text(lead, self._tz),
                   "parse_mode": "HTML", "disable_web_page_preview": True}
        try:
            resp = self._client.post(self._url, json=payload)
        except httpx.HTTPError as exc:  # the message of httpx errors may contain the URL = token
            raise RuntimeError(f"telegram: {type(exc).__name__}") from None
        if resp.status_code != 200:
            raise RuntimeError(f"telegram: HTTP {resp.status_code} {resp.text[:200]}")
        if not resp.json().get("ok"):
            raise RuntimeError("telegram: ok=false")


class EmailSink:
    name = "email"

    def __init__(self, host: str, port: int, user: str, password: str, sender: str,
                 recipients: tuple[str, ...], tz: str, starttls: bool = True,
                 smtp_factory: Callable[..., Any] | None = None, timeout: float = 15.0):
        self._host, self._port, self._user, self._password = host, port, user, password
        self._sender, self._recipients, self._tz = sender, recipients, tz
        self._starttls, self._timeout = starttls, timeout
        self._factory = smtp_factory or (smtplib.SMTP_SSL if port == 465 else smtplib.SMTP)

    def build_message(self, lead: Lead) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = formatting.email_subject(lead)
        msg["From"] = self._sender
        msg["To"] = ", ".join(self._recipients)
        if lead.email:
            msg["Reply-To"] = lead.email
        msg.set_content(formatting.email_body(lead, self._tz))
        return msg

    def send(self, lead: Lead) -> None:
        msg = self.build_message(lead)
        with self._factory(self._host, self._port, timeout=self._timeout) as smtp:
            if self._starttls and self._port != 465:
                smtp.starttls()
            if self._user:
                smtp.login(self._user, self._password)
            smtp.send_message(msg)


def build_sinks(s: Settings) -> list[Sink]:
    """Only configured channels are switched on."""
    sinks: list[Sink] = []
    if s.sheets_credentials_file and s.sheets_spreadsheet_id:
        provider = gspread_worksheet_provider(s.sheets_credentials_file, s.sheets_spreadsheet_id,
                                              s.sheets_worksheet)
        sinks.append(SheetsSink(provider, s.timezone))
    if s.telegram_bot_token and s.telegram_chat_id:
        sinks.append(TelegramSink(s.telegram_bot_token, s.telegram_chat_id, s.timezone))
    if s.smtp_host and s.smtp_from and s.smtp_to:
        sinks.append(EmailSink(s.smtp_host, s.smtp_port, s.smtp_user, s.smtp_password,
                               s.smtp_from, s.smtp_to, s.timezone, s.smtp_starttls))
    return sinks
