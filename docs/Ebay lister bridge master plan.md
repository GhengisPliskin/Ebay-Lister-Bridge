# Master Project Plan — Lister-Bridge Hybrid Agent

**Generated:** March 29, 2026  
**Status:** Confirmed  
**Version:** 1.1  
**Revision Note:** Incorporated Phase 1 calibration feedback — Ground Rule 11 added, FMEA cross-references populated, FMEA statuses corrected, constraint IDs renumbered, Section 9 formatting fixed, Repomix confirmed.

---

## 1. Project Intelligence Roster

This section is populated from Step 0.0 (Intelligence Profiling). The human defines all model assignments.

| Tier | Role | Assigned Model(s) | Max Context Window | Notes |
|---|---|---|---|---|
| **Tier 1** — Complex Reasoning & Multi-Constraint Logic | Margin-Guard Pricing & Market Analysis, 2% sub-ceiling GMV rule enforcement | Gemini 3 Flash (`thinking_level: HIGH`) | 32k tokens | Text-only context to minimize cost/latency while maximizing reasoning depth. |
| **Tier 2** — Standard Execution & Coding | Image Extraction, Condition Assessment, Defect ID | Gemini 3 Flash (`media_resolution: HIGH`) | 1M tokens | Multimodal inputs; must output exact 2026 eBay GraphQL JSON schema. |
| **Tier 3** — Boilerplate, Scaffolding, & Formatting | eBay GraphQL formatting, Title SEO generation | Standard Gemini 3 Flash | 8k tokens | Lightweight text processing. |

### Context Window Implications
- Prompt headers for Tier 1 tasks must not exceed 2000 tokens of context preamble.
- Repository map configuration (Repomix) must exclude image files, Google Drive payloads, and `working/` contents to stay within the smallest context window in active use.
- The interactive terminal loop must maintain conversational context but should flush previous item contexts after a listing is approved to prevent token bloat.

---

## 2. Project Overview

### 2.1 Purpose
The Lister-Bridge Hybrid Agent is an automated market research and eBay listing tool. It monitors Google Drive for incoming item photos, utilizes Gemini Multimodal Vision to extract details and establish a GMV-optimized "Margin-Guard" price, and uses an interactive terminal interface to resolve ambiguities with the user before publishing directly to eBay via the GraphQL API.

### 2.2 Stakeholders
| Role | Name / Team | Responsibilities |
|---|---|---|
| Owner / Lead | User | Final listing approval, answering terminal prompts, physical photo capture, API credential management |
| Contributor | AI Agents | Code generation, schema formatting, market analysis, visual extraction |

### 2.3 Success Criteria
- **Margin & Velocity:** `marginGuardPrice` results in a 30-day sell-through rate of >80%.
- **Data Accuracy:** Zero listings flagged by eBay for inaccurate Item Specifics.
- **Vision Reliability:** The Vision Agent successfully identifies and documents 95% of visible physical defects.

---

## 3. Requirements

### 3.1 Functional Requirements
| ID | Requirement | Priority | Source |
|---|---|---|---|
| FR-001 | The system must use `.env` files and `.gitignore` to securely manage Gemini API keys, Google Service Account JSONs, and eBay OAuth 2.0 credentials. | Must | Architecture Decision |
| FR-002 | The system must never execute the eBay GraphQL `startListingPreviewsCreation` mutation without explicit human confirmation via the CLI terminal. | Must | Architecture Decision |
| FR-003 | Image ingestion must be handled via the Google Drive API, pulling from a designated staging folder. | Must | Architecture Decision |
| FR-004 | The system must utilize a multi-turn chat sequence in the terminal to ask the user for missing details (e.g., obscured model numbers) before finalizing the listing. | Must | Architecture Decision |

