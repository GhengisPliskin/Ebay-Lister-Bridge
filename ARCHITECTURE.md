# ARCHITECTURE.md — Lister-Bridge Hybrid Agent

**Last Updated:** March 30, 2026
**Phase Status:** Phase 0 — COMPLETE ✓ | Phase 1 — Pending | Phase 2 — Pending

---

## High-Level Architecture

The system is a Python-based application with five components:

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
[UI — src/ui/app.py]           ←── Streamlit review/approve (human-in-the-loop, PI-007)
        │  approved payload (after operator clicks Approve)
        ▼
[API/eBay — ebay_client.py]
        │  Media createImageFromFile → createInventoryItem → createOffer → publishOffer
        ▼
[eBay REST Sell Inventory + Media API]
```

---

## Directory Structure

```text
lister-bridge/
├── src/
│   ├── contracts/              # FROZEN pydantic data contracts (Phase 1 deliverable)
│   │   ├── __init__.py          # Single import surface (re-exports all models)
│   │   ├── vision.py            # VisionAgentOutput (Vision -> Margin-Guard)
│   │   ├── pricing.py           # MarginGuardOutput + ActiveCompRange
│   │   ├── ebay.py              # ListingPayload + REST bodies + result shapes
│   │   └── state.py             # ItemRecord / ItemStatus / TokenCacheRecord
│   ├── core/
│   │   ├── orchestrator.py      # Sequencing, per-item state, context flush
│   │   ├── state_store.py       # SQLite dedup/resume + token cache
│   │   ├── drive_fetcher.py     # Google Drive IO (recursive + fully paginated)
│   │   └── paths.py             # Frozen-aware .env / data-dir resolution
│   ├── ai/
│   │   ├── provider.py          # Swappable AI provider interface (Gemini default)
│   │   ├── vision_agent.py      # Gemini extraction -> VisionAgentOutput
│   │   └── margin_guard.py      # Active-comp + human + floor pricing
│   ├── api/
│   │   ├── ebay_auth.py         # OAuth refresh -> cached access token
│   │   └── ebay_client.py       # Browse comps, Media upload, REST publish sequence
│   ├── marketplace/             # MarketplaceAdapter layer (v1.2)
│   │   ├── base.py              # MarketplaceAdapter / AutoPublishAdapter / DraftAdapter
│   │   ├── ebay_adapter.py      # Auto-publish adapter wrapping ebay_client
│   │   └── other_adapter.py     # Draft-only adapter (Facebook Marketplace, Mercari, ...)
│   └── ui/
│       ├── app.py               # Streamlit review/approve front end (the human gate)
│       └── review.py            # Pure, Streamlit-free review/validation helpers
├── desktop_app.py                # Desktop entry point — launches the Streamlit GUI
├── packaging/
│   └── lister_bridge.spec        # PyInstaller spec for the standalone .exe
├── scripts/
│   ├── build_desktop.py         # Builds dist/lister-bridge.exe
│   └── ebay_sandbox_spike.py    # Live/mocked end-to-end eBay de-risk runner
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
| Contracts | Frozen typed schemas all modules build against | (imported by every layer) | `src/contracts/*` |
| Core/IO | Fetching images from Drive, sequencing, state/dedup | Google Drive API, State store | `orchestrator.py`, `drive_fetcher.py`, `state_store.py` |
| AI/Vision | Extracting item specifics, condition, and defects | Core/IO, AI provider | `provider.py`, `vision_agent.py` |
| AI/Logic | Establishing the Margin-Guard price | AI/Vision, eBay Browse comps | `margin_guard.py` |
| API/eBay | OAuth, Media image upload, REST Inventory publish | Core/IO, eBay Media + Sell Inventory + Browse REST APIs | `ebay_auth.py`, `ebay_client.py` |
| Marketplace | Routes an approved listing to eBay (auto-publish) or a generic draft (draft-only) | UI, API/eBay | `base.py`, `ebay_adapter.py`, `other_adapter.py` |
| UI | Streamlit review/approve human gate (PI-007); desktop shell via PyInstaller | Core/IO, Marketplace | `app.py`, `review.py`, `desktop_app.py` |

---

## Intelligence Roster

| Tier | Model | Context | Used For |
|---|---|---|---|
| Tier 1 | Gemini 3 Flash (`thinking_level: HIGH`) | 32k tokens | Margin-Guard pricing, REST integration |
| Tier 2 | Gemini 3 Flash (`media_resolution: HIGH`) | 1M tokens | Vision extraction, orchestrator |
| Tier 3 | Gemini 3 Flash (standard) | 8k tokens | Title SEO, eBay REST payload formatting |

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
