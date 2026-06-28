"""
Module: margin_guard.py
Purpose: Produce an active-comp anchored, human-confirmable, floor-protected price
         for one item, returning the frozen MarginGuardOutput.
Primary Responsibilities:
  - Anchor on Browse API active comps (current asking) and populate the range.
  - Apply the deterministic floor (cost + fees) * 1.15 and flag floor_applied (PI-006).
  - Route missing cost/comp inputs to missing_inputs for the UI; never guess (R-PRICE).
Key Interfaces:
  - Input: VisionAgentOutput + cost inputs + active comps (from ebay_client.Browse).
  - Output: MarginGuardOutput consumed by orchestrator.py and ui/app.py.
FMEA Constraints Enforced:
  - PI-006 — floor overrides a below-floor comp price and sets floor_applied.
  - R-PRICE — missing inputs are surfaced, not invented.
"""

from __future__ import annotations

from src.contracts import ActiveCompRange, MarginGuardOutput, VisionAgentOutput

# The deterministic floor multiplier: a 15% margin over cost + fees.
_FLOOR_MULTIPLIER = 1.15

# Aspect names, in priority order, used to build a Browse comp-search query.
_QUERY_ASPECTS = ("Brand", "Model", "Type", "Product Line", "MPN")


def deterministic_floor(cost: float, fees: float) -> float:
    """
    Compute the deterministic price floor: (cost + fees) * 1.15.

    Args:
        cost: Item acquisition cost (USD).
        fees: Estimated selling fees (USD).

    Returns:
        The floor price (USD), rounded to cents.

    Side Effects:
        None.

    FMEA Constraints:
        PI-006 — the guaranteed backstop retained from the original Margin-Guard.
    """
    return round((cost + fees) * _FLOOR_MULTIPLIER, 2)


