# CODE_DECISIONS_PATCH.md — Provisional Session Decisions

This file is the active scratch space for code decisions during development.
Write all code decisions here during execution sessions.
This file is merged into `CODE_DECISION_LOG.md` at HUMAN gates, then reset.

**Current phase:** Phase 1 (contracts freeze + eBay sandbox spike) — code generated;
awaiting human verification before merge to `CODE_DECISION_LOG.md`.

---

## Architecture / Contracts

| # | Decision | Rationale | If This Breaks, Check... |
|---|----------|-----------|--------------------------|
| C1-1 | Frozen data contracts live in a new `src/contracts/` package (`vision.py`, `pricing.py`, `ebay.py`, `state.py`) re-exported from `__init__.py` as a single import surface. | Parallel module agents need one stable place to import from (`from src.contracts import ...`); splitting by domain keeps files readable. | `src/contracts/__init__.py` `__all__` if an import fails. |
| C1-2 | All contract models set `model_config = ConfigDict(extra="forbid")`. | A drifting producer (e.g. Vision Agent emitting an extra/typo'd key) fails loudly at parse time instead of silently dropping data. | `tests/test_contracts.py::test_vision_output_rejects_unknown_keys`. |
| C1-3 | `VisionAgentOutput.defects_found` and `dropped_fields` are structurally required (default empty list, always serialized). | Enforces PI-004 (forced defect confirmation) and PI-005 (drop, don't invent) at the contract level, not just in prompt text. | `vision.py` field defs. |
| C1-4 | eBay payloads modeled in two layers: internal `ListingPayload` (orchestrator-assembled) + exact REST bodies (`InventoryItemRequest`, `CreateOfferRequest`). Mapping between them is explicit static methods on `EbayClient`, never inferred. | Blueprint mandates "explicit mapping, no dynamic inference"; separates our internal shape from eBay's wire shape so an eBay change touches one mapping site. | `EbayClient.to_inventory_item_request` / `to_create_offer_request`. |

## API / eBay (Phase 1 spike)

| # | Decision | Rationale | If This Breaks, Check... |
|---|----------|-----------|--------------------------|
| C1-5 | Host selection is env-driven (`EBAY_ENV`): Inventory+Browse on `api[.sandbox].ebay.com`, Media on `apim[.sandbox].ebay.com`. | Sandbox-first per blueprint; the Media API uses a different gateway host than the Sell/Browse APIs. | `_API_HOSTS` / `_MEDIA_HOSTS` in `ebay_client.py`. |
| C1-6 | Media `createImageFromFile` reads the EPS URL from the **`Location` response header** on a 201 (multipart field name `image`). | Matches the eBay Media API contract; a 201 without `Location` is treated as an error, never a silent empty URL. | `EbayClient.upload_image`; `tests/test_ebay_client.py::test_upload_image_*`. |
| C1-7 | Image pre-check (format ∈ {jpg,jpeg,png,webp,heic}, ≤12 MB) runs **before** every upload (R-IMG). Limit constants live in `src/contracts/ebay.py`. | Fails fast on a bad image instead of late at publish; constants shared so UI/pre-flight can reuse them. | `EbayClient.precheck_image`. |
| C1-8 | `validate_offer()` checks all publishOffer-required fields (PI-009) and `publish_listing` raises before any eBay write if non-empty. | A payload missing a policy/category/price never reaches eBay only to be rejected; mocked test asserts zero network calls on a bad payload. | `EbayClient.validate_offer`; `test_publish_listing_validation_blocks_bad_payload`. |
| C1-9 | OAuth access token cached in-memory with a 120 s pre-expiry skew; refresh uses Basic-auth client creds + `refresh_token` grant. State-store-backed cache deferred to Phase 4 (interface stable now). | R-AUTH: never race the ~2h expiry; in-memory cache is enough for the spike, and `get_access_token()` won't change when the state-store cache is wired in. | `EbayAuth.get_access_token` / `_refresh`. |
| C1-10 | eBay `createOffer` price is sent as a **stringified** `{value, currency}` amount (`f"{price:.2f}"`, USD). | eBay's `pricingSummary.price.value` is a string field; rounding to 2dp avoids float artifacts. | `EbayClient.to_create_offer_request`. |

## AI / Core (stubs — frozen signatures)

| # | Decision | Rationale | If This Breaks, Check... |
|---|----------|-----------|--------------------------|
| C1-11 | `provider.py`, `vision_agent.py`, `margin_guard.py`, `state_store.py`, `orchestrator.py` shipped as signature+docstring stubs raising `NotImplementedError`, typed against `src.contracts`. | Phase 1 freezes interfaces; parallel agents implement bodies in Phases 2–4 without renegotiating signatures. | The respective module's stub docstring (names the implementing phase). |
| C1-12 | `drive_fetcher.py` left functionally intact; recursive-traversal + full-pagination requirement recorded as a `PENDING ENHANCEMENT` block in the module docstring + inline markers (no logic change, no comments removed — Ground Rule 11). | Blueprint says enhance, not rewrite; public signatures are frozen so the downstream image-path hand-off to `vision_agent` stays stable. | `drive_fetcher.py` module docstring; `list_pending_batches`. |

## Tooling / Tests

| # | Decision | Rationale | If This Breaks, Check... |
|---|----------|-----------|--------------------------|
| C1-13 | External services (eBay via `requests`) mocked through an injected `FakeSession`/`FakeResponse` in `tests/conftest.py`; suite runs with NO live credentials. 25 tests pass. | Module agents + CI must run credential-free; injecting the session keeps production code unaware of the test double. | `tests/conftest.py`; `pytest` from repo root. |
| C1-14 | `scripts/ebay_sandbox_spike.py` runs the live flow when creds are present, else prints a `[PENDING]` report and exits 0. ASCII-only console output (Windows cp1252-safe). | One artifact that de-risks live now (gated on creds) and never blocks a credential-less run; emoji/box-drawing chars crash the Windows console. | `scripts/ebay_sandbox_spike.py`. |

## Assumptions Register

| # | Status | Assumption | What Breaks If Wrong |
|---|--------|------------|----------------------|
| A1-1 | **Open** | Media `createImageFromFile` returns the EPS URL in the `Location` header (per docs; not yet live-verified). | If eBay returns it in the JSON body instead, `upload_image` returns no URL — adjust the parse + its test. |
| A1-2 | **Open** | `createOffer` returns `{"offerId": ...}` and `publishOffer` returns `{"listingId": ...}` in the JSON body. | If field names/shape differ in the live sandbox, `create_offer`/`publish_offer` raise "no offerId/listingId returned" — adjust parse. |
| A1-3 | **Open** | Sandbox business policies + inventory location are pre-created by the operator (Phase 1 acceptance criterion), referenced by the `.env` IDs. | Missing policy/location IDs → `validate_offer` blocks publish (safe), but live publish can't be verified until created. |
| A1-4 | Carried (A-01) | `drive_fetcher` still caps at `pageSize=100` with no recursion. | >100 subfolders/images or nested images are dropped until the Phase 2 enhancement lands. |
