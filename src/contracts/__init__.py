"""
Module: contracts/__init__.py
Purpose: Single import surface for the frozen data contracts the parallel module
         agents build against.
Primary Responsibilities:
  - Re-export every pydantic contract so callers can do:
        from src.contracts import VisionAgentOutput, MarginGuardOutput, ...
Key Interfaces:
  - Output: the typed schemas in vision.py, pricing.py, ebay.py, state.py.
FMEA Constraints Enforced:
  - None directly; the re-exported models carry the FMEA constraints.

THESE CONTRACTS ARE FROZEN (Phase 1 deliverable). Parallel module agents depend
on these signatures being stable. Changing a field is a contract change — log it
in working/CODE_DECISIONS_PATCH.md and coordinate before editing.
"""

from src.contracts.adapter import AdapterCapability, DraftOutput
from src.contracts.ebay import (
    EBAY_MAX_IMAGE_BYTES,
    EBAY_MAX_IMAGES_PER_LISTING,
    EBAY_RECOMMENDED_LONG_SIDE_PX,
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
from src.contracts.pricing import ActiveCompRange, MarginGuardOutput
from src.contracts.state import ItemRecord, ItemStatus, TokenCacheRecord
from src.contracts.vision import VisionAgentOutput

__all__ = [
    # vision
    "VisionAgentOutput",
    # pricing
    "MarginGuardOutput",
    "ActiveCompRange",
    # ebay payloads
    "ListingPayload",
    "InventoryItemRequest",
    "EbayAvailability",
    "ShipToLocationAvailability",
    "EbayProduct",
    "CreateOfferRequest",
    "EbayListingPolicies",
    "EbayPricingSummary",
    "EbayAmount",
    "ImageUploadResult",
    "PublishResult",
    # ebay constants
    "EBAY_MAX_IMAGES_PER_LISTING",
    "EBAY_MAX_IMAGE_BYTES",
    "EBAY_RECOMMENDED_LONG_SIDE_PX",
    "EBAY_SUPPORTED_IMAGE_FORMATS",
    # state
    "ItemRecord",
    "ItemStatus",
    "TokenCacheRecord",
    # adapter (v1.2, additive)
    "AdapterCapability",
    "DraftOutput",
]
