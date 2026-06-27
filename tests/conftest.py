"""
Module: conftest.py
Purpose: Shared pytest fixtures and lightweight fakes so the full test suite runs
         with NO live Gemini / eBay / Drive credentials.
Primary Responsibilities:
  - Provide FakeResponse / FakeSession to stand in for requests.Session.
  - Ensure `src` is importable as a package from the repo root.
Key Interfaces:
  - Output: fixtures consumed by tests/test_*.py.
FMEA Constraints Enforced:
  - None directly; this is test infrastructure enabling the mocked contract tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the repo root importable so `import src...` resolves when pytest is run
# from anywhere within the project.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeResponse:
    """
    Minimal stand-in for requests.Response used by the mocked eBay tests.

    Attributes:
        status_code: HTTP status to report.
        _json: Parsed JSON body to return from .json().
        headers: Response headers (e.g. a Media API Location header).
        text: Raw body text for error diagnostics.
    """

    def __init__(
        self,
        status_code: int = 200,
        json_body: dict | None = None,
        headers: dict | None = None,
        text: str = "",
    ) -> None:
        """Construct a fake response with the given status/body/headers."""
        self.status_code = status_code
        self._json = json_body or {}
        self.headers = headers or {}
        self.text = text or ""

    def json(self) -> dict:
        """Return the canned JSON body."""
        return self._json


class FakeSession:
    """
    Records outgoing calls and returns queued FakeResponses in order.

    Each of get/post/put pops the next queued response (or a default 200). Every
    call is appended to `calls` as a dict so tests can assert on URL, headers,
    params, json, data, and files — i.e. validate request SHAPE without a network.
    """

    def __init__(self, responses: list[FakeResponse] | None = None) -> None:
        """Queue zero or more responses to be returned FIFO."""
        self._responses = list(responses or [])
        self.calls: list[dict] = []

    def _next(self) -> FakeResponse:
        """Pop the next queued response, or default to an empty 200."""
        if self._responses:
            return self._responses.pop(0)
        return FakeResponse(200, {})

    def _record(self, method: str, url: str, kwargs: dict) -> FakeResponse:
        """Record a call and return the next queued response."""
        self.calls.append({"method": method, "url": url, **kwargs})
        return self._next()

    def get(self, url: str, **kwargs) -> FakeResponse:
        """Record a GET and return the next queued response."""
        return self._record("GET", url, kwargs)

    def post(self, url: str, **kwargs) -> FakeResponse:
        """Record a POST and return the next queued response."""
        return self._record("POST", url, kwargs)

    def put(self, url: str, **kwargs) -> FakeResponse:
        """Record a PUT and return the next queued response."""
        return self._record("PUT", url, kwargs)


@pytest.fixture
def fake_response():
    """Expose the FakeResponse class to tests."""
    return FakeResponse


@pytest.fixture
def fake_session():
    """Return a factory that builds a FakeSession from a list of responses."""

    def _make(responses: list[FakeResponse] | None = None) -> FakeSession:
        return FakeSession(responses)

    return _make


@pytest.fixture
def tmp_jpg(tmp_path):
    """Write a tiny fake .jpg file and return its path (passes precheck_image)."""
    p = tmp_path / "photo.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")
    return str(p)
