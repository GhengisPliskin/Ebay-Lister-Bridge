"""
Module: orchestrator.py
Purpose: Sequence the per-item pipeline (drive -> vision -> pricing -> assemble ->
         publish), own per-item state, and flush AI context between items.
Primary Responsibilities:
  - For each pending batch/item: fetch images, extract, price, assemble the
    ListingPayload, and record every step in the state store.
  - Dedup already-published SKUs and resume after interruption (R-STATE).
  - Flush Gemini context after each item to avoid token bloat (PI-003).
  - Provide the headless entry point (`python -m src.core.orchestrator`) that the
    Streamlit UI and a CLI run both share.
Key Interfaces:
  - Input: drive_fetcher batches, AIProvider, StateStore, ebay_client.
  - Output: per-item ItemRecord updates; assembled ListingPayload(s) for the UI;
    PublishResult after an approved publish.
FMEA Constraints Enforced:
  - PI-003 — context flushed per item.
  - R-STATE — dedup + resume via the state store.

STATUS: interface stub (signatures + docstrings). Implemented by a parallel
Phase 4 agent against the frozen contracts. The human approval gate lives in the
UI (PI-007); the orchestrator never auto-publishes.
"""

from __future__ import annotations

from src.ai.provider import AIProvider
from src.contracts import ListingPayload, PublishResult
from src.core.state_store import StateStore


def derive_sku(batch_folder_id: str) -> str:
    """
    Derive the deterministic SKU for a batch from its Drive subfolder ID.

    Args:
        batch_folder_id: The Drive subfolder ID for the item.

    Returns:
        The SKU string, e.g. "LB-{folderId}" (the idempotency key).

    Raises:
        NotImplementedError: This is a Phase 4 stub.

    FMEA Constraints:
        R-STATE — stable SKU is the dedup/idempotency anchor.
    """
    raise NotImplementedError("orchestrator.derive_sku is a Phase 4 stub")


def scan_and_prepare(
    provider: AIProvider,
    store: StateStore,
) -> list[ListingPayload]:
    """
    Run drive -> vision -> pricing for every pending, not-yet-published item and
    return assembled (un-published) ListingPayloads for operator review.

    Args:
        provider: AIProvider for the vision step.
        store: StateStore for dedup, resume, and per-step recording.

    Returns:
        A list of ListingPayload, one per prepared item, ready for the UI review
        screen. Nothing is published here — publishing requires explicit Approve.

    Side Effects:
        Drive downloads; AI calls (context flushed per item, PI-003); state writes.

    Raises:
        NotImplementedError: This is a Phase 4 stub.

    FMEA Constraints:
        PI-003 — flush AI context after each item.
        R-STATE — skip SKUs already PUBLISHED; resume mid-batch safely.
    """
    raise NotImplementedError("orchestrator.scan_and_prepare is a Phase 4 stub")


def publish_approved(payload: ListingPayload, store: StateStore) -> PublishResult:
    """
    Publish a single operator-approved payload via ebay_client and record IDs.

    Args:
        payload: The ListingPayload the operator approved in the UI.
        store: StateStore to record offer_id/listing_id immediately after the call.

    Returns:
        PublishResult with offer_id, listing_id, and EPS URLs.

    Side Effects:
        Uploads images, creates inventory item/offer, publishes the offer, and
        writes the resulting IDs to the state store before returning.

    Raises:
        NotImplementedError: This is a Phase 4 stub.

    FMEA Constraints:
        PI-007 — only ever called after an explicit human Approve in the UI.
        R-STATE — IDs written immediately so resume never double-publishes.
    """
    raise NotImplementedError("orchestrator.publish_approved is a Phase 4 stub")


def main() -> None:
    """
    Headless entry point: `python -m src.core.orchestrator`.

    Wires up the provider, state store, and runs scan_and_prepare in a headless
    (no-Streamlit) mode for scripting/CI smoke use. Publishing still requires an
    explicit approval input (PI-007).

    Returns:
        None

    Raises:
        NotImplementedError: This is a Phase 4 stub.
    """
    raise NotImplementedError("orchestrator.main is a Phase 4 stub")


if __name__ == "__main__":
    main()
