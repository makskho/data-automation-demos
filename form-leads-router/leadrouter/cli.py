"""Command line: serve | retry | status.

    python -m leadrouter serve --port 8000
    python -m leadrouter retry            # one pass over deliveries that are due
    python -m leadrouter retry --loop 60  # keep retrying every 60 s
    python -m leadrouter status
"""
from __future__ import annotations

import argparse
import logging
import time
from typing import Callable, Sequence

from .router import LeadRouter
from .store import Store


def _default_router() -> LeadRouter:
    from dotenv import load_dotenv

    from .config import Settings
    from .sinks import build_sinks

    load_dotenv()
    settings = Settings.from_env()
    return LeadRouter(Store(settings.db_path), build_sinks(settings), settings)


def main(argv: Sequence[str] | None = None,
         router_factory: Callable[[], LeadRouter] | None = None,
         out: Callable[[str], None] = print) -> int:
    parser = argparse.ArgumentParser(prog="leadrouter", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="run the webhook server (development; use gunicorn in production)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    retry = sub.add_parser("retry", help="resend deliveries that failed earlier")
    retry.add_argument("--force", action="store_true", help="ignore the backoff timer")
    retry.add_argument("--loop", type=int, metavar="SECONDS", help="repeat every N seconds")
    sub.add_parser("status", help="outbox counters and the latest errors")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    router = (router_factory or _default_router)()

    if args.cmd == "serve":
        from .server import create_app

        create_app(router.settings, list(router.sinks.values()), router.store).run(
            host=args.host, port=args.port)
        return 0

    if args.cmd == "status":
        stats = router.store.stats()
        out("outbox: " + ", ".join(f"{k}={v}" for k, v in stats.items()))
        for row in router.store.list_outbox("pending") + router.store.list_outbox("dead"):
            out(f"  #{row.id} {row.sink} lead={row.lead_id[:8]} {row.status} "
                f"attempts={row.attempts} error={row.last_error}")
        return 0

    while True:
        rep = router.retry_due(force=args.force)
        out(f"retry: due={rep.due} sent={rep.sent} failed={rep.failed} dead={rep.dead}")
        if not args.loop:
            return 1 if rep.failed else 0
        time.sleep(args.loop)
