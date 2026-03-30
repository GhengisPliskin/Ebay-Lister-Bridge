# CONTRIBUTING.md — Lister-Bridge Hybrid Agent

---

## Before You Start

No code or documentation may be generated without an active, assigned GitHub Issue (Ground Rule 1).

1. Check the [Issues](https://github.com/GhengisPliskin/Ebay-Lister-Bridge/issues) board for an open, unassigned issue matching your work.
2. Assign it to yourself and move it to **In Progress** on the Kanban board.
3. Load the corresponding prompt header from `docs/lister-bridge-prompt-headers.md` (if AI-assisted).

---

## Contribution Workflow

1. **Branch** from `main` using the convention: `task/<task-id>-short-description` (e.g., `task/0.2-drive-fetcher`).
2. **Write code** following the Code Comment Standard below.
3. **Log decisions** to `working/CODE_DECISIONS_PATCH.md` (never directly to `CODE_DECISION_LOG.md`).
4. **Open a PR** referencing the Issue (e.g., `Closes #2`).
5. **PR checklist** (reviewer verifies before merge):
   - [ ] Issue is referenced and linked
   - [ ] All new `.py` files have module-level docstrings
   - [ ] All new public functions have docstrings
   - [ ] All non-trivial logic blocks have block comments
   - [ ] No existing comments removed or truncated
   - [ ] `working/CODE_DECISIONS_PATCH.md` updated with any code decisions
   - [ ] `ARCHITECTURE.md` updated if structural drift occurred (Ground Rule 4)
   - [ ] FMEA constraint IDs cited for any FMEA-linked decisions (Ground Rule 5)

---

## Code Comment Standard

All `.py` files in this project must follow this format. These are acceptance criteria
on every task — they are not optional and are not individually negotiated.

### Module Docstring (required in every `.py` file)

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
FMEA Constraints Enforced: PI-XXX (write "None" if not applicable)
"""
```

### Function Docstring (required for every public function)

```python
def my_function(param: str) -> dict:
    """
    Brief description of what this function does.

    Args:
        param (str): Description of the parameter.

    Returns:
        dict: Description of the return value and its structure.

    Side Effects:
        List any side effects (file writes, API calls, global state changes).
        Write "None" if there are no side effects.

    FMEA Constraints:
        PI-XXX — Description of the constraint this function enforces.
        Write "None" if not applicable.
    """
```

### Block Comments (required before every non-trivial logic block)

```python
# Check the local cache before hitting the Drive API to avoid
# unnecessary quota consumption (PI-001 mitigation).
cached = check_cache(file_id)
if cached:
    return cached
```

### Comment Preservation Rule (C-007)

AI sessions and human contributors must not remove, truncate, or rewrite existing
comments. If a comment is inaccurate due to a code change, update it to reflect the
new behavior — do not delete it. Comment preservation is verified at every PR review.

---

## Ground Rules Reference

| # | Rule |
|---|---|
| 1 | No code or docs without an active, assigned Issue. |
| 2 | Code decisions → `working/CODE_DECISIONS_PATCH.md`. Merged at HUMAN gate. |
| 3 | State Kanban column change at start and end of every action. |
| 4 | `ARCHITECTURE.md` updated concurrently with any structural change. |
| 5 | FMEA constraint references in every affected decision. |
| 6 | Read template files before generating structured documents. |
| 7 | `spike` issues cannot reach Done without a linked formalization issue. |
| 8 | FMEA constraints are immutable during execution. |
| 9 | Constraint conflicts → HALT, propose FMEA Amendment. |
| 10 | Ingest a fresh repo map (Repomix) at the start of every execution session. |
| 11 | All `.py` files: module docstring, function docstrings, block comments. Never remove existing comments. |

Full ground rules with enforcement mechanisms are in `README.md` and the Master Plan.
