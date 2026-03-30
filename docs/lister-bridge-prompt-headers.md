# Prompt Headers — Lister-Bridge Hybrid Agent

**Generated:** March 29, 2026
**Calibration Reference:** Task 0.3 prompt header (approved)
**Execution Order:** 0.2 → 0.3 (approved) → 0.4 → 0.5 → 0.6

---

## Session 0.2 — Implement Google Drive API Fetcher

| | |
|---|---|
| **Task ID** | 0.2 |
| **Component** | `src/core/drive_fetcher.py` |
| **Model Tier** | Tier 2 — Standard Execution & Coding (Gemini 3 Flash, `media_resolution: HIGH`, 1M context) |
| **Depends On** | Task 0.1 (Repo scaffolded, `.env` configured with Google Service Account JSON path) |
| **Delivers To** | Task 0.3 (Vision Agent consumes image file references from this module) |
| **Reference** | ARCHITECTURE.md §4.1, §4.3 — Core/IO component; CONSTRAINTS.md C-003; FMEA PI-001 |

### Role
You are a Python developer building reliable cloud API integrations. You design for intermittent failure — network timeouts, quota limits, and partial responses are expected, not exceptional.

### Context
This module is the system's only interface to Google Drive. The Orchestrator (Task 0.5) calls this module to poll a designated staging folder for new item photo batches. Each batch is a subfolder containing one or more images for a single item. The module must download these images (or provide local file references) so the Vision Agent (Task 0.3) can process them.

The primary risk is PI-001: Drive API sync failures halting the pipeline. The user takes photos on a mobile phone and drops them into a shared Drive folder — network latency, upload delays, and API quota exhaustion are all realistic scenarios.

> **Relevant Specs / FMEA Constraints**
> - **PI-001** — Severity 6, RPN 90 — The module MUST implement a local cache fallback and exponential backoff retries. If the Drive API is unreachable or returns an error, the module must: (1) retry with exponential backoff up to 3 attempts, (2) if all retries fail, check the local cache for previously downloaded images of the same item batch, (3) if no cache exists, surface a clear error to the Orchestrator for terminal display — do not silently skip the item.
> - **C-003** — Python environment using `google-api-python-client` for Drive integration.
>
> **Ground Rule 8 applies:** These constraints are immutable during execution. If a constraint is logically impossible, HALT and invoke Ground Rule 9.

### Requirements

**R1 — Drive Folder Polling**
Build a function that authenticates via Service Account credentials (path from `.env`) and lists subfolders in the designated staging folder. Each subfolder represents one item batch. Return a list of batch metadata (folder ID, name, file count, timestamps).

**R2 — Image Download with Cache**
Build a function that downloads all images from a given batch subfolder to a local working directory. Before downloading, check if a local cached copy already exists (match by file ID and modification timestamp). Skip download for cached files. Return local file paths.

**R3 — Exponential Backoff & Failure Handling (PI-001 Mitigation)**
Wrap all Drive API calls in a retry decorator or utility function implementing exponential backoff (base 2 seconds, max 3 attempts). On total failure:
- If cached files exist for the requested batch, return cached paths with a warning flag.
- If no cache exists, raise a structured exception that the Orchestrator can catch and display to the user.

**R4 — Batch Lifecycle**
Provide a function to archive a completed batch — move the Drive subfolder to an "archived" folder after the listing is approved and published. This prevents re-processing.

### Ground Rule Compliance
- **Issue Binding:** This task is bound to Issue #[TBD].
- **Decision Logging:** Write all code decisions to `working/CODE_DECISIONS_PATCH.md`. Do not write directly to `CODE_DECISION_LOG.md`.
- **State Sync:** Move Kanban card from Ready → In Progress at start; In Progress → In Review at completion.
- **Comment Standard:** Ground Rule 11 and C-004 through C-007 apply. `drive_fetcher.py` must open with a module-level docstring. All public functions require docstrings. All non-trivial logic blocks (retry logic, cache checks, archive operations) require preceding plain-English block comments. No existing comments may be removed or truncated.

