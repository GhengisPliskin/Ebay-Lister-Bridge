# KANBAN_SETUP.md — Board Configuration: Lister-Bridge Hybrid Agent

---

## Board Columns

| Column | Purpose | WIP Limit |
|---|---|---|
| Triage | New issues awaiting specification | None |
| Ready | Specified and unblocked | 10 |
| In Progress | Actively being worked | 5 |
| In Review | Awaiting human review (Two-Phase Commit gate) | 5 |
| Done | Completed and documented | None |
| Blocked | Unresolved dependencies | None |

---

## Label Taxonomy

| Group | Labels | Color |
|---|---|---|
| Type | `type:core`, `type:ai`, `type:api` | Blue `#0075ca` |
| Phase | `phase:0`, `phase:1`, `phase:2` | Purple `#7057ff` |
| Boundary | `human-only`, `ai-eligible`, `ai-with-review` | Green `#0e8a16` |
| Priority | `priority:high`, `priority:medium`, `priority:low` | Red `#b60205` / Orange `#e4e669` / Yellow `#fef2c0` |
| Spike | `spike` | Red `#d73a4a` |

---

## Spike Done-Lock

Spike issues are prohibited from moving to Done without a linked formalization issue.
This is enforced by two layers:

**Layer 1 — GitHub Project Automation (visual)**
In the GitHub Projects UI:
1. Open the project board.
2. Go to Settings → Workflows.
3. Add a workflow: "When item with label `spike` is moved to Done → move back to In Review and add comment: Spike issues require a formalization issue before Done."

**Layer 2 — CI Hard Enforcement**
`.github/workflows/spike-check.yml` runs on `issues` → `closed` events.
If the closing issue carries the `spike` label and has no linked formalization issue, the workflow fails and leaves a comment blocking closure.

See `.github/workflows/spike-check.yml` for the implementation.

---

## WIP Limit Enforcement

WIP limits are advisory (tracked by convention, not automated). The assignee is responsible for:
- Not starting a new In Progress issue when already at the limit.
- Moving blockers to the Blocked column promptly to free up WIP slots.

---

## Issue Creation Checklist

Before creating any issue, confirm:
- [ ] Task has a corresponding entry in the Task Registry (Master Plan §6)
- [ ] Labels are drawn from the taxonomy above (no ad-hoc labels)
- [ ] Acceptance criteria are boolean (true/false verifiable)
- [ ] Dependency issue numbers are referenced in the body

---

## Execution Order (Initial Issue Set)

Issues must be worked in dependency order:

```
#1 (0.1 — Scaffold)
    └── #2 (0.2 — Drive Fetcher)
            └── #3 (0.3 — Vision Extraction)
                    ├── #4 (0.4 — Margin-Guard)
                    │       └── #5 (0.5 — Terminal Loop)
                    └── #5 (0.5 — Terminal Loop)
                                └── #6 (0.6 — eBay GraphQL)
```
