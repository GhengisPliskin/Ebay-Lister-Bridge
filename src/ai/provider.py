"""
Module: provider.py
Purpose: Swappable AI provider interface so the model/vendor is config-driven and
         the pipeline never imports a vendor SDK directly.
Primary Responsibilities:
  - Define AIProvider, the abstract interface vision_agent.py calls.
  - Define GeminiProvider as the default concrete implementation (DECISION D-9:
    Gemini 3.5 Flash via google-genai), pinned by GEMINI_MODEL, high media res.
Key Interfaces:
  - Input: image paths + a prompt + generation config (media_resolution/thinking).
  - Output: raw model text/JSON for vision_agent.py to parse into VisionAgentOutput.
FMEA Constraints Enforced:
  - R-COST — a single chokepoint for all AI calls enables model downgrade,
    batch mode, and media-resolution levers without touching pipeline code.
  - PI-003 — generate_from_images is stateless per call (no chat/session retained)
    so the orchestrator can flush context between items.

NOTE: the google-genai SDK is imported LAZILY (inside methods) so this module
imports cleanly in environments without the SDK, and so tests can inject a fake
client. NO network call happens at import or construction time.
"""

from __future__ import annotations

import abc
import os

# Map a local image extension to the MIME type Gemini expects for inline bytes.
# Mirrors drive_fetcher's accepted formats (iPhone HEIC included).
_EXT_TO_MIME = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "heic": "image/heic",
    "heif": "image/heic",
    "webp": "image/webp",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
}

# String -> google.genai MediaResolution enum-name suffix (R-COST lever).
_MEDIA_RES_TO_ENUM = {
    "HIGH": "MEDIA_RESOLUTION_HIGH",
    "MEDIUM": "MEDIA_RESOLUTION_MEDIUM",
    "LOW": "MEDIA_RESOLUTION_LOW",
}

# Default pinned model (DECISION D-9). Overridable via GEMINI_MODEL.
_DEFAULT_MODEL = "gemini-3.5-flash"


def _mime_for(path: str) -> str:
    """
    Return the image MIME type for a local file path by extension.

    Args:
        path: Local image path.

    Returns:
        The MIME type string; defaults to "image/jpeg" for unknown extensions
        so an unusual extension never blocks an upload.
    """
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return _EXT_TO_MIME.get(ext, "image/jpeg")


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

        FMEA Constraints:
            R-COST — media_resolution / thinking_level are cost levers.
            PI-003 — stateless per call; no cross-item context bleed.
        """
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def model_name(self) -> str:
        """
        Return the pinned model identifier this provider is configured with.

        Returns:
            The model id string (e.g. "gemini-3.5-flash").
        """
        raise NotImplementedError


class GeminiProvider(AIProvider):
    """
    Default AIProvider backed by Gemini via the google-genai SDK (DECISION D-9).

    Reads GEMINI_API_KEY and GEMINI_MODEL from the environment. The model is
    pinned by config (default gemini-3.5-flash) so cost and behavior are stable.
    A client may be injected (tests pass a fake) to avoid any network or SDK
    dependency at construction.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        *,
        client: object | None = None,
    ) -> None:
        """
        Configure the Gemini provider.

        Args:
            api_key: Override for GEMINI_API_KEY (else read from env).
            model: Override for GEMINI_MODEL (else env, else the pinned default).
            client: Optional pre-built google.genai Client (tests inject a fake);
                when provided, no real client is constructed and no api_key needed.

        Returns:
            None

        Side Effects:
            Reads GEMINI_API_KEY / GEMINI_MODEL from the environment. Does NOT
            perform any network call. The real SDK client is built lazily on
            first use unless one is injected here.

        Raises:
            ValueError: If no client is injected AND no api_key is available when
                a generation is later attempted (raised lazily in _get_client).
        """
        self._api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY")
        self._model = model or os.environ.get("GEMINI_MODEL") or _DEFAULT_MODEL
        self._client = client  # may be a real or fake client, or None (lazy build)

    @property
    def model_name(self) -> str:
        """Return the pinned model id (e.g. 'gemini-3.5-flash')."""
        return self._model

    def _get_client(self):
        """
        Return the google.genai Client, building it lazily on first use.

        Returns:
            The genai.Client (injected or freshly built).

        Side Effects:
            Imports google.genai and constructs a Client the first time.

        Raises:
            ValueError: If no client was injected and GEMINI_API_KEY is missing.
        """
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set; cannot construct a Gemini client. "
                "Set it in .env or inject a client for testing."
            )
        # Lazy import keeps the module importable without the SDK installed.
        from google import genai

        self._client = genai.Client(api_key=self._api_key)
        return self._client

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
        Run one stateless Gemini generation over the images + prompt.

        Args:
            image_paths: Local image paths; each is read and attached as inline bytes.
            prompt: The extraction instruction text.
            response_mime_type: Response MIME (default JSON).
            media_resolution: "HIGH"/"MEDIUM"/"LOW" (R-COST lever).
            thinking_level: "HIGH"/"LOW" reasoning budget (R-COST lever).

        Returns:
            The model's response text (JSON string when response_mime_type is JSON).

        Side Effects:
            Reads each image from disk; one generate_content call. Stateless (PI-003).

        Raises:
            ValueError: If the client cannot be built (missing API key).

        FMEA Constraints:
            R-COST — resolution/thinking passed straight to the config.
            PI-003 — uses the one-shot generate_content; no chat session is kept.
        """
        # Lazy import of types so the module imports without the SDK present.
        from google.genai import types

        client = self._get_client()

        # Build the multimodal content: the prompt text + one Part per image.
        parts: list = [prompt]
        for path in image_paths:
            with open(path, "rb") as fh:
                data = fh.read()
            parts.append(types.Part.from_bytes(data=data, mime_type=_mime_for(path)))

        # Assemble the generation config from the R-COST levers.
        media_enum = getattr(
            types.MediaResolution,
            _MEDIA_RES_TO_ENUM.get(media_resolution.upper(), "MEDIA_RESOLUTION_HIGH"),
        )
        config = types.GenerateContentConfig(
            response_mime_type=response_mime_type,
            media_resolution=media_enum,
            thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
        )

        response = client.models.generate_content(
            model=self._model,
            contents=parts,
            config=config,
        )
        # The unified SDK exposes the aggregated text on `.text`.
        return response.text or ""
