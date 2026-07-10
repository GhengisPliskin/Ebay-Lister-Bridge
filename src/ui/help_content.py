"""
Module: help_content.py
Purpose: Streamlit-free source of truth for the in-app tip sheet — contextual
         widget hints (TIPS) and the "Help" tab's static content (HELP_SECTIONS)
         — so operator-facing guidance text is testable and never hand-duplicated
         between the UI and its tests.
Primary Responsibilities:
  - Hold every contextual hint string (TIPS), keyed by the widget/location it is
    attached to in src/ui/app.py via each widget's help= parameter (or appended
    to an st.error/st.warning message where help= is not applicable).
  - Hold the Help tab's full content (HELP_SECTIONS): ordered (heading, markdown
    body) pairs covering what the app does, setup, the workflow, error/warning
    meanings, where data lives, platform coverage, and safety notes.
  - Reuse src.core.settings.PORTAL_LINKS for the Facebook Marketplace / Mercari
    posting links rather than hardcoding those URLs a second time here.
Key Interfaces:
  - Input: None (all content is static; PORTAL_LINKS is imported, not computed).
  - Output: TIPS (dict[str, str]) and HELP_SECTIONS (list[tuple[str, str]]),
    consumed by src/ui/app.py's widget help= arguments and the Help tab renderer.
FMEA Constraints Enforced:
  - PI-004 — "description_editor" and the Safety notes section both state that
    defect disclosure is confirmed by the operator before Approve, matching the
    contract's forced defects_found field and orchestrator's description build.
  - PI-007 — "approve_button" and the workflow section both state that eBay
    publishes live immediately while FB/Mercari only ever write a local draft,
    matching src/marketplace/other_adapter.py's DRAFT_ONLY capability.

NOTE: this module must NEVER import streamlit — it is imported by tests that do
not have streamlit installed, and by src/ui/app.py, which does. This mirrors the
existing src/core/settings.py / src/ui/app.py split (pure logic vs. widgets).
"""

from __future__ import annotations

from src.core.settings import PORTAL_LINKS

# ── Contextual tips ────────────────────────────────────────────────────────────
#
# Short (one-two sentence, <300 char) hints keyed by the widget/location they
# are attached to in src/ui/app.py. Each key below is referenced by name in
# app.py (via TIPS["<key>"]) — see tests/test_help_content.py for the dead-
# constant check that keeps this dict and its call sites in lockstep.
TIPS: dict[str, str] = {
    "scan_button": (
        "Scan lists new Drive batches, runs vision extraction and pricing, and "
        "prepares review cards below. Nothing is published yet — Scan never "
        "publishes or writes a draft by itself."
    ),
    "condition_select": (
        "Pick the eBay condition that matches the photos. This is pre-filled "
        "from the AI's guess, but verify it against the item before approving."
    ),
    "description_editor": (
        "Defects the AI found are disclosed here (PI-004). Confirm or correct "
        "this text before approving — it publishes verbatim to the buyer."
    ),
    "approve_button": (
        "eBay: publishes the listing live immediately. Facebook Marketplace / "
        "Mercari: writes a local draft folder for you to paste in manually — "
        "nothing is posted automatically for those platforms."
    ),
    "error_banner": (
        "Failed batches are retried automatically on the next Scan — fix the "
        "underlying cause first, or the same batch will simply fail again."
    ),
    "stale_cache": (
        "These photos are served from the local cache because Drive was "
        "unreachable during the last Scan — verify they still match the item "
        "before approving."
    ),
}


def _tips_markdown_bullets() -> str:
    """
    Not used by app.py — retained only to keep TIPS import-adjacent to any
    future markdown rendering need without duplicating its keys elsewhere.

    Returns:
        An empty string placeholder (no current callers).

    Side Effects:
        None.
    """
    # Intentionally minimal: HELP_SECTIONS below is hand-written prose, not
    # generated from TIPS, so the Help tab reads naturally rather than as a
    # dumped key/value list.
    return ""


# ── Help tab sections ──────────────────────────────────────────────────────────
#
# Ordered (heading, markdown body) pairs rendered as st.subheader + st.markdown
# pairs by src/ui/app.py's Help tab. Content is deliberately concise and
# operator-focused (no dev jargon); every factual claim here was checked
# against src/core/orchestrator.py, src/core/drive_fetcher.py, src/ui/review.py,
# and src/marketplace/other_adapter.py before being written.
#
# Facebook Marketplace / Mercari links are NOT hardcoded here — the "Platforms"
# section below reuses src.core.settings.PORTAL_LINKS (the same registry the
# Setup tab's draft-platform expander already renders from) so a URL only ever
# lives in one place.
_FB_LINK = PORTAL_LINKS["facebook_marketplace"][0]
_MERCARI_LINK = PORTAL_LINKS["mercari"][0]

