"""The real sink classes against fakes: HTTP transport, SMTP server, worksheet."""
from __future__ import annotations

import httpx
import pytest

from leadrouter import formatting
from leadrouter.config import Settings
from leadrouter.normalize import Lead
from leadrouter.sinks import EmailSink, SheetsSink, TelegramSink, build_sinks

LEAD = Lead(id="abc123", created_at="2026-10-19T11:32:05+00:00", name="Анна <b>Петрова</b>",
            phone="+79991234567", email="anna@example.com", message="Нужен лендинг",
            source="tilda", form="form123456", extra={"Город": "Казань"})


def test_telegram_posts_escaped_html_to_bot_api():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["json"] = str(request.url), request.read().decode()
        return httpx.Response(200, json={"ok": True})

    sink = TelegramSink("123:TOKEN", "-1001", "Europe/Moscow",
                        httpx.Client(transport=httpx.MockTransport(handler)))
    sink.send(LEAD)
    assert seen["url"] == "https://api.telegram.org/bot123:TOKEN/sendMessage"
    import json

    payload = json.loads(seen["json"])
    assert payload["chat_id"] == "-1001" and payload["parse_mode"] == "HTML"
    assert "Анна &lt;b&gt;Петрова&lt;/b&gt;" in payload["text"]  # user input cannot inject markup
    assert "Время: 19.10.2026 14:32" in payload["text"]  # UTC -> Moscow


@pytest.mark.parametrize("status", [400, 429, 500])
def test_telegram_http_error_raises_without_leaking_token(status):
    sink = TelegramSink("123:TOKEN", "1", "UTC", httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(status, text="nope"))))
    with pytest.raises(RuntimeError, match=f"HTTP {status}") as err:
        sink.send(LEAD)
    assert "TOKEN" not in str(err.value)


def test_telegram_network_error_does_not_leak_token():
    def boom(request):
        raise httpx.ConnectError("cannot connect to https://api.telegram.org/bot123:TOKEN/x")

    sink = TelegramSink("123:TOKEN", "1", "UTC", httpx.Client(transport=httpx.MockTransport(boom)))
    with pytest.raises(RuntimeError) as err:
        sink.send(LEAD)
    assert "TOKEN" not in str(err.value)


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.log, self.messages = host, port, [], []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.log.append("starttls")

    def login(self, user, password):
        self.log.append(("login", user, password))

    def send_message(self, msg):
        self.messages.append(msg)


def test_email_sink_sends_message_over_starttls():
    FakeSMTP.instances.clear()
    sink = EmailSink("smtp.example.com", 587, "bot@example.com", "pw", "bot@example.com",
                     ("boss@example.com", "sales@example.com"), "Europe/Moscow",
                     smtp_factory=FakeSMTP)
    sink.send(LEAD)
    smtp = FakeSMTP.instances[0]
    assert smtp.log == ["starttls", ("login", "bot@example.com", "pw")]
    msg = smtp.messages[0]
    assert msg["To"] == "boss@example.com, sales@example.com"
    assert msg["Reply-To"] == "anna@example.com"
    assert msg["Subject"] == "Новая заявка с сайта: Анна <b>Петрова</b>"
    body = msg.get_content()
    assert "Телефон: +79991234567" in body and "Город: Казань" in body


def test_email_sink_port_465_uses_ssl_class_without_starttls():
    FakeSMTP.instances.clear()
    sink = EmailSink("h", 465, "", "", "a@b.ru", ("c@d.ru",), "UTC", smtp_factory=FakeSMTP)
    sink.send(LEAD)
    assert FakeSMTP.instances[0].log == []  # no starttls, no login without a user


class FakeWorksheet:
    def __init__(self):
        self.rows = []

    def append_row(self, values, value_input_option=None):
        self.rows.append((values, value_input_option))


def test_sheets_sink_appends_row_as_raw():
    ws = FakeWorksheet()
    SheetsSink(lambda: ws, "Europe/Moscow").send(LEAD)
    row, option = ws.rows[0]
    assert option == "RAW"  # "+7999..." stays text
    assert row == ["2026-10-19 14:32:05", "Анна <b>Петрова</b>", "+79991234567", "anna@example.com",
                   "Нужен лендинг", "Tilda", "form123456", "", "Город=Казань", "abc123"]
    assert len(row) == len(formatting.SHEET_HEADER)


def test_build_sinks_enables_only_configured_channels():
    assert build_sinks(Settings()) == []
    s = Settings(telegram_bot_token="1:x", telegram_chat_id="5", smtp_host="h",
                 smtp_from="a@b.ru", smtp_to=("c@d.ru",))
    assert [x.name for x in build_sinks(s)] == ["telegram", "email"]
    s2 = Settings(sheets_credentials_file="sa.json", sheets_spreadsheet_id="id")
    assert [x.name for x in build_sinks(s2)] == ["sheets"]  # lazy: gspread is not touched here


def test_settings_from_env():
    s = Settings.from_env({"SMTP_TO": "a@b.ru, c@d.ru", "SMTP_PORT": "465", "SMTP_STARTTLS": "0",
                           "HONEYPOT_FIELDS": "trap", "DEDUPE_WINDOW_SEC": "120"})
    assert s.smtp_to == ("a@b.ru", "c@d.ru") and s.smtp_port == 465 and not s.smtp_starttls
    assert s.honeypot_fields == ("trap",) and s.dedupe_window_sec == 120
