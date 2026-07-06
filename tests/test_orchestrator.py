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


# ── scan_and_prepare: per-batch error isolation (Fix 1) ────────────────────────


class _FlakyOnFirstBatchProvider:
    """Raises a ValueError (simulating a Gemini JSON-parse failure) for the
    first batch's images only; any other batch gets the canned vision JSON."""

    def __init__(self, bad_path: str, good_text: str) -> None:
        self._bad_path = bad_path
        self._good_text = good_text

    def generate_from_images(self, image_paths, prompt, **kwargs) -> str:
        if image_paths and image_paths[0] == self._bad_path:
            raise ValueError("Vision response was not valid JSON: bad json")
        return self._good_text

    @property
    def model_name(self) -> str:
        return "stub"


def test_scan_vision_error_on_one_batch_does_not_abort_the_scan(mock_drive, store):
    """
    A Gemini JSON-parse ValueError on batch 1 of 2 must not abort the scan:
    batch 2 is still prepared, and batch 1 is recorded ItemStatus.ERROR with a
    human-readable reason (PI-001 — one bad item must never discard completed
    work for the rest of the run).
    """
    provider = _FlakyOnFirstBatchProvider("/cache/F1.jpg", _VISION_JSON)
    summary = orchestrator.scan_and_prepare(provider, store)

    # Batch 2 (Camera) still got prepared despite batch 1 failing.
    assert {p.item_sku for p in summary.payloads} == {"LB-F2"}

    # Batch 1 is recorded as an error with a human-readable (non-traceback) reason.
    assert len(summary.errors) == 1
    err = summary.errors[0]
    assert err.batch_folder_id == "F1"
    assert "ValueError" in err.reason
    assert "Traceback" not in err.reason

    # State store reflects the failure explicitly (ItemStatus.ERROR is now used).
    rec = store.get_item("LB-F1")
    assert rec is not None
    assert rec.status is ItemStatus.ERROR

    # The healthy batch was still recorded PRICED as usual.
    assert store.get_item("LB-F2").status is ItemStatus.PRICED


def test_scan_drive_fetch_error_on_one_batch_does_not_abort_the_scan(monkeypatch, store):
    """
    A DriveFetchError raised while downloading one batch's images must not
    abort the scan: the other batch is still prepared and the failing batch
    is recorded ItemStatus.ERROR (PI-001).
    """
    from src.core.drive_fetcher import DriveFetchError

    batches = [
        {"folder_id": "F1", "folder_name": "Headphones", "image_files": []},
        {"folder_id": "F2", "folder_name": "Camera", "image_files": []},
    ]
    monkeypatch.setattr(orchestrator.drive_fetcher, "list_pending_batches", lambda: batches)

    def _download(batch):
        if batch["folder_id"] == "F1":
            raise DriveFetchError(
                batch_folder_id="F1", batch_folder_name="Headphones",
                cause=ConnectionError("network down"),
            )
        return ([f"/cache/{batch['folder_id']}.jpg"], False)

    monkeypatch.setattr(orchestrator.drive_fetcher, "download_batch_images", _download)

    provider = _StubProvider(_VISION_JSON)
    summary = orchestrator.scan_and_prepare(provider, store)

    assert {p.item_sku for p in summary.payloads} == {"LB-F2"}
    assert len(summary.errors) == 1
    assert summary.errors[0].batch_folder_id == "F1"
    assert "DriveFetchError" in summary.errors[0].reason

    rec = store.get_item("LB-F1")
    assert rec.status is ItemStatus.ERROR
    assert store.get_item("LB-F2").status is ItemStatus.PRICED


def test_scan_error_reason_is_truncated(monkeypatch, store):
    """A very long exception message is capped (~300 chars) in the recorded reason."""
    batches = [{"folder_id": "F1", "folder_name": "Headphones", "image_files": []}]
    monkeypatch.setattr(orchestrator.drive_fetcher, "list_pending_batches", lambda: batches)
    monkeypatch.setattr(
        orchestrator.drive_fetcher,
        "download_batch_images",
        lambda batch: ([f"/cache/{batch['folder_id']}.jpg"], False),
    )

    class _HugeErrorProvider:
        def generate_from_images(self, image_paths, prompt, **kwargs):
            raise ValueError("x" * 5000)

        @property
        def model_name(self):
            return "stub"

    summary = orchestrator.scan_and_prepare(_HugeErrorProvider(), store)
    assert len(summary.errors) == 1
    assert len(summary.errors[0].reason) <= 300


