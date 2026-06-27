"""
Module: ebay.py
Purpose: Frozen data contracts for the eBay listing/inventory payloads — both the
         internal assembled payload and the REST request/response shapes.
Primary Responsibilities:
  - Define ListingPayload, the internal contract the orchestrator assembles and
    hands to ebay_client (the single source of truth before eBay mapping).
  - Define the typed REST bodies for createInventoryItem and createOffer using
    eBay's exact JSON shapes, so ebay_client maps explicitly (no inference).
  - Define result shapes for the Media upload (EPS URL) and publish (listing ID).
Key Interfaces:
  - Input: VisionAgentOutput + MarginGuardOutput + config (policies, location).
  - Output: ListingPayload -> ebay_client.py -> eBay REST/Media APIs.
FMEA Constraints Enforced:
  - PI-009 — required Offer fields are modeled so pre-submit validation can check
    them before publishOffer.
  - R-IMG — ImageUploadResult carries the EPS URL; pre-upload size/format checks
    live in ebay_client and reference the constants here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# ── eBay Media constraints (blueprint "eBay images") — enforced before upload ──
# Up to 24 free photos/listing (40 rolling out); 12 MB/image; ~1600px long side
# recommended. Supported: JPG, PNG, WEBP, HEIC. ebay_client pre-checks against
# these to mitigate R-IMG.
EBAY_MAX_IMAGES_PER_LISTING = 24
EBAY_MAX_IMAGE_BYTES = 12 * 1024 * 1024
EBAY_RECOMMENDED_LONG_SIDE_PX = 1600
EBAY_SUPPORTED_IMAGE_FORMATS = ("jpg", "jpeg", "png", "webp", "heic")


# ── Internal assembled payload (orchestrator -> ebay_client) ──────────────────


class ListingPayload(BaseModel):
    """
    The internal, pre-eBay listing payload assembled by the orchestrator.

    This is the contract handed to ebay_client.publish_listing(). ebay_client
    maps each field to the eBay REST bodies per the blueprint mapping table —
    explicitly, with no dynamic inference.

    Attributes:
        item_sku: Deterministic SKU (idempotency key), e.g. "LB-{folderId}".
        title: Listing title -> product.title.
        item_specifics: Aspect name -> value -> product.aspects (list-wrapped).
        condition: eBay condition enum string (e.g. "USED_EXCELLENT") -> condition.
        quantity: Available quantity -> availability.shipToLocationAvailability.quantity.
        price: Final price (USD) from Margin-Guard -> pricingSummary.price.value.
        category_id: eBay category -> offer.categoryId.
        local_image_paths: Local photo paths to upload via Media createImageFromFile.
        eps_image_urls: EPS URLs returned by the Media API -> product.imageUrls.
        fulfillment_policy_id: -> listingPolicies.fulfillmentPolicyId.
        payment_policy_id: -> listingPolicies.paymentPolicyId.
        return_policy_id: -> listingPolicies.returnPolicyId.
        merchant_location_key: -> offer.merchantLocationKey.
        marketplace_id: -> offer.marketplaceId (e.g. "EBAY_US").
        listing_description: -> offer.listingDescription.

    FMEA Constraints:
        PI-009 — carries every field required by createOffer so pre-submit
        validation can run before publishOffer.
    """

    model_config = ConfigDict(extra="forbid")

    item_sku: str = Field(description="Deterministic SKU / idempotency key.")
    title: str = Field(description="Listing title.")
    item_specifics: dict[str, str] = Field(default_factory=dict)
    condition: str = Field(default="", description="eBay condition enum string.")
    quantity: int = Field(default=1, ge=1)
    price: float = Field(ge=0, description="Final price (USD).")
    category_id: str = Field(default="", description="eBay category ID.")
    local_image_paths: list[str] = Field(default_factory=list)
    eps_image_urls: list[str] = Field(default_factory=list)
    fulfillment_policy_id: str = Field(default="")
    payment_policy_id: str = Field(default="")
    return_policy_id: str = Field(default="")
    merchant_location_key: str = Field(default="")
    marketplace_id: str = Field(default="EBAY_US")
    listing_description: str = Field(default="")


# ── eBay REST request bodies (exact JSON shapes) ──────────────────────────────


class ShipToLocationAvailability(BaseModel):
    """Quantity wrapper for createInventoryItem availability."""

    model_config = ConfigDict(extra="forbid")

    quantity: int = Field(ge=0)


class EbayAvailability(BaseModel):
    """availability object for the createInventoryItem body."""

    model_config = ConfigDict(extra="forbid")

    shipToLocationAvailability: ShipToLocationAvailability


class EbayProduct(BaseModel):
    """
    product object for createInventoryItem.

    aspects uses eBay's list-wrapped form: {"Brand": ["Sony"]}. imageUrls are
    EPS URLs returned by the Media API.
    """

    model_config = ConfigDict(extra="forbid")

    title: str
    aspects: dict[str, list[str]] = Field(default_factory=dict)
    imageUrls: list[str] = Field(default_factory=list)


class InventoryItemRequest(BaseModel):
    """
    Full body for PUT createInventoryItem (Sell Inventory API).

    Attributes:
        availability: Quantity availability block.
        condition: eBay condition enum string (e.g. "USED_EXCELLENT").
        product: Title, aspects, and EPS imageUrls.

    FMEA Constraints:
        R-IMG — product.imageUrls only ever holds EPS URLs that passed the
        pre-upload checks in ebay_client.
    """

    model_config = ConfigDict(extra="forbid")

    availability: EbayAvailability
    condition: str
    product: EbayProduct


class EbayAmount(BaseModel):
    """A monetary amount in eBay's {value, currency} string form."""

    model_config = ConfigDict(extra="forbid")

    value: str = Field(description="Stringified amount, e.g. '19.99'.")
    currency: str = Field(default="USD")


