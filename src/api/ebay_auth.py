"""
Module: ebay_auth.py
Purpose: Mint and cache short-lived eBay OAuth USER access tokens from a stored
         refresh token, auto-renewing before expiry.
Primary Responsibilities:
  - Select the sandbox/production OAuth host from EBAY_ENV.
  - Exchange EBAY_OAUTH_REFRESH_TOKEN for an access token (refresh_token grant).
  - Cache the token in memory (and, in Phase 4, the state store) and renew it
    before the ~2h expiry so the pipeline never stalls mid-run (R-AUTH).
Key Interfaces:
  - Input: EBAY_ENV, EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, EBAY_OAUTH_REFRESH_TOKEN,
    EBAY_OAUTH_SCOPES (from .env).
  - Output: a Bearer access token string for ebay_client.py.
FMEA Constraints Enforced:
  - R-AUTH — refresh token stored once; access tokens auto-renew before expiry.

STATUS: implemented (Phase 1 spike). Runs live against the eBay sandbox when
credentials are present; otherwise driven by mocked `requests` in tests. The
token-cache hand-off to state_store.py is wired in Phase 4 (see _TokenCache).
"""

from __future__ import annotations

import base64
import os
import time

import requests
from dotenv import load_dotenv

from src.contracts import TokenCacheRecord

load_dotenv()

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

    A single instance owns one in-memory token cache. In Phase 4 the cache is
    backed by state_store.TokenCacheRecord so a process restart reuses a still-
    valid token; the interface (get_access_token) is stable now.
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
    ) -> None:
        """
        Configure the auth client from explicit args or the environment.

        Args:
            env: "sandbox" or "production"; defaults to EBAY_ENV (then "sandbox").
            client_id: App client ID; defaults to EBAY_CLIENT_ID.
            client_secret: App client secret; defaults to EBAY_CLIENT_SECRET.
            refresh_token: USER refresh token; defaults to EBAY_OAUTH_REFRESH_TOKEN.
            scopes: Space-separated scopes; defaults to EBAY_OAUTH_SCOPES.
            session: Optional injected requests.Session (tests pass a mock).

        Returns:
            None

        Side Effects:
            Reads eBay env vars. Does NOT perform any network call at construction.
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
        self._session = session or requests.Session()
        # In-memory cache; replaced/augmented by state_store in Phase 4.
        self._cached: TokenCacheRecord | None = None

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
        # time.time() is the wall clock; we renew _EXPIRY_SKEW_SECONDS early.
        return time.time() < (self._cached.expires_at_epoch - _EXPIRY_SKEW_SECONDS)

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        """
        Return a valid Bearer access token, refreshing if needed.

        Args:
            force_refresh: If True, bypass the cache and mint a new token.

        Returns:
            The access token string (use as `Authorization: Bearer <token>`).

        Side Effects:
            On a cache miss/forced refresh, performs one HTTPS POST to eBay's
            token endpoint and updates the in-memory cache.

        Raises:
            EbayAuthError: Missing credentials, transport failure, or non-2xx.

        FMEA Constraints:
            R-AUTH — returns a cached token until the skew window, then renews.
        """
        if not force_refresh and self._is_cache_valid():
            return self._cached.access_token  # type: ignore[union-attr]
        return self._refresh().access_token

    def _refresh(self) -> TokenCacheRecord:
        """
        Mint a new access token via the refresh_token grant and cache it.

        Returns:
            The new TokenCacheRecord (also stored in self._cached).

        Side Effects:
            One HTTPS POST to the eBay token endpoint.

        Raises:
            EbayAuthError: On missing credentials or a non-2xx eBay response.

        FMEA Constraints:
            R-AUTH — Basic-auth client creds + refresh_token grant; expiry stamped
            from the returned expires_in.
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
        return record
