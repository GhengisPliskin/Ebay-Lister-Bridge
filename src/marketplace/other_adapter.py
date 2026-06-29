"""
Module: other_adapter.py
Purpose: OtherDraftAdapter (v1.2) — a generic DRAFT_ONLY adapter that renders a
         platform-tailored, ready-to-post draft from the platform-agnostic listing
         and writes it to disk for manual posting.
Primary Responsibilities:
  - Hold per-platform templates (Facebook Marketplace + Mercari to start).
  - Render a Markdown posting (title, specifics, price, description) + a photo
    manifest, written under <output_dir>/<item_sku>/<platform>/.
Key Interfaces:
  - Input: a ListingPayload + an output directory.
  - Output: a DraftOutput (+ files on disk).
FMEA Constraints Enforced:
  - PI-007 — emits a draft the operator posts manually; never auto-posts.
  - PI-008 — the posting is a tidy, human-readable document, not raw JSON.

Adding a platform: add one entry to _PLATFORM_TEMPLATES — no other code changes.
"""

from __future__ import annotations

from pathlib import Path

from src.contracts import DraftOutput, ListingPayload
from src.marketplace.base import DraftAdapter

# Per-platform templates. Add a new key here to support a new platform.
#   label       — human-readable platform name
#   title_max   — platform title character cap
#   preamble    — short guidance line written at the top of the posting
#   footer      — platform-specific reminders (shipping, category, etc.)
_PLATFORM_TEMPLATES: dict[str, dict] = {
    "facebook_marketplace": {
        "label": "Facebook Marketplace",
        "title_max": 100,
        "preamble": "Paste into Facebook Marketplace > Create new listing > Item for sale.",
        "footer": (
            "Reminders: choose a Category and Condition in the FB form; set "
            "Location; FB has no item-specifics fields, so the key details are "
            "folded into the description below."
        ),
    },
    "mercari": {
        "label": "Mercari",
        "title_max": 80,
        "preamble": "Paste into Mercari > Sell > List an item.",
        "footer": (
            "Reminders: pick a Category, Brand, Condition, and Shipping option in "
            "the Mercari form; Mercari title cap is 80 chars."
        ),
    },
}


def supported_platforms() -> list[str]:
    """Return the list of platform keys the draft adapter supports."""
    return list(_PLATFORM_TEMPLATES.keys())


class OtherDraftAdapter(DraftAdapter):
    """
    Draft-only adapter that renders a posting for a chosen non-API platform.

    One instance targets one platform (e.g. "mercari"). The registry creates one
    per supported platform.
    """

    def __init__(self, platform: str) -> None:
        """
        Configure the adapter for a specific platform.

        Args:
            platform: A key in _PLATFORM_TEMPLATES (e.g. "facebook_marketplace").

        Returns:
            None

        Raises:
            ValueError: If the platform is not supported.
        """
        if platform not in _PLATFORM_TEMPLATES:
            raise ValueError(
                f"Unsupported draft platform '{platform}'. "
                f"Supported: {', '.join(supported_platforms())}"
            )
        self.platform = platform
        self._tpl = _PLATFORM_TEMPLATES[platform]

    @property
    def name(self) -> str:
        """The registry key (e.g. 'other:mercari')."""
        return f"other:{self.platform}"

    @property
    def platform_label(self) -> str:
        """Human-readable platform name."""
        return self._tpl["label"]

    def _render_markdown(self, payload: ListingPayload, title: str) -> str:
        """
        Build the Markdown posting text from the payload + platform template.

        Args:
            payload: The listing payload.
            title: The (already length-capped) title.

        Returns:
            The posting as a Markdown string.
        """
        lines: list[str] = []
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"_{self._tpl['preamble']}_")
        lines.append("")
        lines.append(f"**Price:** ${payload.price:.2f}")
        lines.append("")
        if payload.item_specifics:
            lines.append("**Item specifics**")
            lines.append("")
            lines.append("| Field | Value |")
            lines.append("| --- | --- |")
            for k, v in payload.item_specifics.items():
                lines.append(f"| {k} | {v} |")
            lines.append("")
        lines.append("**Description**")
        lines.append("")
        lines.append(payload.listing_description or "")
        lines.append("")
        if payload.local_image_paths:
            lines.append("**Photos**")
            lines.append("")
            for p in payload.local_image_paths:
                lines.append(f"- {p}")
            lines.append("")
        lines.append("---")
        lines.append(self._tpl["footer"])
        lines.append("")
        return "\n".join(lines)

    def render_draft(self, payload: ListingPayload, output_dir: str) -> DraftOutput:
        """
        Render the posting + photo manifest and write them under output_dir.

        Writes:
            <output_dir>/<item_sku>/<platform>/posting.md
            <output_dir>/<item_sku>/<platform>/photos_manifest.txt

        Args:
            payload: The operator-approved ListingPayload.
            output_dir: Base directory for drafts.

        Returns:
            A DraftOutput with the rendered fields and the written file paths.

        Side Effects:
            Creates the per-item/per-platform directory and writes two files.

        FMEA Constraints:
            PI-007 — the operator posts the draft manually.
            PI-008 — a tidy Markdown posting, not raw JSON.
        """
        title = (payload.title or payload.item_sku)[: self._tpl["title_max"]]

        target_dir = Path(output_dir) / payload.item_sku / self.platform
        target_dir.mkdir(parents=True, exist_ok=True)

        posting_path = target_dir / "posting.md"
        manifest_path = target_dir / "photos_manifest.txt"

        posting_path.write_text(self._render_markdown(payload, title), encoding="utf-8")
        # The manifest lists the source photo paths (one per line) for manual upload.
        manifest_path.write_text(
            "\n".join(payload.local_image_paths) + ("\n" if payload.local_image_paths else ""),
            encoding="utf-8",
        )

        return DraftOutput(
            item_sku=payload.item_sku,
            platform=self.platform,
            platform_label=self.platform_label,
            title=title,
            price=payload.price,
            item_specifics=dict(payload.item_specifics),
            description=payload.listing_description,
            photo_paths=list(payload.local_image_paths),
            draft_path=str(posting_path),
            manifest_path=str(manifest_path),
        )
