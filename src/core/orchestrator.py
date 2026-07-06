"""
Module: orchestrator.py
Purpose: Sequence the per-item pipeline (drive -> vision -> pricing -> assemble ->
         publish), own per-item state, and flush AI context between items.
Primary Responsibilities:
  - For each pending batch/item: fetch images, extract, price, assemble the
    ListingPayload, and record every step in the state store.
  - Dedup already-published SKUs and resume after interruption (R-STATE).
  - Flush Gemini context after each item to avoid token bloat (PI-003).
  - Isolate a single batch's failure (a Gemini JSON parse ValueError, a
    DriveFetchError, or any other Exception raised while preparing one batch)
    so it can never abort the rest of the scan; the failing batch is recorded
    ItemStatus.ERROR with a truncated human-readable reason and the scan
    continues with the next batch (see ScanSummary / _prepare_one_batch).
  - After a successful auto-publish, archive the source Drive batch
    (drive_fetcher.archive_batch) so it is not re-listed by future scans;
    archive failures are logged but never fail or roll back the publish.
  - Provide the headless entry point (`python -m src.core.orchestrator`) that the
    Streamlit UI and a CLI run both share; main() never lets an exception
    escape as a raw traceback (PI-001's "never a raw traceback" contract
    applies at this boundary too).
Key Interfaces:
  - Input: drive_fetcher batches, AIProvider, StateStore, ebay_client.
  - Output: per-item ItemRecord updates; a ScanSummary (payloads + per-batch
    errors + stale-cache flag) for the UI; PublishResult after an approved
    publish.
FMEA Constraints Enforced:
  - PI-003 — context flushed per item (the provider is stateless per call).
  - R-STATE — dedup + resume via the state store; IDs written right after publish.
  - PI-007 — the orchestrator never auto-publishes; publish_approved is only
    called after an explicit human Approve in the UI.
  - PI-001 — archive_batch is wrapped so a Drive-side archive failure is a
    best-effort/logged event, never a publish failure (the state store's
    dedup guard is the durable safeguard against re-processing either way).
    The same "never a raw traceback" contract is honored for per-batch
    failures in scan_and_prepare and for main()'s top-level flow.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

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

# Cap on the persisted/collected human-readable error reason (Ground Rule /
# per-task spec): long exception messages (e.g. a full Gemini response echoed
# into a ValueError) are truncated so the state store and UI never have to
# render an unbounded blob.
_ERROR_REASON_MAX_LEN = 300


@dataclass
class BatchError:
    """
    One batch's failure record, collected by scan_and_prepare for the UI.

    Attributes:
        batch_folder_id: The Drive subfolder ID of the failed batch.
        folder_name: Human-readable folder name for display.
        reason: Truncated human-readable exception message (see
            _truncate_reason); never a raw traceback.

    FMEA Constraints:
        PI-001 — surfaces the same "never a raw traceback" failure info the
        state store records, so the UI and the state store agree.
    """

    batch_folder_id: str
    folder_name: str
    reason: str


@dataclass
class ScanSummary:
    """
    Aggregate result of scan_and_prepare: prepared payloads + failures.

    This is a plain (non-pydantic) result object, not a contract model —
    src/contracts/ is frozen (extra="forbid") and adding a field there for
    the stale-cache flag would be a contract change. Keeping this shape in
    orchestrator.py instead lets the UI see richer scan results without
    touching the frozen contracts.

    Attributes:
        payloads: Assembled ListingPayloads ready for operator review, one
            per successfully prepared batch.
        errors: One BatchError per batch that raised during preparation; the
            scan continues past these (see scan_and_prepare).
        stale_cache: True if ANY prepared batch had its images served from a
            stale local cache because a Drive download failed but a cached
            copy existed (drive_fetcher.download_batch_images' warning flag,
            previously discarded — see module docstring history).

    FMEA Constraints:
        PI-001 — stale_cache surfaces the previously-discarded warning flag
        from download_batch_images so the operator can see degraded data.
    """

    payloads: list[ListingPayload] = field(default_factory=list)
    errors: list[BatchError] = field(default_factory=list)
    stale_cache: bool = False

    def __iter__(self):
        """
        Iterate over `payloads` for backward compatibility with callers that
        used to do `for payload in scan_and_prepare(...)`.

        Returns:
            An iterator over self.payloads.
        """
        return iter(self.payloads)

    def __len__(self) -> int:
        """Return len(self.payloads), for backward-compatible truthiness checks."""
        return len(self.payloads)

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


def _truncate_reason(exc: Exception) -> str:
    """
    Render an exception as a truncated, human-readable one-line reason.

    Args:
        exc: The exception to describe.

    Returns:
        "{ExceptionClassName}: {message}", capped at _ERROR_REASON_MAX_LEN
        characters (with a trailing ellipsis marker when truncated) so long
        messages (e.g. an echoed Gemini response body) never blow up the
        state store column or the UI's error display.

    FMEA Constraints:
        PI-001 — this is the "human-readable reason" recorded on ItemStatus.ERROR
        and surfaced to the UI; it is deliberately never a raw traceback.
    """
    message = f"{type(exc).__name__}: {exc}"
    if len(message) > _ERROR_REASON_MAX_LEN:
        return message[: _ERROR_REASON_MAX_LEN - 1].rstrip() + "…"
    return message


def _prepare_one_batch(
    batch: dict,
    provider: AIProvider,
    store: StateStore,
    *,
    ebay_client=None,
    cost_lookup=None,
) -> tuple[ListingPayload | None, bool]:
    """
    Run drive -> vision -> pricing -> assemble for exactly one batch.

    Split out of scan_and_prepare so the per-batch body can be wrapped in a
    single try/except at the call site without duplicating the pipeline
    steps — any exception raised here (DriveFetchError, the vision step's
    JSON-parse ValueError, or anything else) propagates to the caller, which
    is responsible for catching it, recording ItemStatus.ERROR, and moving on
    to the next batch.

    Args:
        batch: One BatchMetadata dict from drive_fetcher.list_pending_batches().
        provider: AIProvider for the vision step.
        store: StateStore for per-step status recording.
        ebay_client: Optional eBay client; see scan_and_prepare.
        cost_lookup: Optional cost/fees lookup callable; see scan_and_prepare.

    Returns:
        A (payload, stale_warning) tuple, or (None, False) if the SKU is
        already PUBLISHED (R-STATE dedup skip — not an error).

    Side Effects:
        Drive downloads; an AI call (context flushed per item, PI-003); state
        writes (upsert to NEW, then EXTRACTED, then PRICED).

    Raises:
        Exception: Propagates any failure from drive_fetcher or the vision/
            pricing steps; the caller (scan_and_prepare) is responsible for
            catching it and recording ItemStatus.ERROR (PI-001).

    FMEA Constraints:
        PI-003 — the vision call is a stateless one-shot; context is flushed
        between items by construction.
        R-STATE — skips SKUs already PUBLISHED before any expensive work.
    """
    folder_id = batch["folder_id"]
    sku = derive_sku(folder_id)

    # R-STATE: never reprocess an already-live item.
    if store.is_published(sku):
        return None, False

    # Record the item as seen before doing any expensive work.
    store.upsert_item(
        ItemRecord(item_sku=sku, batch_folder_id=folder_id, status=ItemStatus.NEW)
    )

    # 1) Drive: download this batch's images (recursive + paginated).
    image_paths, stale_warning = drive_fetcher.download_batch_images(batch)

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
    payload = _assemble_payload(sku, batch, image_paths, vision, pricing)
    return payload, stale_warning


def scan_and_prepare(
    provider: AIProvider,
    store: StateStore,
    *,
    ebay_client=None,
    cost_lookup=None,
) -> ScanSummary:
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
        A ScanSummary: `.payloads` holds one ListingPayload per successfully
        prepared batch, ready for the UI review screen (nothing is published
        here — publishing requires explicit Approve). `.errors` holds one
        BatchError per batch that raised during preparation. `.stale_cache`
        is True if any prepared batch's images came from a stale local cache.
        ScanSummary is iterable/sized over `.payloads` for backward
        compatibility with callers written against the old `list[ListingPayload]`
        return type.

    Side Effects:
        Drive downloads; AI calls (context flushed per item, PI-003); state
        writes, including ItemStatus.ERROR for any batch whose preparation
        raises (see FMEA Constraints below).

    FMEA Constraints:
        PI-003 — each vision call is a stateless one-shot, so context is flushed
        between items by construction.
        R-STATE — skip SKUs already PUBLISHED; every step is recorded so an
        interrupted run resumes without redoing published items. A batch that
        errors is recorded ItemStatus.ERROR rather than left at NEW/EXTRACTED;
        is_published() only matches PUBLISHED, so an ERROR batch is NOT
        skipped on the next scan — it is retried automatically. This mirrors
        the existing dedup semantics (only a live PUBLISHED SKU is ever
        skipped) and means a transient failure (e.g. a flaky Drive call or a
        malformed Gemini response) self-heals on the next scan without any
        manual reset of the state store.
        PI-001 — one batch's exception (DriveFetchError, the vision step's
        JSON-parse ValueError, or anything else) is caught here so it can
        never abort the rest of the scan; the failure is recorded with a
        truncated human-readable reason (never a raw traceback) and the loop
        continues to the next batch.
    """
    summary = ScanSummary()

    for batch in drive_fetcher.list_pending_batches():
        folder_id = batch["folder_id"]
        folder_name = batch.get("folder_name", folder_id)

        try:
            payload, stale_warning = _prepare_one_batch(
                batch, provider, store, ebay_client=ebay_client, cost_lookup=cost_lookup
            )
        except Exception as exc:  # noqa: BLE001 - one bad batch must never abort the scan
            # PI-001: record the failure against this batch's SKU so it is
            # visible in the state store (ItemStatus.ERROR) and in the scan
            # summary, then continue to the next batch. The reason is
            # truncated and never a raw traceback.
            reason = _truncate_reason(exc)
            sku = derive_sku(folder_id)
            store.upsert_item(
                ItemRecord(
                    item_sku=sku,
                    batch_folder_id=folder_id,
                    status=ItemStatus.ERROR,
                )
            )
            print(
                f"[orchestrator] ERROR: batch '{folder_name}' (id={folder_id}) "
                f"failed to prepare and was skipped: {reason}",
                flush=True,
            )
            summary.errors.append(
                BatchError(batch_folder_id=folder_id, folder_name=folder_name, reason=reason)
            )
            continue

        if payload is None:
            # R-STATE dedup skip (already PUBLISHED) — not an error.
            continue

        summary.payloads.append(payload)
        if stale_warning:
            summary.stale_cache = True

    return summary


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


