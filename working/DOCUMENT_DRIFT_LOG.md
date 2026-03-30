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

*(Log is empty — no drift detected)*
