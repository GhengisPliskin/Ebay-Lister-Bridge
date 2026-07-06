"""
Module: test_drive_fetcher.py
Purpose: Tests for the Phase 4 drive_fetcher enhancement — recursive subfolder
         traversal + full pageToken pagination — via a fake Drive service (no
         network, no credentials). Also covers _load_cache_manifest robustness
         (a corrupt manifest.json must degrade to a cold cache, not raise).
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


# ── _load_cache_manifest robustness (corrupt manifest -> cold cache) ─────────


def test_load_cache_manifest_missing_returns_empty(tmp_path):
    """No manifest.json at all -> empty dict (first run)."""
    assert drive_fetcher._load_cache_manifest(str(tmp_path)) == {}


def test_load_cache_manifest_corrupt_json_returns_empty(tmp_path):
    """A malformed manifest.json is treated as a cold cache, not raised (PI-001)."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{not valid json!!", encoding="utf-8")

    result = drive_fetcher._load_cache_manifest(str(tmp_path))

    assert result == {}


def test_load_cache_manifest_corrupt_json_scan_proceeds(fake_drive, tmp_path, monkeypatch):
    """
    A corrupt manifest does not block download_batch_images: the batch downloads
    fresh (cold cache) instead of raising, and a fresh manifest is written.
    """
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{not valid json!!", encoding="utf-8")

    monkeypatch.setenv("DRIVE_CACHE_DIR", str(tmp_path))

    # Fake the file download itself: get_media().execute()-style chunked read.
    class _FakeDownloader:
        def __init__(self, *a, **kw):
            pass

        def next_chunk(self):
            return (None, True)

    class _FakeMediaFiles:
        def get_media(self, fileId):
            return object()

    class _FakeMediaService:
        def files(self):
            return _FakeMediaFiles()

    monkeypatch.setattr(drive_fetcher, "_get_drive_service", lambda: _FakeMediaService())
    monkeypatch.setattr(drive_fetcher, "MediaIoBaseDownload", lambda *a, **kw: _FakeDownloader())

    batch = {
        "folder_id": "F1",
        "folder_name": "F1",
        "image_files": [
            {"file_id": "i1", "name": "a.jpg", "mime_type": "image/jpeg",
             "modified_time": "2026-01-01T00:00:00Z"}
        ],
    }

    local_paths, cache_fallback_used = drive_fetcher.download_batch_images(batch)

    assert len(local_paths) == 1
    assert cache_fallback_used is False
    # A fresh manifest was written (the corrupt one was overwritten), and it
    # now parses cleanly and contains the newly downloaded file.
    fresh_manifest = drive_fetcher._load_cache_manifest(str(tmp_path))
    assert "i1" in fresh_manifest
