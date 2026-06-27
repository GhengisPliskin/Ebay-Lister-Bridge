"""
Module: vision.py
Purpose: Frozen data contract for the Vision Agent's output, which is also the
         Margin-Guard's pricing input.
Primary Responsibilities:
  - Define VisionAgentOutput, the typed schema produced by vision_agent.py.
  - Force a defects_found list so the model cannot silently omit defects (PI-004).
  - Carry dropped_fields so the UI can surface aspects the model declined to
    invent rather than hallucinating them (PI-005).
Key Interfaces:
  - Input: a Gemini extraction (raw dict / JSON) parsed into this model.
  - Output: VisionAgentOutput consumed by margin_guard.py and ui/app.py.
FMEA Constraints Enforced:
  - PI-004 — defects_found is a required field (default empty list, but always
    present in the serialized contract) so a forced confirmation is possible.
  - PI-005 — dropped_fields records aspects that failed category-enum validation
    and were dropped rather than invented.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VisionAgentOutput(BaseModel):
    """
    Schema-valid result of Gemini visual extraction for a single item.

    This is the frozen Vision -> Margin-Guard contract from the blueprint
    "Data contracts and schemas" section. Parallel module agents build
    vision_agent.py to produce this and margin_guard.py to consume it.

    Attributes:
        item_specifics: Map of eBay aspect name -> value (e.g. {"Brand": "Sony"}).
            Validated against eBay category enums upstream; only surviving
            aspects appear here (PI-005).
        condition: Human/eBay condition descriptor (e.g. "Used - Very Good").
            Empty string means the model could not determine condition.
        defects_found: Explicit list of observed defects. ALWAYS present, even
            when empty, to force defect confirmation in the UI (PI-004).
        dropped_fields: Aspect names the model proposed but that failed category
            enum validation and were dropped rather than invented (PI-005). The
            UI resolves these with the operator.

    FMEA Constraints:
        PI-004 — defects_found is structurally required.
        PI-005 — dropped_fields is structurally required.
    """

    # Reject unknown keys so a drifting producer fails loudly instead of
    # silently dropping data into an untyped bag.
    model_config = ConfigDict(extra="forbid")

    item_specifics: dict[str, str] = Field(
        default_factory=dict,
        description="eBay aspect name -> value, post category-enum validation.",
    )
    condition: str = Field(
        default="",
        description="eBay/condition descriptor; empty if undetermined.",
    )
    defects_found: list[str] = Field(
        default_factory=list,
        description="Observed defects; always present to force confirmation (PI-004).",
    )
    dropped_fields: list[str] = Field(
        default_factory=list,
        description="Aspects dropped for failing enum validation, not invented (PI-005).",
    )
