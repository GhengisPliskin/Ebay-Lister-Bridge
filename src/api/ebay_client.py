"""
Module: ebay_client.py
Purpose: eBay integration layer — Browse comps, Media image upload, and the REST
         Sell Inventory publish sequence (createInventoryItem -> createOffer ->
         publishOffer), with pre-submit validation.
Primary Responsibilities:
  - Select sandbox/production API + Media hosts from EBAY_ENV.
  - Pre-check images (bytes/format) before upload (R-IMG), then upload via the
    Media API createImageFromFile and return EPS URLs.
  - Map the internal ListingPayload to the eBay REST bodies explicitly (no
    inference), validate required Offer fields (PI-009), and run the 3-step publish.
  - Query the Browse API for active comparable prices (pricing anchor input).
Key Interfaces:
  - Input: ListingPayload + an EbayAuth (for Bearer tokens).
  - Output: ImageUploadResult / PublishResult / list[float] active comps.
FMEA Constraints Enforced:
  - R-IMG — image size/format pre-checks before createImageFromFile.
  - PI-009 — required Offer fields validated before publishOffer.
  - R-AUTH — every call carries a fresh Bearer token from EbayAuth.

STATUS: implemented (Phase 1 spike). Request/response shapes follow the eBay docs
cited in the blueprint. Runs live against the sandbox when credentials are present;
otherwise exercised by mocked `requests` + fixtures in tests/. Live sandbox
verification is PENDING credentials.
"""

from __future__ import annotations

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from src.api.ebay_auth import EbayAuth
from src.contracts import (
    EBAY_MAX_IMAGE_BYTES,
    EBAY_SUPPORTED_IMAGE_FORMATS,
    CreateOfferRequest,
    EbayAmount,
    EbayAvailability,
    EbayListingPolicies,
    EbayPricingSummary,
    EbayProduct,
    ImageUploadResult,
    InventoryItemRequest,
    ListingPayload,
    PublishResult,
    ShipToLocationAvailability,
)

load_dotenv()

# ── Host selection (blueprint: sandbox-first) ─────────────────────────────────
# The Sell Inventory + Browse APIs share the api[.sandbox].ebay.com host; the
# Media API lives on the apim[.sandbox].ebay.com gateway host.
_API_HOSTS = {
    "sandbox": "https://api.sandbox.ebay.com",
    "production": "https://api.ebay.com",
}
_MEDIA_HOSTS = {
    "sandbox": "https://apim.sandbox.ebay.com",
    "production": "https://apim.ebay.com",
}

_INVENTORY_ITEM_PATH = "/sell/inventory/v1/inventory_item/{sku}"
_OFFER_PATH = "/sell/inventory/v1/offer"
_PUBLISH_OFFER_PATH = "/sell/inventory/v1/offer/{offer_id}/publish/"
_BROWSE_SEARCH_PATH = "/buy/browse/v1/item_summary/search"
_MEDIA_CREATE_IMAGE_PATH = "/commerce/media/v1_beta/image/create_image_from_file"

# eBay requires Content-Language on Inventory writes; US English for EBAY_US.
_CONTENT_LANGUAGE = "en-US"
_DEFAULT_TIMEOUT = 60


class EbayClientError(Exception):
    """
    Raised on a failed eBay API call or a payload that fails pre-submit validation.

    Attributes:
        status_code: HTTP status, or None for validation/transport errors.
        body: Response body text (truncated) for diagnostics.

    FMEA Constraints:
        PI-009 / R-IMG — carries enough context to surface a clear, actionable
        error rather than a raw traceback.
    """

    def __init__(self, message: str, status_code: int | None = None, body: str = "") -> None:
        """Construct an EbayClientError with optional HTTP context."""
        self.status_code = status_code
        self.body = body
        super().__init__(message)