> **EXIT CONDITION — Acceptance Criteria**
> - [ ] `drive_fetcher.py` exists with a complete module-level docstring
> - [ ] Service Account authentication reads credentials path from `.env`
> - [ ] Staging folder polling returns structured batch metadata
> - [ ] Image download checks local cache before hitting Drive API
> - [ ] All Drive API calls use exponential backoff with max 3 retries (PI-001)
> - [ ] Total API failure with existing cache returns cached paths + warning flag (PI-001)
> - [ ] Total API failure with no cache raises a structured exception (PI-001)
> - [ ] Batch archive function moves completed subfolder to "archived" folder
> - [ ] All public functions have docstrings
> - [ ] All non-trivial logic blocks have plain-English block comments
> - [ ] No existing comments removed or truncated
> - [ ] All code decisions written to `working/CODE_DECISIONS_PATCH.md`
> - [ ] ARCHITECTURE.md updated if structural drift occurred (Ground Rule 4)

**PHASE 1: Execution**
1. Generate or modify the required code files per the Requirements above.
2. Output the exact string: `[AWAITING_HUMAN_APPROVAL: Code generation complete. Please test and verify.]`
3. HALT completely. Do not proceed to Phase 2.

**PHASE 2: Documentation (Execute ONLY after human replies "Approved")**
1. Audit the final, approved code against PI-001 constraints.
2. Generate the required `working/CODE_DECISIONS_PATCH.md` entry.
3. Generate an `ARCHITECTURE_PATCH.md` if structural drift occurred.

---

## Session 0.4 — Implement Margin-Guard Pricing Logic

