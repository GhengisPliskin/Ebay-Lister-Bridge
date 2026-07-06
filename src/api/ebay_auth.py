"""
Module: ebay_auth.py
Purpose: Mint and cache short-lived eBay OAuth USER access tokens from a stored
         refresh token, auto-renewing before expiry.
Primary Responsibilities:
  - Select the sandbox/production OAuth host from EBAY_ENV.
  - Validate EBAY_OAUTH_SCOPES at construction time — every scope must be a
    full eBay scope URL, so a malformed scope fails fast instead of surfacing
    as an opaque invalid_scope error on the first refresh call (R-AUTH).
  - Exchange EBAY_OAUTH_REFRESH_TOKEN for an access token (refresh_token grant).
  - Cache the token in memory, and (optionally) in a caller-supplied StateStore
    via TokenCacheRecord, so a process restart reuses a still-valid token
    instead of re-minting one on every run (R-AUTH / R-COST).
Key Interfaces:
  - Input: EBAY_ENV, EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, EBAY_OAUTH_REFRESH_TOKEN,
    EBAY_OAUTH_SCOPES (from .env); an optional injected state_store.StateStore.
  - Output: a Bearer access token string for ebay_client.py.
FMEA Constraints Enforced:
  - R-AUTH — refresh token stored once; access tokens auto-renew before expiry;
    scope format is validated at construction so failures surface immediately.

STATUS: implemented (Phase 1 spike; Phase 4 token-cache wiring complete). Runs
live against the eBay sandbox when credentials are present; otherwise driven by
mocked `requests` in tests. The token cache checks memory first, then the
injected StateStore (if any), then refreshes over HTTP as a last resort — see
EbayAuth.get_access_token / EbayAuth._load_from_state_store.
"""

from __future__ import annotations

import base64
import os
import time

import requests

from src.contracts import TokenCacheRecord
from src.core.paths import load_app_dotenv

# Frozen-aware .env discovery (tries the exe dir / %APPDATA%/ListerBridge
# first under a PyInstaller onefile build; unchanged plain load_dotenv()
# otherwise). See src/core/paths.py (R-STATE).
load_app_dotenv()

# ── Host selection (blueprint: sandbox-first) ─────────────────────────────────
# The OAuth token endpoint differs only by host between environments.
_OAUTH_HOSTS = {
    "sandbox": "https://api.sandbox.ebay.com",
    "production": "https://api.ebay.com",
}
_OAUTH_TOKEN_PATH = "/identity/v1/oauth2/token"

# Renew this many seconds BEFORE the reported expiry so an in-flight pipeline
# step never races the ~2h boundary (R-AUTH).
_EXPIRY_SKEW_SECONDS = 120

# Default timeout for the token request (seconds).
_TOKEN_REQUEST_TIMEOUT = 30

# eBay OAuth scopes are always full URLs under this prefix (sandbox and
# production share the same scope URLs — only the API host differs by env).
# A short-form scope like "sell.inventory" is silently sent verbatim to eBay
# and rejected as invalid_scope on the FIRST LIVE refresh call; validating the
# format at construction turns that into an immediate, actionable ValueError
# instead (R-AUTH: fail fast at construction, not mid-pipeline on refresh).
_SCOPE_URL_PREFIX = "https://api.ebay.com/oauth/"


class EbayAuthError(Exception):
    """
    Raised when an OAuth token refresh fails (bad credentials, network, or a
    non-2xx response from eBay).

    Attributes:
        status_code: HTTP status from eBay, or None for transport errors.
        body: Response body text (truncated) for diagnostics.

    FMEA Constraints:
        R-AUTH — surfaced to the caller so a stalled pipeline reports a clear
        auth failure rather than a raw traceback.
    """

    def __init__(self, message: str, status_code: int | None = None, body: str = "") -> None:
        """Construct an EbayAuthError with optional HTTP context."""
        self.status_code = status_code
        self.body = body
        super().__init__(message)


