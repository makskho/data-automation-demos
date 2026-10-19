"""Lead pipeline: spam check -> validation -> duplicate check -> outbox -> fan-out -> retry."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .config import Settings
from .normalize import Lead, build_lead, detect_source, is_honeypot_hit
from .sinks import Sink
from .store import OutboxRow, Store

log = logging.getLogger("leadrouter")


@dataclass
class Result:
    status: str  # accepted | test | spam | duplicate
    lead_id: str = ""
    delivery: dict[str, str] = field(default_factory=dict)  # sink -> done | pending | dead


@dataclass
class RetryReport:
    due: int = 0
    sent: int = 0
    failed: int = 0
    dead: int = 0


class LeadRouter:
    def __init__(self, store: Store, sinks: Sequence[Sink], settings: Settings,
                 clock: Callable[[], float] = time.time):
        self.store, self.settings, self.clock = store, settings, clock
        self.sinks: dict[str, Sink] = {s.name: s for s in sinks}

    def handle(self, raw: Mapping[str, Any], is_json: bool = False) -> Result:
        """Raises ValidationError for a bad lead. Every other outcome is a Result."""
        if str(raw.get("test", "")).strip() == "test":  # Tilda ping when the webhook is saved
            return Result("test")
        if is_honeypot_hit(raw, self.settings.honeypot_fields):
            log.info("honeypot hit, lead dropped")
            return Result("spam")
        now = self.clock()
        lead = build_lead(raw, detect_source(raw, is_json), now, self.settings.honeypot_fields)
        if not self.store.claim(lead.dedupe_keys(), now, self.settings.dedupe_window_sec):
            return Result("duplicate")
        row_ids = self.store.add_lead(lead, list(self.sinks), now)  # saved BEFORE any network call
        result = Result("accepted", lead.id)
        for row_id in row_ids:
            row = self.store.get_outbox(row_id)
            self.deliver(row, lead)
            result.delivery[row.sink] = self.store.get_outbox(row_id).status
        return result

    def deliver(self, row: OutboxRow, lead: Lead | None = None) -> bool:
        lead = lead or self.store.get_lead(row.lead_id)
        now = self.clock()
        try:
            sink = self.sinks.get(row.sink)
            if sink is None:
                raise RuntimeError(f"sink '{row.sink}' is not configured")
            sink.send(lead)
        except Exception as exc:  # noqa: BLE001 - a sink failure must only delay, never lose
            attempts = row.attempts + 1
            dead = attempts >= self.settings.max_attempts
            delay = min(self.settings.backoff_base_sec * 2 ** (attempts - 1),
                        self.settings.backoff_max_sec)
            error = f"{type(exc).__name__}: {exc}"
            self.store.mark_failed(row.id, error, now + delay, dead, now)
            log.warning("sink %s failed for lead %s (attempt %d%s): %s", row.sink, row.lead_id,
                        attempts, ", giving up" if dead else "", error)
            return False
        self.store.mark_done(row.id, now)
        return True

    def retry_due(self, force: bool = False) -> RetryReport:
        report = RetryReport()
        for row in self.store.due(self.clock(), force=force):
            report.due += 1
            if self.deliver(row):
                report.sent += 1
            else:
                report.failed += 1
                if self.store.get_outbox(row.id).status == "dead":
                    report.dead += 1
        return report
