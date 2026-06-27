"""
Module: test_ebay_auth.py
Purpose: Mocked tests for ebay_auth.EbayAuth — token refresh, caching, host
         selection — with NO live eBay credentials.
FMEA Constraints Enforced (asserted): R-AUTH.
"""

from __future__ import annotations

import pytest

from src.api.ebay_auth import EbayAuth, EbayAuthError


def _auth(session, **kw):
    """Build an EbayAuth with dummy creds and an injected fake session."""
    defaults = dict(
        env="sandbox",
        client_id="cid",
        client_secret="csecret",
        refresh_token="rtoken",
        scopes="sell.inventory commerce.media buy.browse",
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
    assert call["data"]["scope"] == "sell.inventory commerce.media buy.browse"


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
