"""
Module: state_store.py
Purpose: SQLite-backed state for dedup/resume — processed items, SKUs, eBay
         offer/listing IDs, EPS URLs, and the eBay access-token cache.
Primary Responsibilities:
  - Create/migrate the SQLite schema (items table + token cache).
  - Upsert/read ItemRecord rows keyed by the deterministic item_sku.
  - Provide dedup queries (is this SKU already published?) for the orchestrator.
  - Cache the eBay OAuth access token (TokenCacheRecord) for ebay_auth.
Key Interfaces:
  - Input: ItemRecord / TokenCacheRecord writes from orchestrator.py & ebay_auth.py.
  - Output: ItemRecord / TokenCacheRecord reads; STATE_STORE_DB_PATH from .env.
FMEA Constraints Enforced:
  - R-STATE — item_sku is the unique idempotency key; offer_id/listing_id written
    immediately after each eBay call so crash-and-resume never double-publishes.
  - R-AUTH / R-COST — token cache avoids re-minting a valid (~2h) access token.

STATUS: interface stub (signatures + docstrings). Implemented by a parallel
Phase 0/4 agent against the frozen state contracts (src.contracts.state).
"""

from __future__ import annotations

from src.contracts import ItemRecord, ItemStatus, TokenCacheRecord


class StateStore:
    """
    SQLite state store. One instance owns one database file.

    The items table has ≤7 columns (item_sku PK, batch_folder_id, status,
    offer_id, listing_id, eps_urls, updated_at). A small token_cache table holds
    the eBay access token. All writes are keyed on item_sku for idempotency.
    """

    def __init__(self, db_path: str | None = None) -> None:
        """
        Open (and lazily create/migrate) the SQLite database.

        Args:
            db_path: Override for STATE_STORE_DB_PATH (else read from env).

        Returns:
            None

        Side Effects:
            Opens a SQLite connection; creates the schema on first use.

        Raises:
            NotImplementedError: This is a stub.
        """
        raise NotImplementedError("StateStore.__init__ is a stub")

    def upsert_item(self, record: ItemRecord) -> None:
        """
        Insert or update an item row, keyed on item_sku.

        Args:
            record: The ItemRecord to persist.

        Returns:
            None

        Side Effects:
            Writes one row to the items table; sets updated_at.

        Raises:
            NotImplementedError: This is a stub.

        FMEA Constraints:
            R-STATE — written immediately after each pipeline/eBay step so a
            crash-and-resume sees committed offer_id/listing_id.
        """
        raise NotImplementedError("StateStore.upsert_item is a stub")

    def get_item(self, item_sku: str) -> ItemRecord | None:
        """
        Fetch one item by SKU.

        Args:
            item_sku: The deterministic SKU / idempotency key.

        Returns:
            The ItemRecord, or None if the SKU is unknown.

        Raises:
            NotImplementedError: This is a stub.
        """
        raise NotImplementedError("StateStore.get_item is a stub")

    def is_published(self, item_sku: str) -> bool:
        """
        Return True if the SKU is already PUBLISHED (dedup guard).

        Args:
            item_sku: The deterministic SKU / idempotency key.

        Returns:
            True if a row exists with status == PUBLISHED.

        Raises:
            NotImplementedError: This is a stub.

        FMEA Constraints:
            R-STATE — the orchestrator calls this before any eBay publish to
            skip already-live items.
        """
        raise NotImplementedError("StateStore.is_published is a stub")

    def set_status(self, item_sku: str, status: ItemStatus) -> None:
        """
        Update only the status (and updated_at) of an existing item.

        Args:
            item_sku: The SKU to update.
            status: The new ItemStatus.

        Returns:
            None

        Side Effects:
            Writes status + updated_at for the row.

        Raises:
            NotImplementedError: This is a stub.
        """
        raise NotImplementedError("StateStore.set_status is a stub")

    def get_cached_token(self) -> TokenCacheRecord | None:
        """
        Return the cached eBay access token, or None if absent/expired-unknown.

        Returns:
            The TokenCacheRecord, or None. Expiry checking is the caller's
            responsibility (ebay_auth compares expires_at_epoch to now).

        Raises:
            NotImplementedError: This is a stub.

        FMEA Constraints:
            R-AUTH / R-COST — lets ebay_auth reuse a valid token.
        """
        raise NotImplementedError("StateStore.get_cached_token is a stub")

    def save_cached_token(self, token: TokenCacheRecord) -> None:
        """
        Persist the eBay access token to the cache.

        Args:
            token: The TokenCacheRecord to store.

        Returns:
            None

        Side Effects:
            Overwrites the single cached token row.

        Raises:
            NotImplementedError: This is a stub.
        """
        raise NotImplementedError("StateStore.save_cached_token is a stub")
