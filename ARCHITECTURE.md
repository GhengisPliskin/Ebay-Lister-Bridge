# ARCHITECTURE.md — Lister-Bridge Hybrid Agent

**Last Updated:** March 30, 2026
**Phase Status:** Phase 0 — COMPLETE ✓ | Phase 1 — Pending | Phase 2 — Pending

---

## High-Level Architecture

The system is a Python-based CLI application with four components:

```
[Google Drive Folder]
        │  images (mobile phone uploads)
        ▼
[Core/IO — drive_fetcher.py]
        │  local file paths
        ▼
[AI/Vision — vision_agent.py]  ←── Gemini (media_resolution: HIGH, 1M ctx)
        │  structured JSON (item specifics, condition, defects)
        ▼
[AI/Logic — margin_guard.py]   ←── Gemini (thinking_level: HIGH, 32k ctx)
        │  marginGuardPrice + reasoning
        ▼
[Core/IO — orchestrator.py]    ←── Interactive CLI (human-in-the-loop)
        │  approved payload (after user types APPROVE)
        ▼
[API/eBay — ebay_graphql.py]
        │  startListingPreviewsCreation mutation
        ▼
[eBay GraphQL API]
```

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
│   ├── templates/               # Skill reference templates (read-only after scaffolding)
│   │   ├── templates.md
│   │   └── master-plan-template.md
│   └── proposals/               # Scope change proposals and their dispositions
├── working/                     # Ephemeral per-session scratch space
│   ├── CODE_DECISIONS_PATCH.md  # Provisional decisions — merged at HUMAN gate
│   ├── ISSUE_QUEUE.md           # Transit queue for gh issue create (Housekeeping)
│   └── DOCUMENT_DRIFT_LOG.md   # Stale-fact registry (Housekeeping)
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

## Component Descriptions

| Component | Responsibility | Interfaces | Key Files |
|---|---|---|---|
| Core/IO | Fetching images from Drive, managing the CLI loop | Google Drive API, User Terminal | `orchestrator.py`, `drive_fetcher.py` |
| AI/Vision | Extracting item specifics, condition, and defects | Core/IO, Gemini Multimodal | `vision_agent.py` |
| AI/Logic | Establishing the Margin-Guard price | AI/Vision, Gemini standard | `margin_guard.py` |
| API/eBay | Transforming internal JSON to GraphQL schema and posting | Core/IO, eBay GraphQL API | `ebay_graphql.py` |

---

## Intelligence Roster

| Tier | Model | Context | Used For |
|---|---|---|---|
| Tier 1 | Gemini 3 Flash (`thinking_level: HIGH`) | 32k tokens | Margin-Guard pricing, GraphQL integration |
| Tier 2 | Gemini 3 Flash (`media_resolution: HIGH`) | 1M tokens | Vision extraction, orchestrator |
| Tier 3 | Gemini 3 Flash (standard) | 8k tokens | Title SEO, eBay GraphQL formatting |

---

## Data Flow

### Input Contract (Vision Agent → Margin-Guard)
```json
{
  "item_specifics": {},
  "condition": "",
  "defects": [],
  "dropped_fields": []
}
```

### Pricing Contract (Margin-Guard Output)
```json
{
  "margin_guard_price": 0.00,
  "suggested_price": 0.00,
  "floor_price": 0.00,
  "floor_applied": false,
  "comparable_range": { "low": 0.00, "high": 0.00 },
  "reasoning": "",
  "missing_inputs": []
}
```

---

## Code Comment Standard

All `.py` files must follow this format. See `CLAUDE.md` for the full template.

- **Module docstring:** File purpose, responsibilities, key interfaces, FMEA constraints enforced.
- **Function docstrings:** Args, returns, side effects, FMEA constraints.
- **Block comments:** Plain-English explanation of intent before every non-trivial logic block.

Constraints: C-004, C-005, C-006, C-007 (see `CONSTRAINTS.md`).
Ground Rule 11 applies to every task without individual negotiation.
