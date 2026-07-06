"""
Module: app.py
Purpose: Streamlit review/approve front end — the human gate (PI-007). Scan ->
         review photos beside extracted data + suggested price -> Approve -> live
         listing link.
Primary Responsibilities:
  - Trigger a Scan (orchestrator.scan_and_prepare) and hold the prepared payloads,
    plus any per-batch scan errors and the stale-cache warning flag from the
    returned ScanSummary, displaying both via st.error/st.warning so a failed
    batch or a stale-cache fallback is visible to the operator instead of
    being silently dropped.
  - Render each item: photos beside specifics/condition/defects + suggested price.
  - Let the operator edit fields (including the description, so PI-004 defect-
    disclosure corrections are actually captured) via a validated condition
    selectbox (src.ui.review.EBAY_CONDITION_VALUES) instead of free text, enter
    a human-confirmed comp + cost/fees (with a Terapeak / sold-search link), and
    recompute the price live.
  - Require an explicit Approve to publish (PI-007); then show the listing link.
  - Hold one EbayClient and one StateStore per Streamlit session (session_state,
    created lazily) so the in-memory + persisted OAuth token cache (Fix 2) is
    actually shared across Scan and Approve actions instead of being rebuilt
    (and its cache lost) on every button click.
Key Interfaces:
  - Input: Drive batches via the orchestrator; operator edits via Streamlit widgets.
  - Output: published eBay listings; state recorded in the state store.
FMEA Constraints Enforced:
  - PI-007 — nothing publishes without an explicit Approve click.
  - PI-008 — a tidy summary (photos + table), never raw JSON.
  - PI-004 — description edits are captured, not silently discarded; a dead,
    non-functional upload widget was removed rather than left as a silent no-op.
  - R-PRICE — comp/cost/fees are operator inputs; price recomputes via Margin-Guard.

Run:  streamlit run src/ui/app.py
This module is a thin shell; the testable logic lives in src/ui/review.py.
"""

from __future__ import annotations

import os

import streamlit as st

from src.ai.provider import GeminiProvider
from src.api.ebay_client import EbayClient
from src.contracts import DraftOutput, VisionAgentOutput
from src.core import orchestrator
from src.core.state_store import StateStore
from src import marketplace
from src.ui import review


def _get_store() -> StateStore:
    """Return a cached StateStore for this Streamlit session."""
    if "store" not in st.session_state:
        st.session_state["store"] = StateStore()
    return st.session_state["store"]


def _get_ebay_client(store: StateStore) -> EbayClient:
    """
    Return a single, session-cached EbayClient, created lazily on first use.

    Args:
        store: The session's StateStore, forwarded into the client's EbayAuth so
            the OAuth token cache is durable across a process restart (Fix 2:
            R-AUTH / R-COST).

    Returns:
        The EbayClient stored in st.session_state, constructing it on first call.

    Side Effects:
        On first call, constructs one EbayClient (env-only; no network at
        construction) and stores it in st.session_state for reuse by every
        subsequent Scan/Approve action in this session.

    FMEA Constraints:
        R-AUTH / R-COST — reusing one EbayClient (and therefore one EbayAuth)
        means the in-memory token cache and the state-store-backed cache both
        actually help, instead of being rebuilt (and their in-memory half lost)
        on every button click.
    """
    if "ebay_client" not in st.session_state:
        st.session_state["ebay_client"] = EbayClient(state_store=store)
    return st.session_state["ebay_client"]


def _vision_from_payload(payload) -> VisionAgentOutput:
    """
    Reconstruct a minimal VisionAgentOutput from a payload for re-pricing.

    Defects do not affect price, so specifics + condition are sufficient to let
    review.recompute_price run when the operator edits comp/cost/fees.
    """
    return VisionAgentOutput(
        item_specifics=dict(payload.item_specifics),
        condition=payload.condition,
        defects_found=[],
        dropped_fields=[],
    )


