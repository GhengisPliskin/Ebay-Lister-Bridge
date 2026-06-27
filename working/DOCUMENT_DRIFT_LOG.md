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

## Drift Entry — 2026-06-27
**Changed fact:** UI is **interactive CLI** → **Streamlit** (DECISION 4 superseded; CLI retained as headless mode). Pipeline entry point is `python -m src.core.orchestrator`, not a CLI loop in `orchestrator.py`.
**Triggering session:** Phase 1 — contracts freeze + eBay sandbox spike.
**Stale documents:**
- `ARCHITECTURE.md` — "Interactive CLI (human-in-the-loop)" labels and "managing the CLI loop" descriptions.
- `KEY_DECISION_LOG.md` — DECISION 4 disposition.
**Action required:** Mark DECISION 4 superseded; describe Streamlit review/approve as the default front end with a headless mode.

## Drift Entry — 2026-06-27
**Changed fact:** `drive_fetcher` pagination cap (assumption A-01) — `pageSize=100`, no recursion → **required** recursive subfolder traversal + full `pageToken` pagination (not yet implemented; requirement noted in code).
**Triggering session:** Phase 1 — contracts freeze + eBay sandbox spike.
**Stale documents:**
- `docs/Ebay lister bridge master plan.md` / `docs/FMEA.md` — confirm A-01 / PI-001 notes reflect the pending enhancement.
**Action required:** Track the Drive enhancement as its own Phase 2 issue; the code already carries a `PENDING ENHANCEMENT` block.
