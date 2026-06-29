"""
Module: adapter.py
Purpose: ADDITIVE v1.2 contracts for the multi-marketplace adapter layer — an
         adapter-capability enum and the draft-output type for draft-only
         marketplaces. Existing contracts are unchanged.
Primary Responsibilities:
  - Define AdapterCapability (auto-publish vs draft-only).
  - Define DraftOutput, the platform-tailored posting a draft adapter emits.
Key Interfaces:
  - Input: a ListingPayload + a target platform.
  - Output: DraftOutput consumed by the UI and written to disk for manual posting.
FMEA Constraints Enforced:
  - PI-007 — draft adapters never auto-publish; they emit a draft the operator
    posts manually, preserving the human gate by construction.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AdapterCapability(str, Enum):
    """
    What a MarketplaceAdapter can do.

    AUTO_PUBLISH — the adapter publishes a live listing via an API and returns a
        PublishResult (e.g. eBay).
    DRAFT_ONLY — the adapter renders a platform-tailored posting for the operator
        to paste/upload manually and returns a DraftOutput (e.g. the generic
        "Other" adapter for Facebook Marketplace / Mercari).
    """

    AUTO_PUBLISH = "auto_publish"
    DRAFT_ONLY = "draft_only"


class DraftOutput(BaseModel):
    """
    A ready-to-post draft for a draft-only marketplace.

    Mirrors the platform-agnostic listing (specifics + pricing + photos) rendered
    for one platform, plus the on-disk paths of the written posting and photo
    manifest so the operator can post it manually.

    Attributes:
        item_sku: The item's deterministic SKU.
        platform: Platform key (e.g. "facebook_marketplace", "mercari").
        platform_label: Human-readable platform name (e.g. "Facebook Marketplace").
        title: Platform-tailored title.
        price: Suggested price (USD).
        item_specifics: Aspect name -> value map.
        description: Platform-tailored description text (discloses defects).
        photo_paths: Local photo paths to upload manually.
        draft_path: Path to the written posting file (e.g. a Markdown posting).
        manifest_path: Path to the written photo manifest file.

    FMEA Constraints:
        PI-007 — a draft is never auto-posted; the operator posts it manually.
    """

    model_config = ConfigDict(extra="forbid")

    item_sku: str
    platform: str
    platform_label: str = ""
    title: str = ""
    price: float = Field(default=0.0, ge=0)
    item_specifics: dict[str, str] = Field(default_factory=dict)
    description: str = ""
    photo_paths: list[str] = Field(default_factory=list)
    draft_path: str = ""
    manifest_path: str = ""
