"""
Module: ebay_adapter.py
Purpose: EbayAdapter (v1.2) — wraps the existing eBay REST publish path behind the
         MarketplaceAdapter interface. Refactor, not rewrite: all eBay behavior is
         delegated unchanged to ebay_client.EbayClient.
Primary Responsibilities:
  - Declare the 'ebay' AUTO_PUBLISH adapter.
  - Delegate publish() to EbayClient.publish_listing (Media upload + REST publish).
Key Interfaces:
  - Input: a ListingPayload + an optional injected EbayClient (tests pass a fake).
  - Output: PublishResult.
FMEA Constraints Enforced:
  - PI-007 — publish() is only invoked after an explicit human Approve.
  - R-AUTH / R-IMG / PI-009 — all enforced inside the wrapped EbayClient.
"""

from __future__ import annotations

from src.contracts import ListingPayload, PublishResult
from src.marketplace.base import AutoPublishAdapter


class EbayAdapter(AutoPublishAdapter):
    """
    Auto-publish adapter for eBay, wrapping ebay_client.EbayClient.

    The client is injected for tests; otherwise it is constructed lazily on first
    publish so importing/constructing the adapter needs no eBay env or network.
    """

    def __init__(self, client=None) -> None:
        """
        Configure the adapter.

        Args:
            client: An EbayClient (or compatible fake exposing publish_listing).
                When None, a real EbayClient is built lazily inside publish().

        Returns:
            None

        Side Effects:
            None at construction (no env read, no network).
        """
        self._client = client

    @property
    def name(self) -> str:
        """The registry key for this adapter."""
        return "ebay"

    def publish(self, payload: ListingPayload) -> PublishResult:
        """
        Publish the payload to eBay via the wrapped client.

        Args:
            payload: The operator-approved ListingPayload.

        Returns:
            The PublishResult from EbayClient.publish_listing.

        Side Effects:
            Media upload + 3-step REST publish against eBay (via the client).

        FMEA Constraints:
            PI-007 — only called after an explicit human Approve.
        """
        client = self._client
        if client is None:
            # Lazy construction keeps adapter import/use env-free until publish.
            from src.api.ebay_client import EbayClient

            client = EbayClient()
        return client.publish_listing(payload)