def _render_item(payload, store) -> None:
    """
    Render one item's review card: photos, summary, edits, and the Approve gate.

    Args:
        payload: The prepared ListingPayload for this item.
        store: The session StateStore.

    Side Effects:
        Draws Streamlit widgets; on Approve, publishes via the orchestrator and
        records state.
    """
    st.subheader(f"{payload.title}  ·  `{payload.item_sku}`")
    photos_col, data_col = st.columns([1, 1])

    # ── Photos (PI-008: show the images, not JSON) ────────────────────────────
    with photos_col:
        for path in payload.local_image_paths:
            if os.path.exists(path):
                st.image(path, use_container_width=True)
            else:
                st.caption(f"(image not found locally: {path})")

    # ── Extracted data + editable fields ──────────────────────────────────────
    with data_col:
        title = st.text_input("Title", payload.title, key=f"title_{payload.item_sku}")
        st.markdown("**Item specifics**")
        st.table(
            {"Aspect": list(payload.item_specifics.keys()),
             "Value": list(payload.item_specifics.values())}
        )
        # Condition is a validated selectbox over the canonical eBay condition
        # enum (mirrors orchestrator._CONDITION_MAP's target values; see
        # src.ui.review.EBAY_CONDITION_VALUES) rather than free text, so an
        # operator typo can never reach createInventoryItem as an invalid
        # condition value.
        condition_options = list(review.EBAY_CONDITION_VALUES)
        if payload.condition not in condition_options:
            # Defensive: keep the payload's current value selectable even if
            # it somehow falls outside the canonical list (e.g. unset "").
            condition_options = [payload.condition] + condition_options
        condition = st.selectbox(
            "eBay condition", condition_options,
            index=condition_options.index(payload.condition),
            key=f"cond_{payload.item_sku}",
        )
        st.markdown("**Description (defects disclosed — confirm before approving)**")
        description = st.text_area(
            "Description", payload.listing_description, key=f"desc_{payload.item_sku}",
            height=120,
        )

        # ── Human-in-the-loop pricing (R-PRICE) ───────────────────────────────
        query = " ".join(payload.item_specifics.values()).strip() or payload.title
        st.markdown(
            f"[Terapeak research]({review.build_terapeak_url(query)}) · "
            f"[Sold/completed search]({review.build_sold_comp_url(query)})"
        )
        cost = st.number_input("Your cost (USD)", min_value=0.0, value=0.0,
                               key=f"cost_{payload.item_sku}")
        fees = st.number_input("Est. fees (USD)", min_value=0.0, value=0.0,
                               key=f"fees_{payload.item_sku}")
        user_comp = st.number_input("Confirmed sold comp (USD)", min_value=0.0, value=0.0,
                                    key=f"comp_{payload.item_sku}")

        # Recompute the price from the operator's inputs (floor + missing-inputs).
        pricing = review.recompute_price(
            _vision_from_payload(payload),
            cost=cost or None,
            fees=fees or None,
            active_comps=None,
            user_confirmed_comp=user_comp or None,
        )
        price = st.number_input(
            "Final price (USD)", min_value=0.0,
            value=float(pricing.margin_guard_price or payload.price),
            key=f"price_{payload.item_sku}",
        )
        if pricing.floor_applied:
            st.warning(f"Floor applied (PI-006): {pricing.reasoning}")
        if pricing.missing_inputs:
            st.info(f"Unresolved inputs: {', '.join(pricing.missing_inputs)}")

        category_id = st.text_input(
            "eBay category ID", payload.category_id, key=f"cat_{payload.item_sku}"
        )

        # ── Build the edited payload + validate before Approve (PI-009) ───────
        # description is included so operator corrections to the PI-004
        # defect-disclosure text are actually carried into the payload instead
        # of being read by st.text_area and then discarded (Fix 3).
        edited = review.apply_operator_edits(
            payload, title=title, price=price, condition=condition,
            category_id=category_id, description=description,
        )
        problems = review.validate_for_publish(edited)
        if problems:
            st.error("Cannot publish yet: " + "; ".join(problems))

        # ── Target selection (v1.2): eBay auto-publish vs an "Other" draft ────
        targets = marketplace.list_targets()
        target = st.selectbox(
            "Target marketplace",
            targets,
            format_func=marketplace.target_label,
            key=f"target_{payload.item_sku}",
        )
        is_draft = target != "ebay"

        # Draft targets don't need eBay policy/category fields, so only block
        # auto-publish on validation problems.
        button_label = (
            f"Generate {marketplace.target_label(target)}"
            if is_draft else "Approve & Publish to eBay"
        )

        # ── The human gate (PI-007) ───────────────────────────────────────────
        if st.button(button_label, disabled=(bool(problems) and not is_draft),
                     key=f"approve_{payload.item_sku}"):
            try:
                result = orchestrator.fulfill_approved(
                    edited, store, target=target, ebay_client=_get_ebay_client(store),
                )
                if isinstance(result, DraftOutput):
                    st.success(
                        f"Draft for {result.platform_label} written to "
                        f"`{result.draft_path}`"
                    )
                    st.caption(f"Photo manifest: `{result.manifest_path}`")
                else:
                    url = result.listing_url or (
                        f"https://www.ebay.com/itm/{result.listing_id}"
                        if result.listing_id else ""
                    )
                    st.success(
                        f"Published! Offer {result.offer_id} · Listing {result.listing_id}"
                    )
                    if url:
                        st.markdown(f"[View live listing]({url})")
            except Exception as exc:  # surface adapter errors, don't crash the UI
                st.error(f"Action failed: {type(exc).__name__}: {exc}")


