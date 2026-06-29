"""
Module: test_orchestrator.py
Purpose: Tests for the Phase 4b orchestrator wiring — scan_and_prepare (drive ->
         vision -> pricing -> state) and publish_approved (eBay + state), all with
         mocked drive/provider/eBay and an in-memory state store. No network.
FMEA Constraints Enforced (asserted): R-STATE, PI-007, R-PRICE.
"""

from __future__ import annotations

import pytest

from src.contracts import DraftOutput, ItemStatus, ListingPayload, PublishResult
from src.core import orchestrator
from src.core.state_store import StateStore


# ── Fakes ─────────────────────────────────────────────────────────────────────


class _StubProvider:
    """Returns a canned vision JSON for any call."""

    def __init__(self, text: str) -> None:
        self._text = text

    def generate_from_images(self, image_paths, prompt, **kwargs) -> str:
        return self._text

    @property
    def model_name(self) -> str:
        return "stub"


class _FakeEbayClient:
    """search_active_comps + publish_listing doubles for the orchestrator."""

    def __init__(self, comps=None, publish_result: PublishResult | None = None) -> None:
        self._comps = comps or []
        self._publish_result = publish_result
        self.published: list[ListingPayload] = []

    def search_active_comps(self, query, *, limit=20, extra_filter=None):
        return self._comps

    def publish_listing(self, payload: ListingPayload) -> PublishResult:
        self.published.append(payload)
        return self._publish_result or PublishResult(
            item_sku=payload.item_sku,
            offer_id="OFFER-X",
            listing_id="LIST-X",
            eps_image_urls=["https://i.ebayimg.com/eps.jpg"],
        )


_VISION_JSON = (
    '{"item_specifics": {"Brand": "Sony", "Model": "WH-1000XM4"}, '
    '"condition": "Used - Very Good", "defects_found": [], "dropped_fields": []}'
)


@pytest.fixture
def store():
    s = StateStore(":memory:")
    yield s
    s.close()


@pytest.fixture
def mock_drive(monkeypatch):
    """Two pending batches; downloads return fixed local paths."""
    batches = [
        {"folder_id": "F1", "folder_name": "Headphones", "image_files": []},
        {"folder_id": "F2", "folder_name": "Camera", "image_files": []},
    ]
    monkeypatch.setattr(orchestrator.drive_fetcher, "list_pending_batches", lambda: batches)
    monkeypatch.setattr(
        orchestrator.drive_fetcher,
        "download_batch_images",
        lambda batch: ([f"/cache/{batch['folder_id']}.jpg"], False),
    )
    return batches


# ── derive_sku ────────────────────────────────────────────────────────────────


def test_derive_sku():
    assert orchestrator.derive_sku("abc123") == "LB-abc123"


# ── scan_and_prepare ──────────────────────────────────────────────────────────


def test_scan_prepares_payloads_and_records_state(mock_drive, store):
    """Scan runs the pipeline, returns payloads, and records PRICED state."""
    provider = _StubProvider(_VISION_JSON)
    payloads = orchestrator.scan_and_prepare(provider, store)
    assert {p.item_sku for p in payloads} == {"LB-F1", "LB-F2"}
    # Title built from aspects; condition mapped to an eBay enum.
    p1 = next(p for p in payloads if p.item_sku == "LB-F1")
    assert p1.title == "Sony WH-1000XM4"
    assert p1.condition == "USED_VERY_GOOD"
    assert p1.local_image_paths == ["/cache/F1.jpg"]
    # State recorded for both items.
    assert store.get_item("LB-F1").status is ItemStatus.PRICED
    assert store.get_item("LB-F2").status is ItemStatus.PRICED


def test_scan_skips_already_published(mock_drive, store):
    """A published SKU is skipped on re-scan (R-STATE dedup)."""
    from src.contracts import ItemRecord

    store.upsert_item(
        ItemRecord(item_sku="LB-F1", batch_folder_id="F1", status=ItemStatus.PUBLISHED)
    )
    payloads = orchestrator.scan_and_prepare(_StubProvider(_VISION_JSON), store)
    assert {p.item_sku for p in payloads} == {"LB-F2"}  # F1 skipped