HELP_SECTIONS: list[tuple[str, str]] = [
    (
        "What Lister-Bridge does",
        (
            "Lister-Bridge turns a folder of item photos into a ready-to-publish "
            "eBay listing (or a ready-to-post draft for Facebook Marketplace / "
            "Mercari). It scans a Google Drive staging folder, uses AI to read "
            "the photos and suggest a title, condition, description, and price, "
            "then waits for you to review and correct everything before "
            "anything goes live."
        ),
    ),
    (
        "Before you start",
        (
            "Enter your Google Drive, Gemini, and eBay credentials on the "
            "**Setup** tab, then use each **Test** button to confirm they work "
            "before your first Scan.\n\n"
            "Drive folder layout: your staging folder should contain **one "
            "subfolder per item**, and each item's photos go inside its "
            "subfolder (nested sub-subfolders are also picked up, so photos "
            "can be organized further if needed). Each item subfolder becomes "
            "one review card after Scan."
        ),
    ),
    (
        "The workflow",
        (
            "1. Photograph the item.\n"
            "2. Upload its photos into a new subfolder inside the Drive "
            "staging folder.\n"
            "3. Click **Scan Drive for new items** (Review & approve tab).\n"
            "4. Review each card: check the title, price, condition, and "
            "description against the photos.\n"
            "5. Click **Approve** — eBay listings publish live; Facebook "
            "Marketplace / Mercari write a local draft instead.\n"
            "6. The item is published (eBay) or a draft is written to disk "
            "(Facebook Marketplace / Mercari).\n"
            "7. For eBay, the source Drive batch is automatically archived so "
            "it will not be re-scanned. Draft targets leave the batch in "
            "staging until you separately archive or remove it."
        ),
    ),
    (
        "Understanding warnings & errors",
        (
            "**Red error banners** on a batch mean that batch failed to "
            "prepare (for example, a Drive download or AI extraction problem). "
            "Failed batches are retried automatically on the next Scan, so fix "
            "the underlying cause (credentials, connectivity, folder contents) "
            "before scanning again — the same problem will otherwise repeat.\n\n"
            "**Stale-cache warnings** mean Drive was unreachable during a Scan "
            "and the app fell back to previously cached photos; verify they "
            "still match the current contents of that item's folder.\n\n"
            "**\"Cannot publish yet\"** messages on a review card list specific "
            "missing or invalid fields (e.g. a policy ID or category); the "
            "Approve button stays disabled for eBay until these are resolved."
        ),
    ),
    (
        "Where your data lives",
        (
            "Running from source: everything lives under the project's `data/` "
            "directory (image cache, SQLite state database, generated drafts).\n\n"
            "Running the packaged .exe: data lives under "
            "`%APPDATA%\\ListerBridge` instead (same contents: the state "
            "database and image cache), since a packaged app's own folder is "
            "not a safe place to store data between runs.\n\n"
            "Safe to delete: the image cache (photos are simply re-downloaded "
            "from Drive on the next Scan). Do not delete the SQLite state "
            "database unless you intend to lose dedup/resume history and "
            "reprocess everything from scratch."
        ),
    ),
    (
        "Platforms",
        (
            "**eBay** — auto-publishes via the eBay API once you click "
            "Approve, using the fulfillment/payment/return policies and "
            "inventory location configured on the Setup tab.\n\n"
            f"**Facebook Marketplace** and **Mercari** — these do not auto-"
            "publish. Approving for either writes a ready-to-post local draft "
            "(title, description, price, photo list) that you paste in "
            "manually. Posting pages: "
            f"[{_FB_LINK.label}]({_FB_LINK.url}) and "
            f"[{_MERCARI_LINK.label}]({_MERCARI_LINK.url})."
        ),
    ),
    (
        "Safety notes",
        (
            "**Defect disclosure is your responsibility.** The AI flags "
            "defects it sees in the photos, but only the description text you "
            "confirm (or correct) before Approve actually publishes — always "
            "read it against the real item first.\n\n"
            "**Price is a suggestion, not a fact.** Sanity-check the suggested "
            "price against the sold/comp rationale shown on the card before "
            "approving; the app will never guess a price it cannot support "
            "with a comp, cost, or fee input."
        ),
    ),
]