### 3.2 Non-Functional Requirements
| ID | Requirement | Category | Threshold |
|---|---|---|---|
| NFR-001 | The interactive terminal interface must clearly display the AI's question, proposed pricing, and status without overwhelming the user with raw JSON. | Usability | N/A |
| NFR-002 | All `.py` files must include module-level docstrings, public function docstrings, and plain-English block comments on all non-trivial logic. AI sessions must not remove or truncate existing comments. | Code Quality | See `ARCHITECTURE.md` — "Code Comment Standard" section for format. Enforced via Ground Rule 11 and CONSTRAINTS.md C-004 through C-007. Zero exceptions. |

### 3.3 Constraints
| ID | Constraint | Type | Impact |
|---|---|---|---|
| C-001 | FMEA Deferral | Procedural | Section 5 is populated. Risk analysis is active via the FMEA register. |
| C-002 | eBay GraphQL Requirement | Tech Stack | Must use the 2026 eBay GraphQL schema, specifically the `startListingPreviewsCreation` mutation and `mappingReferenceID` for error tracking. |
| C-003 | Python Environment | Tech Stack | Local execution environment restricted to Python to leverage `google-genai` and `google-api-python-client` libraries. |
| C-004 | Module Docstrings Required | Code Quality | Every `.py` file must begin with a module-level docstring describing the file's purpose, primary responsibilities, and key interfaces. |
| C-005 | Function Docstrings Required | Code Quality | Every public function must include a docstring describing parameters, return values, side effects, and any FMEA constraints it enforces. |
| C-006 | Block Comments Required | Code Quality | All non-trivial logic blocks (conditionals, loops, data transformations, API calls) must include a preceding plain-English block comment explaining intent. |
| C-007 | Comment Preservation | Code Quality | AI sessions must not remove, truncate, or rewrite existing comments. Comment preservation is verified at every code review gate. |

---

## 4. Architecture & Directory Structure

### 4.1 High-Level Architecture
The system is a Python-based CLI application. The **Orchestrator** polls a designated Google Drive folder for new item batches. For each item, the **Vision Agent** (Gemini `media_resolution: HIGH`) extracts visual data, and the **Logic Agent** (Gemini `thinking_level: HIGH`) calculates the Margin-Guard price.

If data is missing, the Orchestrator pauses and drops into an interactive CLI loop, prompting the user for clarification. Once the user approves the generated listing data in the terminal, the payload is formatted to strictly match the 2026 schema and pushed to eBay via the GraphQL API.

### 4.2 Directory Structure
```text
lister-bridge/
├── src/
│   ├── core/
│   │   ├── orchestrator.py      # Main CLI loop and Drive API integration
│   │   └── drive_fetcher.py     # Handles Google Drive IO
│   ├── ai/
│   │   ├── vision_agent.py      # High-res image ingestion & Gemini extraction
│   │   └── margin_guard.py      # Pricing logic and market analysis
│   └── api/
│       └── ebay_graphql.py      # Formats and posts startListingPreviewsCreation
├── tests/
├── docs/
│   ├── FMEA.md
│   ├── KANBAN_SETUP.md
│   ├── templates/               # Skill reference templates (read-only after scaffolding)
│   │   ├── templates.md
│   │   └── master-plan-template.md
│   └── proposals/
├── working/                     # Ephemeral per-session scratch space
│   └── CODE_DECISIONS_PATCH.md  # Provisional decisions — merged into CODE_DECISION_LOG.md at HUMAN gate
├── .github/
│   └── workflows/
│       └── spike-check.yml      # Spike Done-Lock enforcement (Ground Rule 7)
├── CLAUDE.md                    # Session briefing — read automatically at every session start
├── CONTRIBUTING.md              # Code comment standard, contribution workflow, ground rules
├── ARCHITECTURE.md
├── CONSTRAINTS.md
├── KEY_DECISION_LOG.md
├── CODE_DECISION_LOG.md
├── .env                         # SECURE: API Keys & OAuth (Ignored in Git)
├── .repomixignore               # Excludes .env, images, Drive payloads, working/
├── repomix.config.json           # Repomix configuration
├── requirements.txt
└── README.md
```

### 4.3 Component Descriptions