def _archive_batch_safely(batch_folder_id: str, batch_folder_name: str) -> None:
    """
    Archive a completed Drive batch, never letting a failure surface upward.

    Args:
        batch_folder_id: The Drive subfolder ID of the just-published batch.
        batch_folder_name: Human-readable name for log messages only (best
            available label — see the call site in _auto_publish for how it
            is derived when the true Drive folder name isn't in hand).

    Returns:
        None

    Side Effects:
        Calls drive_fetcher.archive_batch(), which moves the Drive subfolder
        from staging to archive. On any exception (network failure, missing
        env vars, etc.) the error is logged to stderr-equivalent (print) and
        swallowed — archiving is a best-effort cleanup step, not part of the
        publish transaction.

    FMEA Constraints:
        R-STATE / PI-001 — archiving is intentionally decoupled from publish
        success: a batch that fails to archive simply re-appears in the next
        list_pending_batches() poll, where it is skipped anyway because the
        state store's is_published() dedup guard already covers it. The
        publish itself must never be rolled back or reported as failed just
        because the follow-up Drive move failed.
    """
    try:
        drive_fetcher.archive_batch(batch_folder_id, batch_folder_name)
    except Exception as exc:  # noqa: BLE001 - archive failure must never propagate
        # Archiving is best-effort housekeeping; a failure here must never
        # fail or roll back an already-successful publish (R-STATE). The
        # batch simply stays in staging and is skipped on the next scan via
        # the state store's PUBLISHED dedup guard.
        print(
            f"[orchestrator] WARNING: archive_batch failed for "
            f"'{batch_folder_name}' (id={batch_folder_id}): "
            f"{type(exc).__name__}: {exc}. Batch remains in staging; "
            f"dedup still prevents re-publishing.",
            flush=True,
        )


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
        On a fresh (non-dedup) publish, also archives the source Drive batch
        (drive_fetcher.archive_batch) so it stops being re-listed by future
        scans; an archive failure is logged but never fails this call.

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

    # The Drive subfolder ID is recovered from the deterministic SKU
    # (derive_sku produces "LB-{folderId}"), so no new field needs to be
    # threaded through ListingPayload/PublishResult just to archive the batch.
    batch_folder_id = payload.item_sku.removeprefix("LB-")

    # R-STATE: persist offer/listing IDs immediately after the publish call.
    store.upsert_item(
        ItemRecord(
            item_sku=result.item_sku,
            batch_folder_id=batch_folder_id,
            status=ItemStatus.PUBLISHED,
            offer_id=result.offer_id,
            listing_id=result.listing_id,
            eps_urls=result.eps_image_urls,
        )
    )

    # Archive the now-published batch so it stops being re-scanned (bug fix:
    # archive_batch previously had zero callers, so batches never left
    # staging). The Drive folder's human-readable name isn't carried on
    # ListingPayload/PublishResult, so the listing title is used as the best
    # available label for log messages — archive_batch never uses this value
    # for anything but display. Wrapped so a failure here never fails or
    # rolls back the publish that already succeeded above.
    _archive_batch_safely(batch_folder_id, payload.title or batch_folder_id)

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


