"""429 handling: unit tests on the wrapper plus a real HTTP round trip to a local server."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ozon_sync.client import OzonClient
from ozon_sync.errors import ApiError, RateLimitError, TransportError
from ozon_sync.transport import HttpTransport, RetryingTransport


class Flaky:
    """Fails with the given errors in order, then answers {"ok": True}."""

    def __init__(self, *errors):
        self.errors = list(errors)
        self.calls = 0

    def post(self, path, payload):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return {"ok": True}


def make(inner, **kw):
    slept = []
    return RetryingTransport(inner, sleep=slept.append, **kw), slept


def test_429_is_retried_and_retry_after_is_honoured():
    inner = Flaky(RateLimitError(retry_after=3), RateLimitError(retry_after=7))
    transport, slept = make(inner)
    assert transport.post("/x", {}) == {"ok": True}
    assert inner.calls == 3 and slept == [3, 7]


def test_backoff_doubles_without_retry_after_and_is_capped():
    inner = Flaky(*[RateLimitError() for _ in range(5)])
    transport, slept = make(inner, base_delay=1, max_delay=10, max_retries=5)
    transport.post("/x", {})
    assert slept == [1, 2, 4, 8, 10]  # 16 capped to 10


def test_gives_up_after_max_retries_and_raises_the_429():
    inner = Flaky(*[RateLimitError() for _ in range(10)])
    transport, slept = make(inner, max_retries=3)
    with pytest.raises(RateLimitError):
        transport.post("/x", {})
    assert inner.calls == 4 and len(slept) == 3  # first try + 3 retries


def test_gateway_errors_are_retried_but_client_errors_are_not():
    transport, slept = make(Flaky(ApiError(503, "unavailable")))
    assert transport.post("/x", {}) == {"ok": True} and slept == [1]

    inner = Flaky(ApiError(400, "bad request"))
    transport, slept = make(inner)
    with pytest.raises(ApiError):
        transport.post("/x", {})
    assert inner.calls == 1 and slept == []  # a 400 will not get better by waiting


def test_on_retry_callback_gets_attempt_and_delay():
    seen = []
    inner = Flaky(RateLimitError(retry_after=2))
    transport = RetryingTransport(inner, sleep=lambda s: None, on_retry=lambda *a: seen.append(a[:3]))
    transport.post("/v1/x", {})
    assert seen == [("/v1/x", 1, 2)]


# ---- real HTTP against a local server (no Ozon involved) -------------------------------------


class _Server:
    def __init__(self, script):
        """script: list of (status, headers, body) answered in order; the last one repeats."""
        self.script, self.requests = list(script), []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                owner.requests.append((self.path, dict(self.headers), json.loads(self.rfile.read(length) or b"{}")))
                status, headers, body = owner.script.pop(0) if len(owner.script) > 1 else owner.script[0]
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

            def log_message(self, *args):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    servers = []

    def start(script):
        servers.append(_Server(script))
        return servers[-1]

    yield start
    for s in servers:
        s.close()


def test_http_429_then_success_over_a_real_socket(server):
    srv = server([(429, {"Retry-After": "2"}, {"message": "slow down"}), (429, {}, {"message": "slow down"}), (200, {}, {"result": {"items": []}})])
    transport, slept = make(HttpTransport("12345", "secret-key-123", srv.url))
    data = OzonClient(transport).transport.post("/v3/product/list", {"limit": 1})
    assert data == {"result": {"items": []}}
    assert len(srv.requests) == 3
    assert slept == [2, 2]  # Retry-After: 2, then back-off attempt 2 (1 * 2**1)
    path, headers, body = srv.requests[0]
    assert path == "/v3/product/list" and body == {"limit": 1}
    assert headers["Client-Id"] == "12345" and headers["Api-Key"] == "secret-key-123"


def test_http_error_message_does_not_leak_the_key(server):
    srv = server([(403, {}, {"code": 7, "message": "Invalid Api-Key"})])
    transport = HttpTransport("12345", "secret-key-123", srv.url)
    with pytest.raises(ApiError) as caught:
        transport.post("/v3/product/list", {})
    assert caught.value.status == 403 and "Invalid Api-Key" in str(caught.value)
    assert "secret-key-123" not in str(caught.value)


def test_unreachable_host_becomes_transport_error():
    transport = HttpTransport("1", "k", "http://127.0.0.1:9", timeout=2)  # discard port, nothing listens
    with pytest.raises(TransportError):
        transport.post("/x", {})
