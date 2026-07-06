# ISSUE_QUEUE.md — GitHub Issue Transit Queue

Issues queued here are created via `gh issue create` during a Housekeeping session.
After creation, record the assigned issue number and clear the entry.

**Disposition note — 2026-07-03 (Phase 6 hardening session):** the three issues
below — "eBay OAuth scopes in wrong format", "Token cache dead code", and
"Operator description edits silently discarded; condition field unvalidated" —
were implemented and verified (113/113 tests passing) in this execution
session. See `working/CODE_DECISIONS_PATCH.md` (C6-1/C6-2/C6-3) for the
decisions and `working/DOCUMENT_DRIFT_LOG.md` (2026-07-03 entry) for the
resulting doc drift. A Housekeeping session should create/close the
corresponding GitHub Issues (or close them directly if already open) rather
than filing them as new work, then clear these three entries.

**Format:**

```
## Issue: [Title]
**Labels:** [comma-separated labels]
**Milestone:** Phase [X]
**Depends on:** #[issue numbers] or "None"
**Assignee:** [human-gate | ai-eligible | ai-with-review]

[Description body]

### Acceptance Criteria
- [ ] [Boolean criterion]
```

---

## Issue: Frozen .exe loses SQLite state and image cache (relative paths anchor to %TEMP%)
**Labels:** bug, critical, packaging
**Milestone:** Phase 6 (hardening)
**Depends on:** None
**Assignee:** ai-with-review

`state_store.py:62` and `drive_fetcher.py:397` anchor relative `STATE_STORE_DB_PATH` / `DRIVE_CACHE_DIR` to `Path(__file__).parent.parent.parent`. In the PyInstaller onefile build this resolves inside the `sys._MEIPASS` temp extraction dir, deleted on exit — dedup state and cache are lost every run, violating R-STATE (crash-and-resume never double-publishes). `.env` discovery via `load_dotenv()` is cwd-relative and has the same problem.

### Acceptance Criteria
- [ ] A single shared `resolve_app_path()` helper anchors relative paths to `%APPDATA%\ListerBridge` when `getattr(sys, "frozen", False)`, else project root (current behavior).
- [ ] Both `state_store.py` and `drive_fetcher.py` use the helper (dedup the two copies of anchoring logic).
- [ ] `.env` is loaded from the exe's directory and `%APPDATA%\ListerBridge` when frozen.
- [ ] Unit test with monkeypatched `sys.frozen` proves anchoring for both frozen and non-frozen cases.

## Issue: eBay OAuth scopes in wrong format — first live token refresh fails
**Labels:** bug, critical, api
**Milestone:** Phase 6 (hardening)
**Depends on:** None
**Assignee:** ai-with-review

`.env.example:49` sets `EBAY_OAUTH_SCOPES=sell.inventory commerce.media buy.browse`; eBay requires full scope URLs (e.g. `https://api.ebay.com/oauth/api_scope/sell.inventory`; Browse uses the base `api_scope`). `ebay_auth.py` sends the string verbatim → `invalid_scope`. Mocked tests only assert pass-through.

### Acceptance Criteria
- [ ] `.env.example` carries correct full-URL scopes for sandbox and production.
- [ ] `EbayAuth.__init__` raises a clear `ValueError` if any scope does not start with `https://api.ebay.com/oauth/`.
- [ ] Test covers the rejection path.

## Issue: Operator description edits silently discarded; condition field unvalidated
**Labels:** bug, high, ui
**Milestone:** Phase 6 (hardening)
**Depends on:** None
**Assignee:** ai-with-review

`app.py` renders an editable Description `st.text_area` but never reads it; `review.apply_operator_edits` (review.py:113) has no `description` parameter, so PI-004 defect-disclosure corrections are thrown away. eBay condition is a free-text input with no enum validation.

### Acceptance Criteria
- [ ] `apply_operator_edits` accepts `description`; `app.py` passes the text_area value through.
- [ ] Condition input replaced with `st.selectbox` over the canonical enum values from `orchestrator._CONDITION_MAP`.
- [ ] Tests in `test_review.py` cover description edit application.

## Issue: Orchestrator has no error handling; ItemStatus.ERROR never assigned
**Labels:** bug, high, core
**Milestone:** Phase 6 (hardening)
**Depends on:** None
**Assignee:** ai-with-review

`orchestrator.py` contains no try/except: one bad item (Gemini JSON `ValueError`, `DriveFetchError`) aborts the whole scan and discards completed work; `main()` prints a raw traceback, contradicting drive_fetcher's documented PI-001 contract. The stale-cache warning flag is discarded at `orchestrator.py:239`.

### Acceptance Criteria
- [ ] Per-batch try/except: failed batch recorded as `ItemStatus.ERROR` with a reason string; scan continues.
- [ ] Stale-cache warning surfaced on the payload/summary for UI display.
- [ ] `main()` catches top-level exceptions and prints a human-readable message, no raw traceback.
- [ ] Tests cover the continue-on-error path and error-status persistence.

## Issue: Token cache dead code — new eBay token minted per UI action
**Labels:** bug, high, api
**Milestone:** Phase 6 (hardening)
**Depends on:** None
**Assignee:** ai-with-review

`StateStore.get_cached_token`/`save_cached_token` have zero callers; `ebay_auth.py:19` references a `_TokenCache` that does not exist. `app.py` constructs a fresh `EbayClient()` in each button handler, so every Scan/Approve mints a new access token (defeats R-AUTH/R-COST).