| Component | Responsibility | Interfaces | Key Files |
|---|---|---|---|
| Core/IO | Fetching images from Drive, managing the CLI loop | Google Drive API, User Terminal | orchestrator.py, drive_fetcher.py |
| AI/Vision | Extracting item specifics, condition, and defects | Core/IO, Gemini Multimodal | vision_agent.py |
| AI/Logic | Establishing the Margin-Guard price | AI/Vision, Gemini standard | margin_guard.py |
| API/eBay | Transforming internal JSON to GraphQL schema and posting | Core/IO, eBay GraphQL API | ebay_graphql.py |

---

## 5. Risk Register (FMEA)

| ID | Failure Mode | Potential Effect | S | O | D | RPN | Mitigation | Status | Owner |
|---|---|---|---|---|---|---|---|---|---|
| PI-001 | Google Drive API sync failure/delay | Images or source files unavailable, halting listing pipeline | 6 | 5 | 3 | 90 | Implement local cache fallback and exponential backoff retries | Open — mitigation planned | DevOps/Data Eng |
| PI-002 | Accidental exposure of `.env` credentials | Malicious actors drain API credits or hijack eBay account | 10 | 2 | 4 | 80 | Add `.env` to `.gitignore`; script automated pre-commit hooks to scan for secrets | Mitigated | Security/DevOps |
| PI-003 | Context window token bloat | Orchestrator loop crashes midway through a session | 8 | 6 | 5 | 240 | State Machine Flush: Clear `messages` array of previous item JSON/images after approval | Open — mitigation planned | AI Engineer |
| PI-004 | Vision Agent misses physical defects | Listing goes live with hidden damage, leading to INAD returns | 8 | 4 | 7 | 224 | Negative Confirmation Prompting: Force structured JSON output `defects_found: []` | Open — mitigation planned | Prompt Engineer |
| PI-005 | Vision Agent hallucinates Item Specifics | Data accuracy flags on eBay; poor search visibility | 7 | 6 | 4 | 168 | Strict JSON Schema enforcement mapped to eBay category enums; drop invalid values | Open — mitigation planned | AI Engineer |
| PI-006 | Margin-Guard calculates unviable price | Item fails >80% 30-day sell-through rate goal | 8 | 3 | 6 | 144 | Hardcode deterministic floor function `(Cost+Fees)*1.15` that overrides AI | Open — mitigation planned | Product Owner |
| PI-007 | User approves flawed payload | Bad listing goes live on eBay | 7 | 5 | 8 | 280 | CLI "Diff" View: Highlight critical changes in color, require typing `APPROVE` | Open — mitigation planned | UI/CLI Dev |
| PI-008 | Terminal overwhelms user with raw JSON | User fatigue leading to "blind approvals" | 5 | 8 | 4 | 160 | Parse JSON into a clean, human-readable summary table in the CLI | Open — mitigation planned | UI/CLI Dev |
| PI-009 | Payload fails 2026 GraphQL schema | Mutation rejection by eBay API | 7 | 5 | 2 | 70 | Enforce strict JSON Schema validation before sending the API request | Open — mitigation planned | Integration Dev |

### Revision History

| Date | Change | Author | Amendment # |
|---|---|---|---|
| March 29, 2026 | Initial FMEA generated from Master Plan | AI Systems Reliability Engineer | — |
| March 29, 2026 | Assigned role-based owners to open risks | AI Systems Reliability Engineer | 1 |
| March 29, 2026 | Added architectural mitigation plans for all High-Risk (RPN ≥ 100) items | AI Systems Reliability Engineer | 2 |
| March 29, 2026 | Finalized statuses for sub-100 RPN items based on SRE recommendations | AI Systems Reliability Engineer | 3 |
| March 29, 2026 | Corrected statuses: items with unbuilt mitigations moved from Mitigated to Open — mitigation planned | Calibration Review | 4 |

---

## 6. Task Registry

This is the master list of all work items. Each row becomes a GitHub Issue and a Prompt Header.

