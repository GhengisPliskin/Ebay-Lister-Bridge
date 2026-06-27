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

STATUS: interface stub (signatures + docstrings). Implemented by a parallel
Phase 3 agent against the frozen MarginGuardOutput contract.
"""

from __future__ import annotations

from src.contracts import MarginGuardOutput, VisionAgentOutput


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

    Args:
        vision: The item's VisionAgentOutput (specifics/condition/defects).
        cost: Item acquisition cost (USD), or None if unknown (-> missing_inputs).
        fees: Estimated selling fees (USD), or None if unknown (-> missing_inputs).
        active_comps: Active comparable asking prices from the Browse API; used as
            the anchor and to populate active_comp_range.
        user_confirmed_comp: Operator-entered true sold-comp price, if provided.

    Returns:
        MarginGuardOutput: Final price with anchor, range, floor, floor_applied,
        reasoning, and any missing_inputs.

    Side Effects:
        None (pure computation; comps are passed in, not fetched here).

    Raises:
        NotImplementedError: This is a Phase 3 stub.

    FMEA Constraints:
        PI-006 — floor = (cost + fees) * 1.15 overrides below-floor prices and
        sets floor_applied.
        R-PRICE — missing cost/comp routes to missing_inputs, never guessed.
    """
    raise NotImplementedError("margin_guard.price_item is a Phase 3 stub")


def deterministic_floor(cost: float, fees: float) -> float:
    """
    Compute the deterministic price floor: (cost + fees) * 1.15.

    Args:
        cost: Item acquisition cost (USD).
        fees: Estimated selling fees (USD).

    Returns:
        The floor price (USD).

    Side Effects:
        None.

    Raises:
        NotImplementedError: This is a Phase 3 stub.

    FMEA Constraints:
        PI-006 — the guaranteed backstop retained from the original Margin-Guard.
    """
    raise NotImplementedError("margin_guard.deterministic_floor is a Phase 3 stub")
