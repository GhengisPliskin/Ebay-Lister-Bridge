"""
Module: review.py
Purpose: Pure, Streamlit-free helpers for the review/approve screen — comp-search
         links, price recomputation, operator-edit application, and pre-publish
         validation. Kept separate from app.py so it is unit-testable without
         Streamlit.
Primary Responsibilities:
  - Build the operator's Terapeak / sold-comp research links (human-in-the-loop).
  - Recompute the Margin-Guard price when the operator enters a comp / cost / fees.
  - Apply operator edits (including description corrections) to a ListingPayload
    immutably.
  - Expose the canonical eBay condition enum for the UI's condition selectbox,
    mirroring orchestrator._CONDITION_MAP without importing streamlit-side code
    into core.
  - Report pre-publish validation problems + remaining missing inputs.
Key Interfaces:
  - Input: VisionAgentOutput, MarginGuardOutput, ListingPayload + operator edits.
  - Output: URLs, recomputed MarginGuardOutput, edited ListingPayload, problem lists.
FMEA Constraints Enforced:
  - PI-006 / R-PRICE — recompute routes through margin_guard (floor + missing_inputs).
  - PI-009 — validate_for_publish reuses EbayClient.validate_offer before Approve.
  - PI-008 — surfaces tidy fields (no raw JSON) for the UI to render.
  - PI-004 — apply_operator_edits carries operator corrections to the defect-
    disclosure description through to the payload instead of discarding them.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from src.ai import margin_guard
from src.api.ebay_client import EbayClient
from src.contracts import ListingPayload, MarginGuardOutput, VisionAgentOutput

# eBay marketplace used for the research links.
_SOLD_SEARCH_BASE = "https://www.ebay.com/sch/i.html"
_TERAPEAK_BASE = "https://www.ebay.com/sh/research"

# Canonical eBay condition enum values, in the same order as (and mirroring)
# orchestrator._CONDITION_MAP's target values (deduplicated, order-preserved).
# Kept here — rather than imported from orchestrator — so app.py (a Streamlit
# module) never needs to import core orchestrator internals just to populate a
# selectbox; if _CONDITION_MAP's target set changes, update this list to match.
EBAY_CONDITION_VALUES: list[str] = [
    "FOR_PARTS_OR_NOT_WORKING",
    "LIKE_NEW",
    "NEW_OTHER",
    "NEW",
    "USED_EXCELLENT",
    "USED_VERY_GOOD",
    "USED_ACCEPTABLE",
    "USED_GOOD",
]


def build_sold_comp_url(query: str) -> str:
    """
    Build a public eBay "sold + completed" search URL for operator comp checks.

    Args:
        query: The item search text (e.g. "Sony WH-1000XM4").

    Returns:
        A URL filtering to sold, completed listings.

    Side Effects:
        None.

    FMEA Constraints:
        R-PRICE — supports the human-in-the-loop sold-comp confirmation step.
    """
    q = quote_plus(query.strip())
    return f"{_SOLD_SEARCH_BASE}?_nkw={q}&LH_Sold=1&LH_Complete=1"


def build_terapeak_url(query: str) -> str:
    """
    Build a Terapeak (Seller Hub research) URL for the given query.

    Args:
        query: The item search text.

    Returns:
        A Terapeak research URL (requires the operator to be signed in).

    Side Effects:
        None.

    FMEA Constraints:
        R-PRICE — the preferred sold-data research tool surfaced to the operator.
    """
    q = quote_plus(query.strip())
    return f"{_TERAPEAK_BASE}?marketplace=EBAY-US&keywords={q}&tabName=SOLD"


def recompute_price(
    vision: VisionAgentOutput,
    *,
    cost: float | None,
    fees: float | None,
    active_comps: list[float] | None,
    user_confirmed_comp: float | None,
) -> MarginGuardOutput:
    """
    Recompute the Margin-Guard price from the operator's current inputs.

    Thin passthrough to margin_guard.price_item so the UI re-prices live as the
    operator enters a confirmed comp / cost / fees.

    Args:
        vision: The item's extraction result.
        cost: Operator-entered cost (USD) or None.
        fees: Operator-entered fees (USD) or None.
        active_comps: Active comps already fetched (anchor), if any.
        user_confirmed_comp: Operator-entered sold-comp price, if any.

    Returns:
        A fresh MarginGuardOutput (price, floor_applied, missing_inputs, reasoning).

    Side Effects:
        None.

    FMEA Constraints:
        PI-006 / R-PRICE — floor + missing-input handling live in price_item.
    """
    return margin_guard.price_item(
        vision,
        cost=cost,
        fees=fees,
        active_comps=active_comps,
        user_confirmed_comp=user_confirmed_comp,
    )


def apply_operator_edits(
    payload: ListingPayload,
    *,
    title: str | None = None,
    price: float | None = None,
    condition: str | None = None,
    category_id: str | None = None,
    item_specifics: dict[str, str] | None = None,
    description: str | None = None,
) -> ListingPayload:
    """
    Return a copy of the payload with the operator's edits applied.

    Args:
        payload: The original assembled ListingPayload.
        title: Edited title, if changed.
        price: Edited final price (USD), if changed.
        condition: Edited eBay condition enum, if changed.
        category_id: Edited eBay category ID, if changed.
        item_specifics: Edited aspects map, if changed.
        description: Edited listing description, if changed. Operator
            corrections here matter because the description is where PI-004
            defect disclosures live — leaving this unread from the UI silently
            discards operator fixes to defect-disclosure text.

    Returns:
        A new ListingPayload with the provided fields overridden (others kept).

    Side Effects:
        None (pydantic model_copy is immutable-style).

    FMEA Constraints:
        PI-004 — description edits (defect disclosures) are applied like every
        other field; None leaves the original text untouched.
    """
    updates: dict = {}
    if title is not None:
        updates["title"] = title
    if price is not None:
        updates["price"] = price
    if condition is not None:
        updates["condition"] = condition
    if category_id is not None:
        updates["category_id"] = category_id
    if item_specifics is not None:
        updates["item_specifics"] = item_specifics
    if description is not None:
        updates["listing_description"] = description
    return payload.model_copy(update=updates)


def validate_for_publish(payload: ListingPayload) -> list[str]:
    """
    Return the list of problems blocking publish (empty == ready to Approve).

    Args:
        payload: The (possibly operator-edited) ListingPayload.

    Returns:
        Human-readable problem strings from EbayClient.validate_offer (PI-009).
        Note: images upload at publish time, so an empty eps_image_urls is NOT
        flagged here when local_image_paths are present.

    Side Effects:
        None.

    FMEA Constraints:
        PI-009 — the same required-field check the publish path enforces, surfaced
        in the UI before the operator can Approve.
    """
    problems = EbayClient.validate_offer(payload)
    # Pre-publish, EPS URLs don't exist yet; treat local photos as sufficient.
    if payload.local_image_paths:
        problems = [p for p in problems if "EPS image URL" not in p]
    return problems


def review_summary(
    vision: VisionAgentOutput, pricing: MarginGuardOutput
) -> dict:
    """
    Build a tidy, operator-facing summary dict (no raw JSON dumps; PI-008).

    Args:
        vision: The item's extraction result.
        pricing: The item's Margin-Guard result.

    Returns:
        A flat dict of display rows: specifics, condition, defects, suggested
        price, comp anchor/range, floor status, and any unresolved inputs.

    Side Effects:
        None.

    FMEA Constraints:
        PI-008 — a clean summary table, not raw JSON, drives operator review.
    """
    return {
        "specifics": dict(vision.item_specifics),
        "condition": vision.condition,
        "defects_found": list(vision.defects_found),
        "dropped_fields": list(vision.dropped_fields),
        "suggested_price": pricing.margin_guard_price,
        "active_comp_anchor": pricing.active_comp_anchor,
        "active_comp_range": (pricing.active_comp_range.low, pricing.active_comp_range.high),
        "floor_price": pricing.floor_price,
        "floor_applied": pricing.floor_applied,
        "reasoning": pricing.reasoning,
        "missing_inputs": list(pricing.missing_inputs),
    }
