"""
Module: test_ebay_client.py
Purpose: Mocked tests for ebay_client.EbayClient — Media upload, the 3-step REST
         publish, Browse comps, image pre-checks, and offer validation — with NO
         live eBay credentials. Validates request SHAPE against the eBay docs.
FMEA Constraints Enforced (asserted): R-IMG, PI-009, R-PRICE, R-AUTH.
"""

from __future__ import annotations

import pytest

from src.api.ebay_auth import EbayAuth
from src.api.ebay_client import EbayClient, EbayClientError
from src.contracts import ListingPayload


def _client(session):
    """Build an EbayClient whose auth returns a static token (no token network)."""
    auth = EbayAuth(
        env="sandbox", client_id="c", client_secret="s", refresh_token="r",
        session=session,
    )
    # Pre-seed the token cache so client calls don't try to refresh.
    from src.contracts import TokenCacheRecord
    import time

    auth._cached = TokenCacheRecord(
        access_token="AT-TEST", expires_at_epoch=time.time() + 7200, scopes=""
    )
    return EbayClient(auth=auth, env="sandbox", session=session)


def _full_payload(**overrides) -> ListingPayload:
    """A fully-populated, publishable payload."""
    data = dict(
        item_sku="LB-folder123",
        title="Sony WH-1000XM4 Headphones",
        item_specifics={"Brand": "Sony", "Model": "WH-1000XM4"},
        condition="USED_EXCELLENT",
        quantity=1,
        price=199.99,
        category_id="112529",
        eps_image_urls=["https://i.ebayimg.com/images/g/abc/s-l1600.jpg"],
        fulfillment_policy_id="FP-1",
        payment_policy_id="PP-1",
        return_policy_id="RP-1",
        merchant_location_key="LOC-1",
        marketplace_id="EBAY_US",
    )
    data.update(overrides)
    return ListingPayload(**data)


# ── Host selection ────────────────────────────────────────────────────────────


def test_host_selection_sandbox(fake_session):
    """API + Media hosts resolve to the sandbox gateways."""
    c = _client(fake_session([]))
    assert c.api_host == "https://api.sandbox.ebay.com"
    assert c.media_host == "https://apim.sandbox.ebay.com"


# ── Media upload (R-IMG) ──────────────────────────────────────────────────────


def test_precheck_rejects_unsupported_format(tmp_path):
    """precheck_image rejects an unsupported extension (R-IMG)."""
    bad = tmp_path / "doc.txt"
    bad.write_text("nope")
    with pytest.raises(EbayClientError):
        EbayClient.precheck_image(str(bad))


def test_precheck_rejects_missing_file():
    """precheck_image rejects a missing path (R-IMG)."""
    with pytest.raises(EbayClientError):
        EbayClient.precheck_image("/no/such/photo.jpg")


def test_upload_image_returns_eps_url_from_location_header(fake_session, fake_response, tmp_jpg):
    """createImageFromFile returns the EPS URL from the Location header (R-IMG)."""
    eps = "https://i.ebayimg.com/images/g/xyz/s-l1600.jpg"
    sess = fake_session([fake_response(201, {}, headers={"Location": eps})])
    c = _client(sess)
    result = c.upload_image(tmp_jpg)
    assert result.eps_url == eps
    call = sess.calls[0]
    # Hits the Media gateway endpoint with a multipart "image" field + Bearer token.
    assert call["url"].endswith("/commerce/media/v1_beta/image/create_image_from_file")
    assert "image" in call["files"]
    assert call["headers"]["Authorization"] == "Bearer AT-TEST"


def test_upload_image_missing_location_raises(fake_session, fake_response, tmp_jpg):
    """A 201 without a Location header is an error, not a silent empty URL."""
    sess = fake_session([fake_response(201, {}, headers={})])
    c = _client(sess)
    with pytest.raises(EbayClientError):
        c.upload_image(tmp_jpg)


# ── Browse comps (R-PRICE) ────────────────────────────────────────────────────


