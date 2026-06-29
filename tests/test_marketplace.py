"""
Module: test_marketplace.py
Purpose: Tests for the v1.2 MarketplaceAdapter layer — capability typing, EbayAdapter
         conformance (wraps a fake client), the OtherDraftAdapter draft output +
         per-platform templates, and the registry. No network.
FMEA Constraints Enforced (asserted): PI-007, PI-008.
"""

from __future__ import annotations

import pytest

from src.contracts import AdapterCapability, DraftOutput, ListingPayload, PublishResult
from src.marketplace import (
    EbayAdapter,
    OtherDraftAdapter,
    get_adapter,
    list_targets,
    supported_platforms,
    target_label,
)
from src.marketplace.base import AutoPublishAdapter, DraftAdapter, MarketplaceAdapter


def _payload(**overrides) -> ListingPayload:
    data = dict(
        item_sku="LB-F1",
        title="Sony WH-1000XM4 Wireless Headphones",
        item_specifics={"Brand": "Sony", "Model": "WH-1000XM4"},
        condition="USED_VERY_GOOD",
        price=199.99,
        category_id="112529",
        local_image_paths=["/cache/F1.jpg", "/cache/F1b.jpg"],
        fulfillment_policy_id="FP",
        payment_policy_id="PP",
        return_policy_id="RP",
        merchant_location_key="LOC",
        listing_description="Condition: Used - Very Good.\nNo visible defects noted.",
    )
    data.update(overrides)
    return ListingPayload(**data)


class _FakeEbayClient:
    def __init__(self):
        self.published = []

    def publish_listing(self, payload):
        self.published.append(payload)
        return PublishResult(
            item_sku=payload.item_sku, offer_id="O-1", listing_id="L-1",
            eps_image_urls=["https://i.ebayimg.com/x.jpg"],
        )


# ── capability enum ───────────────────────────────────────────────────────────


def test_adapter_capability_values():
    assert AdapterCapability.AUTO_PUBLISH.value == "auto_publish"
    assert AdapterCapability.DRAFT_ONLY.value == "draft_only"


# ── EbayAdapter conformance ───────────────────────────────────────────────────


def test_ebay_adapter_is_auto_publish_and_conforms():
    adapter = EbayAdapter(client=_FakeEbayClient())
    assert isinstance(adapter, (MarketplaceAdapter, AutoPublishAdapter))
    assert adapter.name == "ebay"
    assert adapter.capability is AdapterCapability.AUTO_PUBLISH


def test_ebay_adapter_publish_delegates_to_client():
    client = _FakeEbayClient()
    adapter = EbayAdapter(client=client)
    result = adapter.publish(_payload())
    assert isinstance(result, PublishResult)
    assert result.listing_id == "L-1"
    assert len(client.published) == 1


# ── OtherDraftAdapter ─────────────────────────────────────────────────────────


def test_other_adapter_is_draft_only_and_conforms():
    adapter = OtherDraftAdapter("mercari")
    assert isinstance(adapter, (MarketplaceAdapter, DraftAdapter))
    assert adapter.name == "other:mercari"
    assert adapter.capability is AdapterCapability.DRAFT_ONLY


def test_other_adapter_unknown_platform_raises():
    with pytest.raises(ValueError):
        OtherDraftAdapter("craigslist")


def test_other_adapter_renders_and_writes_files(tmp_path):
    adapter = OtherDraftAdapter("facebook_marketplace")
    out = adapter.render_draft(_payload(), str(tmp_path))
    assert isinstance(out, DraftOutput)
    assert out.platform == "facebook_marketplace"
    assert out.platform_label == "Facebook Marketplace"
    # Files written under <out>/<sku>/<platform>/.
    from pathlib import Path

    posting = Path(out.draft_path)
    manifest = Path(out.manifest_path)
    assert posting.is_file() and manifest.is_file()
    text = posting.read_text(encoding="utf-8")
    assert "Sony WH-1000XM4" in text
    assert "$199.99" in text
    assert "| Brand | Sony |" in text  # specifics table (PI-008 tidy)
    # Manifest lists both photos.
    assert manifest.read_text(encoding="utf-8").count("/cache/") == 2


def test_other_adapter_mercari_title_cap(tmp_path):
    """Mercari caps titles at 80 chars; the draft truncates accordingly."""
    long_title = "X" * 200
    out = OtherDraftAdapter("mercari").render_draft(
        _payload(title=long_title), str(tmp_path)
    )
    assert len(out.title) == 80


# ── registry ──────────────────────────────────────────────────────────────────


def test_list_targets_includes_ebay_and_drafts():
    targets = list_targets()
    assert targets[0] == "ebay"
    assert "other:facebook_marketplace" in targets
    assert "other:mercari" in targets
    assert set(targets[1:]) == {f"other:{p}" for p in supported_platforms()}


def test_get_adapter_routes_by_key():
    assert isinstance(get_adapter("ebay"), EbayAdapter)
    assert isinstance(get_adapter("other:mercari"), OtherDraftAdapter)


def test_get_adapter_unknown_raises():
    with pytest.raises(ValueError):
        get_adapter("amazon")


def test_target_label_is_human_readable():
    assert "auto-publish" in target_label("ebay")
    assert target_label("other:mercari") == "Mercari (draft)"
