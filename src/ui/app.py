"""
Module: app.py
Purpose: Streamlit review/approve front end — the human gate (PI-007). Scan ->
         review photos beside extracted data + suggested price -> Approve -> live
         listing link. Also hosts the Setup tab: a guided credential-entry wizard
         with per-service live-validation Test buttons, so a new user can hand-
         author their .env from within the app instead of editing .env.example
         blind.
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
  - Render a "Setup" tab (per-service expanders driven by src.core.settings):
    credential inputs (masked for secret fields), a portal link + one-line
    guidance per service, a "Test" button invoking the matching validator, and
    a "Save settings" button that writes the .env via settings.write_settings.
    Also shows a startup warning banner naming any still-missing required keys.
  - Render a "Help" tab (src.ui.help_content.HELP_SECTIONS): static operator
    guidance covering the workflow, error/warning meanings, data locations,
    platform coverage, and safety notes. Attach short contextual hints
    (src.ui.help_content.TIPS) to the Scan/condition/description/Approve
    widgets via their help= parameter, and append the error-banner /
    stale-cache tips to the existing st.error/st.warning messages.
Key Interfaces:
  - Input: Drive batches via the orchestrator; operator edits via Streamlit widgets;
    credential values entered on the Setup tab.
  - Output: published eBay listings; state recorded in the state store; a
    written .env file (Setup tab).
FMEA Constraints Enforced:
  - PI-007 — nothing publishes without an explicit Approve click.
  - PI-008 — a tidy summary (photos + table), never raw JSON.
  - PI-004 — description edits are captured, not silently discarded; a dead,
    non-functional upload widget was removed rather than left as a silent no-op.
  - R-PRICE — comp/cost/fees are operator inputs; price recomputes via Margin-Guard.
  - R-STATE — Setup writes to the exact .env path load_app_dotenv() itself
    searches (src.core.settings.settings_env_path), so saved credentials are
    the ones the app actually loads on next run.

Run:  streamlit run src/ui/app.py
This module is a thin shell; the testable logic lives in src/ui/review.py,
src/core/settings.py, and src/ui/help_content.py (none of which import
streamlit).
"""

from __future__ import annotations

import os

import streamlit as st

from src.ai.provider import GeminiProvider
from src.api.ebay_client import EbayClient
from src.contracts import DraftOutput, VisionAgentOutput
from src.core import orchestrator
from src.core import settings as settings_logic
from src.core.state_store import StateStore
from src import marketplace
from src.ui import review
from src.ui.help_content import HELP_SECTIONS, TIPS


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
            help=TIPS["condition_select"],
        )
        st.markdown("**Description (defects disclosed — confirm before approving)**")
        description = st.text_area(
            "Description", payload.listing_description, key=f"desc_{payload.item_sku}",
            height=120,
            help=TIPS["description_editor"],
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
                     key=f"approve_{payload.item_sku}", help=TIPS["approve_button"]):
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


def _render_review_tab(store: StateStore) -> None:
    """
    Render the existing "Review & approve" tab: Scan sidebar + review cards.

    This is the pre-Setup-tab behavior of main(), moved (not rewritten) into
    its own function so main() can host it alongside the new Setup tab via
    st.tabs without altering any of its logic.

    Args:
        store: The session's StateStore.

    Side Effects:
        Draws the Scan sidebar controls and, for each prepared payload, one
        review card (see _render_item). May trigger a Drive scan or an eBay
        publish/draft action.
    """
    with st.sidebar:
        st.header("Scan")
        if st.button("Scan Drive for new items", help=TIPS["scan_button"]):
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
            st.caption(TIPS["error_banner"])
        if st.session_state.get("scan_stale_cache"):
            st.warning(
                "One or more items used a stale local image cache because a "
                "Drive download failed; photos shown may be out of date."
            )
            st.caption(TIPS["stale_cache"])
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


def _render_portal_links(service: str) -> None:
    """
    Render the portal link(s) + one-line guidance for a Setup group.

    Args:
        service: The SettingsGroup.service key (also the src.core.settings
            PORTAL_LINKS lookup key).

    Side Effects:
        Draws one st.markdown line per PortalLink registered for `service`.
        No-op if the service has no registered links.
    """
    for link in settings_logic.PORTAL_LINKS.get(service, ()):
        st.markdown(f"[{link.label}]({link.url})")
        st.caption(link.guidance)