def test_search_active_comps_extracts_prices(fake_session, fake_response):
    """Browse search returns the list of active asking prices (R-PRICE)."""
    body = {
        "itemSummaries": [
            {"price": {"value": "189.99", "currency": "USD"}},
            {"price": {"value": "205.00", "currency": "USD"}},
            {"title": "no price item"},
        ]
    }
    sess = fake_session([fake_response(200, body)])
    c = _client(sess)
    prices = c.search_active_comps("Sony WH-1000XM4", limit=10)
    assert prices == [189.99, 205.00]
    call = sess.calls[0]
    assert call["headers"]["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_US"
    assert call["params"]["q"] == "Sony WH-1000XM4"


# ── Mapping (explicit, blueprint table) ───────────────────────────────────────


def test_inventory_item_mapping_list_wraps_aspects():
    """Aspects map to eBay's list-wrapped form; imageUrls come from EPS URLs."""
    payload = _full_payload()
    body = EbayClient.to_inventory_item_request(payload).model_dump()
    assert body["product"]["aspects"] == {"Brand": ["Sony"], "Model": ["WH-1000XM4"]}
    assert body["product"]["imageUrls"] == payload.eps_image_urls
    assert body["availability"]["shipToLocationAvailability"]["quantity"] == 1
    assert body["condition"] == "USED_EXCELLENT"


def test_offer_mapping_price_is_stringified():
    """createOffer price maps to a stringified {value, currency} amount."""
    payload = _full_payload(price=199.9)
    body = EbayClient.to_create_offer_request(payload).model_dump()
    assert body["pricingSummary"]["price"] == {"value": "199.90", "currency": "USD"}
    assert body["listingPolicies"]["fulfillmentPolicyId"] == "FP-1"
    assert body["merchantLocationKey"] == "LOC-1"


# ── Offer validation (PI-009) ─────────────────────────────────────────────────


def test_validate_offer_flags_missing_required_fields():
    """validate_offer reports every missing required Offer field (PI-009)."""
    incomplete = ListingPayload(item_sku="LB-1", title="x", price=0)
    problems = EbayClient.validate_offer(incomplete)
    assert any("price" in p for p in problems)
    assert any("category_id" in p for p in problems)
    assert any("EPS image URL" in p for p in problems)
    assert any("fulfillment_policy_id" in p for p in problems)


def test_validate_offer_passes_full_payload():
    """A fully-populated payload passes validation (no problems)."""
    assert EbayClient.validate_offer(_full_payload()) == []


# ── Full publish sequence ─────────────────────────────────────────────────────


def test_publish_listing_runs_three_step_sequence(fake_session, fake_response):
    """publish_listing runs createInventoryItem -> createOffer -> publishOffer."""
    sess = fake_session(
        [
            fake_response(204, {}),                      # createInventoryItem (PUT)
            fake_response(201, {"offerId": "OFFER-9"}),  # createOffer (POST)
            fake_response(200, {"listingId": "LIST-42"}),  # publishOffer (POST)
        ]
    )
    c = _client(sess)
    result = c.publish_listing(_full_payload())
    assert result.offer_id == "OFFER-9"
    assert result.listing_id == "LIST-42"
    # Verify the three calls hit the right verbs/endpoints in order.
    methods = [(x["method"], x["url"]) for x in sess.calls]
    assert methods[0][0] == "PUT" and methods[0][1].endswith("/inventory_item/LB-folder123")
    assert methods[1][0] == "POST" and methods[1][1].endswith("/offer")
    assert methods[2][0] == "POST" and methods[2][1].endswith("/offer/OFFER-9/publish/")
    # Inventory write carried Content-Language (eBay requirement).
    assert sess.calls[0]["headers"]["Content-Language"] == "en-US"


def test_publish_listing_validation_blocks_bad_payload(fake_session):
    """A payload missing required fields never reaches eBay (PI-009)."""
    sess = fake_session([])
    c = _client(sess)
    bad = _full_payload(category_id="")
    with pytest.raises(EbayClientError):
        c.publish_listing(bad)
    assert sess.calls == []  # nothing was sent