def test_scan_stale_cache_flag_propagates_to_summary(monkeypatch, store):
    """
    The stale-cache warning flag from download_batch_images (previously
    discarded via `image_paths, _stale_warning = ...`) now propagates onto
    the ScanSummary for the UI to display.
    """
    batches = [{"folder_id": "F1", "folder_name": "Headphones", "image_files": []}]
    monkeypatch.setattr(orchestrator.drive_fetcher, "list_pending_batches", lambda: batches)
    monkeypatch.setattr(
        orchestrator.drive_fetcher,
        "download_batch_images",
        lambda batch: ([f"/cache/{batch['folder_id']}.jpg"], True),  # stale cache used
    )

    summary = orchestrator.scan_and_prepare(_StubProvider(_VISION_JSON), store)
    assert summary.stale_cache is True
    assert len(summary.payloads) == 1
    assert summary.errors == []


def test_scan_no_stale_cache_when_all_fresh(mock_drive, store):
    """When no batch reports a stale-cache fallback, the summary flag is False."""
    summary = orchestrator.scan_and_prepare(_StubProvider(_VISION_JSON), store)
    assert summary.stale_cache is False


def test_scan_summary_is_iterable_like_the_old_list_return(mock_drive, store):
    """
    Backward compatibility: ScanSummary supports iteration/len so callers
    written against the old `list[ListingPayload]` return type still work.
    """
    summary = orchestrator.scan_and_prepare(_StubProvider(_VISION_JSON), store)
    assert len(summary) == 2
    assert {p.item_sku for p in summary} == {"LB-F1", "LB-F2"}


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


# ── archive_batch wiring (bug fix: archive_batch previously had zero callers) ─


def test_publish_approved_archives_batch(monkeypatch, store):
    """A fresh publish archives the source Drive batch via drive_fetcher."""
    archive_calls = []
    monkeypatch.setattr(
        orchestrator.drive_fetcher,
        "archive_batch",
        lambda folder_id, folder_name: archive_calls.append((folder_id, folder_name)),
    )

    client = _FakeEbayClient()
    orchestrator.publish_approved(_full_payload(), store, ebay_client=client)

    assert len(archive_calls) == 1
    folder_id, _folder_name = archive_calls[0]
    # derive_sku produces "LB-{folderId}"; the archive call must recover the
    # original Drive folder id from the SKU.
    assert folder_id == "F1"


def test_publish_approved_dedup_hit_does_not_archive(monkeypatch, store):
    """A dedup hit (already published) must not re-archive the batch."""
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
    archive_calls = []
    monkeypatch.setattr(
        orchestrator.drive_fetcher,
        "archive_batch",
        lambda folder_id, folder_name: archive_calls.append((folder_id, folder_name)),
    )

    client = _FakeEbayClient()
    orchestrator.publish_approved(_full_payload(), store, ebay_client=client)

    assert archive_calls == []  # nothing to archive on a dedup hit


def test_publish_approved_archive_failure_does_not_fail_publish(monkeypatch, store):
    """
    An archive_batch failure is logged/swallowed — the publish result must still
    report success and the state store must still show PUBLISHED (R-STATE: the
    publish itself is never rolled back by a downstream archive failure).
    """

    def _boom(folder_id, folder_name):
        raise RuntimeError("Drive is down")

    monkeypatch.setattr(orchestrator.drive_fetcher, "archive_batch", _boom)

    client = _FakeEbayClient()
    result = orchestrator.publish_approved(_full_payload(), store, ebay_client=client)

    # Publish result unaffected by the archive failure.
    assert result.offer_id == "OFFER-X"
    assert result.listing_id == "LIST-X"
    # State store still recorded the publish.
    rec = store.get_item("LB-F1")
    assert rec.status is ItemStatus.PUBLISHED
    assert rec.offer_id == "OFFER-X"


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
