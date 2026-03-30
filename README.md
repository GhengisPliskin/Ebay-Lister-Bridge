# Lister-Bridge Hybrid Agent

An automated market research and eBay listing tool. Monitors Google Drive for incoming
item photos, uses Gemini Multimodal Vision to extract details and establish a
GMV-optimized "Margin-Guard" price, and uses an interactive terminal interface to
resolve ambiguities before publishing directly to eBay via the GraphQL API.

---

## Success Criteria

| Metric | Target |
|---|---|
| Margin & Velocity | `marginGuardPrice` achieves >80% 30-day sell-through rate |
| Data Accuracy | Zero listings flagged by eBay for inaccurate Item Specifics |
| Vision Reliability | Vision Agent identifies ≥95% of visible physical defects |

---

## Architecture Overview

The system is a Python-based CLI application. The **Orchestrator** polls a designated
Google Drive folder for new item batches. For each item, the **Vision Agent**
(Gemini `media_resolution: HIGH`) extracts visual data, and the **Logic Agent**
(Gemini `thinking_level: HIGH`) calculates the Margin-Guard price.

If data is missing, the Orchestrator pauses and drops into an interactive CLI loop.
Once the user types `APPROVE`, the payload is formatted and pushed to eBay via
the `startListingPreviewsCreation` GraphQL mutation.

---

## Directory Structure

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
│   ├── templates/
│   └── proposals/
├── working/                     # Ephemeral per-session scratch space
│   ├── CODE_DECISIONS_PATCH.md
│   ├── ISSUE_QUEUE.md
│   └── DOCUMENT_DRIFT_LOG.md
├── .github/
│   └── workflows/
│       └── spike-check.yml
├── CLAUDE.md
├── CONTRIBUTING.md
├── ARCHITECTURE.md
├── CONSTRAINTS.md
├── KEY_DECISION_LOG.md
├── CODE_DECISION_LOG.md
├── .env                         # SECURE — Never commit
├── .repomixignore
├── repomix.config.json
├── requirements.txt
└── README.md
```

---

## Operational Ground Rules

| # | Rule | Mechanism |
|---|---|---|
| 1 | **Issue Binding** — No code or documentation generated without an active, assigned Issue. | PR template requires Issue reference. |
| 2 | **Decision Logging** — Architectural decisions → `KEY_DECISION_LOG.md`. Code decisions → `working/CODE_DECISIONS_PATCH.md`. Merged into `CODE_DECISION_LOG.md` at HUMAN gate. | PR review checklist. |
| 3 | **State Synchronization** — AI explicitly states Kanban column changes at start and end of each action. | Prompt headers include State Sync section. |
| 4 | **Source Truth** — `ARCHITECTURE.md` updated concurrently with any structural change. | PR review checklist. |
| 5 | **Constraint Traceability** — Decisions impacting FMEA reference the FMEA ID. | FMEA labels on Issues. |
| 6 | **Template Adherence** — AI must read templates before generating files. No memory reconstruction. | Embedded in workflow. |
| 7 | **[SPIKE] Exemption** — Spike issues bypass structural requirements. Formalization required before Done. | `spike` label + Kanban Done-lock enforced by `spike-check.yml`. |
| 8 | **Execution-Locked FMEA** — FMEA constraints are immutable during task execution. | Prompt headers cite constraints with immutability notice. |
| 9 | **FMEA Amendment Protocol** — Constraint conflicts halt execution for human review. | FMEA Amendment Proposal template. |
| 10 | **Codebase State Sync** — Fresh repository map required at start of execution sessions. | Prompt header preamble check. |
| 11 | **Code Comment Standard** — All `.py` files must include module-level docstrings, function docstrings, and plain-English block comments. AI sessions must not remove or truncate existing comments. | Enforced via `CONSTRAINTS.md` C-004–C-007. Standing acceptance criterion. |

---

## Setup

1. Copy `.env.example` to `.env` and populate credentials (Gemini API key, Google Service Account JSON path, eBay OAuth tokens).
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `python src/core/orchestrator.py`
