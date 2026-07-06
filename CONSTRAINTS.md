# CONSTRAINTS.md — Lister-Bridge Hybrid Agent

All constraints are active and enforced unless explicitly superseded by a logged decision in `KEY_DECISION_LOG.md`.

---

## Non-Functional Requirements

| ID | Requirement | Category | Threshold |
|---|---|---|---|
| NFR-001 | The Streamlit review/approve interface must clearly display the AI's question, proposed pricing, and status without overwhelming the user with raw JSON. | Usability | N/A |
| NFR-002 | All `.py` files must include module-level docstrings, public function docstrings, and plain-English block comments on all non-trivial logic. AI sessions must not remove or truncate existing comments. | Code Quality | See `ARCHITECTURE.md` — "Code Comment Standard" section. Enforced via Ground Rule 11 and C-004 through C-007. Zero exceptions. |

---

## Constraints

| ID | Constraint | Type | Impact |
|---|---|---|---|
| C-001 | FMEA Register Active | Procedural | Section 5 of the Master Plan is populated. Risk analysis is active. Ground Rules 5, 8, and 9 are in full enforcement. |
| C-002 | eBay REST Requirement | Tech Stack | Must use the eBay REST Sell Inventory publish sequence (`createInventoryItem` → `createOffer` → `publishOffer`) plus the Media API (`createImageFromFile`) for image upload. Amended per blueprint v1.1 — supersedes the original GraphQL `startListingPreviewsCreation` / `mappingReferenceID` requirement. |
| C-003 | Python Environment | Tech Stack | Local execution environment restricted to Python to leverage `google-genai` and `google-api-python-client` libraries. |
| C-004 | Module Docstrings Required | Code Quality | Every `.py` file must begin with a module-level docstring describing the file's purpose, primary responsibilities, key interfaces, and any FMEA constraints it enforces. |
| C-005 | Function Docstrings Required | Code Quality | Every public function must include a docstring describing parameters, return values, side effects, and any FMEA constraints it enforces. |
| C-006 | Block Comments Required | Code Quality | All non-trivial logic blocks (conditionals, loops, data transformations, API calls) must include a preceding plain-English block comment explaining intent. |
| C-007 | Comment Preservation | Code Quality | AI sessions must not remove, truncate, or rewrite existing comments. Comment preservation is verified at every code review gate. |

---

## Constraint Change Protocol

Any modification to this file requires:
1. A logged decision in `KEY_DECISION_LOG.md` with `FMEA Impact` populated.
2. If the constraint is FMEA-linked, a FMEA Amendment Proposal (Ground Rule 9) approved by the human owner before the change takes effect.
