"""
Module: base.py
Purpose: The MarketplaceAdapter interface (v1.2) — a capability-typed abstraction
         over publish targets so the orchestrator/UI can route a listing to eBay
         (auto-publish) or a generic draft (draft-only) uniformly.
Primary Responsibilities:
  - Declare MarketplaceAdapter (name + capability).
  - Declare AutoPublishAdapter (publish -> PublishResult) and DraftAdapter
    (render_draft -> DraftOutput) specializations.
Key Interfaces:
  - Input: a ListingPayload.
  - Output: PublishResult (auto-publish) or DraftOutput (draft-only).
FMEA Constraints Enforced:
  - PI-007 — capability typing makes auto-publish explicit; draft adapters cannot
    publish, preserving the human gate.
"""

from __future__ import annotations

import abc

from src.contracts import AdapterCapability, DraftOutput, ListingPayload, PublishResult


class MarketplaceAdapter(abc.ABC):
    """
    Base interface for a publish target.

    Every adapter declares a stable `name` (its registry key) and a `capability`
    (AUTO_PUBLISH or DRAFT_ONLY). Callers branch on `capability` to pick the right
    method — publish() vs render_draft().
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Return the adapter's stable registry key (e.g. 'ebay')."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def capability(self) -> AdapterCapability:
        """Return AUTO_PUBLISH or DRAFT_ONLY."""
        raise NotImplementedError


class AutoPublishAdapter(MarketplaceAdapter):
    """A marketplace that publishes a live listing via an API."""

    @property
    def capability(self) -> AdapterCapability:
        """Auto-publish adapters always report AUTO_PUBLISH."""
        return AdapterCapability.AUTO_PUBLISH

    @abc.abstractmethod
    def publish(self, payload: ListingPayload) -> PublishResult:
        """
        Publish the payload as a live listing.

        Args:
            payload: The operator-approved ListingPayload.

        Returns:
            A PublishResult (offer/listing IDs + EPS URLs).

        FMEA Constraints:
            PI-007 — only called after an explicit human Approve.
        """
        raise NotImplementedError


class DraftAdapter(MarketplaceAdapter):
    """A marketplace with no publish API — emits a draft for manual posting."""

    @property
    def capability(self) -> AdapterCapability:
        """Draft adapters always report DRAFT_ONLY."""
        return AdapterCapability.DRAFT_ONLY

    @abc.abstractmethod
    def render_draft(self, payload: ListingPayload, output_dir: str) -> DraftOutput:
        """
        Render a platform-tailored posting and write it under output_dir.

        Args:
            payload: The operator-approved ListingPayload.
            output_dir: Base directory to write the draft + photo manifest into.

        Returns:
            A DraftOutput describing the posting and the written file paths.

        FMEA Constraints:
            PI-007 — the operator posts the draft manually; nothing is auto-posted.
        """
        raise NotImplementedError
