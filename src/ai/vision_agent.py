"""
Module: vision_agent.py
Purpose: Extract eBay item specifics, condition, and defects from item photos via
         the swappable AI provider, returning the frozen VisionAgentOutput.
Primary Responsibilities:
  - Build the extraction prompt and call provider.generate_from_images().
  - Parse/validate the model output into VisionAgentOutput (schema-valid JSON).
  - Force a defects_found array (PI-004) and validate aspects against eBay
    category enums, dropping (not inventing) invalid values (PI-005).
Key Interfaces:
  - Input: local image paths (from drive_fetcher) + an AIProvider + category context.
  - Output: VisionAgentOutput consumed by margin_guard.py and ui/app.py.
FMEA Constraints Enforced:
  - PI-004 — defects_found always present; a forced-confirmation step.
  - PI-005 — invalid aspects dropped into dropped_fields, never invented.

STATUS: interface stub (signatures + docstrings). Implemented by a parallel
Phase 2 agent against the frozen VisionAgentOutput contract.
"""

from __future__ import annotations

from src.ai.provider import AIProvider
from src.contracts import VisionAgentOutput


def extract_item(
    image_paths: list[str],
    provider: AIProvider,
    *,
    category_aspect_enums: dict[str, list[str]] | None = None,
) -> VisionAgentOutput:
    """
    Extract specifics, condition, and defects for one item from its photos.

    Args:
        image_paths: Local photo paths for a single item (one batch subfolder).
        provider: The AIProvider to run extraction through (vendor-agnostic).
        category_aspect_enums: Optional map of aspect -> allowed values for the
            target eBay category; aspects whose values are not in their enum are
            dropped into dropped_fields rather than invented (PI-005).

    Returns:
        VisionAgentOutput: Schema-valid extraction with a forced defects_found
        list and any dropped_fields recorded.

    Side Effects:
        One AI provider call (per item). No state retained between items (PI-003).

    Raises:
        NotImplementedError: This is a Phase 2 stub.

    FMEA Constraints:
        PI-004 — defects_found is always populated/present.
        PI-005 — invalid aspects are dropped, not hallucinated.
    """
    raise NotImplementedError("vision_agent.extract_item is a Phase 2 stub")
