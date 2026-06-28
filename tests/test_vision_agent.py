"""
Module: test_vision_agent.py
Purpose: Tests for the Phase 2 AI layer — GeminiProvider (with an injected fake
         client, NO network) and vision_agent.extract_item parsing/validation.
FMEA Constraints Enforced (asserted): PI-004, PI-005, PI-003, R-COST.
"""

from __future__ import annotations

import pytest

from src.ai.provider import GeminiProvider
from src.ai.vision_agent import extract_item
from src.contracts import VisionAgentOutput


# ── Fakes ─────────────────────────────────────────────────────────────────────


class _FakeResponse:
    """Stand-in for a google-genai GenerateContentResponse (.text only)."""

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    """Records the generate_content call and returns a canned response."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.last_kwargs: dict | None = None

    def generate_content(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeResponse(self._text)


class _FakeClient:
    """Minimal fake genai.Client exposing `.models.generate_content`."""

    def __init__(self, text: str) -> None:
        self.models = _FakeModels(text)


class _StubProvider:
    """A trivial AIProvider for vision_agent tests; returns canned JSON text."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[dict] = []

    def generate_from_images(self, image_paths, prompt, **kwargs) -> str:
        self.calls.append({"image_paths": image_paths, "prompt": prompt, **kwargs})
        return self._text

    @property
    def model_name(self) -> str:
        return "stub"


# ── GeminiProvider ────────────────────────────────────────────────────────────


def test_provider_model_name_defaults_to_pinned():
    """The pinned model defaults to gemini-3.5-flash (DECISION D-9)."""
    p = GeminiProvider(api_key="k", client=_FakeClient("{}"))
    assert p.model_name == "gemini-3.5-flash"


def test_provider_model_override():
    """GEMINI_MODEL / explicit override wins over the default pin."""
    p = GeminiProvider(api_key="k", model="gemini-3.5-flash-lite", client=_FakeClient("{}"))
    assert p.model_name == "gemini-3.5-flash-lite"


def test_provider_generate_passes_config_and_returns_text(tmp_jpg):
    """generate_from_images attaches images, sets config, returns .text (R-COST)."""
    fake = _FakeClient('{"ok": true}')
    p = GeminiProvider(api_key="k", client=fake)
    out = p.generate_from_images([tmp_jpg], "extract", media_resolution="LOW")
    assert out == '{"ok": true}'
    kw = fake.models.last_kwargs
    assert kw["model"] == "gemini-3.5-flash"
    # Config carries the JSON mime + the low media-resolution lever.
    assert kw["config"].response_mime_type == "application/json"
    assert "LOW" in str(kw["config"].media_resolution)
    # Contents = prompt text + one image Part.
    assert kw["contents"][0] == "extract"
    assert len(kw["contents"]) == 2


def test_provider_missing_key_raises_only_on_use():
    """No API key + no client raises lazily at call time, not construction."""
    p = GeminiProvider(api_key="", client=None)  # constructs fine
    with pytest.raises(ValueError):
        p.generate_from_images(["x.jpg"], "p")


# ── vision_agent.extract_item ─────────────────────────────────────────────────


def test_extract_item_happy_path():
    """A clean JSON response maps straight into VisionAgentOutput."""
    text = (
        '{"item_specifics": {"Brand": "Sony"}, "condition": "Used - Good", '
        '"defects_found": ["scuff on left cup"], "dropped_fields": []}'
    )
    out = extract_item(["a.jpg"], _StubProvider(text))
    assert isinstance(out, VisionAgentOutput)
    assert out.item_specifics == {"Brand": "Sony"}
    assert out.condition == "Used - Good"
    assert out.defects_found == ["scuff on left cup"]


def test_extract_item_forces_defects_list_pi004():
    """A response omitting defects_found still yields a present empty list (PI-004)."""
    text = '{"item_specifics": {"Brand": "Sony"}, "condition": "New"}'
    out = extract_item(["a.jpg"], _StubProvider(text))
    assert out.defects_found == []
    assert "defects_found" in out.model_dump()


def test_extract_item_drops_invalid_aspects_pi005():
    """Aspects outside the category enum are dropped, not invented (PI-005)."""
    text = (
        '{"item_specifics": {"Brand": "Sony", "Color": "Plaid"}, '
        '"condition": "Used", "defects_found": []}'
    )
    enums = {"Color": ["Black", "Blue", "Silver"]}
    out = extract_item(["a.jpg"], _StubProvider(text), category_aspect_enums=enums)
    assert "Color" not in out.item_specifics  # dropped — not in enum
    assert out.item_specifics == {"Brand": "Sony"}
    assert "Color" in out.dropped_fields


def test_extract_item_tolerates_code_fences():
    """A fenced ```json block parses correctly."""
    text = '```json\n{"item_specifics": {}, "condition": "New", "defects_found": []}\n```'
    out = extract_item(["a.jpg"], _StubProvider(text))
    assert out.condition == "New"


def test_extract_item_empty_paths_raises():
    """No images is a programming error, surfaced clearly."""
    with pytest.raises(ValueError):
        extract_item([], _StubProvider("{}"))


def test_extract_item_unparsable_raises():
    """A non-JSON response raises a clear ValueError."""
    with pytest.raises(ValueError):
        extract_item(["a.jpg"], _StubProvider("sorry, I can't do that"))