def _median(values: list[float]) -> float:
    """
    Return the median of a non-empty numeric list (0.0 for an empty list).

    Args:
        values: Numbers to summarize.

    Returns:
        The median (the mean of the two middle values for an even count), or 0.0
        when the list is empty.

    Side Effects:
        None.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def build_comp_query(vision: VisionAgentOutput) -> str:
    """
    Build a Browse search query string from the extracted item specifics.

    Args:
        vision: The item's VisionAgentOutput.

    Returns:
        A space-joined query from priority aspects (Brand, Model, ...). Falls back
        to all aspect values, then to an empty string if there are none.

    Side Effects:
        None.
    """
    parts = [
        vision.item_specifics[a] for a in _QUERY_ASPECTS if a in vision.item_specifics
    ]
    if not parts:
        # Fall back to whatever specifics we do have, preserving insertion order.
        parts = list(vision.item_specifics.values())
    return " ".join(p for p in parts if p).strip()


def price_item(
    vision: VisionAgentOutput,
    *,
    cost: float | None,
    fees: float | None,
    active_comps: list[float] | None = None,
    user_confirmed_comp: float | None = None,
) -> MarginGuardOutput:
    """
    Compute the suggested price for one item.

    Pricing model (blueprint v1.1): active-comp anchored + human-confirmed + floor.
      - The anchor is the median of the active comps; the range is their min/max.
      - The pricing basis is the human-confirmed comp when provided, else the anchor.
      - The deterministic floor overrides any basis below it (PI-006).
      - Missing cost/fees/comp inputs are reported in missing_inputs (R-PRICE).

    Args:
        vision: The item's VisionAgentOutput (kept for traceability/reasoning).
        cost: Item acquisition cost (USD), or None if unknown (-> missing_inputs).
        fees: Estimated selling fees (USD), or None if unknown (-> missing_inputs).
        active_comps: Active comparable asking prices from the Browse API.
        user_confirmed_comp: Operator-entered true sold-comp price, if provided.

    Returns:
        MarginGuardOutput: Final price with anchor, range, floor, floor_applied,
        reasoning, and any missing_inputs.

    Side Effects:
        None (pure computation; comps are passed in, not fetched here).

    FMEA Constraints:
        PI-006 — floor = (cost + fees) * 1.15 overrides below-floor prices and
        sets floor_applied.
        R-PRICE — missing cost/comp routes to missing_inputs, never guessed.
    """
    comps = [float(c) for c in (active_comps or []) if c is not None and c > 0]
    missing_inputs: list[str] = []

    # ── Active-comp anchor + range ────────────────────────────────────────────
    anchor = round(_median(comps), 2) if comps else 0.0
    comp_range = ActiveCompRange(
        low=round(min(comps), 2) if comps else 0.0,
        high=round(max(comps), 2) if comps else 0.0,
    )

    # ── Floor (only computable when both cost and fees are known) ──────────────
    floor_computable = cost is not None and fees is not None
    floor_price = deterministic_floor(cost, fees) if floor_computable else 0.0
    if cost is None:
        missing_inputs.append("cost")
    if fees is None:
        missing_inputs.append("fees")

    # ── Pricing basis: human-confirmed comp wins; else the active-comp anchor ──
    if user_confirmed_comp is not None and user_confirmed_comp > 0:
        basis = round(float(user_confirmed_comp), 2)
        basis_label = "human-confirmed comp"
    elif anchor > 0:
        basis = anchor
        basis_label = "active-comp anchor"
    else:
        basis = None
        basis_label = None
        # No comp signal at all — the operator must supply one.
        missing_inputs.append("active_comp_or_user_comp")

    # ── Resolve the final price + floor override (PI-006) ──────────────────────
    floor_applied = False
    if basis is None:
        # No comp basis: fall back to the floor if we can compute it, else 0.
        final_price = floor_price if floor_computable else 0.0
        if floor_computable:
            floor_applied = True
            reasoning = (
                f"No comparable price available; defaulted to the deterministic "
                f"floor of ${floor_price:.2f} ((cost + fees) x {_FLOOR_MULTIPLIER}). "
                f"Confirm a comp to refine."
            )
        else:
            reasoning = (
                "No comparable price and no cost/fees available; cannot price. "
                "Provide a comp and cost/fees in the review screen."
            )
    else:
        if floor_computable and basis < floor_price:
            final_price = floor_price
            floor_applied = True
            reasoning = (
                f"{basis_label.capitalize()} of ${basis:.2f} was below the "
                f"deterministic floor of ${floor_price:.2f}; floor applied (PI-006)."
            )
        else:
            final_price = basis
            floor_note = (
                f" (above the ${floor_price:.2f} floor)" if floor_computable else ""
            )
            reasoning = f"Priced from the {basis_label} of ${basis:.2f}{floor_note}."

    return MarginGuardOutput(
        margin_guard_price=round(final_price, 2),
        active_comp_anchor=anchor,
        user_confirmed_comp=(
            round(float(user_confirmed_comp), 2)
            if user_confirmed_comp is not None
            else None
        ),
        floor_price=floor_price,
        floor_applied=floor_applied,
        active_comp_range=comp_range,
        reasoning=reasoning,
        missing_inputs=missing_inputs,
    )


def fetch_and_price(
    vision: VisionAgentOutput,
    ebay_client,
    *,
    cost: float | None,
    fees: float | None,
    user_confirmed_comp: float | None = None,
    limit: int = 20,
    extra_filter: str | None = None,
) -> MarginGuardOutput:
    """
    Convenience wrapper: fetch active comps via ebay_client, then price_item.

    Keeps price_item pure (comps passed in) while wiring the existing Browse call
    for the orchestrator. The query is built from the extracted item specifics.

    Args:
        vision: The item's VisionAgentOutput.
        ebay_client: An object exposing search_active_comps(query, *, limit,
            extra_filter) -> list[float] (src.api.ebay_client.EbayClient).
        cost: Item acquisition cost (USD) or None.
        fees: Estimated selling fees (USD) or None.
        user_confirmed_comp: Operator-entered sold-comp price, if any.
        limit: Max comps to request from Browse.
        extra_filter: Optional eBay Browse `filter` expression.

    Returns:
        MarginGuardOutput from price_item using the fetched comps.

    Side Effects:
        One Browse API call via ebay_client (the client itself may be mocked).

    FMEA Constraints:
        R-PRICE — comps feed the anchor; missing comps still route to missing_inputs.
    """
    query = build_comp_query(vision)
    comps: list[float] = []
    if query:
        comps = ebay_client.search_active_comps(
            query, limit=limit, extra_filter=extra_filter
        )
    return price_item(
        vision,
        cost=cost,
        fees=fees,
        active_comps=comps,
        user_confirmed_comp=user_confirmed_comp,
    )
