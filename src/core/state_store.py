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
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from src.contracts import ItemRecord, ItemStatus, TokenCacheRecord
from src.core.paths import load_app_dotenv, resolve_app_path

# Frozen-aware .env discovery (tries the exe dir / %APPDATA%/ListerBridge
# first when running as a PyInstaller onefile build; unchanged plain
# load_dotenv() otherwise). See src/core/paths.py (R-STATE).
load_app_dotenv()

# Default DB location if STATE_STORE_DB_PATH is unset.
_DEFAULT_DB_PATH = "data/state/lister_bridge.db"

# The token cache holds a single row, addressed by this fixed id.
_TOKEN_ROW_ID = 1


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string (for updated_at)."""
    return datetime.now(timezone.utc).isoformat()


def _resolve_db_path(db_path: str | None) -> str:
    """
    Resolve the SQLite DB path, anchoring a relative path to a run-safe root.

    Args:
        db_path: Explicit path, or None to read STATE_STORE_DB_PATH / default.

    Returns:
        An absolute path string; the parent directory is created if missing.

    Side Effects:
        Creates the parent directory tree.

    FMEA Constraints:
        R-STATE — relative paths are anchored via resolve_app_path(), which
        anchors to %APPDATA%/ListerBridge when frozen (PyInstaller onefile)
        instead of the ephemeral sys._MEIPASS extraction dir, so the dedup DB
        survives across runs of the packaged .exe.
    """
    raw = db_path or os.environ.get("STATE_STORE_DB_PATH") or _DEFAULT_DB_PATH
    # resolve_app_path anchors relative paths appropriately for the current
    # runtime mode (frozen vs. source) and passes absolute paths through as-is.
    resolved = resolve_app_path(raw)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return str(resolved)


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
            db_path: Override for STATE_STORE_DB_PATH (else env / default). Pass
                ":memory:" for an ephemeral in-process DB (used by tests).

        Returns:
            None

        Side Effects:
            Opens a SQLite connection; creates the schema on first use.
        """
        # ":memory:" is passed straight through; everything else is resolved/created.
        self.db_path = db_path if db_path == ":memory:" else _resolve_db_path(db_path)
        # check_same_thread=False keeps a single Streamlit/orchestrator process
        # flexible across threads; access is serialized by SQLite's own locking.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        """
        Create the items + token_cache tables if they do not already exist.

        Returns:
            None

        Side Effects:
            Executes DDL and commits.
        """
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS items (
                item_sku        TEXT PRIMARY KEY,
                batch_folder_id TEXT NOT NULL,
                status          TEXT NOT NULL,
                offer_id        TEXT,
                listing_id      TEXT,
                eps_urls        TEXT NOT NULL DEFAULT '[]',
                updated_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS token_cache (
                id               INTEGER PRIMARY KEY CHECK (id = 1),
                access_token     TEXT NOT NULL,
                expires_at_epoch REAL NOT NULL,
                scopes           TEXT NOT NULL DEFAULT ''
            );
            """
        )
        self._conn.commit()

    # ── items ────────────────────────────────────────────────────────────────

    def _row_to_record(self, row: sqlite3.Row) -> ItemRecord:
        """
        Convert a sqlite Row into an ItemRecord (parsing eps_urls JSON).

        Args:
            row: A sqlite3.Row from the items table.

        Returns:
            The corresponding ItemRecord.
        """
        return ItemRecord(
            item_sku=row["item_sku"],
            batch_folder_id=row["batch_folder_id"],
            status=ItemStatus(row["status"]),
            offer_id=row["offer_id"],
            listing_id=row["listing_id"],
            eps_urls=json.loads(row["eps_urls"]) if row["eps_urls"] else [],
            updated_at=row["updated_at"],
        )

    def upsert_item(self, record: ItemRecord) -> None:
        """
        Insert or update an item row, keyed on item_sku.

        Args:
            record: The ItemRecord to persist. updated_at is stamped here if the
                record does not already carry one.

        Returns:
            None

        Side Effects:
            Writes one row to the items table; commits.

        FMEA Constraints:
            R-STATE — written immediately after each pipeline/eBay step so a
            crash-and-resume sees committed offer_id/listing_id.
        """
        updated_at = record.updated_at or _utc_now_iso()
        self._conn.execute(
            """
            INSERT INTO items
                (item_sku, batch_folder_id, status, offer_id, listing_id,
                 eps_urls, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_sku) DO UPDATE SET
                batch_folder_id = excluded.batch_folder_id,
                status          = excluded.status,
                offer_id        = excluded.offer_id,
                listing_id      = excluded.listing_id,
                eps_urls        = excluded.eps_urls,
                updated_at      = excluded.updated_at
            """,
            (
                record.item_sku,
                record.batch_folder_id,
                record.status.value,
                record.offer_id,
                record.listing_id,
                json.dumps(record.eps_urls),
                updated_at,
            ),
        )
        self._conn.commit()

    def get_item(self, item_sku: str) -> ItemRecord | None:
        """
        Fetch one item by SKU.

        Args:
            item_sku: The deterministic SKU / idempotency key.

        Returns:
            The ItemRecord, or None if the SKU is unknown.
        """
        cur = self._conn.execute(
            "SELECT * FROM items WHERE item_sku = ?", (item_sku,)
        )
        row = cur.fetchone()
        return self._row_to_record(row) if row else None

    def is_published(self, item_sku: str) -> bool:
        """
        Return True if the SKU is already PUBLISHED (dedup guard).

        Args:
            item_sku: The deterministic SKU / idempotency key.

        Returns:
            True if a row exists with status == PUBLISHED.

        FMEA Constraints:
            R-STATE — the orchestrator calls this before any eBay publish to
            skip already-live items.
        """
        cur = self._conn.execute(
            "SELECT 1 FROM items WHERE item_sku = ? AND status = ?",
            (item_sku, ItemStatus.PUBLISHED.value),
        )
        return cur.fetchone() is not None

    def set_status(self, item_sku: str, status: ItemStatus) -> None:
        """
        Update only the status (and updated_at) of an existing item.

        Args:
            item_sku: The SKU to update.
            status: The new ItemStatus.

        Returns:
            None

        Side Effects:
            Writes status + updated_at for the row; commits. No-op if the SKU is
            unknown (the orchestrator upserts before setting status).
        """
        self._conn.execute(
            "UPDATE items SET status = ?, updated_at = ? WHERE item_sku = ?",
            (status.value, _utc_now_iso(), item_sku),
        )
        self._conn.commit()

    def list_items(self) -> list[ItemRecord]:
        """
        Return all item records, newest update first.

        Returns:
            A list of ItemRecord ordered by updated_at descending. Useful for the
            UI to render the current pipeline state.
        """
        cur = self._conn.execute("SELECT * FROM items ORDER BY updated_at DESC")
        return [self._row_to_record(r) for r in cur.fetchall()]

    # ── token cache ──────────────────────────────────────────────────────────

    def get_cached_token(self) -> TokenCacheRecord | None:
        """
        Return the cached eBay access token, or None if none is stored.

        Returns:
            The TokenCacheRecord, or None. Expiry checking is the caller's
            responsibility (ebay_auth compares expires_at_epoch to now).

        FMEA Constraints:
            R-AUTH / R-COST — lets ebay_auth reuse a valid token.
        """
        cur = self._conn.execute(
            "SELECT access_token, expires_at_epoch, scopes FROM token_cache WHERE id = ?",
            (_TOKEN_ROW_ID,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return TokenCacheRecord(
            access_token=row["access_token"],
            expires_at_epoch=row["expires_at_epoch"],
            scopes=row["scopes"],
        )

    def save_cached_token(self, token: TokenCacheRecord) -> None:
        """
        Persist the eBay access token to the cache (single-row upsert).

        Args:
            token: The TokenCacheRecord to store.

        Returns:
            None

        Side Effects:
            Overwrites the single cached token row; commits.
        """
        self._conn.execute(
            """
            INSERT INTO token_cache (id, access_token, expires_at_epoch, scopes)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                access_token     = excluded.access_token,
                expires_at_epoch = excluded.expires_at_epoch,
                scopes           = excluded.scopes
            """,
            (_TOKEN_ROW_ID, token.access_token, token.expires_at_epoch, token.scopes),
        )
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()