class EbayClient:
    """
    Thin, typed client over the eBay Browse, Media, and Sell Inventory APIs.

    All authorization flows through the injected EbayAuth, so a token refresh is
    transparent to callers (R-AUTH). Request/response shapes match the eBay docs
    referenced in the blueprint.
    """

    def __init__(
        self,
        auth: EbayAuth | None = None,
        env: str | None = None,
        *,
        marketplace_id: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        """
        Configure the client.

        Args:
            auth: An EbayAuth instance; constructed from env if omitted.
            env: "sandbox"/"production"; defaults to EBAY_ENV (then "sandbox").
            marketplace_id: e.g. "EBAY_US"; defaults to EBAY_MARKETPLACE_ID.
            session: Optional injected requests.Session (tests pass a mock).

        Returns:
            None

        Side Effects:
            Reads eBay env vars. No network call at construction.
        """
        self.env = (env or os.environ.get("EBAY_ENV") or "sandbox").lower()
        if self.env not in _API_HOSTS:
            raise EbayClientError(f"Unknown EBAY_ENV '{self.env}' (expected sandbox|production)")
        self.auth = auth or EbayAuth(env=self.env, session=session)
        self.marketplace_id = (
            marketplace_id or os.environ.get("EBAY_MARKETPLACE_ID") or "EBAY_US"
        )
        self._session = session or requests.Session()

    # ── Hosts / headers ───────────────────────────────────────────────────────

    @property
    def api_host(self) -> str:
        """Return the Sell Inventory + Browse API host for the selected env."""
        return _API_HOSTS[self.env]

    @property
    def media_host(self) -> str:
        """Return the Media API gateway host for the selected env."""
        return _MEDIA_HOSTS[self.env]

    def _auth_header(self) -> dict[str, str]:
        """Return the Bearer Authorization header with a fresh token (R-AUTH)."""
        return {"Authorization": f"Bearer {self.auth.get_access_token()}"}

    # ── Media API — image upload (R-IMG) ──────────────────────────────────────

    @staticmethod
    def precheck_image(path: str) -> None:
        """
        Validate an image against eBay's size/format limits before upload (R-IMG).

        Args:
            path: Local path to the image file.

        Returns:
            None (returns normally when the image passes).

        Side Effects:
            Reads the file's size and extension from disk.

        Raises:
            EbayClientError: File missing, unsupported format, or over 12 MB.

        FMEA Constraints:
            R-IMG — rejects oversize/unsupported images before createImageFromFile
            so a publish never fails late on a bad image.
        """
        p = Path(path)
        if not p.is_file():
            raise EbayClientError(f"Image not found: {path}")
        ext = p.suffix.lower().lstrip(".")
        if ext not in EBAY_SUPPORTED_IMAGE_FORMATS:
            raise EbayClientError(
                f"Unsupported image format '.{ext}' for {path}; "
                f"allowed: {', '.join(EBAY_SUPPORTED_IMAGE_FORMATS)}"
            )
        size = p.stat().st_size
        if size > EBAY_MAX_IMAGE_BYTES:
            raise EbayClientError(
                f"Image {path} is {size} bytes; exceeds eBay limit of "
                f"{EBAY_MAX_IMAGE_BYTES} bytes (12 MB)"
            )

    def upload_image(self, path: str) -> ImageUploadResult:
        """
        Upload one image via Media createImageFromFile and return its EPS URL.

        The image bytes are sent as multipart/form-data (field name "image").
        On success eBay returns 201 Created with the EPS image URL in the
        `Location` response header.

        Args:
            path: Local image path (already downloaded from Drive).

        Returns:
            ImageUploadResult with the EPS URL and source path.

        Side Effects:
            Runs precheck_image, then one HTTPS POST to the Media API.

        Raises:
            EbayClientError: On a failed pre-check or a non-2xx response, or if
                no Location header is returned.

        FMEA Constraints:
            R-IMG — precheck_image runs first; only EPS URLs from a 201 are returned.
        """
        self.precheck_image(path)
        url = self.media_host + _MEDIA_CREATE_IMAGE_PATH
        headers = self._auth_header()
        with open(path, "rb") as fh:
            # The multipart field MUST be named "image" per the Media API spec.
            files = {"image": (Path(path).name, fh)}
            try:
                resp = self._session.post(
                    url, headers=headers, files=files, timeout=_DEFAULT_TIMEOUT
                )
            except requests.RequestException as exc:
                raise EbayClientError(f"Media upload request failed: {exc}") from exc

        if resp.status_code not in (200, 201):
            raise EbayClientError(
                f"createImageFromFile returned {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text[:500],
            )
        # The EPS URL is returned in the Location header.
        eps_url = resp.headers.get("Location") or resp.headers.get("location")
        if not eps_url:
            raise EbayClientError(
                "createImageFromFile succeeded but no Location header was returned",
                status_code=resp.status_code,
            )
        return ImageUploadResult(eps_url=eps_url, source_path=path)

    def upload_images(self, paths: list[str]) -> list[ImageUploadResult]:
        """
        Upload several images, preserving order.

        Args:
            paths: Local image paths to upload.

        Returns:
            ImageUploadResults in the same order as `paths`.

        Side Effects:
            One Media API call per image.

        Raises:
            EbayClientError: Propagated from upload_image on the first failure.
        """
        return [self.upload_image(p) for p in paths]

    # ── Browse API — active comps (pricing anchor) ────────────────────────────

    def search_active_comps(
        self, query: str, *, limit: int = 20, extra_filter: str | None = None
    ) -> list[float]:
        """
        Return active comparable asking prices from the Browse API.

        Args:
            query: Free-text search (e.g. brand + model + key aspects).
            limit: Max item summaries to request.
            extra_filter: Optional eBay `filter` expression (e.g. condition/price).

        Returns:
            A list of active asking prices (USD floats). Empty if none found.

        Side Effects:
            One HTTPS GET to the Browse API.

        Raises:
            EbayClientError: On a non-2xx response.

        FMEA Constraints:
            R-PRICE — supplies the active-comp anchor; margin_guard turns these
            into active_comp_anchor + active_comp_range.
        """
        url = self.api_host + _BROWSE_SEARCH_PATH
        headers = {
            **self._auth_header(),
            "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
        }
        params: dict[str, str] = {"q": query, "limit": str(limit)}
        if extra_filter:
            params["filter"] = extra_filter
        try:
            resp = self._session.get(
                url, headers=headers, params=params, timeout=_DEFAULT_TIMEOUT
            )
        except requests.RequestException as exc:
            raise EbayClientError(f"Browse search request failed: {exc}") from exc

        if resp.status_code != 200:
            raise EbayClientError(
                f"Browse item_summary/search returned {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text[:500],
            )
        data = resp.json()
        prices: list[float] = []
        for summary in data.get("itemSummaries", []):
            price = summary.get("price", {})
            value = price.get("value")
            if value is not None:
                prices.append(float(value))
        return prices

    # ── Payload mapping (explicit; blueprint mapping table) ───────────────────

    @staticmethod
    def to_inventory_item_request(payload: ListingPayload) -> InventoryItemRequest:
        """
        Map a ListingPayload to the createInventoryItem body (explicit mapping).

        Args:
            payload: The assembled internal listing payload.

        Returns:
            InventoryItemRequest with quantity, condition, title, list-wrapped
            aspects, and EPS imageUrls.

        Side Effects:
            None.

        FMEA Constraints:
            R-IMG — imageUrls is sourced only from payload.eps_image_urls.
        """
        # eBay aspects are list-wrapped: {"Brand": ["Sony"]}.
        aspects = {k: [v] for k, v in payload.item_specifics.items()}
        return InventoryItemRequest(
            availability=EbayAvailability(
                shipToLocationAvailability=ShipToLocationAvailability(
                    quantity=payload.quantity
                )
            ),
            condition=payload.condition,
            product=EbayProduct(
                title=payload.title,
                aspects=aspects,
                imageUrls=payload.eps_image_urls,
            ),
        )

    @staticmethod
    def to_create_offer_request(payload: ListingPayload) -> CreateOfferRequest:
        """
        Map a ListingPayload to the createOffer body (explicit mapping).

        Args:
            payload: The assembled internal listing payload.

        Returns:
            CreateOfferRequest with price, category, policies, and location.

        Side Effects:
            None.
        """
        return CreateOfferRequest(
            sku=payload.item_sku,
            marketplaceId=payload.marketplace_id,
            availableQuantity=payload.quantity,
            categoryId=payload.category_id,
            listingDescription=payload.listing_description,
            listingPolicies=EbayListingPolicies(
                fulfillmentPolicyId=payload.fulfillment_policy_id,
                paymentPolicyId=payload.payment_policy_id,
                returnPolicyId=payload.return_policy_id,
            ),
            # eBay expects price as a string value.
            pricingSummary=EbayPricingSummary(
                price=EbayAmount(value=f"{payload.price:.2f}", currency="USD")
            ),
            merchantLocationKey=payload.merchant_location_key,
        )

    @staticmethod
    def validate_offer(payload: ListingPayload) -> list[str]:
        """
        Return a list of missing/invalid required Offer fields (PI-009).

        Args:
            payload: The assembled listing payload to validate.

        Returns:
            A list of human-readable problems; empty means the payload is
            publishable. The caller (publish_listing) raises if non-empty.

        Side Effects:
            None.

        FMEA Constraints:
            PI-009 — checks every field publishOffer requires so a payload is
            never sent to eBay only to be rejected late.
        """
        problems: list[str] = []
        if not payload.item_sku:
            problems.append("item_sku is required")
        if not payload.category_id:
            problems.append("category_id is required")
        if payload.price <= 0:
            problems.append("price must be > 0")
        if not payload.eps_image_urls:
            problems.append("at least one EPS image URL is required")
        if not payload.fulfillment_policy_id:
            problems.append("fulfillment_policy_id is required")
        if not payload.payment_policy_id:
            problems.append("payment_policy_id is required")
        if not payload.return_policy_id:
            problems.append("return_policy_id is required")
        if not payload.merchant_location_key:
            problems.append("merchant_location_key is required")
        return problems

    # ── Sell Inventory — the 3-step publish ───────────────────────────────────

    def create_inventory_item(self, payload: ListingPayload) -> None:
        """
        PUT createInventoryItem for the payload's SKU.

        Args:
            payload: The listing payload (its item_sku is the path key).

        Returns:
            None (eBay returns 200/204 with no useful body).

        Side Effects:
            One HTTPS PUT to the Sell Inventory API (Content-Language: en-US).

        Raises:
            EbayClientError: On a non-2xx response.
        """
        url = self.api_host + _INVENTORY_ITEM_PATH.format(sku=payload.item_sku)
        headers = {
            **self._auth_header(),
            "Content-Type": "application/json",
            "Content-Language": _CONTENT_LANGUAGE,
            "Accept": "application/json",
        }
        body = self.to_inventory_item_request(payload).model_dump()
        try:
            resp = self._session.put(
                url, headers=headers, json=body, timeout=_DEFAULT_TIMEOUT
            )
        except requests.RequestException as exc:
            raise EbayClientError(f"createInventoryItem request failed: {exc}") from exc
        if resp.status_code not in (200, 201, 204):
            raise EbayClientError(
                f"createInventoryItem returned {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text[:500],
            )

    def create_offer(self, payload: ListingPayload) -> str:
        """
        POST createOffer and return the new offerId.

        Args:
            payload: The listing payload.

        Returns:
            The offerId string from eBay.

        Side Effects:
            One HTTPS POST to the Sell Inventory API (Content-Language: en-US).

        Raises:
            EbayClientError: On a non-2xx response or a body missing offerId.
        """
        url = self.api_host + _OFFER_PATH
        headers = {
            **self._auth_header(),
            "Content-Type": "application/json",
            "Content-Language": _CONTENT_LANGUAGE,
            "Accept": "application/json",
        }
        body = self.to_create_offer_request(payload).model_dump()
        try:
            resp = self._session.post(
                url, headers=headers, json=body, timeout=_DEFAULT_TIMEOUT
            )
        except requests.RequestException as exc:
            raise EbayClientError(f"createOffer request failed: {exc}") from exc
        if resp.status_code not in (200, 201):
            raise EbayClientError(
                f"createOffer returned {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text[:500],
            )
        offer_id = resp.json().get("offerId")
        if not offer_id:
            raise EbayClientError(
                "createOffer succeeded but no offerId was returned",
                status_code=resp.status_code,
                body=resp.text[:500],
            )
        return offer_id

    def publish_offer(self, offer_id: str) -> str:
        """
        POST publishOffer and return the live listingId.

        Args:
            offer_id: The offerId returned by create_offer.

        Returns:
            The listingId string for the live listing.

        Side Effects:
            One HTTPS POST to the Sell Inventory API.

        Raises:
            EbayClientError: On a non-2xx response or a body missing listingId.
        """
        url = self.api_host + _PUBLISH_OFFER_PATH.format(offer_id=offer_id)
        headers = {
            **self._auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            resp = self._session.post(url, headers=headers, timeout=_DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            raise EbayClientError(f"publishOffer request failed: {exc}") from exc
        if resp.status_code not in (200, 201):
            raise EbayClientError(
                f"publishOffer returned {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text[:500],
            )
        listing_id = resp.json().get("listingId")
        if not listing_id:
            raise EbayClientError(
                "publishOffer succeeded but no listingId was returned",
                status_code=resp.status_code,
                body=resp.text[:500],
            )
        return listing_id

    def publish_listing(self, payload: ListingPayload) -> PublishResult:
        """
        Run the full publish flow for one approved payload.

        Sequence: pre-submit validation (PI-009) -> upload any not-yet-uploaded
        images (R-IMG) -> createInventoryItem -> createOffer -> publishOffer.

        Args:
            payload: The operator-approved ListingPayload. If eps_image_urls is
                empty, local_image_paths are uploaded first.

        Returns:
            PublishResult with offer_id, listing_id, and EPS URLs.

        Side Effects:
            Media upload(s) + three Sell Inventory calls against eBay.

        Raises:
            EbayClientError: On validation failure or any failed eBay call.

        FMEA Constraints:
            PI-007 — only called after explicit human approval (orchestrator).
            PI-009 — validate_offer must pass before any eBay write.
            R-IMG — images pre-checked and uploaded before the inventory item.
        """
        # Upload images first so the EPS URLs exist before offer validation.
        if not payload.eps_image_urls and payload.local_image_paths:
            results = self.upload_images(payload.local_image_paths)
            payload = payload.model_copy(
                update={"eps_image_urls": [r.eps_url for r in results]}
            )

        problems = self.validate_offer(payload)
        if problems:
            raise EbayClientError(
                "Offer payload failed pre-submit validation (PI-009): "
                + "; ".join(problems)
            )

        self.create_inventory_item(payload)
        offer_id = self.create_offer(payload)
        listing_id = self.publish_offer(offer_id)
        return PublishResult(
            item_sku=payload.item_sku,
            offer_id=offer_id,
            listing_id=listing_id,
            eps_image_urls=payload.eps_image_urls,
        )
