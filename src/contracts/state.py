"""
Module: state.py
Purpose: Frozen data contract for the state-store records (SQLite items table +
         token cache).
Primary Responsibilities:
  - Define ItemStatus, the lifecycle status enum for an item.
  - Define ItemRecord, the ≤7-column items-table row from the blueprint.
  - Define TokenCacheRecord for the cached eBay access token (R-AUTH / R-COST).
Key Interfaces:
  - Input: orchestrator.py writes records as items move through the pipeline.
  - Output: state_store.py persists/reads these; orchestrator dedups on them.
FMEA Constraints Enforced:
  - R-STATE — item_sku is the deterministic idempotency key; offer_id/listing_id
    are recorded immediately after each eBay call so crash-and-resume never
    double-publishes.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ItemStatus(str, Enum):
    """
    Lifecycle status of an item in the state store.

    Mirrors the blueprint items-table status values. String-valued so it
    serializes directly into the SQLite `status` column.
    """

    NEW = "new"
    EXTRACTED = "extracted"
    PRICED = "priced"
    PUBLISHED = "published"
    ERROR = "error"


class ItemRecord(BaseModel):
    """
    One row of the state-store items table (blueprint: ≤7 columns).

    Attributes:
        item_sku: Deterministic SKU derived from the Drive subfolder ID
            (e.g. "LB-{folderId}"); the idempotency key (R-STATE).
        batch_folder_id: Drive subfolder ID this item came from.
        status: Lifecycle status (ItemStatus).
        offer_id: eBay offer ID (set after createOffer).
        listing_id: eBay listing ID (set after publishOffer; live).
        eps_urls: Uploaded EPS image URLs.
        updated_at: ISO 8601 timestamp of the last update.

    FMEA Constraints:
        R-STATE — dedup skips any item already PUBLISHED; offer_id/listing_id are
        written immediately after each eBay call so resume never double-publishes.
    """

    model_config = ConfigDict(extra="forbid")

    item_sku: str = Field(description="Deterministic SKU / idempotency key.")
    batch_folder_id: str = Field(description="Drive subfolder ID.")
    status: ItemStatus = Field(default=ItemStatus.NEW)
    offer_id: str | None = Field(default=None)
    listing_id: str | None = Field(default=None)
    eps_urls: list[str] = Field(default_factory=list)
    updated_at: str = Field(default="", description="ISO 8601 timestamp.")


class TokenCacheRecord(BaseModel):
    """
    Cached eBay OAuth access token (R-AUTH / R-COST).

    Stored by ebay_auth.py via state_store.py so a short-lived (~2h) access token
    is reused across calls instead of being re-minted every request.

    Attributes:
        access_token: The current eBay OAuth access token.
        expires_at_epoch: Unix epoch seconds at which the token expires.
        scopes: The space-joined scopes the token was minted with.

    FMEA Constraints:
        R-AUTH — ebay_auth refreshes before expiry; this record is the cache it
        checks first.
    """

    model_config = ConfigDict(extra="forbid")

    access_token: str
    expires_at_epoch: float = Field(description="Unix epoch seconds of expiry.")
    scopes: str = Field(default="")
