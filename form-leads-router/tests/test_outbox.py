"""A failing channel must not lose the lead: outbox -> backoff -> retry."""
from __future__ import annotations

import pytest

from conftest import TILDA_FORM, FakeSink
from leadrouter import cli
from leadrouter.router import LeadRouter
from leadrouter.server import create_app


def test_one_sink_down_lead_is_kept_and_retried(client, app, sinks, store, clock):
    sinks["telegram"].fail_times = 1  # first call fails, then recovers
    resp = client.post("/webhook", json={"name": "Анна", "phone": "89991234567"})
    assert resp.status_code == 200  # the visitor still sees success
    assert resp.get_json()["delivery"] == {"sheets": "done", "telegram": "pending", "email": "done"}
    assert len(sinks["sheets"].sent) == 1 and len(sinks["email"].sent) == 1
    assert not sinks["telegram"].sent
    pending = store.list_outbox("pending")
    assert [(r.sink, r.attempts) for r in pending] == [("telegram", 1)]
    assert "telegram is down" in pending[0].last_error

    router: LeadRouter = app.config["ROUTER"]
    assert router.retry_due().due == 0  # backoff has not elapsed yet
    clock.advance(31)  # base backoff is 30 s
    report = router.retry_due()
    assert (report.due, report.sent, report.failed) == (1, 1, 0)
    assert len(sinks["telegram"].sent) == 1
    assert sinks["telegram"].sent[0].phone == "+79991234567"
    assert store.stats() == {"pending": 0, "done": 3, "dead": 0}
    assert len(sinks["sheets"].sent) == 1  # the healthy sinks were not repeated


def test_backoff_grows_exponentially_and_gives_up(settings, make_settings, store, clock):
    sink = FakeSink("telegram", fail_times=None)  # always down
    cfg = make_settings(max_attempts=4, backoff_base_sec=30, backoff_max_sec=100)
    router = LeadRouter(store, [sink], cfg, clock)
    router.handle({"name": "A", "email": "a@example.com"}, is_json=True)
    delays = []
    for _ in range(3):
        row = store.list_outbox()[0]
        delays.append(row.next_at - clock())
        clock.advance(row.next_at - clock())
        router.retry_due()
    assert delays == [30, 60, 100]  # 30, 60, capped at 100 (would be 120)
    last = store.list_outbox()[0]
    assert (last.status, last.attempts) == ("dead", 4)
    assert router.retry_due().due == 0  # dead rows are not retried
    assert router.retry_due(force=True).due == 0
    assert store.get_lead(last.lead_id).email == "a@example.com"  # the lead itself is still there


def test_force_ignores_backoff(app, sinks, client, store):
    sinks["email"].fail_times = 1
    client.post("/webhook", data=TILDA_FORM)
    report = app.config["ROUTER"].retry_due(force=True)
    assert (report.due, report.sent) == (1, 1)


def test_all_sinks_down_lead_survives_restart(settings, store, clock):
    sinks = [FakeSink("sheets", None), FakeSink("telegram", None), FakeSink("email", None)]
    app = create_app(settings, sinks, store, clock)
    assert app.test_client().post("/webhook", data=TILDA_FORM).status_code == 200
    assert store.stats()["pending"] == 3
    # "restart": new objects over the same SQLite file, channels are healthy again
    healthy = [FakeSink(n) for n in ("sheets", "telegram", "email")]
    router = LeadRouter(type(store)(settings.db_path), healthy, settings, clock)
    clock.advance(60)
    assert router.retry_due().sent == 3
    assert all(len(s.sent) == 1 and s.sent[0].name == "Анна Петрова" for s in healthy)


def test_cli_retry_and_status(settings, store, clock):
    flaky = FakeSink("telegram", fail_times=1)
    router = LeadRouter(store, [flaky], settings, clock)
    router.handle({"name": "A", "phone": "+79991112233"}, is_json=True)
    lines: list[str] = []

    assert cli.main(["status"], lambda: router, lines.append) == 0
    assert lines[0] == "outbox: pending=1, done=0, dead=0"
    assert "telegram is down" in lines[1]

    lines.clear()
    assert cli.main(["retry"], lambda: router, lines.append) == 0
    assert lines == ["retry: due=0 sent=0 failed=0 dead=0"]  # too early
    assert cli.main(["retry", "--force"], lambda: router, lines.append) == 0
    assert lines[-1] == "retry: due=1 sent=1 failed=0 dead=0"
    assert store.stats()["done"] == 1


def test_cli_retry_exit_code_is_nonzero_when_still_failing(settings, store, clock):
    router = LeadRouter(store, [FakeSink("telegram", None)], settings, clock)
    router.handle({"name": "A", "phone": "+79991112233"}, is_json=True)
    assert cli.main(["retry", "--force"], lambda: router, lambda s: None) == 1


@pytest.mark.parametrize("sink_name", ["sheets", "telegram", "email"])
def test_unconfigured_sink_in_outbox_is_retried_not_crashing(settings, store, clock, sink_name):
    LeadRouter(store, [FakeSink(sink_name, None)], settings, clock).handle(
        {"name": "A", "phone": "+79991112233"}, is_json=True)
    router = LeadRouter(store, [], settings, clock)  # the channel was removed from .env
    clock.advance(60)
    assert router.retry_due().failed == 1
    assert "not configured" in store.list_outbox()[0].last_error
