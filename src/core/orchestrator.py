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
  - PI-003 — context flushed per item (the provider is stateless per call).
  - R-STATE — dedup + resume via the state store; IDs written right after publish.
  - PI-007 — the orchestrator never auto-publishes; publish_approved is only
    called after an explicit human Approve in the UI.
"""

from __future__ import annotations

import os

from src.ai.provider import AIProvider, GeminiProvider
from src.ai import margin_guard, vision_agent
from src.contracts import (
    AdapterCapability,
    DraftOutput,
    ItemRecord,
    ItemStatus,
    ListingPayload,
    MarginGuardOutput,
    PublishResult,
    VisionAgentOutput,
)
from src.core import drive_fetcher
from src.core.state_store import StateStore
from src.marketplace import EbayAdapter, get_adapter

# Aspects used (in order) to build a default listing title from the specifics.
_TITLE_ASPECTS = ("Brand", "Product Line", "Model", "Type")

# Free-text condition -> eBay condition enum. Checked in order; first hit wins.
_CONDITION_MAP = [
    ("for parts", "FOR_PARTS_OR_NOT_WORKING"),
    ("not working", "FOR_PARTS_OR_NOT_WORKING"),
    ("like new", "LIKE_NEW"),
    ("new other", "NEW_OTHER"),
    ("open box", "NEW_OTHER"),
    ("brand new", "NEW"),
    ("excellent", "USED_EXCELLENT"),
    ("very good", "USED_VERY_GOOD"),
    ("acceptable", "USED_ACCEPTABLE"),
    ("good", "USED_GOOD"),
    ("used", "USED_GOOD"),
    ("new", "NEW"),
]


def derive_sku(batch_folder_id: str) -> str:
    """
    Derive the deterministic SKU for a batch from its Drive subfolder ID.

    Args:
        batch_folder_id: The Drive subfolder ID for the item.

    Returns:
        The SKU string, e.g. "LB-{folderId}" (the idempotency key).

    Side Effects:
        None.

    FMEA Constraints:
        R-STATE — stable SKU is the dedup/idempotency anchor.
    """
    return f"LB-{batch_folder_id}"


def _to_ebay_condition(condition_text: str) -> str:
    """
    Map a free-text condition descriptor to an eBay condition enum string.

    Args:
        condition_text: The Vision Agent's condition string (e.g. "Used - Good").

    Returns:
        An eBay condition enum (e.g. "USED_GOOD"); defaults to "USED_GOOD" when
        nothing matches and a value is present, or "" when the input is empty
        (so the operator must set it in the UI).
    """
    text = (condition_text or "").strip().lower()
    if not text:
        return ""
    for needle, enum_value in _CONDITION_MAP:
        if needle in text:
            return enum_value
    return "USED_GOOD"


def _build_description(vision: VisionAgentOutput) -> str:
    """
    Build a human-readable eBay item description that DISCLOSES defects (PI-004).

    Args:
        vision: The item's VisionAgentOutput.

    Returns:
        A plain-text description: condition line + an explicit defects section
        (or a "no visible defects noted" line). This carries the defects through
        the payload so the operator confirms them on the review screen and so the
        live listing discloses them to the buyer.
    """
    lines: list[str] = []
    if vision.condition:
        lines.append(f"Condition: {vision.condition}.")
    if vision.defects_found:
        lines.append("Noted defects:")
        lines.extend(f"- {d}" for d in vision.defects_found)
    else:
        lines.append("No visible defects noted.")
    return "\n".join(lines)


def _build_title(vision: VisionAgentOutput, fallback: str) -> str:
    """
    Build a listing title from priority aspects, falling back to the folder name.

    Args:
        vision: The item's VisionAgentOutput.
        fallback: A fallback title (e.g. the Drive folder name).

    Returns:
        A title string capped at 80 characters (eBay's title limit).
    """
    parts = [
        vision.item_specifics[a] for a in _TITLE_ASPECTS if a in vision.item_specifics
    ]
    title = " ".join(p for p in parts if p).strip() or fallback
    return title[:80]


def _assemble_payload(
    sku: str,
    batch: dict,
    image_paths: list[str],
    vision: VisionAgentOutput,
    pricing: MarginGuardOutput,
) -> ListingPayload:
    """
    Assemble a ListingPayload from the per-item results + env config.

    Args:
        sku: The deterministic SKU.
        batch: The drive_fetcher BatchMetadata dict (for folder name).
        image_paths: Local image paths to upload at publish time.
        vision: The item's extraction result.
        pricing: The item's Margin-Guard result.

    Returns:
        A ListingPayload with everything known pre-approval. EPS URLs are empty
        here (images upload at publish time); policies/location/category come
        from .env. The operator finalizes price/condition/category in the UI.

    Side Effects:
        Reads eBay policy/location/marketplace/category env vars.
    """
    return ListingPayload(
        item_sku=sku,
        title=_build_title(vision, batch.get("folder_name", sku)),
        item_specifics=vision.item_specifics,
        condition=_to_ebay_condition(vision.condition),
        quantity=1,
        price=pricing.margin_guard_price,
        category_id=os.environ.get("EBAY_DEFAULT_CATEGORY_ID", ""),
        local_image_paths=image_paths,
        eps_image_urls=[],
        fulfillment_policy_id=os.environ.get("EBAY_FULFILLMENT_POLICY_ID", ""),
        payment_policy_id=os.environ.get("EBAY_PAYMENT_POLICY_ID", ""),
        return_policy_id=os.environ.get("EBAY_RETURN_POLICY_ID", ""),
        merchant_location_key=os.environ.get("EBAY_INVENTORY_LOCATION_KEY", ""),
        marketplace_id=os.environ.get("EBAY_MARKETPLACE_ID", "EBAY_US"),
        # Description discloses defects (PI-004); pricing.reasoning stays internal.
        listing_description=_build_description(vision),
    )


def scan_and_prepare(
    provider: AIProvider,
    store: StateStore,
    *,
    ebay_client=None,
    cost_lookup=None,
) -> list[ListingPayload]:
    """
    Run drive -> vision -> pricing for every pending, not-yet-published item and
    return assembled (un-published) ListingPayloads for operator review.

    Args:
        provider: AIProvider for the vision step.
        store: StateStore for dedup, resume, and per-step recording.
        ebay_client: Optional eBay client exposing search_active_comps; when
            provided, active comps anchor the price. When None, pricing proceeds
            with no comps (their absence routes to missing_inputs).
        cost_lookup: Optional callable sku -> (cost, fees); returns (None, None)
            when unknown so the UI resolves them (R-PRICE). Defaults to unknown.

    Returns:
        A list of ListingPayload, one per prepared item, ready for the UI review
        screen. Nothing is published here — publishing requires explicit Approve.

    Side Effects:
        Drive downloads; AI calls (context flushed per item, PI-003); state writes.

    FMEA Constraints:
        PI-003 — each vision call is a stateless one-shot, so context is flushed
        between items by construction.
        R-STATE — skip SKUs already PUBLISHED; every step is recorded so an
        interrupted run resumes without redoing published items.
    """
    payloads: list[ListingPayload] = []

    for batch in drive_fetcher.list_pending_batches():
        folder_id = batch["folder_id"]
        sku = derive_sku(folder_id)

        # R-STATE: never reprocess an already-live item.
        if store.is_published(sku):
            continue

        # Record the item as seen before doing any expensive work.
        store.upsert_item(
            ItemRecord(item_sku=sku, batch_folder_id=folder_id, status=ItemStatus.NEW)
        )

        # 1) Drive: download this batch's images (recursive + paginated).
        image_paths, _stale_warning = drive_fetcher.download_batch_images(batch)

        # 2) Vision: extract specifics/condition/defects (stateless call, PI-003).
        vision = vision_agent.extract_item(image_paths, provider)
        store.set_status(sku, ItemStatus.EXTRACTED)

        # 3) Pricing: cost/fees are operator inputs (unknown here -> missing_inputs).
        cost, fees = (cost_lookup(sku) if cost_lookup else (None, None))
        if ebay_client is not None:
            pricing = margin_guard.fetch_and_price(
                vision, ebay_client, cost=cost, fees=fees
            )
        else:
            pricing = margin_guard.price_item(
                vision, cost=cost, fees=fees, active_comps=None
            )
        store.set_status(sku, ItemStatus.PRICED)

        # 4) Assemble the review payload (not published; PI-007).
        payloads.append(_assemble_payload(sku, batch, image_paths, vision, pricing))

    return payloads


def publish_approved(
    payload: ListingPayload,
    store: StateStore,
    *,
    ebay_client=None,
) -> PublishResult:
    """
    Publish a single operator-approved payload via ebay_client and record IDs.

    Args:
        payload: The ListingPayload the operator approved in the UI.
        store: StateStore to record offer_id/listing_id immediately after the call.
        ebay_client: Optional EbayClient (tests inject a fake). When None, a real
            EbayClient is constructed from the environment.

    Returns:
        PublishResult with offer_id, listing_id, and EPS URLs.

    Side Effects:
        Uploads images, creates inventory item/offer, publishes the offer, and
        writes the resulting IDs to the state store before returning.

    FMEA Constraints:
        PI-007 — only ever called after an explicit human Approve in the UI.
        R-STATE — IDs written immediately so resume never double-publishes.
    """
    # The eBay path is now one AUTO_PUBLISH adapter among many; this function is
    # kept as the stable eBay entry point and delegates to the shared helper.
    return _auto_publish(EbayAdapter(client=ebay_client), payload, store)


def _auto_publish(adapter, payload: ListingPayload, store: StateStore) -> PublishResult:
    """
    Run an AUTO_PUBLISH adapter with dedup + immediate state recording.

    Args:
        adapter: An AutoPublishAdapter (e.g. EbayAdapter) exposing publish().
        payload: The operator-approved ListingPayload.
        store: StateStore for dedup + ID recording.

    Returns:
        The PublishResult (fresh, or reconstructed from state on a dedup hit).

    Side Effects:
        Calls adapter.publish() and writes PUBLISHED state immediately after.

    FMEA Constraints:
        R-STATE — defensive dedup + IDs persisted right after the publish call.
        PI-007 — only reached after an explicit human Approve.
    """
    # R-STATE: defensive dedup — never double-publish a live SKU.
    if store.is_published(payload.item_sku):
        existing = store.get_item(payload.item_sku)
        return PublishResult(
            item_sku=payload.item_sku,
            offer_id=existing.offer_id or "",
            listing_id=existing.listing_id or "",
            eps_image_urls=existing.eps_urls,
        )

    result = adapter.publish(payload)

    # R-STATE: persist offer/listing IDs immediately after the publish call.
    store.upsert_item(
        ItemRecord(
            item_sku=result.item_sku,
            batch_folder_id=payload.item_sku.removeprefix("LB-"),
            status=ItemStatus.PUBLISHED,
            offer_id=result.offer_id,
            listing_id=result.listing_id,
            eps_urls=result.eps_image_urls,
        )
    )
    return result


def fulfill_approved(
    payload: ListingPayload,
    store: StateStore,
    *,
    target: str = "ebay",
    ebay_client=None,
    output_dir: str | None = None,
) -> PublishResult | DraftOutput:
    """
    Route an approved payload to the chosen marketplace target (v1.2).

    Auto-publish targets (e.g. "ebay") publish live and return a PublishResult,
    recording PUBLISHED state. Draft-only targets (e.g. "other:mercari") render a
    posting to disk and return a DraftOutput, leaving item state unchanged (a
    draft is a manual export, not a publish — PI-007).

    Args:
        payload: The operator-approved ListingPayload.
        store: StateStore for dedup + state recording (auto-publish path).
        target: A marketplace target key (see marketplace.list_targets()).
        ebay_client: Optional injected EbayClient for the eBay adapter (tests).
        output_dir: Base directory for draft output; defaults to
            DRAFT_OUTPUT_DIR env or "data/drafts".

    Returns:
        PublishResult for auto-publish targets, DraftOutput for draft targets.

    Side Effects:
        Auto-publish: a live publish + state write. Draft: files written to disk.

    Raises:
        ValueError: If the target key is unknown.

    FMEA Constraints:
        PI-007 — drafts are never auto-posted; auto-publish only after Approve.
        R-STATE — auto-publish records IDs immediately (via _auto_publish).
    """
    adapter = get_adapter(target, ebay_client=ebay_client)

    if adapter.capability == AdapterCapability.AUTO_PUBLISH:
        return _auto_publish(adapter, payload, store)

    # DRAFT_ONLY: render a posting to disk for manual upload.
    out_dir = output_dir or os.environ.get("DRAFT_OUTPUT_DIR", "data/drafts")
    return adapter.render_draft(payload, out_dir)


def main() -> None:
    """
    Headless entry point: `python -m src.core.orchestrator`.

    Wires up the provider and state store and runs scan_and_prepare in a headless
    (no-Streamlit) mode for scripting/CI smoke use. Publishing still requires an
    explicit approval step in the UI (PI-007), so this only prepares + reports.

    Returns:
        None

    Side Effects:
        Reads env config; runs the scan pipeline; prints a summary to stdout.
    """
    provider = GeminiProvider()
    store = StateStore()
    payloads = scan_and_prepare(provider, store)

    print(f"Prepared {len(payloads)} item(s) for review:")
    for p in payloads:
        print(f"  - {p.item_sku}: {p.title} @ ${p.price:.2f} ({len(p.local_image_paths)} photos)")
    print("Open the Streamlit UI to review and Approve before publishing (PI-007).")


if __name__ == "__main__":
    main()
