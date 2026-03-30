# KEY_DECISION_LOG.md — Lister-Bridge Hybrid Agent

All architectural decisions are recorded here. Code-level decisions go to
`working/CODE_DECISIONS_PATCH.md` and are merged here at HUMAN gates.

---

## DECISION 1 — Optimize for Margin & Accuracy over Speed

**Status:** RESOLVED

**Resolution:** Prioritize a >80% sell-through rate using Gemini's `thinking_level: HIGH`
and `media_resolution: HIGH`.

**Rationale:** Maximizes Gross Merchandise Value (GMV) and minimizes return risk. Speed
is secondary to listing quality for a low-volume, high-accuracy use case.

**FMEA Impact:** Directly mitigates PI-004 (Vision Agent misses defects) and PI-006
(Margin-Guard calculates unviable price) by using the highest-fidelity model configurations.

**Documents updated:**
- `ARCHITECTURE.md` — Intelligence Roster populated with tier assignments
- `CONSTRAINTS.md` — C-003 (Python environment) confirmed

**Downstream impact:**
- Tier 1 prompt headers must cap context preamble at 2000 tokens (32k window constraint).
- Tier 3 tasks must remain lightweight text operations only.

---

## DECISION 2 — Select Python as Core Environment

**Status:** RESOLVED

**Resolution:** Use Python for the local development environment and execution script.

**Rationale:** Best-in-class support for the Google GenAI SDK (`google-genai`),
Google Drive API (`google-api-python-client`), and terminal IO. No viable alternative
with equivalent library coverage.

**FMEA Impact:** None — purely infrastructural.

**Documents updated:**
- `CONSTRAINTS.md` — C-003 added

**Downstream impact:**
- All source files must be `.py`.
- `requirements.txt` is a required deliverable of Task 0.1.

---

## DECISION 3 — Adopt Google Drive for Asset Ingestion

**Status:** RESOLVED

**Resolution:** Image staging and archiving handled via Google Drive shared folders.

**Rationale:** Enables mobile phone photo drops without requiring a dedicated upload
server or local network transfer tooling. The user photographs items and drops them
into a shared Drive folder from any device.

**FMEA Impact:** Introduces PI-001 (Drive API sync failure/delay). Mitigation:
exponential backoff retries + local cache fallback (Task 0.2, R3).

**Documents updated:**
- `docs/FMEA.md` — PI-001 recorded
- `ARCHITECTURE.md` — Core/IO component defined

**Downstream impact:**
- Task 0.2 must implement local cache fallback before Task 0.3 can be started.
- `.repomixignore` must exclude Google Drive image payloads.

---

## DECISION 4 — Interactive Terminal for Human-in-the-Loop

**Status:** RESOLVED

**Resolution:** Use a CLI-based conversational loop instead of local Markdown file editing.

**Rationale:** Batched, point-in-time execution leveraging Gemini's conversational API
to resolve ambiguities. Terminal is sufficient for the single-user, low-volume use case.
A web UI would add unnecessary complexity.

**FMEA Impact:** Introduces PI-007 (user approves flawed payload) and PI-008 (terminal
overwhelms user with raw JSON). Mitigations: color-highlighted diff view requiring
`APPROVE` string (PI-007), human-readable summary table (PI-008).

**Documents updated:**
- `docs/FMEA.md` — PI-007, PI-008 recorded
- `ARCHITECTURE.md` — Orchestrator component defined

**Downstream impact:**
- Task 0.5 is the highest-RPN convergence point (PI-003 + PI-007 + PI-008).
- Terminal must use `colorama` or equivalent for color output.

---

## DECISION 5 — Adopt Repomix for Codebase Context

**Status:** RESOLVED

**Resolution:** Use Repomix for repository mapping. Configure `.repomixignore` to
exclude `.env`, image files, Google Drive payloads, and `working/` directory contents.

**Rationale:** Keeps context payloads within Tier 1/3 context windows (8k–32k tokens).
Supports Ground Rule 10 (Codebase State Synchronization) without manual file listing.

**FMEA Impact:** None directly. Supports PI-003 mitigation by keeping AI context
payloads small.

**Documents updated:**
- `.repomixignore` — Exclusion rules configured
- `repomix.config.json` — Repomix configuration file created

**Downstream impact:**
- All execution sessions must start with a fresh `repomix` output.
- `.repomixignore` must be maintained as new large binary or data files are added.

---

## DECISION 6 — Renumber Code Comment Constraints

**Status:** RESOLVED

**Resolution:** Code Comment Standard constraints numbered C-004 through C-007,
contiguous with existing C-001 through C-003.

**Rationale:** Eliminates dangling forward references (previously C-019 through C-022
in an earlier draft) and avoids reserving 15 unused constraint IDs. Contiguous
numbering reduces cognitive load when cross-referencing.

**FMEA Impact:** None — purely organizational.

**Documents updated:**
- `CONSTRAINTS.md` — C-004 through C-007 added
- `ARCHITECTURE.md` — Code Comment Standard section references C-004–C-007
- `CLAUDE.md` — Comment standard references C-004–C-007

**Downstream impact:**
- All prompt headers reference C-004–C-007 (not C-019–C-022).
- Ground Rule 11 references C-004–C-007.
