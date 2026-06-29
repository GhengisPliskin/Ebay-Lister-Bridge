"""
Module: marketplace/__init__.py
Purpose: The marketplace-adapter registry (v1.2) — a single place the orchestrator
         and UI use to enumerate and construct publish targets.
Primary Responsibilities:
  - Re-export the adapter interfaces + concrete adapters.
  - Provide list_targets() (registry keys) and get_adapter(target) (factory).
Key Interfaces:
  - Input: a target key string (e.g. "ebay", "other:mercari").
  - Output: a MarketplaceAdapter instance.
FMEA Constraints Enforced:
  - PI-007 — capability is carried on every adapter so callers route correctly.

Target keys:
  - "ebay"                     -> EbayAdapter            (AUTO_PUBLISH)
  - "other:<platform>"         -> OtherDraftAdapter      (DRAFT_ONLY)
    where <platform> is one of other_adapter.supported_platforms().
"""

from __future__ import annotations

from src.marketplace.base import (
    AutoPublishAdapter,
    DraftAdapter,
    MarketplaceAdapter,
)
from src.marketplace.ebay_adapter import EbayAdapter
from src.marketplace.other_adapter import OtherDraftAdapter, supported_platforms

_OTHER_PREFIX = "other:"


def list_targets() -> list[str]:
    """
    Return all selectable target keys (eBay + each supported draft platform).

    Returns:
        e.g. ["ebay", "other:facebook_marketplace", "other:mercari"].
    """
    return ["ebay"] + [f"{_OTHER_PREFIX}{p}" for p in supported_platforms()]


def target_label(target: str) -> str:
    """
    Return a human-readable label for a target key (for UI menus).

    Args:
        target: A target key from list_targets().

    Returns:
        A display label (e.g. "eBay (auto-publish)", "Mercari (draft)").
    """
    if target == "ebay":
        return "eBay (auto-publish)"
    if target.startswith(_OTHER_PREFIX):
        platform = target[len(_OTHER_PREFIX):]
        # Defer to the adapter for the platform's display label.
        return f"{OtherDraftAdapter(platform).platform_label} (draft)"
    return target


def get_adapter(target: str, *, ebay_client=None) -> MarketplaceAdapter:
    """
    Construct the adapter for a target key.

    Args:
        target: A key from list_targets() (e.g. "ebay" or "other:mercari").
        ebay_client: Optional injected EbayClient passed to the eBay adapter
            (tests pass a fake); ignored for draft targets.

    Returns:
        A MarketplaceAdapter instance.

    Raises:
        ValueError: If the target key is unknown or names an unsupported platform.
    """
    if target == "ebay":
        return EbayAdapter(client=ebay_client)
    if target.startswith(_OTHER_PREFIX):
        platform = target[len(_OTHER_PREFIX):]
        return OtherDraftAdapter(platform)
    raise ValueError(
        f"Unknown marketplace target '{target}'. Choose one of: {', '.join(list_targets())}"
    )


__all__ = [
    "MarketplaceAdapter",
    "AutoPublishAdapter",
    "DraftAdapter",
    "EbayAdapter",
    "OtherDraftAdapter",
    "supported_platforms",
    "list_targets",
    "target_label",
    "get_adapter",
]
