"""
Module: test_ebay_auth.py
Purpose: Mocked tests for ebay_auth.EbayAuth — token refresh, caching, host
         selection, scope-format validation, and state_store-backed persistence
         — with NO live eBay credentials.
FMEA Constraints Enforced (asserted): R-AUTH.
"""

from __future__ import annotations

import time

import pytest

from src.api.ebay_auth import EbayAuth, EbayAuthError
from src.contracts import TokenCacheRecord
from src.core.state_store import StateStore

# Full-URL scopes, matching the real .env.example format (eBay scopes are full
# URLs, not short keywords — see Fix 1 / _SCOPE_URL_PREFIX in ebay_auth.py).
_VALID_SCOPES = (
    "https://api.ebay.com/oauth/api_scope "
    "https://api.ebay.com/oauth/api_scope/sell.inventory "
    "https://api.ebay.com/oauth/api_scope/commerce.media"
)


def _auth(session, **kw):
    """Build an EbayAuth with dummy creds and an injected fake session."""
    defaults = dict(
        env="sandbox",
        client_id="cid",
        client_secret="csecret",
        refresh_token="rtoken",
        scopes=_VALID_SCOPES,
    )
    defaults.update(kw)
    return EbayAuth(session=session, **defaults)


def test_token_url_selects_sandbox_host():
    """Host selection points at the sandbox OAuth endpoint."""
    auth = EbayAuth(env="sandbox", client_id="c", client_secret="s", refresh_token="r")
    assert auth.token_url == "https://api.sandbox.ebay.com/identity/v1/oauth2/token"


def test_refresh_returns_access_token_and_sends_basic_auth(fake_session, fake_response):
    """A successful refresh returns the token and sends Basic auth + grant body."""
    sess = fake_session(
        [fake_response(200, {"access_token": "AT-123", "expires_in": 7200})]
    )
    auth = _auth(sess)
    token = auth.get_access_token()
    assert token == "AT-123"
    call = sess.calls[0]
    # Basic auth header present; refresh_token grant in the form body.
    assert call["headers"]["Authorization"].startswith("Basic ")
    assert call["data"]["grant_type"] == "refresh_token"
    assert call["data"]["refresh_token"] == "rtoken"
    assert call["data"]["scope"] == _VALID_SCOPES


def test_token_is_cached_no_second_call(fake_session, fake_response):
    """A valid cached token (R-AUTH) is reused without a second network call."""
    sess = fake_session(
        [fake_response(200, {"access_token": "AT-1", "expires_in": 7200})]
    )
    auth = _auth(sess)
    assert auth.get_access_token() == "AT-1"
    assert auth.get_access_token() == "AT-1"
    assert len(sess.calls) == 1  # only one refresh occurred


def test_force_refresh_mints_new_token(fake_session, fake_response):
    """force_refresh bypasses the cache and mints again."""
    sess = fake_session(
        [
            fake_response(200, {"access_token": "AT-1", "expires_in": 7200}),
            fake_response(200, {"access_token": "AT-2", "expires_in": 7200}),
        ]
    )
    auth = _auth(sess)
    assert auth.get_access_token() == "AT-1"
    assert auth.get_access_token(force_refresh=True) == "AT-2"
    assert len(sess.calls) == 2


def test_missing_credentials_raises(fake_session):
    """Missing credentials raise a clear EbayAuthError, not a transport error."""
    auth = EbayAuth(
        env="sandbox", client_id="", client_secret="", refresh_token="",
        session=fake_session([]),
    )
    with pytest.raises(EbayAuthError):
        auth.get_access_token()


def test_non_200_raises_with_status(fake_session, fake_response):
    """A non-200 token response surfaces the status on the error."""
    sess = fake_session([fake_response(401, {}, text="invalid_client")])
    auth = _auth(sess)
    with pytest.raises(EbayAuthError) as ei:
        auth.get_access_token()
    assert ei.value.status_code == 401