def main() -> None:
    """
    Render the app: header, Scan trigger, and the review cards.

    Side Effects:
        Drives the whole Streamlit page.
    """
    st.set_page_config(page_title="Lister-Bridge", layout="wide")
    st.title("Lister-Bridge — review & approve")
    st.caption("Scan Drive → review photos against extracted data → Approve to publish.")

    store = _get_store()

    with st.sidebar:
        st.header("Scan")
        if st.button("Scan Drive for new items"):
            try:
                provider = GeminiProvider()
                # scan_and_prepare returns a ScanSummary (payloads + any
                # per-batch errors + a stale-cache flag) rather than a bare
                # list, so a single bad batch (e.g. a Gemini JSON parse
                # failure or a DriveFetchError) no longer aborts the whole
                # scan silently — its failure is surfaced below instead.
                summary = orchestrator.scan_and_prepare(
                    provider, store, ebay_client=_get_ebay_client(store)
                )
                st.session_state["payloads"] = summary.payloads
                st.session_state["scan_errors"] = summary.errors
                st.session_state["scan_stale_cache"] = summary.stale_cache
            except Exception as exc:
                st.error(f"Scan failed: {type(exc).__name__}: {exc}")

        # Surface any per-batch failures and the stale-cache warning from the
        # last scan (previously the stale_warning flag from
        # download_batch_images was discarded entirely).
        for err in st.session_state.get("scan_errors", []):
            st.error(
                f"Batch '{err.folder_name}' (id={err.batch_folder_id}) failed: "
                f"{err.reason}"
            )
        if st.session_state.get("scan_stale_cache"):
            st.warning(
                "One or more items used a stale local image cache because a "
                "Drive download failed; photos shown may be out of date."
            )
        # NOTE: the in-GUI "upload photos directly" widget was removed here.
        # It captured a file_uploader() return value that was never read, so
        # the advertised upload silently did nothing (a PI-004-class hazard:
        # a control that appears functional but is not). Re-adding in-GUI
        # upload requires actually wiring the returned UploadedFile objects
        # into the pipeline (e.g. writing them to a batch dir and feeding
        # drive_fetcher/orchestrator); out of scope for this fix.

    payloads = st.session_state.get("payloads", [])
    if not payloads:
        st.info("No items prepared yet. Click **Scan Drive for new items** in the sidebar.")
        return

    for payload in payloads:
        _render_item(payload, store)
        st.divider()


if __name__ == "__main__":
    main()
