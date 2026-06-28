"""
Module: test_state_store.py
Purpose: Tests for the Phase 4 SQLite StateStore against the frozen contracts.
         Uses an in-memory database (no disk, no network).
FMEA Constraints Enforced (asserted): R-STATE, R-AUTH.
"""

from __future__ import annotations

import pytest

from src.contracts import ItemRecord, ItemStatus, TokenCacheRecord
from src.core.state_store import StateStore


@pytest.fixture
def store():
    """An ephemeral in-memory StateStore."""
    s = StateStore(":memory:")
    yield s
    s.close()


def test_upsert_and_get_roundtrip(store):
    """An item round-trips, including eps_urls JSON and status enum."""
    rec = ItemRecord(
        item_sku="LB-f1",
        batch_folder_id="f1",
        status=ItemStatus.PRICED,
        eps_urls=["https://i.ebayimg.com/a.jpg", "https://i.ebayimg.com/b.jpg"],
    )
    store.upsert_item(rec)
    got = store.get_item("LB-f1")
    assert got is not None
    assert got.status is ItemStatus.PRICED
    assert got.eps_urls == ["https://i.ebayimg.com/a.jpg", "https://i.ebayimg.com/b.jpg"]
    assert got.updated_at  # stamped on write


def test_get_missing_returns_none(store):
    """Unknown SKU returns None."""
    assert store.get_item("nope") is None


def test_upsert_updates_existing(store):
    """A second upsert on the same SKU updates in place (idempotency, R-STATE)."""
    store.upsert_item(ItemRecord(item_sku="LB-f1", batch_folder_id="f1"))
    store.upsert_item(
        ItemRecord(
            item_sku="LB-f1",
            batch_folder_id="f1",
            status=ItemStatus.PUBLISHED,
            offer_id="OFFER-1",
            listing_id="LIST-1",
        )
    )
    got = store.get_item("LB-f1")
    assert got.status is ItemStatus.PUBLISHED
    assert got.offer_id == "OFFER-1"
    assert got.listing_id == "LIST-1"
    # Still a single row.
    assert len(store.list_items()) == 1


def test_is_published_dedup_guard(store):
    """is_published reflects PUBLISHED status only (R-STATE dedup)."""
    store.upsert_item(
        ItemRecord(item_sku="LB-a", batch_folder_id="a", status=ItemStatus.NEW)
    )
    assert store.is_published("LB-a") is False
    store.set_status("LB-a", ItemStatus.PUBLISHED)
    assert store.is_published("LB-a") is True


def test_set_status_updates_timestamp(store):
    """set_status updates status and refreshes updated_at."""
    store.upsert_item(ItemRecord(item_sku="LB-a", batch_folder_id="a", updated_at="old"))
    store.set_status("LB-a", ItemStatus.EXTRACTED)
    got = store.get_item("LB-a")
    assert got.status is ItemStatus.EXTRACTED
    assert got.updated_at != "old"


def test_token_cache_roundtrip(store):
    """Token cache saves and reads back (R-AUTH)."""
    assert store.get_cached_token() is None
    store.save_cached_token(
        TokenCacheRecord(access_token="AT-1", expires_at_epoch=1234567.0, scopes="x y")
    )
    got = store.get_cached_token()
    assert got.access_token == "AT-1"
    assert got.expires_at_epoch == 1234567.0
    assert got.scopes == "x y"
    # Overwrite stays single-row.
    store.save_cached_token(
        TokenCacheRecord(access_token="AT-2", expires_at_epoch=2.0, scopes="")
    )
    assert store.get_cached_token().access_token == "AT-2"
