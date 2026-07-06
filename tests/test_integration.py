"""
Module: test_integration.py
Purpose: End-to-end pipeline test across ALL layers with every external service
         mocked — Google Drive, Gemini (provider), and eBay (Browse + publish).
         Exercises drive -> vision -> margin -> assemble -> review -> approve ->
         publish -> state, plus crash-resume dedup. No network, no credentials.
FMEA Constraints Enforced (asserted): R-STATE, PI-006, PI-007, PI-009, R-PRICE.
"""

from __future__ import annotations

import pytest

from src.contracts import ItemStatus, ListingPayload, PublishResult, VisionAgentOutput
from src.core import orchestrator
from src.core.state_store import StateStore
from src.ui import review


# ── Mocks for the three external services ─────────────────────────────────────


class _FakeProvider:
    """Gemini stand-in: returns canned extraction JSON keyed by image path."""

    _BY_ITEM = {
        "/cache/F1.jpg": (
            '{"item_specifics": {"Brand": "Sony", "Model": "WH-1000XM4"}, '
            '"condition": "Used - Very Good", '
            '"defects_found": ["light scuff on headband"], "dropped_fields": []}'
        ),
        "/cache/F2.jpg": (
            '{"item_specifics": {"Brand": "Canon", "Model": "EOS R"}, '
            '"condition": "Used - Good", "defects_found": [], "dropped_fields": []}'
        ),
    }

    def generate_from_images(self, image_paths, prompt, **kwargs) -> str:
        return self._BY_ITEM[image_paths[0]]

    @property
    def model_name(self) -> str:
        return "fake-gemini"


class _FakeEbayClient:
    """eBay stand-in: Browse comps per query + a recorded publish sequence."""

    def __init__(self) -> None:
        self.published: list[ListingPayload] = []
        self._offer_seq = 0

    def search_active_comps(self, query, *, limit=20, extra_filter=None):
        # Sony headphones ~ $300; Canon camera ~ $900.
        if "Sony" in query:
            return [290.0, 300.0, 320.0]
        if "Canon" in query:
            return [880.0, 900.0, 950.0]
        return []

    def publish_listing(self, payload: ListingPayload) -> PublishResult:
        # Mirror EbayClient: enforce PI-009 before "publishing".
        from src.api.ebay_client import EbayClient

        problems = EbayClient.validate_offer(payload)
        if payload.local_image_paths:
            problems = [p for p in problems if "EPS image URL" not in p]
        if problems:
            raise AssertionError(f"would-be eBay rejection (PI-009): {problems}")
        self._offer_seq += 1
        n = self._offer_seq
        self.published.append(payload)
        return PublishResult(
            item_sku=payload.item_sku,
            offer_id=f"OFFER-{n}",
            listing_id=f"LIST-{n}",
            eps_image_urls=[f"https://i.ebayimg.com/{payload.item_sku}.jpg"],
            listing_url=f"https://www.ebay.com/itm/LIST-{n}",
        )


@pytest.fixture
def mocked_drive(monkeypatch):
    """Two pending item batches; downloads return one local path each."""
    batches = [
        {"folder_id": "F1", "folder_name": "Sony Headphones", "image_files": []},
        {"folder_id": "F2", "folder_name": "Canon Camera", "image_files": []},
    ]
    monkeypatch.setattr(orchestrator.drive_fetcher, "list_pending_batches", lambda: batches)
    monkeypatch.setattr(
        orchestrator.drive_fetcher,
        "download_batch_images",
        lambda batch: ([f"/cache/{batch['folder_id']}.jpg"], False),
    )
    # eBay policies/location/category from env so payloads are publishable.
    for k, v in {
        "EBAY_FULFILLMENT_POLICY_ID": "FP-1",
        "EBAY_PAYMENT_POLICY_ID": "PP-1",
        "EBAY_RETURN_POLICY_ID": "RP-1",
        "EBAY_INVENTORY_LOCATION_KEY": "LOC-1",
        "EBAY_DEFAULT_CATEGORY_ID": "112529",
    }.items():
        monkeypatch.setenv(k, v)
    return batches


@pytest.fixture
def store():
    s = StateStore(":memory:")
    yield s
    s.close()


# ── The end-to-end happy path ─────────────────────────────────────────────────