### Acceptance Criteria
- [ ] `EbayAuth` accepts an optional `StateStore` and reads/writes the cached token around `_refresh`.
- [ ] `app.py` holds one `EbayClient` (and one `StateStore`) in `st.session_state`.
- [ ] Stale docstring corrected (no phantom `_TokenCache`).
- [ ] Test proves a valid cached token skips the refresh call.

## Issue: archive_batch never called — batches never leave staging
**Labels:** bug, high, core
**Milestone:** Phase 6 (hardening)
**Depends on:** None
**Assignee:** ai-with-review

`drive_fetcher.archive_batch` (drive_fetcher.py:794) has zero callers. Every scan re-lists all historical batches; dedup rests entirely on the state store the frozen build currently deletes. Compounds into re-listing sold items.

### Acceptance Criteria
- [ ] `_auto_publish` archives the batch after the PUBLISHED state write succeeds; archive failure is logged, never blocks the publish result.
- [ ] Also catch `JSONDecodeError` in `_load_cache_manifest` (treat as cold cache per its own docstring).
- [ ] Integration test asserts archive is invoked post-publish.

## Issue: PyInstaller spec stale (PyInstaller 6 kwargs, wrong relative paths); two divergent build routes
**Labels:** bug, high, packaging
**Milestone:** Phase 6 (hardening)
**Depends on:** None
**Assignee:** ai-with-review

`packaging/lister_bridge.spec` uses `win_no_prefer_redirects`/`win_private_assemblies`/`cipher` (removed in PyInstaller 6.0, exactly what requirements-build.txt pins) and spec-relative paths that resolve to nonexistent `packaging/desktop_app.py`. `scripts/build_desktop.py` builds a different entry point. Two routes, different artifacts.

### Acceptance Criteria
- [ ] One canonical build route producing a single .exe wrapping `desktop_app.py`; the other route removed or delegating to it.
- [ ] Spec uses `SPECPATH`-relative joins; PyInstaller-6-removed kwargs deleted; `googleapiclient` data files collected.
- [ ] Human gate: Alan builds and launches the .exe on Windows; scan + approve round-trip persists state across app restarts.

## Issue: Documentation drift — GraphQL/CLI references contradict REST + Streamlit implementation
**Labels:** docs, housekeeping
**Milestone:** Phase 6 (hardening)
**Depends on:** None
**Assignee:** ai-with-review

Per DOCUMENT_DRIFT_LOG entry 2026-06-27: README, ARCHITECTURE, CONSTRAINTS C-002, FMEA PI-009, KEY_DECISION_LOG DECISION 4, and the master plan still describe the GraphQL `startListingPreviewsCreation` path and/or a CLI interface. Code is REST Sell Inventory (createInventoryItem → createOffer → publishOffer) + Media API + Streamlit. Also: README directory tree lists `ebay_graphql.py`; CODE_DECISIONS_PATCH says "71 tests" (actual: 85+).

### Acceptance Criteria
- [ ] All GraphQL/CLI references replaced with REST + Streamlit equivalents across the six documents.
- [ ] README directory tree matches the actual repo layout.
- [ ] Drift-log entry annotated as processed (pending human commit).
- [ ] `CODE_DECISION_LOG.md` merge NOT performed (human-gate action per Ground Rule 2).

## Issue: Prompt header Session 0.6 still instructs building ebay_graphql.py (GraphQL)
**Labels:** docs, high, housekeeping
**Milestone:** Phase 6 (hardening)
**Depends on:** None
**Assignee:** ai-with-review

`docs/lister-bridge-prompt-headers.md` (Session 0.6, ~lines 270-322) is a live, un-amended prompt header instructing a future execution session to build `src/api/ebay_graphql.py` against the 2026 GraphQL schema / `startListingPreviewsCreation`. CLAUDE.md's Execution-Session startup sequence loads headers from this exact file, so this is an operational hazard: a future AI session could faithfully build the wrong integration. Requires a substantive rewrite (REST Sell Inventory mapping, validation steps, acceptance criteria), not a find-and-replace — hence queued rather than patched during the 2026-07-03 doc-drift session.

### Acceptance Criteria
- [ ] Session 0.6 header rewritten for the REST path (createInventoryItem → createOffer → publishOffer + Media API) or marked SUPERSEDED with a pointer to the implemented `ebay_client.py`.
- [ ] No prompt header in the file instructs creation of `ebay_graphql.py`.

## Issue: SQLite thread-safety rationale is wrong; publish dedup is not atomic
**Labels:** bug, medium, core
**Milestone:** Phase 6 (hardening)
**Depends on:** None
**Assignee:** ai-with-review

`state_store.py` (~line 95) opens the connection with `check_same_thread=False`, commented "access is serialized by SQLite's own locking" — false: SQLite file locking serializes connections, not a single Python `sqlite3.Connection` shared across threads. Streamlit runs script executions on worker threads, and as of the 2026-07-03 hardening session `app.py` holds ONE StateStore/EbayClient in `st.session_state`, making cross-thread sharing the normal case. Separately, `_auto_publish` is check-then-act (`is_published()` → `publish()` → `upsert_item()`) with no claim step, so two concurrent approves of one SKU can both publish.

### Acceptance Criteria
- [ ] Connection access guarded (per-thread connections or a `threading.Lock` around all cursor use); the false comment corrected.
- [ ] WAL mode + `busy_timeout` enabled.
- [ ] Publish claims the SKU transactionally (e.g. write a PUBLISHING status row) before calling eBay; second concurrent approve becomes a dedup no-op.
- [ ] Concurrency test exercising two threads approving the same SKU.
