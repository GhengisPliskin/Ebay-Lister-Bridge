"""
Module: test_review.py
Purpose: Tests for the Phase 5 Streamlit-free review helpers (src/ui/review.py).
         No Streamlit import, no network.
FMEA Constraints Enforced (asserted): R-PRICE, PI-006, PI-009, PI-008, PI-004.
"""

from __future__ import annotations

from src.contracts import ListingPayload, VisionAgentOutput
from src.core import orchestrator
from src.ui import review


def _vision(**specifics) -> VisionAgentOutput:
    return VisionAgentOutput(item_specifics=specifics, condition="Used", defects_found=[])


def _payload(**overrides) -> ListingPayload:
    data = dict(
        item_sku="LB-F1",
        title="Sony WH-1000XM4",
        item_specifics={"Brand": "Sony"},
        condition="USED_VERY_GOOD",
        price=199.99,
        category_id="112529",
        local_image_paths=["/cache/F1.jpg"],
        fulfillment_policy_id="FP",
        payment_policy_id="PP",
        return_policy_id="RP",
        merchant_location_key="LOC",
    )
    data.update(overrides)
    return ListingPayload(**data)


# ── research links (R-PRICE) ──────────────────────────────────────────────────


def test_sold_comp_url_filters_sold_completed():
    url = review.build_sold_comp_url("Sony WH-1000XM4")
    assert "Sony+WH-1000XM4" in url
    assert "LH_Sold=1" in url and "LH_Complete=1" in url


def test_terapeak_url_has_keywords():
    url = review.build_terapeak_url("Sony WH-1000XM4")
    assert "keywords=Sony+WH-1000XM4" in url


# ── recompute (PI-006 / R-PRICE) ──────────────────────────────────────────────


def test_recompute_price_applies_floor():
    out = review.recompute_price(
        _vision(Brand="Sony"), cost=100.0, fees=20.0, active_comps=[80.0],
        user_confirmed_comp=None,
    )
    assert out.floor_applied is True
    assert out.margin_guard_price == 138.00


def test_recompute_price_uses_user_comp():
    out = review.recompute_price(
        _vision(Brand="Sony"), cost=10.0, fees=2.0, active_comps=None,
        user_confirmed_comp=250.0,
    )
    assert out.margin_guard_price == 250.0


# ── edits ─────────────────────────────────────────────────────────────────────


def test_apply_operator_edits_overrides_only_given():
    p = _payload()
    edited = review.apply_operator_edits(p, price=149.0, title="New Title")
    assert edited.price == 149.0
    assert edited.title == "New Title"
    assert edited.category_id == p.category_id  # unchanged
    assert p.price == 199.99  # original untouched (immutable copy)


# ── description edits (PI-004: operator defect-disclosure corrections) ───────


def test_apply_operator_edits_applies_description():
    """A description edit is carried into listing_description (PI-004)."""
    p = _payload(listing_description="Condition: Used.\nNo visible defects noted.")
    edited = review.apply_operator_edits(
        p, description="Condition: Used.\nNoted defects:\n- small scratch on lid"
    )
    assert edited.listing_description == (
        "Condition: Used.\nNoted defects:\n- small scratch on lid"
    )
    # Original payload is untouched (immutable copy).
    assert p.listing_description == "Condition: Used.\nNo visible defects noted."


def test_apply_operator_edits_description_none_leaves_original():
    """description=None leaves the original listing_description untouched."""
    p = _payload(listing_description="Condition: Used.\nNo visible defects noted.")
    edited = review.apply_operator_edits(p, price=149.0)
    assert edited.listing_description == p.listing_description


# ── condition enum (Fix 3: selectbox validation) ──────────────────────────────


def test_ebay_condition_values_matches_orchestrator_condition_map():
    """review.EBAY_CONDITION_VALUES covers exactly the orchestrator._CONDITION_MAP
    target enum values (as a set), so the UI selectbox and the free-text mapper
    agree on the canonical eBay condition vocabulary."""
    expected = {enum_value for _, enum_value in orchestrator._CONDITION_MAP}
    assert set(review.EBAY_CONDITION_VALUES) == expected
    # No duplicates in the UI-facing list.
    assert len(review.EBAY_CONDITION_VALUES) == len(set(review.EBAY_CONDITION_VALUES))


# ── validation (PI-009) ───────────────────────────────────────────────────────


def test_validate_passes_with_local_images_no_eps_yet():
    """EPS URLs absent pre-publish is fine when local photos exist (PI-009)."""
    assert review.validate_for_publish(_payload()) == []


def test_validate_flags_missing_category_and_policies():
    problems = review.validate_for_publish(
        _payload(category_id="", fulfillment_policy_id="")
    )
    assert any("category_id" in p for p in problems)
    assert any("fulfillment_policy_id" in p for p in problems)


def test_validate_flags_no_images_at_all():
    """With neither EPS URLs nor local images, the image requirement is flagged."""
    problems = review.validate_for_publish(_payload(local_image_paths=[]))
    assert any("EPS image URL" in p for p in problems)


# ── summary (PI-008) ──────────────────────────────────────────────────────────


def test_review_summary_is_flat_display_dict():
    from src.ai.margin_guard import price_item

    pricing = price_item(_vision(Brand="Sony"), cost=50.0, fees=10.0, active_comps=[200.0])
    summary = review.review_summary(
        _vision(Brand="Sony"), pricing
    )
    assert summary["suggested_price"] == 200.0
    assert summary["active_comp_range"] == (200.0, 200.0)
    assert "missing_inputs" in summary and "reasoning" in summary