def test_scan_uses_ebay_comps_when_client_given(mock_drive, store):
    """When an eBay client is supplied, comps anchor the price (R-PRICE)."""
    client = _FakeEbayClient(comps=[300.0, 320.0])
    payloads = orchestrator.scan_and_prepare(
        _StubProvider(_VISION_JSON), store, ebay_client=client
    )
    p1 = next(p for p in payloads if p.item_sku == "LB-F1")
    assert p1.price == 310.0  # median of the comps (no cost/fees floor)


# ── publish_approved ──────────────────────────────────────────────────────────


def _full_payload(sku="LB-F1") -> ListingPayload:
    return ListingPayload(
        item_sku=sku,
        title="Sony WH-1000XM4",
        condition="USED_VERY_GOOD",
        price=199.99,
        category_id="112529",
        local_image_paths=["/cache/F1.jpg"],
        fulfillment_policy_id="FP",
        payment_policy_id="PP",
        return_policy_id="RP",
        merchant_location_key="LOC",
    )


def test_publish_approved_records_ids(store):
    """publish_approved publishes and records offer/listing IDs (R-STATE)."""
    client = _FakeEbayClient()
    result = orchestrator.publish_approved(_full_payload(), store, ebay_client=client)
    assert result.offer_id == "OFFER-X"
    assert result.listing_id == "LIST-X"
    rec = store.get_item("LB-F1")
    assert rec.status is ItemStatus.PUBLISHED
    assert rec.offer_id == "OFFER-X"
    assert rec.listing_id == "LIST-X"
    assert rec.eps_urls == ["https://i.ebayimg.com/eps.jpg"]


def test_publish_approved_dedup_no_double_publish(store):
    """A second approve on a live SKU does not call eBay again (R-STATE)."""
    from src.contracts import ItemRecord

    store.upsert_item(
        ItemRecord(
            item_sku="LB-F1",
            batch_folder_id="F1",
            status=ItemStatus.PUBLISHED,
            offer_id="OLD-OFFER",
            listing_id="OLD-LIST",
        )
    )
    client = _FakeEbayClient()
    result = orchestrator.publish_approved(_full_payload(), store, ebay_client=client)
    assert client.published == []  # eBay never called
    assert result.listing_id == "OLD-LIST"


# ── fulfill_approved routing (v1.2) ───────────────────────────────────────────


def test_fulfill_routes_ebay_to_auto_publish(store):
    """target='ebay' publishes and records state (same as publish_approved)."""
    client = _FakeEbayClient()
    result = orchestrator.fulfill_approved(
        _full_payload(), store, target="ebay", ebay_client=client
    )
    assert isinstance(result, PublishResult)
    assert result.listing_id == "LIST-X"
    assert store.get_item("LB-F1").status is ItemStatus.PUBLISHED
    assert len(client.published) == 1


def test_fulfill_routes_other_to_draft(tmp_path, store):
    """target='other:mercari' writes a draft and does NOT touch eBay or publish state."""
    client = _FakeEbayClient()
    result = orchestrator.fulfill_approved(
        _full_payload(), store, target="other:mercari",
        ebay_client=client, output_dir=str(tmp_path),
    )
    assert isinstance(result, DraftOutput)
    assert result.platform == "mercari"
    # No eBay publish, and the item is not marked PUBLISHED (draft is an export).
    assert client.published == []
    assert store.is_published("LB-F1") is False
    # Files were written under the chosen output dir.
    from pathlib import Path

    assert Path(result.draft_path).is_file()
    assert str(tmp_path) in result.draft_path


def test_fulfill_unknown_target_raises(store):
    with pytest.raises(ValueError):
        orchestrator.fulfill_approved(_full_payload(), store, target="amazon")
