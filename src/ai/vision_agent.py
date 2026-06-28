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
"""

from __future__ import annotations

import json

from src.ai.provider import AIProvider
from src.contracts import VisionAgentOutput

# The extraction instruction. We ask for the exact contract keys so the response
# parses straight into VisionAgentOutput. defects_found is explicitly required so
# the model cannot silently omit defects (PI-004).
_EXTRACTION_PROMPT = """\
You are an eBay listing assistant. Inspect the attached photos of a SINGLE item
and extract structured data. Respond with a JSON object and NOTHING else, using
exactly these keys:

  "item_specifics": object of eBay aspect name -> string value (e.g.
                    {"Brand": "Sony", "Model": "WH-1000XM4"}). Only include
                    aspects you can support from the photos. Do NOT invent values.
  "condition":      a short condition descriptor (e.g. "New", "Used - Very Good").
  "defects_found":  an array of short strings describing every visible defect,
                    scratch, wear mark, or missing part. Use an empty array [] ONLY
                    if you are confident there are no visible defects. Never omit
                    this key.
  "dropped_fields": an array of aspect names you were unsure about and chose to
                    leave out rather than guess.

Return only the JSON object.
"""


def _parse_json_block(raw: str) -> dict:
    """
    Parse a model response into a dict, tolerating Markdown code fences.

    Args:
        raw: The raw model text (may be a bare JSON object or a fenced block).

    Returns:
        The parsed dict.

    Side Effects:
        None.

    Raises:
        ValueError: If no valid JSON object can be parsed from the response.
    """
    text = (raw or "").strip()
    # Strip a leading ```json / ``` fence and trailing ``` if present.
    if text.startswith("```"):
        # Drop the first fence line and any trailing fence.
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        # Last resort: extract the outermost {...} span and retry.
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                raise ValueError(f"Vision response was not valid JSON: {exc}") from exc
        else:
            raise ValueError(f"Vision response was not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Vision response JSON was not an object")
    return parsed


def _validate_aspects(
    item_specifics: dict,
    category_aspect_enums: dict[str, list[str]] | None,
) -> tuple[dict[str, str], list[str]]:
    """
    Drop aspects whose values fail the category enum, never invent (PI-005).

    Args:
        item_specifics: Raw aspect name -> value map from the model.
        category_aspect_enums: Map of aspect -> allowed values for the target
            category. If None, no enum validation is applied (all kept).

    Returns:
        A tuple of (valid_aspects, dropped_aspect_names). An aspect is dropped
        when the category defines an enum for it AND the model's value is not in
        that enum.

    Side Effects:
        None.

    FMEA Constraints:
        PI-005 — invalid aspects are removed and reported, not coerced/invented.
    """
    valid: dict[str, str] = {}
    dropped: list[str] = []
    for name, value in item_specifics.items():
        str_value = "" if value is None else str(value)
        allowed = category_aspect_enums.get(name) if category_aspect_enums else None
        if allowed is not None and str_value not in allowed:
            # The category constrains this aspect and the value isn't allowed.
            dropped.append(name)
            continue
        valid[name] = str_value
    return valid, dropped


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
        ValueError: If image_paths is empty or the model returns unparsable JSON.

    FMEA Constraints:
        PI-004 — defects_found is always populated/present.
        PI-005 — invalid aspects are dropped, not hallucinated.
    """
    if not image_paths:
        raise ValueError("extract_item requires at least one image path")

    # Stateless one-shot call through the provider (PI-003); JSON requested.
    raw = provider.generate_from_images(
        image_paths,
        _EXTRACTION_PROMPT,
        response_mime_type="application/json",
        media_resolution="HIGH",
        thinking_level="HIGH",
    )
    parsed = _parse_json_block(raw)

    # Coerce the model output into the frozen contract shape.
    raw_specifics = parsed.get("item_specifics") or {}
    if not isinstance(raw_specifics, dict):
        raw_specifics = {}

    # PI-005: validate aspects against the category enums; collect any drops.
    valid_aspects, enum_dropped = _validate_aspects(raw_specifics, category_aspect_enums)

    # Merge any model-reported dropped_fields with the enum-dropped ones.
    model_dropped = parsed.get("dropped_fields") or []
    if not isinstance(model_dropped, list):
        model_dropped = []
    dropped_fields = sorted({*map(str, model_dropped), *enum_dropped})

    # PI-004: defects_found must always be a present list.
    defects = parsed.get("defects_found")
    if not isinstance(defects, list):
        defects = []
    defects = [str(d) for d in defects]

    condition = parsed.get("condition") or ""
    if not isinstance(condition, str):
        condition = str(condition)

    return VisionAgentOutput(
        item_specifics=valid_aspects,
        condition=condition,
        defects_found=defects,
        dropped_fields=dropped_fields,
    )
