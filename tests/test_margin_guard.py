"""
Module: test_margin_guard.py
Purpose: Tests for the Phase 3 pricing layer — price_item / deterministic_floor /
         fetch_and_price — pure logic + a mocked ebay_client for comps.
FMEA Constraints Enforced (asserted): PI-006, R-PRICE.
"""

from __future__ import annotations

from src.ai.margin_guard import (
    build_comp_query,
    deterministic_floor,
    fetch_and_price,
    price_item,
)
from src.contracts import VisionAgentOutput


def _vision(**specifics) -> VisionAgentOutput:
    """Build a VisionAgentOutput with the given item_specifics."""
    return VisionAgentOutput(item_specifics=specifics, condition="Used", defects_found=[])


class _FakeEbayClient:
    """Stand-in for EbayClient exposing search_active_comps."""

    def __init__(self, comps: list[float]) -> None:
        self._comps = comps
        self.last_query: str | None = None

    def search_active_comps(self, query, *, limit=20, extra_filter=None) -> list[float]:
        self.last_query = query
        return self._comps


# ── deterministic_floor ───────────────────────────────────────────────────────


def test_deterministic_floor_math():
    """Floor = (cost + fees) * 1.15, rounded to cents."""
    assert deterministic_floor(10.0, 2.0) == 13.80
    assert deterministic_floor(100.0, 0.0) == 115.00


# ── anchor + range ────────────────────────────────────────────────────────────


def test_price_item_anchor_is_median_and_range_is_min_max():
    """Anchor = median active comp; range = min/max (R-PRICE)."""
    out = price_item(
        _vision(Brand="Sony"), cost=50.0, fees=10.0, active_comps=[180.0, 200.0, 260.0]
    )
    assert out.active_comp_anchor == 200.0  # median of the three
    assert out.active_comp_range.low == 180.0
    assert out.active_comp_range.high == 260.0
    # 200 is above the 69.00 floor, so no override.
    assert out.floor_applied is False
    assert out.margin_guard_price == 200.0


# ── floor override (PI-006) ───────────────────────────────────────────────────


def test_floor_overrides_below_floor_basis_pi006():
    """A comp basis below the floor is overridden; floor_applied set (PI-006)."""
    out = price_item(
        _vision(Brand="Sony"), cost=100.0, fees=20.0, active_comps=[80.0, 90.0]
    )
    assert out.floor_price == deterministic_floor(100.0, 20.0)  # 138.00
    assert out.floor_applied is True
    assert out.margin_guard_price == 138.00


# ── human-confirmed comp wins ─────────────────────────────────────────────────


def test_user_confirmed_comp_takes_precedence_over_anchor():
    """A human-confirmed comp is the basis even when active comps exist."""
    out = price_item(
        _vision(Brand="Sony"),
        cost=10.0,
        fees=2.0,
        active_comps=[300.0, 320.0],
        user_confirmed_comp=275.0,
    )
    assert out.user_confirmed_comp == 275.0
    assert out.margin_guard_price == 275.0  # not the 310 anchor
    assert "human-confirmed comp" in out.reasoning


# ── missing inputs (R-PRICE) ──────────────────────────────────────────────────


def test_missing_cost_and_fees_route_to_missing_inputs():
    """Unknown cost/fees are reported, never guessed (R-PRICE)."""
    out = price_item(_vision(Brand="Sony"), cost=None, fees=None, active_comps=[150.0])
    assert "cost" in out.missing_inputs
    assert "fees" in out.missing_inputs
    assert out.floor_price == 0.0
    assert out.floor_applied is False
    # Still prices off the anchor since a comp exists.
    assert out.margin_guard_price == 150.0


def test_no_comp_at_all_falls_back_to_floor_and_flags_missing():
    """No comp + no user comp: floor fallback + missing_inputs flagged."""
    out = price_item(_vision(Brand="Sony"), cost=40.0, fees=8.0, active_comps=[])
    assert "active_comp_or_user_comp" in out.missing_inputs
    assert out.floor_applied is True
    assert out.margin_guard_price == deterministic_floor(40.0, 8.0)  # 55.20


def test_no_comp_and_no_cost_cannot_price():
    """No comp and no cost/fees: price 0 and clear missing_inputs."""
    out = price_item(_vision(), cost=None, fees=None, active_comps=[])
    assert out.margin_guard_price == 0.0
    assert "cost" in out.missing_inputs
    assert "active_comp_or_user_comp" in out.missing_inputs


# ── query building + fetch_and_price wiring ───────────────────────────────────


def test_build_comp_query_uses_priority_aspects():
    """The Browse query is built from priority aspects in order."""
    q = build_comp_query(_vision(Model="WH-1000XM4", Brand="Sony", Color="Black"))
    assert q == "Sony WH-1000XM4"  # Brand then Model; Color not a query aspect


def test_fetch_and_price_wires_ebay_client():
    """fetch_and_price queries the (mocked) client and prices off the comps."""
    client = _FakeEbayClient([190.0, 210.0])
    out = fetch_and_price(_vision(Brand="Sony", Model="XM4"), client, cost=50.0, fees=10.0)
    assert client.last_query == "Sony XM4"
    assert out.active_comp_anchor == 200.0
    assert out.margin_guard_price == 200.0
