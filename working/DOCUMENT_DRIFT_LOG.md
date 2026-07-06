# DOCUMENT_DRIFT_LOG.md — Stale-Fact Registry

Log stale facts here when any session changes a project-level fact.
Processed during Housekeeping sessions, then cleared.

**Format:**

```
## Drift Entry — [Date]
**Changed fact:** [Old value] → [New value]
**Triggering session:** Issue #[X] — [Task name]
**Stale documents:** [List of files that still reference the old value]
**Action required:** [Patch description for Housekeeping session]
```

---

## Drift Entry — 2026-06-27
**Changed fact:** eBay integration is GraphQL `startListingPreviewsCreation` → **REST Sell Inventory** (`createInventoryItem` → `createOffer` → `publishOffer`) + Media API image upload (blueprint v1.1 amends C-002, drops the GraphQL preview path).
**Triggering session:** Phase 1 — contracts freeze + eBay sandbox spike.
**Stale documents:**
- `ARCHITECTURE.md` — narrative/diagrams still describe a GraphQL post path; the `ebay_graphql.py` filename was replaced in the structure + component tables this session, but prose elsewhere (e.g. data-flow diagram around line 16–34) may still reference GraphQL.
- `CONSTRAINTS.md` — verify C-002 text reflects the REST amendment.
- `KEY_DECISION_LOG.md` — DECISION 4 (CLI) is superseded by Streamlit; the GraphQL assumption may persist.
- `docs/Ebay lister bridge master plan.md` — check for GraphQL/CLI/sold-comp references.
**Action required:** Reconcile these documents with `PDR_Product_Deployment_Blueprint.md` v1.1 (REST publish, Media upload, Streamlit UI, active-comp pricing, `ebay_auth.py`/`state_store.py`/`provider.py` additions).
**Processed 2026-07-03 (pending human commit):** Patched `ARCHITECTURE.md` (data-flow diagram, directory tree, component table, intelligence-roster tier notes), `CONSTRAINTS.md` (C-002 reworded, marked "amended per blueprint v1.1"), `KEY_DECISION_LOG.md` (DECISION 4 superseded-by annotation added), `README.md` (intro, architecture overview, directory tree), and `docs/Ebay lister bridge master plan.md` (§1, §2.1, §3, §4 reworded with inline "Amended per blueprint v1.1" notes; §10 DECISION 4 and the §6 Task Registry left intact as historical record). `docs/FMEA.md` PI-009 wording also patched (see the FMEA-specific entry below).

## Drift Entry — 2026-06-27
**Changed fact:** UI is **interactive CLI** → **Streamlit** (DECISION 4 superseded; CLI retained as headless mode). Pipeline entry point is `python -m src.core.orchestrator`, not a CLI loop in `orchestrator.py`.
**Triggering session:** Phase 1 — contracts freeze + eBay sandbox spike.
**Stale documents:**
- `ARCHITECTURE.md` — "Interactive CLI (human-in-the-loop)" labels and "managing the CLI loop" descriptions.
- `KEY_DECISION_LOG.md` — DECISION 4 disposition.
**Action required:** Mark DECISION 4 superseded; describe Streamlit review/approve as the default front end with a headless mode.
**Processed 2026-07-03 (pending human commit):** `ARCHITECTURE.md` data-flow diagram now reads "UI — src/ui/app.py ← Streamlit review/approve (human-in-the-loop, PI-007)"; component table adds a UI row (`app.py`, `review.py`, `desktop_app.py`). `KEY_DECISION_LOG.md` DECISION 4 now carries a dated **Superseded (2026-07-03)** note pointing at the Streamlit UI + desktop `.exe` packaging, without deleting/rewriting the original decision text. Also found and patched the same CLI/interactive-terminal wording in `CONSTRAINTS.md` NFR-001 and `docs/Ebay lister bridge master plan.md` §2.2/§3.1/§3.2/§4.1 (not individually listed above but covered by this same UI fact change).

