"""
Module: test_contracts.py
Purpose: Contract tests for the frozen pydantic schemas — the Phase 1 deliverable
         that parallel module agents build against.
Primary Responsibilities:
  - Assert the serialized shapes match the blueprint "Data contracts" JSON.
  - Lock in the FMEA-driven invariants (forced defects_found, floor_applied,
    missing_inputs, deterministic SKU fields, extra="forbid").
Key Interfaces:
  - Input: src.contracts models.
FMEA Constraints Enforced (asserted): PI-004, PI-005, PI-006, R-PRICE, R-STATE.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.contracts import (
    ItemRecord,
    ItemStatus,
    ListingPayload,
    MarginGuardOutput,
    VisionAgentOutput,
)


def test_vision_output_default_shape_matches_blueprint():
    """VisionAgentOutput serializes to the exact blueprint key set."""
    out = VisionAgentOutput()
    assert set(out.model_dump().keys()) == {
        "item_specifics",
        "condition",
        "defects_found",
        "dropped_fields",
    }


def test_vision_output_forces_defects_list_present_pi004():
    """defects_found is always present even when empty (PI-004)."""
    out = VisionAgentOutput(item_specifics={"Brand": "Sony"}, condition="Used")
    assert out.defects_found == []
    assert "defects_found" in out.model_dump()


def test_vision_output_rejects_unknown_keys():
    """extra='forbid' makes a drifting producer fail loudly (PI-005 guard)."""
    with pytest.raises(ValidationError):
        VisionAgentOutput(item_specifics={}, hallucinated_field="x")


def test_margin_guard_output_shape_matches_blueprint():
    """MarginGuardOutput serializes to the exact blueprint key set."""
    out = MarginGuardOutput()
    dumped = out.model_dump()
    assert set(dumped.keys()) == {
        "margin_guard_price",
        "active_comp_anchor",
        "user_confirmed_comp",
        "floor_price",
        "floor_applied",
        "active_comp_range",
        "reasoning",
        "missing_inputs",
    }
    # active_comp_range is a nested {low, high} object.
    assert set(dumped["active_comp_range"].keys()) == {"low", "high"}


def test_margin_guard_floor_flag_and_missing_inputs_defaults():
    """floor_applied defaults False (PI-006); missing_inputs defaults empty (R-PRICE)."""
    out = MarginGuardOutput()
    assert out.floor_applied is False
    assert out.user_confirmed_comp is None
    assert out.missing_inputs == []


def test_item_record_status_enum_and_sku_key_r_state():
    """ItemRecord carries the deterministic SKU and an ItemStatus (R-STATE)."""
    rec = ItemRecord(item_sku="LB-folder123", batch_folder_id="folder123")
    assert rec.status is ItemStatus.NEW
    assert rec.item_sku == "LB-folder123"
    # status serializes to its string value for the SQLite column.
    assert rec.model_dump()["status"] == "new"


def test_listing_payload_requires_sku_and_price():
    """ListingPayload requires the idempotency key and a price field."""
    with pytest.raises(ValidationError):
        ListingPayload(title="x")  # missing item_sku and price
    ok = ListingPayload(item_sku="LB-1", title="x", price=9.99)
    assert ok.marketplace_id == "EBAY_US"
