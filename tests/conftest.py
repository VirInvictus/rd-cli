"""Shared test fixtures. A ``FakeOpener`` stands in for ``urllib``'s opener so
the client can be exercised end-to-end with zero network and zero waiting."""

from __future__ import annotations

import io
import json
import urllib.error
from email.message import Message

import pytest


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code: int, payload: dict | None = None, headers: dict | None = None):
    body = json.dumps(payload).encode() if payload is not None else b""
    hdrs = Message()
    for key, value in (headers or {}).items():
        hdrs[key] = value
    return urllib.error.HTTPError(
        "https://api.raindrop.io/rest/v1/x",
        code,
        "error",
        hdrs,
        io.BytesIO(body),
    )


class FakeOpener:
    """Records requests and returns queued responses in order.

    Queue entries are either dicts (JSON-encoded into a 200 body) or exceptions
    (raised to simulate transport / HTTP errors).
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append(req)
        if not self.responses:
            raise AssertionError("FakeOpener ran out of queued responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(json.dumps(item).encode())

    @property
    def last(self):
        return self.requests[-1]


@pytest.fixture
def opener_factory():
    return FakeOpener


@pytest.fixture
def no_sleep():
    calls = []
    return calls.append, calls
