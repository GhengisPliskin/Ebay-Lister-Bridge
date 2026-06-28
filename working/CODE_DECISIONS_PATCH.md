# CODE_DECISIONS_PATCH.md — Provisional Session Decisions

This file is the active scratch space for code decisions during development.
Write all code decisions here during execution sessions.
This file is merged into `CODE_DECISION_LOG.md` at HUMAN gates, then reset.

**Current phase:** Phases 1–5 + integration complete (built sequentially on `main`,
all external services mocked, 71 tests green). Awaiting human verification before
merge to `CODE_DECISION_LOG.md`.

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

## Phases 2–5 + Integration (sequential build on main)

| # | Decision | Rationale | If This Breaks, Check... |
|---|----------|-----------|--------------------------|
| C2-1 | `GeminiProvider` imports the google-genai SDK **lazily** (inside methods) and accepts an injected `client`. | Module imports without the SDK; tests inject a fake client; no network at construction (PI-003 stateless one-shot per call). | `src/ai/provider.py` `_get_client`. |
| C2-2 | Vision output coerced into the contract: JSON parsed (code-fence tolerant), `defects_found` forced present (PI-004), aspects failing the category enum dropped to `dropped_fields` (PI-005). | Models drift/omit; the contract must hold regardless of model phrasing. | `vision_agent._parse_json_block` / `_validate_aspects`. |
| C3-1 | Anchor = **median** of active comps; range = min/max; human-confirmed comp overrides the anchor; floor `(cost+fees)*1.15` overrides a below-floor basis (sets `floor_applied`, PI-006); unknown cost/fees/comp → `missing_inputs` (R-PRICE). | Median resists outlier asks; the layered model matches blueprint v1.1; nothing is guessed. | `src/ai/margin_guard.py` `price_item`. |
| C3-2 | `price_item` stays **pure** (comps injected); `fetch_and_price` wires `ebay_client.search_active_comps`. | Honors the frozen signature; keeps pricing unit-testable; centralizes the Browse call. | `margin_guard.fetch_and_price`. |
| C4-1 | State store is **SQLite stdlib**; `eps_urls` stored as JSON text; single-row token cache; `:memory:` for tests; items keyed on `item_sku` with `ON CONFLICT` upsert (R-STATE). | No new dependency; idempotent writes; tests need no disk. | `src/core/state_store.py`. |
| C4-2 | `drive_fetcher` enhanced via two private helpers (`_list_all_files` pagination, `_collect_images_recursive`); public signatures unchanged; original A-01 comments **kept** with RESOLVED markers (Ground Rule 11). | Enhance not rewrite; downstream image-path hand-off stays stable; comment-preservation standard honored. | `src/core/drive_fetcher.py`. |
| C4b-1 | Orchestrator keeps the four frozen functions; adds **optional** `ebay_client` / `cost_lookup` kwargs for testability; never auto-publishes (PI-007); writes offer/listing IDs immediately after publish (R-STATE). | Optional kwargs don't break the frozen shape and allow fake injection; the human gate lives in the UI. | `src/core/orchestrator.py`. |
| C4b-2 | `listing_description` carries a real eBay description that **discloses defects** (PI-004), not the internal pricing reasoning. | Defects must reach the buyer + the review screen; pricing reasoning is internal only. | `orchestrator._build_description`. |
| C5-1 | UI split: `ui/review.py` (pure, Streamlit-free, tested) + `ui/app.py` (thin Streamlit shell, not imported by tests). | Keeps the suite runnable without Streamlit installed; isolates testable logic. | `src/ui/review.py` vs `app.py`. |
| C5-2 | `validate_for_publish` reuses `EbayClient.validate_offer` (PI-009) but treats local photos as sufficient pre-upload (EPS URLs don't exist until publish). | One validation source of truth; avoids a false "no image" block on the review screen. | `review.validate_for_publish`. |
| CI-1 | One end-to-end `test_integration.py` mocks Drive + Gemini + eBay and asserts the full path + crash-resume dedup + missing-input routing. | Proves the layers compose; guards against regressions across the seams. | `tests/test_integration.py`. |

## Assumptions Register

| # | Status | Assumption | What Breaks If Wrong |
|---|--------|------------|----------------------|
| A1-1 | **Open** | Media `createImageFromFile` returns the EPS URL in the `Location` header (per docs; not yet live-verified). | If eBay returns it in the JSON body instead, `upload_image` returns no URL — adjust the parse + its test. |
| A1-2 | **Open** | `createOffer` returns `{"offerId": ...}` and `publishOffer` returns `{"listingId": ...}` in the JSON body. | If field names/shape differ in the live sandbox, `create_offer`/`publish_offer` raise "no offerId/listingId returned" — adjust parse. |
| A1-3 | **Open** | Sandbox business policies + inventory location are pre-created by the operator (Phase 1 acceptance criterion), referenced by the `.env` IDs. | Missing policy/location IDs → `validate_offer` blocks publish (safe), but live publish can't be verified until created. |
| A1-4 | **Resolved** | ~~`drive_fetcher` still caps at `pageSize=100` with no recursion.~~ Fixed in Phase 4: full `pageToken` pagination + recursive subfolder traversal (`_list_all_files` / `_collect_images_recursive`). | n/a — resolved; see `test_drive_fetcher.py`. |
