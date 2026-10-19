"""HTTP layer behind a one-method interface.

`Transport.post(path, payload) -> dict` is all the client needs. Production uses `HttpTransport`
(stdlib urllib); tests and `--demo` use `ozon_sync.fake.FakeOzon`. `RetryingTransport` wraps any
transport and retries 429/502/503/504 with back-off.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Callable, Protocol

from .errors import ApiError, RateLimitError, TransportError

DEFAULT_BASE_URL = "https://api-seller.ozon.ru"


class Transport(Protocol):
    def post(self, path: str, payload: dict) -> dict: ...


def _error_message(body: bytes) -> str:
    try:
        data = json.loads(body)
        if isinstance(data, dict) and data.get("message"):
            return str(data["message"])
    except (ValueError, UnicodeDecodeError):
        pass
    return body[:200].decode("utf-8", "replace") or "empty response"


def _retry_after(value: str | None) -> float | None:
    try:
        return max(0.0, float(value)) if value is not None else None
    except ValueError:
        return None


class HttpTransport:
    """Real HTTP. Headers Client-Id / Api-Key; the key is never put into an error message."""

    def __init__(self, client_id: str, api_key: str, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._headers = {
            "Client-Id": str(client_id),
            "Api-Key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ozon-sync/1.0",
        }

    def post(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read()
            if exc.code == 429:
                raise RateLimitError(_error_message(body), _retry_after(exc.headers.get("Retry-After")), body) from None
            raise ApiError(exc.code, _error_message(body), body) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TransportError(f"{path}: {getattr(exc, 'reason', exc)}") from None
        return json.loads(body) if body else {}


class RetryingTransport:
    """Retry 429 and gateway errors: honour Retry-After, otherwise base * 2**attempt (capped)."""

    RETRY_STATUSES = (502, 503, 504)

    def __init__(
        self,
        inner: Transport,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        on_retry: Callable[[str, int, float, ApiError], None] | None = None,
    ):
        self.inner = inner
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._sleep = sleep
        self._on_retry = on_retry

    def post(self, path: str, payload: dict) -> dict:
        attempt = 0
        while True:
            try:
                return self.inner.post(path, payload)
            except ApiError as exc:
                retryable = isinstance(exc, RateLimitError) or exc.status in self.RETRY_STATUSES
                if not retryable or attempt >= self.max_retries:
                    raise
                hint = getattr(exc, "retry_after", None)
                delay = min(self.max_delay, hint if hint is not None else self.base_delay * 2**attempt)
                attempt += 1
                if self._on_retry:
                    self._on_retry(path, attempt, delay, exc)
                self._sleep(delay)
