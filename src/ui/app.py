"""
Module: app.py
Purpose: Streamlit review/approve front end — the human gate (PI-007). Scan ->
         review photos beside extracted data + suggested price -> Approve -> live
         listing link.
Primary Responsibilities:
  - Trigger a Scan (orchestrator.scan_and_prepare) and hold the prepared payloads.
  - Render each item: photos beside specifics/condition/defects + suggested price.
  - Let the operator edit fields, enter a human-confirmed comp + cost/fees (with a
    Terapeak / sold-search link), and recompute the price live.
  - Require an explicit Approve to publish (PI-007); then show the listing link.
  - Offer optional in-GUI photo upload alongside Drive capture.
Key Interfaces:
  - Input: Drive batches via the orchestrator; operator edits via Streamlit widgets.
  - Output: published eBay listings; state recorded in the state store.
FMEA Constraints Enforced:
  - PI-007 — nothing publishes without an explicit Approve click.
  - PI-008 — a tidy summary (photos + table), never raw JSON.
  - R-PRICE — comp/cost/fees are operator inputs; price recomputes via Margin-Guard.

Run:  streamlit run src/ui/app.py
This module is a thin shell; the testable logic lives in src/ui/review.py.
"""

from __future__ import annotations

import os

import streamlit as st

from src.ai.provider import GeminiProvider
from src.api.ebay_client import EbayClient
from src.contracts import VisionAgentOutput
from src.core import orchestrator
from src.core.state_store import StateStore
from src.ui import review


def _get_store() -> StateStore:
    """Return a cached StateStore for this Streamlit session."""
    if "store" not in st.session_state:
        st.session_state["store"] = StateStore()
    return st.session_state["store"]


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
        condition = st.text_input(
            "eBay condition", payload.condition, key=f"cond_{payload.item_sku}"
        )
        st.markdown("**Description (defects disclosed — confirm before approving)**")
        st.text_area(
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
        edited = review.apply_operator_edits(
            payload, title=title, price=price, condition=condition,
            category_id=category_id,
        )
        problems = review.validate_for_publish(edited)
        if problems:
            st.error("Cannot publish yet: " + "; ".join(problems))

        # ── The human gate (PI-007) ───────────────────────────────────────────
        if st.button("Approve & Publish", disabled=bool(problems),
                     key=f"approve_{payload.item_sku}"):
            try:
                result = orchestrator.publish_approved(
                    edited, store, ebay_client=EbayClient()
                )
                url = result.listing_url or (
                    f"https://www.ebay.com/itm/{result.listing_id}"
                    if result.listing_id else ""
                )
                st.success(f"Published! Offer {result.offer_id} · Listing {result.listing_id}")
                if url:
                    st.markdown(f"[View live listing]({url})")
            except Exception as exc:  # surface eBay errors, don't crash the UI
                st.error(f"Publish failed: {type(exc).__name__}: {exc}")


def main() -> None:
    """
    Render the app: header, Scan trigger, optional upload, and the review cards.

    Side Effects:
        Drives the whole Streamlit page.
    """
    st.set_page_config(page_title="Lister-Bridge", layout="wide")
    st.title("Lister-Bridge — review & approve")
    st.caption("Scan Drive → review photos against extracted data → Approve to publish.")

    store = _get_store()

    # Optional in-GUI upload alongside Drive capture (blueprint open option).
    with st.sidebar:
        st.header("Scan")
        if st.button("Scan Drive for new items"):
            try:
                provider = GeminiProvider()
                st.session_state["payloads"] = orchestrator.scan_and_prepare(
                    provider, store, ebay_client=EbayClient()
                )
            except Exception as exc:
                st.error(f"Scan failed: {type(exc).__name__}: {exc}")
        st.file_uploader(
            "Or upload photos directly", accept_multiple_files=True,
            type=["jpg", "jpeg", "png", "webp", "heic"],
        )

    payloads = st.session_state.get("payloads", [])
    if not payloads:
        st.info("No items prepared yet. Click **Scan Drive for new items** in the sidebar.")
        return

    for payload in payloads:
        _render_item(payload, store)
        st.divider()


if __name__ == "__main__":
    main()