| Task ID | Task Name | Component | Complexity | Tier | Depends On | Delivers To | FMEA Refs | Boundary | Phase |
|---|---|---|---|---|---|---|---|---|---|
| 0.1 | Scaffold Repo & Configure Secrets | Core/Security | Low | 3 | None | 0.2, 0.5 | PI-002 | human-only | 0 |
| 0.2 | Implement Google Drive API Fetcher | Core/IO | Medium | 2 | 0.1 | 0.3 | PI-001 | ai-eligible | 1 |
| 0.3 | Build Gemini Vision Extraction Layer | AI/Vision | High | 2 | 0.2 | 0.4 | PI-004, PI-005 | ai-with-review | 1 |
| 0.4 | Implement Margin-Guard Pricing Logic | AI/Logic | High | 1 | 0.3 | 0.5 | PI-006 | ai-with-review | 1 |
| 0.5 | Build Interactive Terminal Q&A Loop | Core/IO | Medium | 2 | 0.3, 0.4 | 0.6 | PI-003, PI-007, PI-008 | ai-eligible | 2 |
| 0.6 | Integrate eBay GraphQL Previews | API/eBay | High | 1 | 0.1, 0.5 | None | PI-009 | ai-with-review | 2 |

---

## 7. Kanban Board Configuration

### Columns

| Column | Purpose | WIP Limit |
|---|---|---|
| Triage | New issues awaiting specification | None |
| Ready | Specified and unblocked | 10 |
| In Progress | Actively being worked | 5 |
| In Review | Awaiting human review | 5 |
| Done | Completed and documented | None |
| Blocked | Unresolved dependencies | None |

### Label Taxonomy

- **Components:** comp:core, comp:ai, comp:api
- **Complexity:** complexity:low, complexity:medium, complexity:high
- **Tier:** tier:1, tier:2, tier:3
- **FMEA:** fmea:[ID] for tasks linked to failure modes
- **Boundary:** human-only, ai-eligible, ai-with-review
- **Phase:** phase:0, phase:1, phase:2
- **Spike:** spike for exploratory tasks under Ground Rule 7

---

## 8. Operational Ground Rules

| # | Rule | Enforcement Mechanism |
|---|---|---|
| 1 | **Issue Binding** — No code or documentation generated without an active, assigned Issue. | PR template requires Issue reference. AI prompt headers include Issue ID. |
| 2 | **Decision Logging** — All architectural decisions → KEY_DECISION_LOG.md. All code decisions → working/CODE_DECISIONS_PATCH.md. Merged into CODE_DECISION_LOG.md at HUMAN gate. | PR review checklist includes decision log verification. |
| 3 | **State Synchronization** — AI explicitly states Kanban column changes at start and end of action. | Prompt headers include State Sync section. |
| 4 | **Source Truth** — ARCHITECTURE.md updated concurrently with any structural change. | PR review checklist includes architecture drift check. |
| 5 | **Constraint Traceability** — Decisions impacting FMEA reference the FMEA ID. | FMEA labels on Issues. |
| 6 | **Template Adherence** — AI must read templates before generating files. No memory reconstruction. | Embedded in workflow. |
| 7 | **[SPIKE] Exemption** — Spike issues bypass structural requirements. Formalization required before Done. | spike label + Kanban Done-lock. |
| 8 | **Execution-Locked FMEA** — FMEA constraints are immutable during task execution. | Prompt headers reference constraints with immutability notice. |
| 9 | **FMEA Amendment Protocol** — Constraint conflicts halt execution for human review. | FMEA Amendment Proposal template. |
| 10 | **Codebase State Sync** — Fresh repository map required at start of execution sessions. | Prompt header preamble check. |
| 11 | **Code Comment Standard** — All `.py` files must include module-level docstrings, public function docstrings, and plain-English block comments on all non-trivial logic. AI sessions must not remove or truncate existing comments. | Enforced via CONSTRAINTS.md C-004 through C-007. Standing acceptance criterion on all tasks. |

---

## 9. Documentation Framework

