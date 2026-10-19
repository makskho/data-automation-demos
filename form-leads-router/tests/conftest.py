from __future__ import annotations

import dataclasses

import pytest

from leadrouter.config import Settings
from leadrouter.server import create_app
from leadrouter.store import Store

T0 = 1_792_000_000.0  # fixed "now" (2026-10-14 ...), seconds


class FakeClock:
    def __init__(self, now: float = T0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeSink:
    """Records leads; fails the first `fail_times` calls (or always when fail_times=None)."""

    def __init__(self, name: str, fail_times: int | None = 0):
        self.name = name
        self.fail_times = fail_times
        self.sent: list = []
        self.calls = 0

    def send(self, lead) -> None:
        self.calls += 1
        if self.fail_times is None or self.calls <= self.fail_times:
            raise ConnectionError(f"{self.name} is down")
        self.sent.append(lead)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(db_path=str(tmp_path / "leads.db"), timezone="Europe/Moscow")


@pytest.fixture
def make_settings(settings):
    return lambda **kw: dataclasses.replace(settings, **kw)


@pytest.fixture
def sinks() -> dict[str, FakeSink]:
    return {n: FakeSink(n) for n in ("sheets", "telegram", "email")}


@pytest.fixture
def store(settings) -> Store:
    return Store(settings.db_path)


@pytest.fixture
def app(settings, sinks, store, clock):
    return create_app(settings, list(sinks.values()), store, clock)


@pytest.fixture
def client(app):
    return app.test_client()


TILDA_FORM = {
    "Name": "Анна Петрова",
    "Phone": "8 (999) 123-45-67",
    "Email": "Anna.Petrova@Example.com",
    "Textarea": "Нужен лендинг на Тильде, срок — две недели.",
    "tranid": "1234567:8901234",
    "formid": "form123456",
    "COOKIES": "_ga=GA1.2.3",
}