## Drift Entry — 2026-06-27
**Changed fact:** `drive_fetcher` pagination cap (assumption A-01) — `pageSize=100`, no recursion → **required** recursive subfolder traversal + full `pageToken` pagination (not yet implemented; requirement noted in code).
**Triggering session:** Phase 1 — contracts freeze + eBay sandbox spike.
**Stale documents:**
- `docs/Ebay lister bridge master plan.md` / `docs/FMEA.md` — confirm A-01 / PI-001 notes reflect the pending enhancement.
**Action required:** Track the Drive enhancement as its own Phase 2 issue; the code already carries a `PENDING ENHANCEMENT` block.
**Processed 2026-07-03 (pending human commit):** Verified — `working/CODE_DECISIONS_PATCH.md` A1-4 already records this as **Resolved** (Phase 4: `_list_all_files` / `_collect_images_recursive`), and `src/core/drive_fetcher.py` reflects the completed enhancement. `docs/Ebay lister bridge master plan.md` and `docs/FMEA.md` carry no A-01/PI-001 text needing a patch beyond what's noted here — no code changes made (out of scope for this Housekeeping pass).

## Drift Entry — 2026-07-03
**Changed fact:** `EBAY_OAUTH_SCOPES` short-form value (`sell.inventory commerce.media buy.browse`) → full-URL scopes (`https://api.ebay.com/oauth/api_scope https://api.ebay.com/oauth/api_scope/sell.inventory https://api.ebay.com/oauth/api_scope/commerce.media`), now enforced by a `ValueError` in `EbayAuth.__init__`.
**Triggering session:** Phase 6 hardening — three-bug fix session (OAuth scope format, token-cache wiring, UI description/condition edits).
**Stale documents:**
- `PDR_Product_Deployment_Blueprint.md` line ~360 — the "Config and secrets" code block still lists `EBAY_OAUTH_SCOPES=sell.inventory commerce.media buy.browse`.
- `working/ISSUE_QUEUE.md` — the three matching queued issues ("eBay OAuth scopes in wrong format", "Token cache dead code", "Operator description edits silently discarded; condition field unvalidated") are now resolved by this session; see disposition note added at the top of that file.
**Action required:** Patch the blueprint's config code block to the full-URL form during the next Housekeeping session; confirm the three `ISSUE_QUEUE.md` entries are closed (or converted to closed GitHub Issues) rather than re-queued.
**Processed 2026-07-03 (pending human commit):** `PDR_Product_Deployment_Blueprint.md` line ~360 now shows the full-URL scopes matching `.env.example`. `working/ISSUE_QUEUE.md` disposition note not independently re-verified in this pass — flagged for the human committer to confirm before clearing.

## Drift Entry — 2026-07-03 (found during Housekeeping, not previously logged)
**Changed fact:** Test suite count → **119 tests green** (up from 71/113 recorded in various in-flight notes) as of 2026-07-03; `docs/FMEA.md` PI-009 wording still said "2026 GraphQL schema" / "Mutation rejection" instead of REST terminology; `CLAUDE.md` "Stack:" line still said "eBay GraphQL API".
**Triggering session:** Housekeeping pass, 2026-07-03.
**Stale documents:**
- `working/CODE_DECISIONS_PATCH.md` line ~8 ("71 tests green").
- `docs/FMEA.md` PI-009 failure-mode wording.
- `CLAUDE.md` Stack line.
**Action required:** none further — patched in this session (see per-file summary below). `docs/FMEA.md` PI-009 **Status**/RPN were deliberately left unchanged (structure/scores are frozen per Ground Rule 8); note for a human reviewer that the mitigation (`EbayClient.validate_offer`) is actually implemented per `working/CODE_DECISIONS_PATCH.md` C1-8, so the Status column ("Open — mitigation planned") may itself be stale and could warrant a proper FMEA Amendment Proposal (Ground Rule 9) rather than a silent Housekeeping edit.
**Processed 2026-07-03 (pending human commit):** All three patched as described above.