| Document | Status | Initial Content Source |
|---|---|---|
| `README.md` | To Generate | §2 + §4.2 + §8 |
| `ARCHITECTURE.md` | To Generate | §4 |
| `CONSTRAINTS.md` | To Generate | §3.2 + §3.3 |
| `docs/FMEA.md` | To Generate | §5 |
| `KEY_DECISION_LOG.md` | To Generate | Phase 0 decisions |
| `CODE_DECISION_LOG.md` | To Generate | Empty (initialized with template) |
| `docs/KANBAN_SETUP.md` | To Generate | §7 |
| `working/CODE_DECISIONS_PATCH.md` | To Generate | Empty (initialized with template) |

### Conditional Documents

| Document | Status | Condition |
|---|---|---|
| `.repomixignore` | Confirmed | User confirmed Repomix usage |
| `repomix.config.json` | Confirmed | User confirmed Repomix usage |

---

## 10. Phase 0 Decisions

### DECISION 1 — Optimize for Margin & Accuracy over Speed

**Status:** RESOLVED

**Resolution:** Prioritize a >80% sell-through rate using Gemini's thinking_level: HIGH and media_resolution: HIGH.

**Rationale:** Maximizes Gross Merchandise Value (GMV) and minimizes return risk.

### DECISION 2 — Select Python as Core Environment

**Status:** RESOLVED

**Resolution:** Use Python for the local development environment and execution script.

**Rationale:** Best-in-class support for the Google GenAI SDK, Google Drive API, and terminal IO.

### DECISION 3 — Adopt Google Drive for Asset Ingestion

**Status:** RESOLVED

**Resolution:** Image staging/archiving handled via Google Drive shared folders.

**Rationale:** Enables mobile phone photo drops.

### DECISION 4 — Interactive Terminal for Human-in-the-Loop

**Status:** RESOLVED

**Resolution:** Use a CLI-based conversational loop instead of local Markdown file editing.

**Rationale:** Batched, point-in-time execution leveraging Gemini's conversational API to resolve ambiguities.

### DECISION 5 — Adopt Repomix for Codebase Context

**Status:** RESOLVED

**Resolution:** Use Repomix for repository mapping. Configure `.repomixignore` to exclude `.env`, image files, Google Drive payloads, and `working/` directory contents.

**Rationale:** Keeps context payloads within Tier 1/3 context windows (8k–32k tokens). Supports Ground Rule 10.

### DECISION 6 — Renumber Code Comment Constraints

**Status:** RESOLVED

**Resolution:** Code Comment Standard constraints numbered C-004 through C-007, contiguous with existing C-001 through C-003.

**Rationale:** Eliminates dangling forward references (previously C-019 through C-022) and avoids reserving 15 unused constraint IDs.

---

---

---

# TRACK A — DOCUMENT TEMPLATES

*(Save these formats in docs/templates/templates.md for AI reference during development)*

## KEY_DECISION_LOG.md

```markdown
## DECISION [#] — [Short Title]

**Status:** [Proposed | RESOLVED — Option [X] selected | Rejected | Superseded]

**Resolution:** [What is the specific action being taken or architecture being adopted? State clearly.]

**Rationale:** [Why is this the optimal path? Cite specific evidence, performance metrics, or cognitive load reductions.]

**FMEA Impact:** [List any FMEA constraints altered, mitigated, or introduced. Write "None" if purely infrastructural.]

**Documents updated:**
- `[Filename.ext]` — [Brief description of what changed in this file]

**Downstream impact:**
- [List specific cascading effects or contingencies triggered by this decision.]
```

---

## CODE_DECISION_LOG.md

*(Updates merged from working/CODE_DECISIONS_PATCH.md at HUMAN gates)*

```markdown
# Code Decision Log

## [Category Name]

| # | Decision | Rationale | If This Breaks, Check... |
|---|----------|-----------|--------------------------|
| D-[XX] | [Brief technical description] | [Why chosen over alternatives] | [Specific debugging heuristic] |

## Assumptions Register

| # | Status | Assumption | What Breaks If Wrong |
|---|--------|-----------|----------------------|
| A-[XX] | [UNVERIFIED | CONFIRMED | INVALIDATED] | [State the assumption] | [Consequence and required refactoring] |
```