class EbayAuth:
    """
    Mints and caches eBay USER access tokens via the refresh_token grant.

    A single instance owns one in-memory token cache. When constructed with a
    state_store, that cache is durable: get_access_token checks memory first,
    then the state store's persisted TokenCacheRecord (loading it into memory
    if still valid), and only performs an HTTP refresh as a last resort — so a
    process restart reuses a still-valid token instead of re-minting one
    (R-AUTH / R-COST). The interface (get_access_token) is stable either way.
    """

    def __init__(
        self,
        env: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        scopes: str | None = None,
        *,
        session: requests.Session | None = None,
        state_store=None,
    ) -> None:
        """
        Configure the auth client from explicit args or the environment.

        Args:
            env: "sandbox" or "production"; defaults to EBAY_ENV (then "sandbox").
            client_id: App client ID; defaults to EBAY_CLIENT_ID.
            client_secret: App client secret; defaults to EBAY_CLIENT_SECRET.
            refresh_token: USER refresh token; defaults to EBAY_OAUTH_REFRESH_TOKEN.
            scopes: Space-separated, full-URL scopes; defaults to EBAY_OAUTH_SCOPES.
                Every scope must start with "https://api.ebay.com/oauth/" — eBay
                scopes are full URLs, not short keywords (R-AUTH).
            session: Optional injected requests.Session (tests pass a mock).
            state_store: Optional state_store.StateStore for a durable token
                cache (R-AUTH / R-COST). Default None keeps EbayAuth trivially
                testable/DI-friendly with only the in-memory cache.

        Returns:
            None

        Side Effects:
            Reads eBay env vars. Does NOT perform any network call at construction.

        Raises:
            ValueError: If any configured scope does not start with the required
                "https://api.ebay.com/oauth/" prefix.

        FMEA Constraints:
            R-AUTH — validating scope format here means a misconfigured .env
            fails immediately and legibly at startup, rather than as an opaque
            invalid_scope error from eBay on the first refresh mid-pipeline.
        """
        self.env = (env or os.environ.get("EBAY_ENV") or "sandbox").lower()
        if self.env not in _OAUTH_HOSTS:
            raise EbayAuthError(f"Unknown EBAY_ENV '{self.env}' (expected sandbox|production)")

        self.client_id = client_id or os.environ.get("EBAY_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("EBAY_CLIENT_SECRET", "")
        self.refresh_token = refresh_token or os.environ.get("EBAY_OAUTH_REFRESH_TOKEN", "")
        self.scopes = scopes if scopes is not None else os.environ.get(
            "EBAY_OAUTH_SCOPES", ""
        )
        self._validate_scopes(self.scopes)
        self._session = session or requests.Session()
        # In-memory cache, checked first on every get_access_token call.
        self._cached: TokenCacheRecord | None = None
        # Optional durable cache (state_store.StateStore); see get_access_token.
        self._state_store = state_store

    @staticmethod
    def _validate_scopes(scopes: str) -> None:
        """
        Validate that every space-separated scope is a full eBay scope URL.

        Args:
            scopes: The raw, space-separated scopes string (may be empty).

        Returns:
            None

        Raises:
            ValueError: Naming the first offending scope and the expected
                format, if any scope does not start with
                "https://api.ebay.com/oauth/".

        Side Effects:
            None.

        FMEA Constraints:
            R-AUTH — fail fast at construction instead of at first refresh;
            eBay rejects short-form scopes (e.g. "sell.inventory") with an
            opaque invalid_scope error that only surfaces on a live HTTP call.
        """
        # An empty scopes string is valid (scope is optional on refresh).
        if not scopes:
            return
        for scope in scopes.split():
            if not scope.startswith(_SCOPE_URL_PREFIX):
                raise ValueError(
                    f"Invalid EBAY_OAUTH_SCOPES entry '{scope}': eBay scopes must "
                    f"be full URLs starting with '{_SCOPE_URL_PREFIX}' (e.g. "
                    f"'{_SCOPE_URL_PREFIX}api_scope/sell.inventory'), not a "
                    "short-form keyword."
                )

    @property
    def token_url(self) -> str:
        """Return the full OAuth token endpoint URL for the selected env."""
        return _OAUTH_HOSTS[self.env] + _OAUTH_TOKEN_PATH

    def _is_cache_valid(self) -> bool:
        """
        Return True if the cached token exists and is not within the skew window.

        Returns:
            True if a cached token is present and still valid past the skew margin.

        Side Effects:
            None.
        """
        if self._cached is None:
            return False
        return self._record_is_valid(self._cached)

    @staticmethod
    def _record_is_valid(record: TokenCacheRecord) -> bool:
        """
        Return True if a TokenCacheRecord is not within the expiry-skew window.

        Args:
            record: The TokenCacheRecord to check (in-memory or state-store-loaded).

        Returns:
            True if the record is still valid past _EXPIRY_SKEW_SECONDS.

        Side Effects:
            None.

        FMEA Constraints:
            R-AUTH — the same expiry-margin logic applies uniformly to the
            in-memory cache and any record loaded from the state store, so a
            persisted-but-nearly-expired token is never treated as usable.
        """
        # time.time() is the wall clock; we renew _EXPIRY_SKEW_SECONDS early.
        return time.time() < (record.expires_at_epoch - _EXPIRY_SKEW_SECONDS)

    def _load_from_state_store(self) -> bool:
        """
        Try to load a still-valid persisted token from the injected state store.

        Args:
            None.

        Returns:
            True if a valid token was found and loaded into the in-memory
            cache; False if no state_store is configured, no token is
            persisted, or the persisted token is within the skew window.

        Side Effects:
            On success, sets self._cached from the persisted TokenCacheRecord.

        FMEA Constraints:
            R-AUTH / R-COST — lets a fresh EbayAuth instance (e.g. after a
            process restart) reuse a still-valid token instead of re-minting
            one over HTTP.
        """
        if self._state_store is None:
            return False
        record = self._state_store.get_cached_token()
        if record is None or not self._record_is_valid(record):
            return False
        self._cached = record
        return True

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        """
        Return a valid Bearer access token, refreshing if needed.

        Cache order: 1) a valid in-memory token, 2) a valid token persisted in
        the injected state_store (loaded into memory on a hit), 3) a fresh HTTP
        refresh, whose result is saved back to memory and (if configured) the
        state store.

        Args:
            force_refresh: If True, bypass both caches and mint a new token.

        Returns:
            The access token string (use as `Authorization: Bearer <token>`).

        Side Effects:
            On a cache miss/forced refresh, performs one HTTPS POST to eBay's
            token endpoint, updates the in-memory cache, and (if a state_store
            was injected) persists the new token there too. A state-store hit
            reads from the store but performs no HTTP call.

        Raises:
            EbayAuthError: Missing credentials, transport failure, or non-2xx.

        FMEA Constraints:
            R-AUTH — returns a cached (memory or persisted) token until the
            skew window, then renews; R-COST — avoids re-minting a valid token
            across process restarts when a state_store is provided.
        """
        if not force_refresh:
            if self._is_cache_valid():
                return self._cached.access_token  # type: ignore[union-attr]
            if self._load_from_state_store():
                return self._cached.access_token  # type: ignore[union-attr]
        return self._refresh().access_token

    def _refresh(self) -> TokenCacheRecord:
        """
        Mint a new access token via the refresh_token grant and cache it.

        Returns:
            The new TokenCacheRecord (also stored in self._cached and, if a
            state_store was injected, persisted there too).

        Side Effects:
            One HTTPS POST to the eBay token endpoint. Updates the in-memory
            cache and, when a state_store is configured, calls its
            save_cached_token so the token survives a process restart.

        Raises:
            EbayAuthError: On missing credentials or a non-2xx eBay response.

        FMEA Constraints:
            R-AUTH — Basic-auth client creds + refresh_token grant; expiry stamped
            from the returned expires_in. R-COST — persisting to the state store
            avoids an unnecessary re-mint on the next process start.
        """
        if not (self.client_id and self.client_secret and self.refresh_token):
            raise EbayAuthError(
                "Missing eBay OAuth credentials "
                "(EBAY_CLIENT_ID / EBAY_CLIENT_SECRET / EBAY_OAUTH_REFRESH_TOKEN)."
            )

        # eBay uses HTTP Basic auth with base64(client_id:client_secret).
        basic = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode("utf-8")
        ).decode("ascii")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {basic}",
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        # Scope is optional on refresh; include it when configured.
        if self.scopes:
            data["scope"] = self.scopes

        try:
            resp = self._session.post(
                self.token_url,
                headers=headers,
                data=data,
                timeout=_TOKEN_REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise EbayAuthError(f"eBay token request failed: {exc}") from exc

        if resp.status_code != 200:
            raise EbayAuthError(
                f"eBay token refresh returned {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text[:500],
            )

        payload = resp.json()
        access_token = payload.get("access_token")
        expires_in = payload.get("expires_in", 0)
        if not access_token:
            raise EbayAuthError(
                "eBay token response missing access_token",
                status_code=resp.status_code,
                body=resp.text[:500],
            )

        record = TokenCacheRecord(
            access_token=access_token,
            expires_at_epoch=time.time() + float(expires_in),
            scopes=self.scopes,
        )
        self._cached = record
        # R-AUTH / R-COST: persist so a process restart can reuse this token
        # instead of re-minting one (see _load_from_state_store).
        if self._state_store is not None:
            self._state_store.save_cached_token(record)
        return record