def _run_main() -> None:
    """
    The actual headless scan-and-report flow, factored out of main() so
    main() can wrap it in a single top-level try/except (PI-001: never a raw
    traceback at the CLI boundary).

    Returns:
        None

    Side Effects:
        Reads env config; runs the scan pipeline; prints a summary (including
        any per-batch errors and the stale-cache warning) to stdout.
    """
    provider = GeminiProvider()
    store = StateStore()
    summary = scan_and_prepare(provider, store)

    print(f"Prepared {len(summary.payloads)} item(s) for review:")
    for p in summary.payloads:
        print(f"  - {p.item_sku}: {p.title} @ ${p.price:.2f} ({len(p.local_image_paths)} photos)")

    if summary.errors:
        print(f"{len(summary.errors)} batch(es) failed and were skipped:")
        for err in summary.errors:
            print(f"  - {err.folder_name} (id={err.batch_folder_id}): {err.reason}")

    if summary.stale_cache:
        print(
            "[orchestrator] WARNING: one or more items used a stale local image "
            "cache because a Drive download failed (see drive_fetcher warnings above)."
        )

    print("Open the Streamlit UI to review and Approve before publishing (PI-007).")


def main() -> None:
    """
    Headless entry point: `python -m src.core.orchestrator`.

    Wires up the provider and state store and runs scan_and_prepare in a headless
    (no-Streamlit) mode for scripting/CI smoke use. Publishing still requires an
    explicit approval step in the UI (PI-007), so this only prepares + reports.
    The whole flow is wrapped in a single try/except so a top-level failure
    (e.g. missing .env config) prints one human-readable line and exits
    nonzero instead of dumping a raw traceback (PI-001's "never a raw
    traceback" contract extended to this CLI boundary).

    Returns:
        None

    Side Effects:
        Reads env config; runs the scan pipeline; prints a summary to stdout,
        or a single error line to stdout and calls sys.exit(1) on failure.
    """
    try:
        _run_main()
    except Exception as exc:  # noqa: BLE001 - CLI boundary must never show a raw traceback
        print(f"[orchestrator] FATAL: {type(exc).__name__}: {exc}", flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
