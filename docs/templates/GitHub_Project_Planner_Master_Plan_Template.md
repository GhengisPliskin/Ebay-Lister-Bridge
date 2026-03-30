# Master Project Plan Template

This is the generative seed for all downstream artifacts. Every section must be
completed during Phase 0. The confirmed Master Plan becomes the source of truth
for scaffolding generation, prompt header creation, and ongoing execution.

When generating a Master Plan, reproduce this structure exactly. Populate every section
from the Phase 0 interview. Mark sections as "[TBD — requires user input]" only if the
user explicitly deferred that decision.

**Ground Rule 6 Reminder:** You are reading this file because you MUST read it before
generating a Master Plan. Do not close this file and reconstruct the template from
memory.

---

```markdown
# Master Project Plan — [Project Name]

**Generated:** [Date]
**Status:** [Draft | Under Review | Confirmed]
**Version:** [1.0]

---

## 1. Project Intelligence Roster

This section is populated from Step 0.0 (Intelligence Profiling). The human defines
all model assignments. The AI is prohibited from self-assigning models or recommending
alternatives based on training data.

| Tier | Role | Assigned Model(s) | Max Context Window | Notes |
|---|---|---|---|---|
| **Tier 1** — Complex Reasoning & Multi-Constraint Logic | Architecture, FMEA analysis, integration planning, cross-cutting concerns | [Human-defined] | [Human-defined] | [Any usage constraints or preferences] |
| **Tier 2** — Standard Execution & Coding | Feature implementation, test writing, documentation, well-scoped tasks | [Human-defined] | [Human-defined] | |
| **Tier 3** — Boilerplate, Scaffolding, & Formatting | File scaffolding, template population, linting, simple transforms | [Human-defined] | [Human-defined] | |

### Context Window Implications
- Prompt headers for Tier [X] tasks must not exceed [Y] tokens of context preamble.
- Repository map configuration (Repomix / equivalent) must exclude files to stay
  within the smallest context window in active use.
- [Any additional constraints derived from the roster.]

---

## 2. Project Overview

### 2.1 Purpose
[One-paragraph description of what the project does and why it exists.]

### 2.2 Stakeholders
| Role | Name / Team | Responsibilities |
|---|---|---|
| [Owner / Lead] | [Name] | [Primary responsibilities] |
| [Contributor] | [Name] | [Scope of contribution] |

### 2.3 Success Criteria
[How will you know this project succeeded? List 3-5 measurable outcomes.]

---

## 3. Requirements

### 3.1 Functional Requirements
| ID | Requirement | Priority | Source |
|---|---|---|---|
| FR-001 | [Description] | [Must / Should / Could] | [Stakeholder / Doc] |

### 3.2 Non-Functional Requirements
| ID | Requirement | Category | Threshold |
|---|---|---|---|
| NFR-001 | [Description] | [Performance / Security / Accessibility / etc.] | [Measurable target] |
| NFR-002 | All `.py` files must include module-level docstrings, public function docstrings, and plain-English block comments on all non-trivial logic. AI sessions must not remove or truncate existing comments. | Code Quality | See `ARCHITECTURE.md` — "Code Comment Standard" section for format. Enforced via Ground Rule 11 and CONSTRAINTS.md C-019 through C-022. Zero exceptions. |

### 3.3 Constraints
| ID | Constraint | Type | Impact |
|---|---|---|---|
| C-001 | [Description] | [Tech Stack / Compliance / Timeline / Budget] | [What this prevents or mandates] |

---

## 4. Architecture & Directory Structure

### 4.1 High-Level Architecture
[Describe the system architecture in 2-3 paragraphs. Identify major components,
their responsibilities, and how they communicate.]

### 4.2 Directory Structure
```
[project-root]/
├── src/
│   ├── [component-a]/
│   └── [component-b]/
├── tests/
├── docs/
│   ├── FMEA.md
│   ├── KANBAN_SETUP.md
│   ├── templates/               # Skill reference templates (read-only after scaffolding)
│   │   ├── templates.md
│   │   └── master-plan-template.md
│   └── [additional docs]
├── working/                     # Ephemeral per-session scratch space
│   └── CODE_DECISIONS_PATCH.md  # Provisional decisions — merged into CODE_DECISION_LOG.md at HUMAN gate
├── .github/
│   └── workflows/
│       └── spike-check.yml      # Spike Done-Lock enforcement (Ground Rule 7)
├── CLAUDE.md                    # Claude Code session briefing — read automatically at every session start
├── CONTRIBUTING.md              # Code comment standard, contribution workflow, ground rules
├── ARCHITECTURE.md
├── CONSTRAINTS.md
├── KEY_DECISION_LOG.md
├── CODE_DECISION_LOG.md
└── README.md
```

### 4.3 Component Descriptions
| Component | Responsibility | Interfaces | Key Files |
|---|---|---|---|
| [Name] | [What it does] | [What it talks to] | [Primary file paths] |

---

## 5. Risk Register (FMEA)

> **If the user opted for the degraded path (no FMEA), replace this section with:**
> "FMEA register is unpopulated. Ground Rules 5, 8, and 9 have reduced enforcement
> until the register is completed. An empty template has been scaffolded at
> `docs/FMEA.md`."

| ID | Failure Mode | Potential Effect | S | O | D | RPN | Mitigation | Status |
|---|---|---|---|---|---|---|---|---|
| PI-001 | [Description] | [Consequence] | [1-10] | [1-10] | [1-10] | [calc] | [Plan] | [Open] |

**Action threshold:** RPN ≥ 100 requires mitigation before any dependent task begins.

**Amendment protocol:** Changes to this register during execution require an FMEA
Amendment Proposal (Ground Rule 9). See `docs/templates/templates.md` for the template.

---

## 6. Task Registry

This is the master list of all work items. Each row becomes a GitHub Issue and a
Prompt Header.

| Task ID | Task Name | Component | Complexity | Tier | Depends On | Delivers To | FMEA Refs | Boundary | Phase |
|---|---|---|---|---|---|---|---|---|---|
| 0.1 | [Name] | [Component] | [L/M/H] | [1/2/3] | [Task IDs] | [Task IDs] | [PI-XXX] | [human-gate / ai-eligible / ai-with-review] | [0/1/2] |

### Two-Phase Commit Applicability
- Tasks marked Tier 1 or Tier 2: Two-Phase Commit is mandatory.
- Tasks marked Tier 3: Two-Phase Commit applies only if FMEA Refs is non-empty.
- Tasks tagged `[SPIKE]`: exempt from Two-Phase Commit (Ground Rule 7).

### Dependency Graph
[Describe the critical path and any parallelizable task clusters. A text-based
dependency graph is acceptable; a Mermaid diagram is preferred if the environment
supports rendering.]

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

### Spike Constraint (Ground Rule 7)
Issues labeled `spike` cannot move to "Done" until a linked formalization issue
reaches "In Review."

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

---

## 8. Operational Ground Rules

These rules are non-negotiable for all contributors (human and AI).

| # | Rule | Enforcement Mechanism |
|---|---|---|
| 1 | **Issue Binding** — No code or documentation generated without an active, assigned Issue. | PR template requires Issue reference. AI prompt headers include Issue ID. |
| 2 | **Decision Logging** — All architectural decisions → KEY_DECISION_LOG.md. All code decisions → `working/CODE_DECISIONS_PATCH.md` during active development. Patch merged into CODE_DECISION_LOG.md at HUMAN gate when phase passes all tests and receives user sign-off. | PR review checklist includes decision log verification and patch merge confirmation. |
| 3 | **State Synchronization** — AI agents explicitly state Kanban column changes at start and end of every action. | Prompt headers include State Sync section. |
| 4 | **Source Truth** — ARCHITECTURE.md updated concurrently with any structural change. | PR review checklist includes architecture drift check. |
| 5 | **Constraint Traceability** — Any decision impacting an FMEA constraint references the FMEA ID in the decision log and prompt header. | FMEA labels on Issues. Prompt headers include FMEA reference field. |
| 6 | **Template Adherence** — AI must execute a file read on templates before generating any project file. No reconstruction from memory. | Embedded in SKILL.md workflow. |
| 7 | **[SPIKE] Exemption** — Spike issues bypass structural requirements. Formalization required before Done. | `spike` label + Kanban Done-lock. |
| 8 | **Execution-Locked FMEA** — FMEA constraints are immutable during task execution. No ad hoc alterations. | Prompt headers reference constraints with immutability notice. |
| 9 | **FMEA Amendment Protocol** — Constraint conflicts or new failure modes halt execution for formal human review. | FMEA Amendment Proposal template. |
| 10 | **Codebase State Sync** — Fresh repository map required at start of execution sessions. | Prompt header preamble check. |

---

## 9. Documentation Framework

| Document | Status | Initial Content Source |
|---|---|---|
| `README.md` | [To Generate / Generated] | §2 + §4.2 + §8 |
| `ARCHITECTURE.md` | [To Generate / Generated] | §4 |
| `CONSTRAINTS.md` | [To Generate / Generated] | §3.2 + §3.3 |
| `docs/FMEA.md` | [To Generate / Generated] | §5 |
| `KEY_DECISION_LOG.md` | [To Generate / Generated] | Phase 0 decisions |
| `CODE_DECISION_LOG.md` | [To Generate / Generated] | Empty (initialized with template) |
| `docs/KANBAN_SETUP.md` | [To Generate / Generated] | §7 |
| `working/CODE_DECISIONS_PATCH.md` | [To Generate / Generated] | Empty (initialized with template) — AI sessions write provisional decisions here; merged into CODE_DECISION_LOG.md at HUMAN gate |
| `working/ISSUE_QUEUE.md` | [To Generate / Generated] | Empty (initialized with format header) — transit queue for GitHub Issue creation, consumed by Housekeeping sessions |
| `working/DOCUMENT_DRIFT_LOG.md` | [To Generate / Generated] | Empty (initialized with format header) — stale-fact registry, consumed by Housekeeping sessions |

### Conditional Documents
| Document | Status | Condition |
|---|---|---|
| `.repomixignore` | [To Generate / Generated / N/A] | User confirmed Repomix usage |
| `repomix.config.json` | [To Generate / Generated / N/A] | User confirmed Repomix usage |
| `docs/proposals/` | [To Generate / Generated / N/A] | Empty directory — scope change proposals (create only if project anticipates scope evolution) |

---

## 10. Phase 0 Decisions

Record any architectural or tooling decisions made during planning here. These seed
the KEY_DECISION_LOG.md during scaffolding generation.

### DECISION 1 — [Title]
**Status:** [Proposed | RESOLVED]
**Resolution:** [What was decided]
**Rationale:** [Why]
**FMEA Impact:** [IDs or "None"]
**Downstream impact:** [Effects]

[Add additional decisions as needed]
```
