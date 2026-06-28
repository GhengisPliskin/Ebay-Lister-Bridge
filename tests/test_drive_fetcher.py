"""
Module: test_drive_fetcher.py
Purpose: Tests for the Phase 4 drive_fetcher enhancement — recursive subfolder
         traversal + full pageToken pagination — via a fake Drive service (no
         network, no credentials).
FMEA Constraints Enforced (asserted): A-01 fix (recursion + pagination), PI-001 path.
"""

from __future__ import annotations

import re

import pytest

from src.core import drive_fetcher


# ── Fake Drive service ────────────────────────────────────────────────────────

# Folder tree: STAGING has two item folders (returned across TWO pages to force
# pagination). F1 nests a subfolder F1N (to force recursion).
_FOLDERS = {"STAGING": ["F1", "F2"], "F1": ["F1N"], "F2": [], "F1N": []}
_FOLDER_META = {
    fid: {
        "id": fid,
        "name": fid,
        "createdTime": f"2026-01-0{i}T00:00:00Z",
        "modifiedTime": f"2026-01-0{i}T00:00:00Z",
    }
    for i, fid in enumerate(["F1", "F2", "F1N"], start=1)
}


def _img(fid, name):
    return {"id": fid, "name": name, "mimeType": "image/jpeg", "modifiedTime": "2026-01-01T00:00:00Z"}


_IMAGES = {"F1": [_img("i1", "a.jpg")], "F1N": [_img("i3", "c.jpg")], "F2": [_img("i2", "b.jpg")]}


class _FakeRequest:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class _FakeFiles:
    def list(self, **kwargs):
        return _FakeRequest(_handle(kwargs))


class _FakeService:
    def files(self):
        return _FakeFiles()


def _handle(kwargs: dict) -> dict:
    """Emulate files().list — parse parent + kind from the query, paginate STAGING."""
    q = kwargs["q"]
    parent = re.search(r"'([^']+)' in parents", q).group(1)
    is_folder = "application/vnd.google-apps.folder" in q
    if is_folder:
        entries = [_FOLDER_META[c] for c in _FOLDERS.get(parent, [])]
        if parent == "STAGING":
            # Force pagination: first folder on page 1 (+token), rest on page 2.
            if kwargs.get("pageToken") is None:
                return {"files": entries[:1], "nextPageToken": "TOKEN2"}
            return {"files": entries[1:]}
        return {"files": entries}
    # Image listing.
    return {"files": _IMAGES.get(parent, [])}


@pytest.fixture
def fake_drive(monkeypatch):
    """Point drive_fetcher at the fake service and a STAGING folder id."""
    monkeypatch.setenv("DRIVE_STAGING_FOLDER_ID", "STAGING")
    monkeypatch.setattr(drive_fetcher, "_get_drive_service", lambda: _FakeService())


def test_pagination_returns_all_batches(fake_drive):
    """Both staging subfolders are returned despite spanning two pages (A-01)."""
    batches = drive_fetcher.list_pending_batches()
    folder_ids = {b["folder_id"] for b in batches}
    assert folder_ids == {"F1", "F2"}


def test_recursion_collects_nested_images(fake_drive):
    """F1's batch includes the image nested in subfolder F1N (recursion)."""
    batches = {b["folder_id"]: b for b in drive_fetcher.list_pending_batches()}
    f1 = batches["F1"]
    names = {img["name"] for img in f1["image_files"]}
    assert names == {"a.jpg", "c.jpg"}  # direct + nested
    assert f1["file_count"] == 2


def test_helpers_paginate_fully(monkeypatch):
    """_list_all_files follows nextPageToken until exhausted."""
    pages = [
        {"files": [{"id": "1"}], "nextPageToken": "p2"},
        {"files": [{"id": "2"}], "nextPageToken": "p3"},
        {"files": [{"id": "3"}]},
    ]
    calls = {"n": 0}

    class _S:
        def files(self):
            return self

        def list(self, **kw):
            page = pages[calls["n"]]
            calls["n"] += 1
            return _FakeRequest(page)

    out = drive_fetcher._list_all_files(_S(), "q", "files(id)")
    assert [f["id"] for f in out] == ["1", "2", "3"]
    assert calls["n"] == 3