---

## SESSION_PROMPT_HEADER.md

*(Instruction set for individual AI task execution)*

```markdown
## Session [X.Y] — [Task Name]

| | |
|---|---|
| **Task ID** | [X.Y] |
| **Component** | [Target Component/File Path] |
| **Model Tier** | [Tier 1 / Tier 2 / Tier 3] |
| **Depends On** | [Prerequisite Task IDs, or "None"] |
| **Delivers To** | [Downstream Task IDs, or "None"] |
| **Reference** | [Specific ARCHITECTURE.md sections, FMEA Constraint IDs] |

### Role
[Define the exact persona required]

### Context
[Explain the "why" of the task. Detail specific failure modes being prevented.]

> **Relevant Specs / FMEA Constraints**
> - [Constraint ID] — [Severity] — [Mechanical rule this task must satisfy]
>
> **Ground Rule 8 applies:** These constraints are immutable during execution. If a constraint is logically impossible, HALT and invoke Ground Rule 9.

### Requirements
**R1 — [Requirement Title]**
[Technical implementation details.]

### Ground Rule Compliance
- **Issue Binding:** This task is bound to Issue #[X].
- **Decision Logging:** Write all code decisions to `working/CODE_DECISIONS_PATCH.md`. Do not write directly to `CODE_DECISION_LOG.md`.
- **State Sync:** Move Kanban card from [Column A] → [Column B] at start; [Column B] → [Column C] at completion.
- **Comment Standard:** Ground Rule 11 and C-004 through C-007 apply. All new `.py` files require module-level docstrings. All new functions require docstrings. All non-trivial logic requires block comments. No existing comments may be removed or truncated.

> **EXIT CONDITION — Acceptance Criteria**
> - [ ] [Boolean criterion — must be verifiable as true/false]
> - [ ] All referenced documentation updated per Ground Rule 4
> - [ ] All code decisions written to `working/CODE_DECISIONS_PATCH.md`
> - [ ] All new `.py` files have module-level docstrings
> - [ ] All non-trivial new logic blocks have plain-English block comments
> - [ ] No existing comments removed or truncated

**PHASE 1: Execution**
1. Generate or modify the required code files per the Requirements above.
2. Output the exact string: `[AWAITING_HUMAN_APPROVAL: Code generation complete. Please test and verify.]`
3. HALT completely. Do not proceed to Phase 2.

**PHASE 2: Documentation (Execute ONLY after human replies "Approved")**
1. Audit the final, approved code against the current FMEA constraints.
2. Generate the required `working/CODE_DECISIONS_PATCH.md` entry.
3. Generate an `ARCHITECTURE_PATCH.md` if structural drift occurred.
```

---

## ARCHITECTURE_PATCH.md

```markdown
## Architecture Patch [#]

**Target Document:** `ARCHITECTURE.md`
**Triggering Decision:** [Reference KEY_DECISION_LOG entry or Phase requirement]

### Section to Modify: [Exact Heading Name]

**Current Text/Structure:**
`[Paste current state]`

**Proposed Replacement:**
`[New state]`

**Rationale for Patch:**
[Why this structural change is necessary.]
```

---

## FMEA Amendment Proposal

```markdown
## FMEA Amendment Proposal [#]

**Date:** [Date]
**Triggering Task:** [Task ID and Issue #]
**Status:** [Proposed | Approved | Rejected]

### Type
[Constraint Conflict | New Failure Mode Identified]

### Description
[Detailed description of what was discovered.]

### Proposed Change
| ID | Proposed Rule | Proposed S | Proposed O | Proposed D | Proposed RPN |
|---|---|---|---|---|---|
| [PI-XXX] | [New constraint text] | [S] | [O] | [D] | [S×O×D] |

### Recommendation
[What the AI recommends and why. The human decides.]
```
