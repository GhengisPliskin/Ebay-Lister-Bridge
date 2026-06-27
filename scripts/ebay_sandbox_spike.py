"""
Module: ebay_sandbox_spike.py
Purpose: Phase 1 de-risk runner — exercises the eBay flow end-to-end against the
         SANDBOX (OAuth refresh -> Media upload -> createInventoryItem ->
         createOffer -> publishOffer) using the real ebay_auth / ebay_client code.
Primary Responsibilities:
  - If sandbox credentials are present, run the full flow live and print results.
  - If credentials are absent, print a clear PENDING report and exit 0 (so CI /
    a credential-less developer can still run it without failing).
Key Interfaces:
  - Input: eBay env vars (.env) + an image path (arg or EBAY_SPIKE_IMAGE).
  - Output: human-readable progress + a final offer/listing summary to stdout.
FMEA Constraints Enforced:
  - R-AUTH, R-IMG, PI-009 — exercised via the production code paths.

Run:  python -m scripts.ebay_sandbox_spike [path/to/photo.jpg]
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from src.api.ebay_auth import EbayAuth, EbayAuthError
from src.api.ebay_client import EbayClient, EbayClientError
from src.contracts import ListingPayload

load_dotenv()

# Env vars that MUST be populated for a live sandbox run.
_REQUIRED = [
    "EBAY_CLIENT_ID",
    "EBAY_CLIENT_SECRET",
    "EBAY_OAUTH_REFRESH_TOKEN",
    "EBAY_FULFILLMENT_POLICY_ID",
    "EBAY_PAYMENT_POLICY_ID",
    "EBAY_RETURN_POLICY_ID",
    "EBAY_INVENTORY_LOCATION_KEY",
]


def _missing_credentials() -> list[str]:
    """Return the list of required env vars that are empty/unset."""
    return [k for k in _REQUIRED if not os.environ.get(k)]


def _build_demo_payload(image_path: str) -> ListingPayload:
    """
    Build a hardcoded demo payload for the spike (blueprint Phase 1 criterion).

    Args:
        image_path: Local path to the image to upload.

    Returns:
        A ListingPayload wired from env policy/location IDs + a demo item.
    """
    return ListingPayload(
        item_sku="LB-SPIKE-001",
        title="Lister-Bridge Sandbox Spike Test Item",
        item_specifics={"Brand": "Unbranded", "Type": "Test"},
        condition="USED_EXCELLENT",
        quantity=1,
        price=19.99,
        category_id=os.environ.get("EBAY_SPIKE_CATEGORY_ID", "171485"),
        local_image_paths=[image_path],
        fulfillment_policy_id=os.environ.get("EBAY_FULFILLMENT_POLICY_ID", ""),
        payment_policy_id=os.environ.get("EBAY_PAYMENT_POLICY_ID", ""),
        return_policy_id=os.environ.get("EBAY_RETURN_POLICY_ID", ""),
        merchant_location_key=os.environ.get("EBAY_INVENTORY_LOCATION_KEY", ""),
        marketplace_id=os.environ.get("EBAY_MARKETPLACE_ID", "EBAY_US"),
        listing_description="Sandbox spike — not a real listing.",
    )


def main(argv: list[str]) -> int:
    """
    Run the sandbox spike, or report PENDING when credentials are absent.

    Args:
        argv: CLI args; argv[0] (optional) is the image path.

    Returns:
        Process exit code (0 on success or clean PENDING; 1 on a live failure).
    """
    print("-- eBay sandbox spike ---------------------------------------------")
    print(f"EBAY_ENV = {os.environ.get('EBAY_ENV', 'sandbox')}")

    missing = _missing_credentials()
    if missing:
        print("\n[PENDING] Live sandbox verification is NOT possible yet.")
        print("Missing/empty required env vars:")
        for k in missing:
            print(f"  - {k}")
        print(
            "\nThe request/response SHAPES are validated by the mocked suite "
            "(tests/test_ebay_auth.py, tests/test_ebay_client.py). Populate the "
            "vars above in .env and re-run this script to verify live.\n"
        )
        return 0

    image_path = argv[0] if argv else os.environ.get("EBAY_SPIKE_IMAGE", "")
    if not image_path:
        print("[ERROR] Provide an image path (arg) or set EBAY_SPIKE_IMAGE.")
        return 1

    try:
        auth = EbayAuth()
        client = EbayClient(auth=auth)

        print("\n[1/4] Refreshing OAuth user access token...")
        token = auth.get_access_token()
        print(f"      OK - token acquired (len={len(token)}).")

        print("[2/4] Uploading image via Media createImageFromFile...")
        payload = _build_demo_payload(image_path)
        uploads = client.upload_images(payload.local_image_paths)
        payload = payload.model_copy(
            update={"eps_image_urls": [u.eps_url for u in uploads]}
        )
        for u in uploads:
            print(f"      OK - EPS URL: {u.eps_url}")

        print("[3/4] Validating + creating inventory item / offer...")
        result = client.publish_listing(payload)

        print("[4/4] Publish complete.")
        print("\n-- RESULT ---------------------------------------------------------")
        print(f"  SKU        : {result.item_sku}")
        print(f"  offerId    : {result.offer_id}")
        print(f"  listingId  : {result.listing_id}")
        print(f"  EPS URLs   : {result.eps_image_urls}")
        return 0

    except (EbayAuthError, EbayClientError) as exc:
        print(f"\n[FAILED] {type(exc).__name__}: {exc}")
        status = getattr(exc, "status_code", None)
        body = getattr(exc, "body", "")
        if status is not None:
            print(f"  HTTP {status}: {body}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