def test_full_pipeline_scan_review_approve_publish(mocked_drive, store):
    """Drive -> vision -> margin -> assemble -> review -> approve -> publish -> state."""
    provider = _FakeProvider()
    client = _FakeEbayClient()

    # 1) SCAN: prepare both items (vision + comp-anchored pricing).
    payloads = orchestrator.scan_and_prepare(provider, store, ebay_client=client)
    assert {p.item_sku for p in payloads} == {"LB-F1", "LB-F2"}

    by_sku = {p.item_sku for p in payloads}
    assert by_sku == {"LB-F1", "LB-F2"}
    sony = next(p for p in payloads if p.item_sku == "LB-F1")
    canon = next(p for p in payloads if p.item_sku == "LB-F2")

    # Title from aspects; condition mapped; comp-anchored price (median).
    assert sony.title == "Sony WH-1000XM4"
    assert sony.condition == "USED_VERY_GOOD"
    assert sony.price == 300.0          # median of [290,300,320]
    assert canon.price == 900.0         # median of [880,900,950]
    # Defects disclosed in the description (PI-004).
    assert "light scuff on headband" in sony.listing_description
    # Both recorded as PRICED (R-STATE).
    assert store.get_item("LB-F1").status is ItemStatus.PRICED
    assert store.get_item("LB-F2").status is ItemStatus.PRICED

    # 2) REVIEW: operator confirms a sold comp on the Sony, then validates.
    edited_sony = review.apply_operator_edits(sony, price=285.0)
    assert review.validate_for_publish(edited_sony) == []

    # 3) APPROVE + PUBLISH both items.
    r_sony = orchestrator.publish_approved(edited_sony, store, ebay_client=client)
    r_canon = orchestrator.publish_approved(canon, store, ebay_client=client)

    assert r_sony.listing_id == "LIST-1"
    assert r_canon.listing_id == "LIST-2"
    assert r_sony.listing_url.endswith("LIST-1")

    # 4) STATE: both PUBLISHED with IDs + EPS URLs recorded (R-STATE).
    s_rec = store.get_item("LB-F1")
    assert s_rec.status is ItemStatus.PUBLISHED
    assert s_rec.offer_id == "OFFER-1" and s_rec.listing_id == "LIST-1"
    assert s_rec.eps_urls == ["https://i.ebayimg.com/LB-F1.jpg"]
    assert len(client.published) == 2


def test_full_pipeline_archives_batches_after_publish(mocked_drive, store, monkeypatch):
    """
    After a successful publish, the source Drive batch is archived (bug fix:
    archive_batch previously had zero callers, so batches never left staging
    and were re-scanned forever).
    """
    archive_calls = []
    monkeypatch.setattr(
        orchestrator.drive_fetcher,
        "archive_batch",
        lambda folder_id, folder_name: archive_calls.append(folder_id),
    )

    provider = _FakeProvider()
    client = _FakeEbayClient()

    payloads = orchestrator.scan_and_prepare(provider, store, ebay_client=client)
    for payload in payloads:
        orchestrator.publish_approved(payload, store, ebay_client=client)

    # Both batches were archived, one call per published item.
    assert sorted(archive_calls) == ["F1", "F2"]


def test_resume_skips_published_and_does_not_republish(mocked_drive, store):
    """A re-scan after one item is live skips it; re-approve never double-publishes."""
    provider = _FakeProvider()
    client = _FakeEbayClient()

    # First pass: publish F1 only.
    payloads = orchestrator.scan_and_prepare(provider, store, ebay_client=client)
    sony = next(p for p in payloads if p.item_sku == "LB-F1")
    orchestrator.publish_approved(sony, store, ebay_client=client)
    assert store.is_published("LB-F1")

    # "Crash" + resume: a fresh scan should only re-prepare the unpublished F2.
    payloads2 = orchestrator.scan_and_prepare(provider, store, ebay_client=client)
    assert {p.item_sku for p in payloads2} == {"LB-F2"}

    # Defensive: approving F1 again must NOT call eBay a second time (R-STATE).
    before = len(client.published)
    again = orchestrator.publish_approved(sony, store, ebay_client=client)
    assert len(client.published) == before
    assert again.listing_id == "LIST-1"


def test_pipeline_routes_missing_inputs_when_no_comps(mocked_drive, store):
    """With no eBay client (no comps) and no cost, price is 0 and inputs flagged."""
    provider = _FakeProvider()
    # No ebay_client -> no comps; cost/fees unknown.
    payloads = orchestrator.scan_and_prepare(provider, store)
    sony = next(p for p in payloads if p.item_sku == "LB-F1")
    # Price could not be anchored; operator must resolve in the UI (R-PRICE).
    assert sony.price == 0.0
    # The review recompute surfaces the missing inputs cleanly.
    pricing = review.recompute_price(
        VisionAgentOutput(item_specifics=sony.item_specifics, condition=sony.condition),
        cost=None, fees=None, active_comps=None, user_confirmed_comp=None,
    )
    assert "active_comp_or_user_comp" in pricing.missing_inputs
