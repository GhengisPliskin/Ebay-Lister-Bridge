# Document Templates Reference

All templates in this file are mandatory formats. Reproduce the structure exactly when
generating project documents. Do not omit sections; write "None" or "N/A" for sections
that don't apply to a specific project.

**Ground Rule 6 Reminder:** You are reading this file because you MUST read it before
generating any project document. Do not close this file and reconstruct templates from
memory.

---

## Table of Contents

1. [KEY_DECISION_LOG.md](#key_decision_logmd)
2. [CODE_DECISION_LOG.md](#code_decision_logmd)
3. [CODE_DECISIONS_PATCH.md](#code_decisions_patchmd)
4. [SESSION_PROMPT_HEADER.md](#session_prompt_headermd)
5. [ARCHITECTURE_PATCH.md](#architecture_patchmd)
6. [KANBAN_SETUP.md](#kanban_setupmd)
7. [README.md Skeleton](#readmemd-skeleton)
8. [FMEA Register](#fmea-register)
9. [FMEA Amendment Proposal](#fmea-amendment-proposal)

---

## KEY_DECISION_LOG.md

Use for macro-level architectural, infrastructural, or tooling decisions. One entry per
decision. Number sequentially. New decisions append; resolved decisions are updated
in-place (never deleted).

```markdown
## DECISION [#] — [Short Title]

**Status:** [Proposed | RESOLVED — Option [X] selected | Rejected | Superseded]

**Resolution:** [What is the specific action being taken or architecture being adopted?
State clearly.]

**Rationale:** [Why is this the optimal path? Cite specific evidence, performance
metrics, or cognitive load reductions.]

**FMEA Impact:** [List any FMEA constraints (e.g., PI-001) altered, mitigated, or
introduced by this decision. Write "None" if purely infrastructural.]

**Documents updated:**
- `[Filename.ext]` — [Brief description of what changed in this file]

**Downstream impact:**
- [List specific cascading effects, necessary patches, or future contingencies
  triggered by this decision.]
```

### Example Entry

```markdown
## DECISION 1 — Select PostgreSQL over SQLite for persistence layer

**Status:** RESOLVED — Option A selected

**Resolution:** Use PostgreSQL 16 with pgvector extension for all persistent storage.

**Rationale:** The project requires concurrent write access from multiple services and
vector similarity search. SQLite cannot support either at the required scale. PostgreSQL
with pgvector provides both capabilities in a single dependency.

**FMEA Impact:** PI-003 (Data loss on concurrent writes) — mitigated by PostgreSQL's
MVCC. RPN reduced from 180 to 40.

**Documents updated:**
- `ARCHITECTURE.md` — Updated persistence layer section
- `CONSTRAINTS.md` — Added PostgreSQL 16+ as infrastructure dependency

**Downstream impact:**
- All data model tasks now require PostgreSQL connection config
- CI pipeline needs PostgreSQL service container
- Local development setup requires Docker or native PostgreSQL install
```

---

## CODE_DECISION_LOG.md

The authoritative, merged record of all structural code decisions. Updated only at
HUMAN gates by merging entries from `working/CODE_DECISIONS_PATCH.md`. Do not write
directly to this file during active development — use the patch file instead.

```markdown
# Code Decision Log

## [Category Name, e.g., Data Model Decisions]

| # | Decision | Rationale | If This Breaks, Check... |
|---|----------|-----------|--------------------------|
| D-[XX] | [Brief technical description] | [Why chosen over alternatives] | [Specific debugging heuristic] |

## [Another Category]

| # | Decision | Rationale | If This Breaks, Check... |
|---|----------|-----------|--------------------------|
| D-[XX] | [Brief technical description] | [Why chosen over alternatives] | [Specific debugging heuristic] |

---

## Assumptions Register

| # | Status | Assumption | What Breaks If Wrong |
|---|--------|-----------|----------------------|
| A-[XX] | [UNVERIFIED | CONFIRMED | INVALIDATED] | [State the assumption] | [Consequence and required refactoring] |
```

### Example Entries

```markdown
## API Layer Decisions

| # | Decision | Rationale | If This Breaks, Check... |
|---|----------|-----------|--------------------------|
| D-01 | Use Pydantic v2 model_validator for cross-field validation | Pydantic v2 validators run post-init, catching invalid field combinations before they hit business logic | Validation errors with confusing tracebacks → check validator ordering in the model class. Pydantic v2 changed decorator names from v1. |
| D-02 | Return 422 (not 400) for schema validation failures | FastAPI convention; client libraries expect 422 for Pydantic errors | If clients get unexpected 400s → check for manual HTTPException raises that should be ValidationErrors |

## Assumptions Register

| # | Status | Assumption | What Breaks If Wrong |
|---|--------|-----------|----------------------|
| A-01 | UNVERIFIED | API consumers will always send UTC timestamps | All time-windowed queries return wrong results. Add timezone normalization middleware. |
| A-02 | CONFIRMED | Redis will be available on the same network segment | Connection timeout errors on cache calls. Check Docker network config or k8s service mesh. |
```

---

## CODE_DECISIONS_PATCH.md

**Location:** `working/CODE_DECISIONS_PATCH.md`

Ephemeral scratch file for code decisions made during active development. AI sessions
write here — never directly to `CODE_DECISION_LOG.md`. At HUMAN gate sign-off (phase
passes all tests, user approves), entries are appended to `CODE_DECISION_LOG.md` and
this file is reset to empty.

**AI session instruction:** Read `CODE_DECISION_LOG.md` first for existing decisions,
then read this file for provisional decisions from the current phase. Both files
together represent the full decision record.

```markdown
# Code Decisions Patch — Phase [X]

**Status:** PROVISIONAL — not yet merged into CODE_DECISION_LOG.md
**Phase:** [X]
**Merge trigger:** Human sign-off after all phase tests pass

---

## [Category Name]

| # | Decision | Rationale | If This Breaks, Check... |
|---|----------|-----------|--------------------------|
| D-[XX] | [Brief technical description] | [Why chosen over alternatives] | [Specific debugging heuristic] |

---

## Assumptions Register (Patch)

| # | Status | Assumption | What Breaks If Wrong |
|---|--------|-----------|----------------------|
| A-[XX] | [UNVERIFIED | CONFIRMED | INVALIDATED] | [State the assumption] | [Consequence and required refactoring] |
```

### Merge Protocol (executed at HUMAN gate)

1. Append all category sections from this patch into `CODE_DECISION_LOG.md`, preserving
   category structure. Renumber entries sequentially from the last entry in the main log.
2. Confirm to user: "Merged [N] decisions (D-XX through D-YY) and [M] assumptions
   (A-XX through A-YY) into CODE_DECISION_LOG.md."
3. Reset this file to the empty initialized template above.
4. Update phase status in `ARCHITECTURE.md` to `COMPLETE ✓`.

---

## SESSION_PROMPT_HEADER.md

The execution instruction set for every individual task. This is the attention-forcing
mechanism for AI agents — it constrains scope, defines success, and prevents drift.

Every field is mandatory. If a field doesn't apply, write "N/A" rather than omitting it.

```markdown
## Session [X.Y] — [Task Name]

| | |
|---|---|
| **Task ID** | [X.Y] |
| **Component** | [Target Component/File Path] |
| **Model Tier** | [Tier 1 / Tier 2 / Tier 3 — from Intelligence Roster] |
| **Assigned Model** | [Specific model name from Intelligence Roster] |
| **Depends On** | [Prerequisite Task IDs, or "None"] |
| **Delivers To** | [Downstream Task IDs, or "None"] |
| **Reference** | [Specific ARCHITECTURE.md sections, FMEA Constraint IDs] |

### Role
[Define the exact persona required, e.g., "Senior Python Systems Developer" or
"Technical Writer with API documentation experience"]

### Context
[Explain the "why" of the task. Detail the specific failure modes being prevented.
This section grounds the AI agent in purpose, not just procedure.]

> **Relevant Specs / FMEA Constraints**
> - [Constraint ID] — [Severity] — [Mechanical rule this task must satisfy]
> - [Additional constraints as needed]
>
> **Ground Rule 8 applies:** These constraints are immutable during execution.
> If a constraint is logically impossible, HALT and invoke Ground Rule 9.

### Requirements

**R1 — [Requirement Title]**
[Technical implementation details. Be specific about inputs, outputs, and interfaces.]

**R2 — [Requirement Title]**
[Technical implementation details.]

[Add R3, R4, etc. as needed.]

### Ground Rule Compliance
- **Issue Binding:** This task is bound to Issue #[X].
- **Decision Logging:** Write all code decisions to `working/CODE_DECISIONS_PATCH.md`.
  Do not write directly to `CODE_DECISION_LOG.md`.
- **State Sync:** Move Kanban card from [Column A] → [Column B] at start;
  [Column B] → [Column C] at completion.

> **EXIT CONDITION — Acceptance Criteria**
> - [ ] [Boolean criterion — must be verifiable as true/false]
> - [ ] [Boolean criterion]
> - [ ] [Boolean criterion]
> - [ ] All referenced documentation updated per Ground Rule 4
> - [ ] All code decisions written to `working/CODE_DECISIONS_PATCH.md`
> - [ ] All new `.py` files have module-level docstrings (MODULE / PURPOSE / FMEA / PHASE)
> - [ ] All new public functions have structured docstrings (WHAT / WHY / ARGS / RETURNS / FMEA)
> - [ ] All non-trivial new logic blocks have plain-English block comments
> - [ ] No existing comments removed or truncated (Ground Rule 11 / C-022)

### Execution Sequence & Two-Phase Commit

> **Include this section for Tier 1 and Tier 2 tasks. For Tier 3 tasks, include ONLY
> if the task touches an FMEA constraint. Otherwise omit this section entirely.**

**PHASE 1: Execution**
1. Generate or modify the required code files per the Requirements above.
2. Output the exact string: `[AWAITING_HUMAN_APPROVAL: Code generation complete. Please test and verify.]`
3. HALT completely. Do not proceed to Phase 2.

**PHASE 2: Documentation (Execute ONLY after human replies "Approved")**
1. Audit the final, approved code against the current FMEA constraints.
2. Generate the required `working/CODE_DECISIONS_PATCH.md` entry using the patch
   template. Do not write to `CODE_DECISION_LOG.md` directly.
3. Generate an `ARCHITECTURE_PATCH.md` if structural drift occurred.
4. Output the final Kanban board state change.
```

### Guidance for Writing Acceptance Criteria

Each criterion must be **strictly boolean** — answerable with yes or no, no judgment
calls. Bad: "Code is well-structured." Good: "All public functions have docstrings
matching the numpy format."

Include at least one documentation criterion in every prompt header to enforce
Ground Rule 4 (Source Truth).

### Guidance for Two-Phase Commit Gating

The Two-Phase Commit prevents the AI from generating documentation that describes
untested code. The human tests the code in Phase 1, then the AI documents what was
actually approved — not what was intended.

- **Tier 1 & Tier 2:** Always include. No exceptions.
- **Tier 3:** Include only if the task references any FMEA constraint ID. Pure
  boilerplate tasks (e.g., "create empty test directory structure") skip the commit
  sequence.

---

## ARCHITECTURE_PATCH.md

Use this template to propose updates to ARCHITECTURE.md without rewriting the entire
document. This ensures human review of architectural drift and maintains an audit trail.

```markdown
## Architecture Patch [#]

**Target Document:** `ARCHITECTURE.md`
**Triggering Decision:** [Reference KEY_DECISION_LOG entry or Phase requirement]

### Section to Modify: [Exact Heading Name]

**Current Text/Structure:**
```text
[Paste current state of the section being modified]
```

**Proposed Replacement:**
```text
[New state of the section]
```

**Rationale for Patch:**
[Why this structural change is necessary. Reference the triggering decision.]

**Downstream Documents Affected:**
- [List any other documents that need corresponding updates]
```

---

## KANBAN_SETUP.md

Defines the Kanban board configuration for GitHub Projects. Adapt column names and
WIP limits to project scale.

```markdown
# Kanban Board Configuration

## Board: [Project Name]

### Columns

| Column | Purpose | WIP Limit | Entry Criteria | Exit Criteria |
|---|---|---|---|---|
| Triage | New issues awaiting decomposition | None | Issue created | Task decomposed, dependencies identified |
| Ready | Fully specified, unblocked tasks | 10 | Prompt header generated, dependencies met | Assigned to developer/agent |
| In Progress | Actively being worked | 5 | Assigned, Kanban state announced (Rule 3) | All acceptance criteria met |
| In Review | Awaiting human review | 5 | PR opened or artifact submitted | Review approved |
| Done | Completed and documented | None | Review approved, docs updated (Rule 4), patch merged (Rule 2) | N/A |
| Blocked | Tasks with unresolved dependencies | None | Blocker identified | Blocker resolved |

### Spike Constraint (Ground Rule 7)
Issues labeled `spike` are prohibited from moving to "Done." They may only reach
"Done" after a linked formalization issue is created and itself reaches "In Review."

Enforcement is two-layer:

**Layer 1 — GitHub Project Automation (visual friction)**
In the GitHub Projects UI under "Workflows":
- Trigger: Item moved to "Done" with label `spike`
- Action: Move back to "In Review"

**Layer 2 — GitHub Actions CI check (hard enforcement)**
Defined in `.github/workflows/spike-check.yml`. Triggers on `issues.closed`.
Re-opens the issue and posts a comment if no linked formalization issue is found.

### Automation Rules
- When PR is opened → move card to "In Review"
- When PR is merged → move card to "Done"
- When issue is labeled `blocked` → move card to "Blocked"
- When issue has label `spike` and moves to "Done" → move back to "In Review" (Layer 1)
- When issue with label `spike` is closed without linked formalization issue → re-open and comment (Layer 2)

### Label Taxonomy

**Phase** — one per issue, required:
`phase:0`, `phase:1`, `phase:2` [extend as needed for project phase count]

**Boundary** — one per issue, required:
`human-gate`, `ai-eligible`, `ai-with-review`

**Type** — one per issue, required:
`task`, `spike`, `decision`, `amendment`

- `task` — standard execution work (coding, testing, documentation)
- `spike` — exploratory work under Ground Rule 7 (formalization issue required before Done)
- `decision` — open architectural question requiring human disposition
- `amendment` — modification to the project's rule set (constraints, FMEA, scope proposals)

**Priority** — one per issue, optional (default: `normal`):
`critical`, `high`, `normal`

- `critical` — blocks multiple other issues or threatens project integrity
- `high` — blocks at least one other issue or has a near-term deadline
- `normal` — standard priority, no urgency

Component, tier, complexity, and individual FMEA constraint information lives in the
issue body and session prompt header — not in labels. This keeps the taxonomy scannable
for board readers without duplicating metadata.
```

---

## README.md Skeleton

The README orients readers and links to authoritative documents. It does not duplicate
content from ARCHITECTURE.md, the Master Plan, or the ground rules — it links to them.
Keep it short. Details live in the documents they belong to.

```markdown
# [Project Name]

[One paragraph: what problem this solves and what it produces. Written for a reader unfamiliar with the project.]

## Project Status

[Current phase and brief state of completion.]

## Quick Start

[Placeholder — populated during Phase 2 execution]

## Documentation

This project is developed using AI coding assistants under human oversight. If you are new to the project, read `ARCHITECTURE.md` first.

| Document | Purpose |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Directory structure, component descriptions, data flow, phase status, code comment standard |
| [`CONSTRAINTS.md`](CONSTRAINTS.md) | FMEA traceability, technical constraints, and code quality requirements |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Code comment standard, contribution workflow, ground rules for contributors |
| [`KEY_DECISION_LOG.md`](KEY_DECISION_LOG.md) | Architectural decisions and rationale |
| [`CODE_DECISION_LOG.md`](CODE_DECISION_LOG.md) | Code-level decisions and debugging heuristics |
| [`docs/KANBAN_SETUP.md`](docs/KANBAN_SETUP.md) | Project board configuration |
| [`docs/FMEA.md`](docs/FMEA.md) | Failure Mode and Effects Analysis — catalogue of silent failure modes and mitigations |
| [`docs/[project]-master-plan.md`](docs/[project]-master-plan.md) | Full project plan, ground rules, task registry |

## Automation

This repo includes GitHub Actions and Project automation for Kanban enforcement.
See [`docs/KANBAN_SETUP.md`](docs/KANBAN_SETUP.md) for setup steps and workflow details.

## Ground Rules

This project uses AI coding assistants under 11 operational ground rules for
traceability and safe AI-assisted development. See the
[Master Plan](docs/[project]-master-plan.md) for full details.

## Contributing

[Placeholder — populated during Phase 2 execution. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the code comment standard and workflow ground rules.]
```

---

## FMEA Register

The Failure Mode and Effects Analysis register. Initialize from the Master Plan's risk
assessment. Update only through the FMEA Amendment Protocol (Ground Rule 9).

```markdown
# Failure Mode and Effects Analysis (FMEA)

## Risk Priority Legend
- **RPN** = Severity × Occurrence × Detection
- **Action threshold:** RPN ≥ 100 requires a mitigation plan before proceeding.

## Register

| ID | Failure Mode | Potential Effect | S | O | D | RPN | Mitigation | Status | Owner |
|---|---|---|---|---|---|---|---|---|---|
| PI-001 | [Description] | [What happens if this fails] | [1-10] | [1-10] | [1-10] | [S×O×D] | [Planned or implemented mitigation] | [Open | Mitigated | Accepted] | [Assignee] |

## Revision History

| Date | Change | Author | Amendment # |
|---|---|---|---|
| [Date] | Initial FMEA generated from Master Plan | [Author] | — |
```

---

## FMEA Amendment Proposal

Use this template when Ground Rule 9 is triggered — the AI has discovered a logical
impossibility in an existing constraint or identified a new systemic failure mode.
This document is submitted for human review. Code generation remains halted until the
amendment is approved or rejected.

```markdown
## FMEA Amendment Proposal [#]

**Date:** [Date]
**Submitted by:** [AI model name from Intelligence Roster, or human name]
**Triggering Task:** [Task ID and Issue #]
**Status:** [Proposed | Approved | Rejected]

### Type
[Constraint Conflict | New Failure Mode Identified]

### Description
[Detailed description of what was discovered. Be specific about the mechanical
conflict or the newly identified failure path.]

### Evidence
[What code, logic, or test result revealed this? Reference specific files, line
numbers, or architectural constraints.]

### Current Constraint (if modifying existing)
| ID | Current Rule | Current Severity | Current RPN |
|---|---|---|---|
| [PI-XXX] | [Current constraint text] | [S] | [RPN] |

### Proposed Change
[Exact proposed modification to the constraint, OR the new constraint to add.]

| ID | Proposed Rule | Proposed S | Proposed O | Proposed D | Proposed RPN |
|---|---|---|---|---|---|
| [PI-XXX] | [New constraint text] | [S] | [O] | [D] | [S×O×D] |

### Impact Assessment
- **Documents affected:** [List files requiring updates if approved]
- **Tasks affected:** [List Task IDs whose prompt headers reference this constraint]
- **Downstream risk:** [What changes if this amendment is approved]

### Recommendation
[What the AI recommends and why. The human decides.]
```