# ── Fix 1: scope format validation (fail fast at construction, R-AUTH) ────────


def test_bad_short_form_scope_raises_value_error(fake_session):
    """A short-form scope (not a full eBay scope URL) raises ValueError at construction."""
    with pytest.raises(ValueError) as ei:
        _auth(fake_session([]), scopes="sell.inventory commerce.media buy.browse")
    # The error names the offending scope and the expected format.
    assert "sell.inventory" in str(ei.value)
    assert "https://api.ebay.com/oauth/" in str(ei.value)


def test_partially_bad_scopes_raises_naming_offender(fake_session):
    """One good + one bad scope still raises, naming the bad one."""
    with pytest.raises(ValueError) as ei:
        _auth(
            fake_session([]),
            scopes="https://api.ebay.com/oauth/api_scope buy.browse",
        )
    assert "buy.browse" in str(ei.value)


def test_good_full_url_scopes_construct_fine(fake_session):
    """Full-URL scopes (the correct format) construct without error."""
    auth = _auth(fake_session([]), scopes=_VALID_SCOPES)
    assert auth.scopes == _VALID_SCOPES


def test_empty_scopes_are_valid(fake_session):
    """An empty scopes string is valid (scope is optional on refresh)."""
    auth = _auth(fake_session([]), scopes="")
    assert auth.scopes == ""


# ── Fix 2: state_store-backed token cache (R-AUTH / R-COST) ──────────────────


@pytest.fixture
def store():
    """An ephemeral in-memory StateStore for token-cache wiring tests."""
    s = StateStore(":memory:")
    yield s
    s.close()


def test_valid_persisted_token_skips_http_refresh(fake_session, store):
    """A valid token already in the state store is used with NO HTTP call."""
    store.save_cached_token(
        TokenCacheRecord(
            access_token="PERSISTED-AT", expires_at_epoch=time.time() + 7200,
            scopes=_VALID_SCOPES,
        )
    )
    sess = fake_session([])  # no responses queued: a refresh call would error
    auth = _auth(sess, state_store=store)
    assert auth.get_access_token() == "PERSISTED-AT"
    assert len(sess.calls) == 0


def test_expired_persisted_token_triggers_refresh_and_resave(fake_session, fake_response, store):
    """An expired persisted token is ignored; a fresh refresh is saved back to the store."""
    store.save_cached_token(
        TokenCacheRecord(
            access_token="STALE-AT", expires_at_epoch=1.0,  # long expired
            scopes=_VALID_SCOPES,
        )
    )
    sess = fake_session(
        [fake_response(200, {"access_token": "FRESH-AT", "expires_in": 7200})]
    )
    auth = _auth(sess, state_store=store)
    assert auth.get_access_token() == "FRESH-AT"
    assert len(sess.calls) == 1
    # The new token was persisted back to the store (R-AUTH / R-COST).
    saved = store.get_cached_token()
    assert saved.access_token == "FRESH-AT"


def test_fresh_refresh_persists_to_state_store_when_no_prior_token(fake_session, fake_response, store):
    """A first-ever refresh (no prior cache) still saves the new token to the store."""
    assert store.get_cached_token() is None
    sess = fake_session(
        [fake_response(200, {"access_token": "AT-NEW", "expires_in": 7200})]
    )
    auth = _auth(sess, state_store=store)
    assert auth.get_access_token() == "AT-NEW"
    assert store.get_cached_token().access_token == "AT-NEW"


def test_no_state_store_behaves_as_memory_only_cache(fake_session, fake_response):
    """Without a state_store, behavior is unchanged (in-memory cache only)."""
    sess = fake_session(
        [fake_response(200, {"access_token": "AT-1", "expires_in": 7200})]
    )
    auth = _auth(sess)  # no state_store kwarg -> defaults to None
    assert auth.get_access_token() == "AT-1"
    assert auth.get_access_token() == "AT-1"
    assert len(sess.calls) == 1
