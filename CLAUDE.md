# CLAUDE.md — Lister-Bridge Hybrid Agent Session Briefing

This file is read automatically by Claude Code at every session start.
Read it completely before taking any action.

---

## Project Identity

**Repo:** `GhengisPliskin/Ebay-Lister-Bridge`
**Stack:** Python 3, Google GenAI SDK, Google Drive API, eBay GraphQL API
**Master Plan:** `docs/Ebay lister bridge master plan.md`

---

## Session Types

There are two distinct session types. Determine which one applies before starting.

### Execution Session

Purpose: Code generation and task execution against an open GitHub Issue.

**Startup sequence:**
1. Confirm the active Issue number and load the corresponding prompt header from `docs/lister-bridge-prompt-headers.md`.
2. If outside an AI-native IDE, request a current Repomix output (Ground Rule 10).
3. State the Kanban column move: `[Current Column] → In Progress`.
4. Proceed only within the scope of the active Issue.

**File write locations during execution:**
- Code decisions → `working/CODE_DECISIONS_PATCH.md` (never directly to `CODE_DECISION_LOG.md`)
- New Issues discovered → `working/ISSUE_QUEUE.md`
- Stale facts detected → `working/DOCUMENT_DRIFT_LOG.md`

### Housekeeping Session

Purpose: Process queued work from `working/` files. No code generation. No task execution.

**Startup sequence:**
1. Read `working/ISSUE_QUEUE.md` — create any queued GitHub Issues via `gh issue create`.
2. Read `working/DOCUMENT_DRIFT_LOG.md` — patch stale facts in listed documents.
3. Commit all changes with a descriptive message summarizing actions taken.
4. Reset processed entries from both queue files.

Trigger a Housekeeping session after any planning session or phase gate where queues have accumulated.

---

## Ground Rules (Quick Reference)

| # | Rule |
|---|---|
| 1 | No code or docs without an active, assigned Issue. |
| 2 | Code decisions → `working/CODE_DECISIONS_PATCH.md`. Merged at HUMAN gate. |
| 3 | State Kanban column change at start and end of every action. |
| 4 | `ARCHITECTURE.md` updated concurrently with any structural change. |
| 5 | FMEA constraint references (e.g., PI-001) in every affected decision. |
| 6 | Read template files before generating structured documents. |
| 7 | `spike` issues cannot reach Done without a linked formalization issue. |
| 8 | FMEA constraints are immutable during execution. |
| 9 | Constraint conflicts → HALT, propose FMEA Amendment. |
| 10 | Ingest a fresh repo map (Repomix) at the start of every execution session. |
| 11 | All `.py` files: module docstring, function docstrings, block comments. Never remove or truncate existing comments. |

---

## Code Comment Standard (Ground Rule 11)

Every `.py` file must include:

```python
"""
Module: filename.py
Purpose: One sentence describing what this module does.
Primary Responsibilities:
  - Responsibility 1
  - Responsibility 2
Key Interfaces:
  - Input: describe inputs
  - Output: describe outputs
FMEA Constraints Enforced: PI-XXX (if applicable)
"""

def my_function(param):
    """
    Brief description of what this function does.

    Args:
        param: Description of the parameter.

    Returns:
        Description of the return value.

    Side Effects:
        Any side effects (file writes, API calls, state changes).

    FMEA Constraints:
        PI-XXX — Description of the constraint this function enforces.
    """
    # Plain-English explanation of what this block does and why
    result = do_something(param)
    return result
```

AI sessions must not remove, truncate, or rewrite existing comments.
Comment presence and preservation are standing acceptance criteria on all tasks.

---

## Two-Phase Commit (Tier 1 & Tier 2 tasks)

**Phase 1 — Execution:**
Generate the required code. Output the exact string:
`[AWAITING_HUMAN_APPROVAL: Code generation complete. Please test and verify.]`
Then HALT completely. Do not proceed.

**Phase 2 — Documentation (only after human replies "Approved"):**
1. Audit code against FMEA constraints.
2. Write decisions to `working/CODE_DECISIONS_PATCH.md`.
3. Generate `ARCHITECTURE_PATCH.md` if structural drift occurred.

---

## Drift Detection Responsibility

If any session changes a project-level fact (constraint text, task count, phase status,
framework name, file path, directory structure), log all other documents containing the
stale version of that fact to `working/DOCUMENT_DRIFT_LOG.md` before ending the session.

Format:
```
## Drift Entry — [Date]
**Changed fact:** [Old value] → [New value]
**Stale documents:** [List of files that still reference the old value]
```
