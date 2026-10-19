"""Flask app: POST /webhook accepts Tilda (form-urlencoded) and JSON (WordPress / custom forms)."""
from __future__ import annotations

import hmac
import logging
import time
from typing import Any, Callable, Sequence

from flask import Flask, Response, jsonify, request

from .config import Settings
from .normalize import ValidationError
from .router import LeadRouter
from .sinks import Sink, build_sinks
from .store import Store

FORM_TYPES = {"application/x-www-form-urlencoded", "multipart/form-data"}


def create_app(settings: Settings | None = None, sinks: Sequence[Sink] | None = None,
               store: Store | None = None, clock: Callable[[], float] = time.time) -> Flask:
    settings = settings or Settings.from_env()
    store = store or Store(settings.db_path)
    router = LeadRouter(store, build_sinks(settings) if sinks is None else sinks, settings, clock)
    app = Flask(__name__)
    app.config["ROUTER"] = router

    @app.get("/health")
    def health() -> Response:
        return jsonify(status="ok", sinks=sorted(router.sinks), outbox=store.stats())

    @app.post("/webhook")
    def webhook() -> Any:
        secret = settings.webhook_secret
        if secret and not hmac.compare_digest(request.args.get("key", ""), secret):
            return jsonify(error="forbidden"), 403

        if request.mimetype == "application/json":
            raw = request.get_json(silent=True)
            if not isinstance(raw, dict):
                return jsonify(error="body must be a JSON object"), 400
            is_json = True
        elif request.mimetype in FORM_TYPES:
            raw = {k: ", ".join(v) for k, v in request.form.to_dict(flat=False).items()}
            is_json = False
        else:
            return jsonify(error="unsupported content type"), 415

        try:
            result = router.handle(raw, is_json=is_json)
        except ValidationError as exc:
            return jsonify(status="invalid", errors=exc.errors), 422

        if is_json:
            return jsonify(status=result.status, lead_id=result.lead_id, delivery=result.delivery)
        # Tilda only needs HTTP 200; the body "ok" is what its documentation shows.
        return Response("ok", status=200, mimetype="text/plain")

    return app


def create_app_from_env() -> Flask:
    """Entry point for gunicorn: gunicorn 'leadrouter.server:create_app_from_env()'."""
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return create_app()
