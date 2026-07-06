# FMEA.md — Risk Register: Lister-Bridge Hybrid Agent

**Status:** Active — Ground Rules 5, 8, and 9 in full enforcement.
**Amendment Protocol:** Any proposed change requires a FMEA Amendment Proposal (Ground Rule 9) approved by the human owner before taking effect.

---

## Risk Register

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
| PI-009 | Payload fails REST Sell Inventory / Media API validation | Request rejection by eBay API (`createInventoryItem`/`createOffer`/`publishOffer`) | 7 | 5 | 2 | 70 | Enforce strict pre-submit field validation before sending the API request | Open — mitigation planned | Integration Dev |

---

## High-Risk Items (RPN ≥ 100)

| ID | RPN | Primary Mitigation Task |
|---|---|---|
| PI-007 | 280 | Task 0.5 — `APPROVE` gate + color diff view |
| PI-003 | 240 | Task 0.5 — Context flush after each listing |
| PI-004 | 224 | Task 0.3 — Negative confirmation prompting |
| PI-005 | 168 | Task 0.3 — JSON schema enforcement |
| PI-008 | 160 | Task 0.5 — Human-readable summary table |
| PI-006 | 144 | Task 0.4 — Deterministic floor function |

---

## Revision History

| Date | Change | Author | Amendment # |
|---|---|---|---|
| March 29, 2026 | Initial FMEA generated from Master Plan | AI Systems Reliability Engineer | — |
| March 29, 2026 | Assigned role-based owners to open risks | AI Systems Reliability Engineer | 1 |
| March 29, 2026 | Added architectural mitigation plans for all High-Risk (RPN ≥ 100) items | AI Systems Reliability Engineer | 2 |
| March 29, 2026 | Finalized statuses for sub-100 RPN items based on SRE recommendations | AI Systems Reliability Engineer | 3 |
| March 29, 2026 | Corrected statuses: items with unbuilt mitigations moved from Mitigated to Open — mitigation planned | Calibration Review | 4 |