| | |
|---|---|
| **Task ID** | 0.4 |
| **Component** | `src/ai/margin_guard.py` |
| **Model Tier** | Tier 1 — Complex Reasoning (Gemini 3 Flash, `thinking_level: HIGH`, 32k context) |
| **Depends On** | Task 0.3 (Vision Agent output JSON is this module's input) |
| **Delivers To** | Task 0.5 (Terminal Q&A displays the proposed price for approval) |
| **Reference** | ARCHITECTURE.md §4.3 — AI/Logic; CONSTRAINTS.md C-004–C-007; FMEA PI-006 |

### Role
Python developer building a pricing engine. Deterministic guardrails override AI suggestions.

### Context
This module receives the Vision Agent's structured JSON (item specifics, condition, defects) and produces a `marginGuardPrice`. The price must achieve a >80% 30-day sell-through rate. PI-006 (RPN 144): the AI calculates an unviable price — too high kills velocity, too low kills margin.

> **FMEA Constraints**
> - **PI-006** — Severity 8 — A deterministic floor function `(Cost+Fees)*1.15` MUST override any AI-suggested price that falls below it. This floor is hardcoded, not configurable by the AI. The AI may suggest prices above the floor; it may never output a price below it.
>
> **Ground Rule 8 applies.** Constraints are immutable. Conflicts → HALT, invoke Ground Rule 9.

### Requirements

**R1 — Market Analysis Prompt**
Build the function that sends item specifics + condition + defects to Gemini 3 Flash with `thinking_level: HIGH`. The prompt must instruct the model to:
- Estimate current market value based on item specifics, condition, and comparable sold listings.
- Apply the 2% sub-ceiling GMV rule: price must be within 2% below the lowest comparable sold price to optimize for velocity without sacrificing margin.
- Return a structured JSON with `suggested_price`, `comparable_range`, `reasoning`.

**R2 — Deterministic Floor Override (PI-006 Mitigation)**
Implement a pure function (no AI involvement) that calculates `(cost + fees) * 1.15`. This function:
- Accepts cost and fee inputs (user-provided or defaults).
- Returns the floor price.
- Is called AFTER the AI suggestion. If `suggested_price < floor_price`, override to `floor_price` and set a `floor_applied: true` flag.

**R3 — Cost Input**
The module must accept item cost as an input parameter. If cost is not provided by the Vision Agent or prior context, flag it for the terminal Q&A loop (Task 0.5).

**R4 — Output Contract**
```json
{
  "margin_guard_price": 0.00,
  "suggested_price": 0.00,
  "floor_price": 0.00,
  "floor_applied": false,
  "comparable_range": { "low": 0.00, "high": 0.00 },
  "reasoning": "",
  "missing_inputs": []
}
```

### Ground Rule Compliance
- **Issue Binding:** Bound to Issue #[TBD].
- **Decision Logging:** Write to `working/CODE_DECISIONS_PATCH.md`.
- **State Sync:** Ready → In Progress → In Review.
- **Comment Standard:** C-004–C-007 apply. Module docstring, function docstrings, block comments required. No comment removal.

> **EXIT CONDITION — Acceptance Criteria**
> - [ ] `margin_guard.py` exists with module-level docstring
> - [ ] Gemini call uses `thinking_level: HIGH`
> - [ ] 2% sub-ceiling GMV rule implemented in prompt
> - [ ] Deterministic floor function is pure (no AI dependency) (PI-006)
> - [ ] Floor override triggers when `suggested_price < floor_price` (PI-006)
> - [ ] `floor_applied` flag set when override activates (PI-006)
> - [ ] Missing cost input flagged in `missing_inputs` array
> - [ ] Output matches R4 contract schema
> - [ ] All public functions have docstrings
> - [ ] All non-trivial logic blocks have block comments
> - [ ] No existing comments removed or truncated
> - [ ] Code decisions written to `working/CODE_DECISIONS_PATCH.md`

**PHASE 1: Execution**
1. Generate or modify the required code files per the Requirements above.
2. Output the exact string: `[AWAITING_HUMAN_APPROVAL: Code generation complete. Please test and verify.]`
3. HALT completely. Do not proceed to Phase 2.

**PHASE 2: Documentation (Execute ONLY after human replies "Approved")**
1. Audit the final, approved code against PI-006 constraints.
2. Generate the required `working/CODE_DECISIONS_PATCH.md` entry.
3. Generate an `ARCHITECTURE_PATCH.md` if structural drift occurred.

---

## Session 0.5 — Build Interactive Terminal Q&A Loop

| | |
|---|---|
| **Task ID** | 0.5 |
| **Component** | `src/core/orchestrator.py` |
| **Model Tier** | Tier 2 — Standard Execution & Coding (Gemini 3 Flash, `media_resolution: HIGH`, 1M context) |
| **Depends On** | Task 0.3 (Vision output), Task 0.4 (Margin-Guard output) |
| **Delivers To** | Task 0.6 (Approved payload is formatted and posted to eBay) |
| **Reference** | ARCHITECTURE.md §4.1, §4.3 — Core/IO; CONSTRAINTS.md C-004–C-007; FMEA PI-003, PI-007, PI-008 |

### Role
You are a Python developer building human-in-the-loop CLI interfaces. You optimize for scannability — a fatigued user at 11 PM must be able to catch errors in your output without reading raw JSON.

### Context
This is the system's primary user-facing module. It orchestrates the full pipeline: poll Drive (Task 0.2), extract via Vision (Task 0.3), price via Margin-Guard (Task 0.4), present results to the user, resolve ambiguities, and — only after explicit approval — hand the payload to the eBay integration (Task 0.6).

Three failure modes converge here:

- **PI-003 (RPN 240):** Context window bloat crashes the session. Previous item data must be flushed after each listing approval.
- **PI-007 (RPN 280):** The user approves a flawed payload. This is the highest RPN in the register. The CLI must make errors visible and require deliberate confirmation.
- **PI-008 (RPN 160):** The terminal overwhelms the user with raw JSON, causing fatigue-driven "blind approvals."

> **Relevant Specs / FMEA Constraints**
> - **PI-003** — Severity 8 — The Orchestrator MUST flush the Gemini `messages` array of all previous item context (images, JSON, Q&A history) after each listing is approved or skipped. Only system-level context and the current item's data may persist.
> - **PI-007** — Severity 7 — The CLI MUST display a color-highlighted diff view of critical listing fields (price, condition, defects, title) and require the user to type the exact string `APPROVE` to confirm. No single-key shortcuts, no default-yes prompts.
> - **PI-008** — Severity 5 — The CLI MUST parse all JSON payloads into a human-readable summary table before displaying to the user. Raw JSON must never be the primary display format. Raw JSON may be available as an optional verbose/debug mode.
>
> **Ground Rule 8 applies:** These constraints are immutable during execution. If a constraint is logically impossible, HALT and invoke Ground Rule 9.

### Requirements

**R1 — Pipeline Orchestration**
Build the main loop that:
1. Calls `drive_fetcher` to get pending batches.
2. For each batch, calls `vision_agent` to extract data.
3. Calls `margin_guard` to generate pricing.
4. Presents results to the user via the summary table (R3).
5. Enters the Q&A loop (R2) if `dropped_fields` or `missing_inputs` exist.
6. On `APPROVE`, hands payload to `ebay_graphql` (Task 0.6).
7. On rejection or skip, logs the decision and moves to the next batch.

**R2 — Multi-Turn Q&A Loop**
When the Vision Agent returns `dropped_fields` or the Margin-Guard returns `missing_inputs`, enter a conversational loop:
- Present each missing/dropped field with context (why it was dropped, what eBay expects).
- Accept user input for each field.
- Re-validate user-provided values against eBay enums where applicable.
- Allow the user to type `SKIP` to leave a field empty (with a warning about listing quality impact).

**R3 — Human-Readable Summary Table (PI-008 Mitigation)**
Build a display function that renders the listing payload as a formatted table. At minimum:
- Title, Category, Condition, Price (with floor indicator if applied)
- Item Specifics (key-value pairs, sorted alphabetically)
- Defects (bulleted list with severity if available)
- Dropped/missing fields (highlighted as action items)

**R4 — Diff View & Approval Gate (PI-007 Mitigation)**
Before the `APPROVE` prompt, display a color-highlighted summary of critical fields:
- Price: green if above floor, yellow if floor-applied
- Condition: standard display
- Defects: red if any exist, green if empty array
- Require the exact string `APPROVE` to proceed. Reject partial matches, abbreviations, and empty input.

**R5 — Context Flush (PI-003 Mitigation)**
After each listing is approved, skipped, or rejected:
- Clear the Gemini `messages` array of all item-specific content.
- Retain only system-level prompts and session metadata.
- Log the flush action for debugging.

### Ground Rule Compliance
- **Issue Binding:** This task is bound to Issue #[TBD].
- **Decision Logging:** Write all code decisions to `working/CODE_DECISIONS_PATCH.md`. Do not write directly to `CODE_DECISION_LOG.md`.
- **State Sync:** Move Kanban card from Ready → In Progress at start; In Progress → In Review at completion.
- **Comment Standard:** Ground Rule 11 and C-004 through C-007 apply. `orchestrator.py` must open with a module-level docstring. All public functions require docstrings. All non-trivial logic blocks require preceding plain-English block comments. No existing comments may be removed or truncated.

> **EXIT CONDITION — Acceptance Criteria**
> - [ ] `orchestrator.py` exists with a complete module-level docstring
> - [ ] Pipeline loop calls drive_fetcher → vision_agent → margin_guard in sequence
> - [ ] Q&A loop activates when `dropped_fields` or `missing_inputs` are non-empty
> - [ ] User-provided values are re-validated against eBay enums
> - [ ] Summary table renders all listing fields without raw JSON (PI-008)
> - [ ] Diff view highlights price, condition, and defects with color (PI-007)
> - [ ] Approval requires exact string `APPROVE` — no shortcuts (PI-007)
> - [ ] Gemini `messages` array is flushed of previous item context after each listing (PI-003)
> - [ ] System-level context is preserved across flushes (PI-003)
> - [ ] All public functions have docstrings
> - [ ] All non-trivial logic blocks have plain-English block comments
> - [ ] No existing comments removed or truncated
> - [ ] All code decisions written to `working/CODE_DECISIONS_PATCH.md`
> - [ ] ARCHITECTURE.md updated if structural drift occurred (Ground Rule 4)

**PHASE 1: Execution**
1. Generate or modify the required code files per the Requirements above.
2. Output the exact string: `[AWAITING_HUMAN_APPROVAL: Code generation complete. Please test and verify.]`
3. HALT completely. Do not proceed to Phase 2.

**PHASE 2: Documentation (Execute ONLY after human replies "Approved")**
1. Audit the final, approved code against PI-003, PI-007, and PI-008 constraints.
2. Generate the required `working/CODE_DECISIONS_PATCH.md` entry.
3. Generate an `ARCHITECTURE_PATCH.md` if structural drift occurred.

---

## Session 0.6 — Integrate eBay GraphQL Previews

| | |
|---|---|
| **Task ID** | 0.6 |
| **Component** | `src/api/ebay_graphql.py` |
| **Model Tier** | Tier 1 — Complex Reasoning (Gemini 3 Flash, `thinking_level: HIGH`, 32k context) |
| **Depends On** | Task 0.1 (eBay OAuth credentials in `.env`), Task 0.5 (Approved payload from Orchestrator) |
| **Delivers To** | None (terminal task) |
| **Reference** | ARCHITECTURE.md §4.3 — API/eBay; CONSTRAINTS.md C-002, C-004–C-007; FMEA PI-009 |

### Role
Python developer integrating with eBay's 2026 GraphQL API. Strict schema compliance — no field improvisation.

### Context
This module receives an approved listing payload from the Orchestrator and transforms it into the exact input shape required by eBay's `startListingPreviewsCreation` GraphQL mutation. PI-009 (RPN 70): a malformed payload is rejected by the API, wasting the user's time and breaking pipeline flow. Although RPN is below threshold, C-002 makes schema compliance a hard constraint.

> **FMEA Constraints**
> - **PI-009** — Severity 7 — The module MUST validate the complete payload against the 2026 eBay GraphQL schema BEFORE sending the mutation. Validation failures must block submission and surface specific field-level errors to the Orchestrator for user display.
> - **C-002** — Must use `startListingPreviewsCreation` mutation and `mappingReferenceID` for error tracking.
>
> **Ground Rule 8 applies.** Constraints are immutable. Conflicts → HALT, invoke Ground Rule 9.

### Requirements

**R1 — Schema Transformation**
Build a function that maps the internal JSON structure (defined in Task 0.3 R4 + Task 0.4 R4) to the eBay `startListingPreviewsCreation` mutation input. This mapping must be explicit — no dynamic field inference.

**R2 — Pre-Submit Validation (PI-009 Mitigation)**
Validate the transformed payload against the 2026 GraphQL schema before submission. The validator must:
- Check all required fields are present and non-null.
- Validate field types match schema expectations.
- Return a list of specific validation errors (field path + expected vs. actual).
- Block submission on any validation failure.

**R3 — Mutation Execution**
Build the function that sends the validated payload via GraphQL. Must:
- Use eBay OAuth 2.0 credentials from `.env`.
- Include `mappingReferenceID` for error tracking per C-002.
- Handle API error responses and surface them to the Orchestrator.

**R4 — Response Parsing**
Parse the eBay API response. Extract: listing preview URL, any warnings, and any field-level errors. Return structured data to the Orchestrator.

### Ground Rule Compliance
- **Issue Binding:** Bound to Issue #[TBD].
- **Decision Logging:** Write to `working/CODE_DECISIONS_PATCH.md`.
- **State Sync:** Ready → In Progress → In Review.
- **Comment Standard:** C-004–C-007 apply. Module docstring, function docstrings, block comments required. No comment removal.

> **EXIT CONDITION — Acceptance Criteria**
> - [ ] `ebay_graphql.py` exists with module-level docstring
> - [ ] Schema transformation maps internal JSON to `startListingPreviewsCreation` input explicitly
> - [ ] Pre-submit validation checks all required fields and types (PI-009)
> - [ ] Validation failure blocks submission and returns field-level errors (PI-009)
> - [ ] Mutation uses `mappingReferenceID` for error tracking (C-002)
> - [ ] OAuth credentials read from `.env`
> - [ ] API error responses parsed and surfaced to Orchestrator
> - [ ] All public functions have docstrings
> - [ ] All non-trivial logic blocks have block comments
> - [ ] No existing comments removed or truncated
> - [ ] Code decisions written to `working/CODE_DECISIONS_PATCH.md`

**PHASE 1: Execution**
1. Generate or modify the required code files per the Requirements above.
2. Output the exact string: `[AWAITING_HUMAN_APPROVAL: Code generation complete. Please test and verify.]`
3. HALT completely. Do not proceed to Phase 2.

**PHASE 2: Documentation (Execute ONLY after human replies "Approved")**
1. Audit the final, approved code against PI-009 and C-002 constraints.
2. Generate the required `working/CODE_DECISIONS_PATCH.md` entry.
3. Generate an `ARCHITECTURE_PATCH.md` if structural drift occurred.
