"""
Module: test_help_content.py
Purpose: Tests for src/ui/help_content.py — the Streamlit-free tip-sheet
         content module (TIPS + HELP_SECTIONS) backing app.py's contextual
         hints and Help tab. No streamlit import, no network.

         app.py itself imports streamlit (not installed in this test
         environment), so its source is read as plain text via Path(...)
         .read_text() rather than imported, matching the pattern already
         used for reading .env.example in tests/test_settings.py.
FMEA Constraints Enforced (asserted): PI-004, PI-007.
"""

from __future__ import annotations

from pathlib import Path

from src.marketplace import other_adapter
from src.ui import help_content
from src.ui.help_content import HELP_SECTIONS, TIPS

_APP_PY_PATH = Path(__file__).resolve().parent.parent / "src" / "ui" / "app.py"
_APP_SOURCE = _APP_PY_PATH.read_text(encoding="utf-8")
_HELP_CONTENT_SOURCE = Path(help_content.__file__).read_text(encoding="utf-8")

# The 7 headings HELP_SECTIONS must contain, in this exact order.
_EXPECTED_HEADINGS = [
    "What Lister-Bridge does",
    "Before you start",
    "The workflow",
    "Understanding warnings & errors",
    "Where your data lives",
    "Platforms",
    "Safety notes",
]


# ── TIPS ────────────────────────────────────────────────────────────────────


def test_tips_values_non_empty_and_under_300_chars():
    """Every TIPS entry is a non-empty string under 300 characters."""
    assert TIPS, "TIPS must not be empty"
    for key, value in TIPS.items():
        assert isinstance(value, str)
        assert value.strip(), f"TIPS[{key!r}] must not be blank"
        assert len(value) < 300, f"TIPS[{key!r}] is {len(value)} chars (limit 300)"


def test_tips_has_expected_keys():
    """The six documented contextual-hint locations are all present."""
    expected_keys = {
        "scan_button",
        "condition_select",
        "description_editor",
        "approve_button",
        "error_banner",
        "stale_cache",
    }
    assert expected_keys.issubset(TIPS.keys())


def test_every_tips_key_referenced_in_app_source():
    """
    No dead TIPS constant: every key must be used somewhere in app.py's
    source (via TIPS["<key>"]), so a tip that exists here is actually wired
    into a widget or message in the UI.
    """
    for key in TIPS:
        needle = f'TIPS["{key}"]'
        assert needle in _APP_SOURCE, (
            f"TIPS key {key!r} is never referenced in src/ui/app.py "
            f"(expected to find {needle!r})"
        )


# ── HELP_SECTIONS ───────────────────────────────────────────────────────────


def test_help_sections_non_empty():
    assert HELP_SECTIONS, "HELP_SECTIONS must not be empty"


def test_help_sections_bodies_non_empty():
    """Every section has a non-blank heading and a non-blank markdown body."""
    for heading, body in HELP_SECTIONS:
        assert isinstance(heading, str) and heading.strip()
        assert isinstance(body, str) and body.strip()


def test_help_sections_headings_present_in_order():
    """The 7 expected headings appear, in exactly this order."""
    headings = [heading for heading, _ in HELP_SECTIONS]
    # Filter to only the expected headings (in case of any incidental extras)
    # and confirm their relative order matches _EXPECTED_HEADINGS exactly.
    filtered = [h for h in headings if h in _EXPECTED_HEADINGS]
    assert filtered == _EXPECTED_HEADINGS


def test_help_sections_under_120_lines_total():
    """Keep the whole Help tab concise: content stays under ~120 lines."""
    total_lines = sum(body.count("\n") + 1 for _, body in HELP_SECTIONS)
    assert total_lines < 120, f"HELP_SECTIONS body content is {total_lines} lines (limit ~120)"


# ── Platform coverage ────────────────────────────────────────────────────────


def test_help_mentions_ebay_and_every_draft_platform_label():
    """
    The Help content must mention eBay plus every platform key/label the
    draft adapter actually supports, so a newly added platform in
    other_adapter._PLATFORM_TEMPLATES can't silently go undocumented.
    """
    all_text = " ".join(body for _, body in HELP_SECTIONS)

    assert "eBay" in all_text

    for platform_key in other_adapter.supported_platforms():
        label = other_adapter.OtherDraftAdapter(platform_key).platform_label
        assert label in all_text, (
            f"Help content never mentions platform label {label!r} "
            f"(key={platform_key!r})"
        )


# ── PORTAL_LINKS reuse (no hardcoded platform URLs) ─────────────────────────


def test_help_content_imports_portal_links_not_hardcoded_urls():
    """
    help_content.py must import PORTAL_LINKS from src.core.settings rather
    than hardcoding the Facebook Marketplace / Mercari URLs a second time.
    """
    assert "from src.core.settings import PORTAL_LINKS" in _HELP_CONTENT_SOURCE

    # The module source itself should not contain the raw platform URLs —
    # those live solely in src.core.settings.PORTAL_LINKS.
    assert "facebook.com/marketplace" not in _HELP_CONTENT_SOURCE
    assert "mercari.com" not in _HELP_CONTENT_SOURCE


def test_help_sections_platforms_section_uses_portal_links_urls():
    """The rendered Platforms section body actually contains the live
    PORTAL_LINKS URLs (proving real reuse, not just an unused import)."""
    from src.core.settings import PORTAL_LINKS

    platforms_body = dict(HELP_SECTIONS)["Platforms"]
    fb_url = PORTAL_LINKS["facebook_marketplace"][0].url
    mercari_url = PORTAL_LINKS["mercari"][0].url

    assert fb_url in platforms_body
    assert mercari_url in platforms_body


# ── No streamlit import ──────────────────────────────────────────────────────


def test_help_content_module_does_not_import_streamlit():
    """
    help_content.py must remain importable without streamlit installed.

    Checks each actual code line (not the module docstring, which
    legitimately discusses the no-streamlit-import rule in prose) for a
    real `import streamlit` / `from streamlit ...` statement.
    """
    for line in _HELP_CONTENT_SOURCE.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("import streamlit")
        assert not stripped.startswith("from streamlit")
    # Also prove it at runtime: the module is already imported above (via
    # `from src.ui import help_content`) in an environment without
    # streamlit installed, so reaching this point is itself confirmation.
    assert help_content is not None
