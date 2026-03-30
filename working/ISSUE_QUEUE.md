# ISSUE_QUEUE.md — GitHub Issue Transit Queue

Issues queued here are created via `gh issue create` during a Housekeeping session.
After creation, record the assigned issue number and clear the entry.

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

*(Queue is empty — no pending issues)*