class EbayPricingSummary(BaseModel):
    """pricingSummary object for createOffer."""

    model_config = ConfigDict(extra="forbid")

    price: EbayAmount


class EbayListingPolicies(BaseModel):
    """listingPolicies object — all three policy IDs referenced by createOffer."""

    model_config = ConfigDict(extra="forbid")

    fulfillmentPolicyId: str
    paymentPolicyId: str
    returnPolicyId: str


class CreateOfferRequest(BaseModel):
    """
    Full body for POST createOffer (Sell Inventory API).

    FMEA Constraints:
        PI-009 — every field here is required for a publishable offer; ebay_client
        validates presence before publishOffer.
    """

    model_config = ConfigDict(extra="forbid")

    sku: str
    marketplaceId: str = Field(default="EBAY_US")
    format: str = Field(default="FIXED_PRICE")
    availableQuantity: int = Field(ge=0)
    categoryId: str
    listingDescription: str = Field(default="")
    listingPolicies: EbayListingPolicies
    pricingSummary: EbayPricingSummary
    merchantLocationKey: str


# ── eBay result shapes ────────────────────────────────────────────────────────


class ImageUploadResult(BaseModel):
    """
    Result of a single Media createImageFromFile upload.

    Attributes:
        eps_url: The EPS URL eBay returns (used in product.imageUrls).
        source_path: The local image path that was uploaded (for traceability).

    FMEA Constraints:
        R-IMG — only produced after the byte/format/dimension pre-checks pass.
    """

    model_config = ConfigDict(extra="forbid")

    eps_url: str
    source_path: str = Field(default="")


class PublishResult(BaseModel):
    """
    Result of the full createInventoryItem -> createOffer -> publishOffer flow.

    Attributes:
        item_sku: The SKU that was published (idempotency key).
        offer_id: eBay offer ID from createOffer.
        listing_id: eBay listing ID from publishOffer (live listing).
        eps_image_urls: The EPS URLs attached to the published listing.
        listing_url: Convenience URL to the live listing, if derivable.
    """

    model_config = ConfigDict(extra="forbid")

    item_sku: str
    offer_id: str = Field(default="")
    listing_id: str = Field(default="")
    eps_image_urls: list[str] = Field(default_factory=list)
    listing_url: str = Field(default="")
