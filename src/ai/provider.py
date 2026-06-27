"""
Module: provider.py
Purpose: Swappable AI provider interface so the model/vendor is config-driven and
         the pipeline never imports a vendor SDK directly.
Primary Responsibilities:
  - Define AIProvider, the abstract interface vision_agent.py calls.
  - Define GeminiProvider as the default concrete implementation (DECISION D-9:
    Gemini 3.5 Flash via google-genai), pinned by GEMINI_MODEL.
Key Interfaces:
  - Input: image bytes/paths + a prompt + generation config.
  - Output: raw model text/JSON for vision_agent.py to parse into VisionAgentOutput.
FMEA Constraints Enforced:
  - R-COST — a single chokepoint for all AI calls enables model downgrade,
    batch mode, and media-resolution levers without touching pipeline code.
  - PI-003 — providers expose per-call statelessness so the orchestrator can
    flush context between items.

STATUS: interface stub (signatures + docstrings). Implemented by a parallel
module agent in Phase 2. The frozen contracts it returns into live in src.contracts.
"""

from __future__ import annotations

import abc


class AIProvider(abc.ABC):
    """
    Vendor-agnostic interface for a multimodal generation provider.

    vision_agent.py depends only on this interface, never on a concrete SDK, so
    the model or vendor is swapped via config (R-COST). Every call is stateless
    by contract — no conversation is retained between calls (PI-003).
    """

    @abc.abstractmethod
    def generate_from_images(
        self,
        image_paths: list[str],
        prompt: str,
        *,
        response_mime_type: str = "application/json",
        media_resolution: str = "HIGH",
        thinking_level: str = "HIGH",
    ) -> str:
        """
        Run a single multimodal generation over the given images and prompt.

        Args:
            image_paths: Local image file paths to attach to the request.
            prompt: The extraction instruction text.
            response_mime_type: Requested response type; "application/json" so the
                caller can parse into VisionAgentOutput.
            media_resolution: Image fidelity lever (e.g. "HIGH"/"LOW") — R-COST.
            thinking_level: Reasoning-budget lever (e.g. "HIGH"/"LOW") — R-COST.

        Returns:
            Raw model output text (JSON when response_mime_type is JSON).

        Side Effects:
            One AI API call. Stateless — retains no context across calls (PI-003).

        Raises:
            NotImplementedError: This is an interface stub.

        FMEA Constraints:
            R-COST — media_resolution / thinking_level are cost levers.
            PI-003 — stateless per call; no cross-item context bleed.
        """
        raise NotImplementedError("provider.generate_from_images is a Phase 2 stub")

    @property
    @abc.abstractmethod
    def model_name(self) -> str:
        """
        Return the pinned model identifier this provider is configured with.

        Returns:
            The model id string (e.g. "gemini-3.5-flash").

        Raises:
            NotImplementedError: This is an interface stub.
        """
        raise NotImplementedError("provider.model_name is a Phase 2 stub")


class GeminiProvider(AIProvider):
    """
    Default AIProvider backed by Gemini via the google-genai SDK (DECISION D-9).

    Reads GEMINI_API_KEY and GEMINI_MODEL from the environment. The model is
    pinned by config (default gemini-3.5-flash) so cost and behavior are stable.

    STATUS: stub — a parallel Phase 2 agent implements the google-genai calls.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        """
        Configure the Gemini provider.

        Args:
            api_key: Override for GEMINI_API_KEY (else read from env).
            model: Override for GEMINI_MODEL (else read from env / default pin).

        Returns:
            None

        Side Effects:
            Reads GEMINI_API_KEY / GEMINI_MODEL from the environment.

        Raises:
            NotImplementedError: This is an interface stub.
        """
        raise NotImplementedError("GeminiProvider.__init__ is a Phase 2 stub")

    def generate_from_images(
        self,
        image_paths: list[str],
        prompt: str,
        *,
        response_mime_type: str = "application/json",
        media_resolution: str = "HIGH",
        thinking_level: str = "HIGH",
    ) -> str:
        """See AIProvider.generate_from_images. Phase 2 stub."""
        raise NotImplementedError("GeminiProvider.generate_from_images is a Phase 2 stub")

    @property
    def model_name(self) -> str:
        """See AIProvider.model_name. Phase 2 stub."""
        raise NotImplementedError("GeminiProvider.model_name is a Phase 2 stub")