def _render_setup_group(group, values: dict) -> None:
    """
    Render one Setup expander: inputs for every field in `group`, a portal
    link + guidance, and a "Test" button that runs the group's validator.

    Args:
        group: A src.core.settings.SettingsGroup.
        values: The in-progress settings dict (st.session_state-backed); each
            input widget both displays and updates this dict in place.

    Side Effects:
        Draws an st.expander containing one input per field (masked for
        secret-flagged fields), the group's portal links, and — for groups
        with a registered validator — a "Test" button that calls it and
        renders st.success/st.error with the result.
    """
    with st.expander(group.title, expanded=False):
        _render_portal_links(group.service)
        for field_ in group.fields:
            widget_key = f"setup_{field_.key}"
            values[field_.key] = st.text_input(
                field_.label,
                value=values.get(field_.key, field_.default),
                help=field_.help_text,
                type="password" if field_.secret else "default",
                key=widget_key,
            )

        validator = _SETUP_VALIDATORS.get(group.service)
        if validator is not None:
            if st.button(f"Test {group.title}", key=f"test_{group.service}"):
                result = validator(values)
                if result.ok:
                    st.success(result.message)
                else:
                    st.error(result.message)


# Maps a SettingsGroup.service id to its src.core.settings validator. Draft
# platforms (facebook_marketplace / mercari) are intentionally absent — they
# carry no credentials, only links (rendered separately, see _render_setup_tab).
_SETUP_VALIDATORS = {
    "google_drive": settings_logic.validate_drive,
    "gemini": settings_logic.validate_gemini,
    "ebay": settings_logic.validate_ebay,
}


def _render_setup_tab() -> None:
    """
    Render the "Setup" tab: per-service credential entry, portal links, Test
    buttons, and a Save settings action.

    Side Effects:
        On first render this session, seeds st.session_state["setup_values"]
        from settings.read_settings(). Draws one expander per SETTINGS_SCHEMA
        group plus a draft-platform links section, and a "Save settings"
        button that calls settings.write_settings and reports the written path.

    FMEA Constraints:
        R-STATE — "Save settings" writes to settings.settings_env_path(), the
        exact path load_app_dotenv() searches, so a restart of the app picks
        up what was just saved here.
    """
    if "setup_values" not in st.session_state:
        st.session_state["setup_values"] = settings_logic.read_settings()
    values = st.session_state["setup_values"]

    st.caption(
        "Enter credentials per service below, use **Test** to verify each one "
        "live, then **Save settings** to write your `.env` file."
    )

    for group in settings_logic.SETTINGS_SCHEMA:
        _render_setup_group(group, values)

    with st.expander("Draft platforms (no credentials needed)", expanded=False):
        st.caption(
            "These platforms don't support API publishing here — Lister-Bridge "
            "generates a listing draft locally, which you paste in manually."
        )
        _render_portal_links("facebook_marketplace")
        _render_portal_links("mercari")

    if st.button("Save settings", key="setup_save"):
        written_path = settings_logic.write_settings(values)
        st.success(
            f"Settings saved to `{written_path}`. "
            "Restart Lister-Bridge for the new settings to take effect."
        )
        # R-STATE: an .env sitting next to the .exe outranks the file Setup
        # writes (load_app_dotenv checks the exe directory first) — warn the
        # operator instead of letting their saved values be shadowed silently.
        shadow = settings_logic.shadowing_env_path()
        if shadow is not None:
            st.warning(
                f"A `.env` file also exists at `{shadow}`, which takes "
                "precedence over the saved settings. Delete or update that "
                "file, or your changes here will be ignored."
            )


def _render_help_tab() -> None:
    """
    Render the "Help" tab: the static operator tip sheet from help_content.

    Side Effects:
        Draws one st.subheader + st.markdown pair per entry in
        src.ui.help_content.HELP_SECTIONS, in order.

    FMEA Constraints:
        PI-004 / PI-007 — the "Safety notes" and "Platforms" sections restate
        the defect-disclosure and eBay-vs-draft publish semantics also
        surfaced as contextual tips elsewhere in this module, so an operator
        who skips the tooltips still encounters them here.
    """
    for heading, body in HELP_SECTIONS:
        st.subheader(heading)
        st.markdown(body)


def main() -> None:
    """
    Render the app: header, missing-credential banner, and the Review/Setup tabs.

    Side Effects:
        Drives the whole Streamlit page.

    FMEA Constraints:
        R-STATE — the missing-required check reads the same .env
        (settings.read_settings) that Setup writes to, so the banner reflects
        the operator's actual current configuration.
    """
    st.set_page_config(page_title="Lister-Bridge", layout="wide")
    st.title("Lister-Bridge — review & approve")
    st.caption("Scan Drive → review photos against extracted data → Approve to publish.")

    # Startup banner: if required credentials are missing, tell the operator
    # to complete Setup rather than letting a later, less legible failure
    # surface deep in the Scan/Approve pipeline.
    current_values = settings_logic.read_settings()
    missing = settings_logic.missing_required(current_values)
    if missing:
        st.warning(
            "Setup is incomplete — missing required settings: "
            + ", ".join(missing)
            + ". Complete them in the **Setup** tab below."
        )

    store = _get_store()

    review_tab, setup_tab, help_tab = st.tabs(["Review & approve", "Setup", "Help"])
    with review_tab:
        _render_review_tab(store)
    with setup_tab:
        _render_setup_tab()
    with help_tab:
        _render_help_tab()


if __name__ == "__main__":
    main()
