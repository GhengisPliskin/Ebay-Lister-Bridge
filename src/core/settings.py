"""
Module: settings.py
Purpose: Streamlit-free settings/credential logic for the guided Setup wizard —
         schema, .env read/write, portal links, and per-service live-validation
         checks — so src/ui/app.py can render a Setup tab without embedding any
         business logic (mirrors the existing ui/review.py + ui/app.py split).
Primary Responsibilities:
  - Describe every .env.example variable, grouped by service, in SETTINGS_SCHEMA
    (key, label, help text, required flag, secret flag, default).
  - Provide PORTAL_LINKS: per-service portal URLs (Google Cloud service accounts,
    Google AI Studio API keys, eBay developer portal) plus draft-platform posting
    links (Facebook Marketplace, Mercari), each with one-line guidance.
  - Resolve the target .env path consistently with src.core.paths.load_app_dotenv's
    search order (settings_env_path), so what Setup writes is what the app reads.
  - Read/write that .env file (read_settings / write_settings), atomically and
    without ever logging secret values.
  - Report which required keys are still empty (missing_required), for the
    startup warning banner.
  - Validate each service's credentials live, via an injectable client/session
    (validate_drive / validate_gemini / validate_ebay), returning a uniform
    ValidationResult so the UI can render success/error without touching SDKs.
Key Interfaces:
  - Input: the on-disk .env (or its absence), and operator-entered values dict
    from the Streamlit Setup tab.
  - Output: SETTINGS_SCHEMA / PORTAL_LINKS (static), dict[str, str] settings,
    the written .env Path, and ValidationResult per service.
FMEA Constraints Enforced:
  - R-STATE — settings_env_path() reuses/extends src.core.paths so the frozen
    vs. non-frozen anchor logic (and therefore .env discovery) never diverges
    between what Setup writes and what load_app_dotenv() later reads.
  - R-AUTH — validate_ebay constructs EbayAuth from the operator-entered values
    (not ambient env), so Setup validates exactly what is about to be saved.

NOTE: this module must NEVER import streamlit — it is imported by tests that do
not have streamlit installed, and by src/ui/app.py, which does. All Streamlit
widgets live in src/ui/app.py; this module is pure logic (mirrors C5-1's
review.py / app.py split for the existing Review & Approve tab).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from src.core.paths import _PROJECT_ROOT, _frozen_anchor_dir

# ── Schema ─────────────────────────────────────────────────────────────────────

# Keys that must be masked (type="password") in the UI and never printed/logged
# in full anywhere (Setup tab, error messages, etc.).
_SECRET_KEYS = frozenset(
    {"GEMINI_API_KEY", "EBAY_CLIENT_SECRET", "EBAY_OAUTH_REFRESH_TOKEN"}
)

# Truncation length for validator error messages (human-readable, no tracebacks).
_MESSAGE_TRUNCATE_LEN = 200


@dataclass(frozen=True)
class SettingField:
    """
    Describes a single .env variable for the Setup wizard.

    Attributes:
        key: The .env variable name (e.g. "GEMINI_API_KEY").
        label: Short human-readable label for the UI.
        help_text: One or two sentences of guidance shown beneath the input.
        required: True if the app cannot run correctly without a non-empty value.
        secret: True if the value should be masked (type="password") and never
            logged in full (see _SECRET_KEYS).
        default: Default value taken from .env.example (may be "").

    FMEA Constraints:
        None directly — this is a pure descriptor; enforcement happens in
        missing_required() (required) and the UI layer (secret masking).
    """

    key: str
    label: str
    help_text: str
    required: bool
    secret: bool
    default: str = ""


@dataclass(frozen=True)
class SettingsGroup:
    """
    A named group of SettingFields shown together as one Setup expander.

    Attributes:
        service: Stable group identifier (e.g. "google_drive"), also used to
            look up PORTAL_LINKS.
        title: Human-readable section title for the UI.
        fields: Ordered tuple of SettingField entries in this group.
    """

    service: str
    title: str
    fields: tuple

    def keys(self) -> list:
        """Return the ordered list of env-var keys in this group."""
        return [f.key for f in self.fields]


@dataclass(frozen=True)
class PortalLink:
    """
    One external portal link shown in the Setup UI.

    Attributes:
        label: Short link text (e.g. "Google Cloud service accounts console").
        url: The destination URL.
        guidance: One-line explanation of what the operator should do there.
    """

    label: str
    url: str
    guidance: str


# Ordered schema: every var in .env.example, grouped by service. Order matches
# the sections in .env.example so the Setup tab reads top-to-bottom the same
# way the file does.
SETTINGS_SCHEMA: tuple = (
    SettingsGroup(
        service="google_drive",
        title="Google Drive",
        fields=(
            SettingField(
                key="GOOGLE_SERVICE_ACCOUNT_JSON",
                label="Service account JSON path",
                help_text=(
                    "Absolute path to the downloaded service account JSON key "
                    "file. The service account's email must be shared (Viewer "
                    "or Editor) on your staging/archive Drive folders."
                ),
                required=True,
                secret=False,
                default="/absolute/path/to/service-account.json",
            ),
            SettingField(
                key="DRIVE_STAGING_FOLDER_ID",
                label="Staging folder ID",
                help_text="Copy from the URL when the staging folder is open in Drive.",
                required=True,
                secret=False,
                default="1xxxxxxxxxxxxxxxxxxxxxxxxxxx",
            ),
            SettingField(
                key="DRIVE_ARCHIVE_FOLDER_ID",
                label="Archive folder ID",
                help_text="Copy from the URL when the archive folder is open in Drive.",
                required=True,
                secret=False,
                default="1yyyyyyyyyyyyyyyyyyyyyyyyyyy",
            ),
            SettingField(
                key="DRIVE_CACHE_DIR",
                label="Local image cache directory",
                help_text=(
                    "Relative (to the app data directory) or absolute path where "
                    "downloaded images are cached."
                ),
                required=False,
                secret=False,
                default="data/cache/images",
            ),
        ),
    ),
    SettingsGroup(
        service="gemini",
        title="Gemini (Vision Agent)",
        fields=(
            SettingField(
                key="GEMINI_API_KEY",
                label="Gemini API key",
                help_text=(
                    "From Google AI Studio. Consumer Google One / AI Pro plans do "
                    "NOT include API tokens — API usage is billed separately; "
                    "start on the AI Studio free tier."
                ),
                required=True,
                secret=True,
                default="",
            ),
            SettingField(
                key="GEMINI_MODEL",
                label="Gemini model",
                help_text="Pinned model id used for every Vision Agent extraction call.",
                required=False,
                secret=False,
                default="gemini-3.5-flash",
            ),
        ),
    ),
    SettingsGroup(
        service="ebay",
        title="eBay",
        fields=(
            SettingField(
                key="EBAY_ENV",
                label="Environment",
                help_text="sandbox or production. Keep on sandbox until verified.",
                required=True,
                secret=False,
                default="sandbox",
            ),
            SettingField(
                key="EBAY_CLIENT_ID",
                label="Client ID",
                help_text="From your eBay developer portal keyset.",
                required=True,
                secret=False,
                default="",
            ),
            SettingField(
                key="EBAY_CLIENT_SECRET",
                label="Client secret",
                help_text="From your eBay developer portal keyset.",
                required=True,
                secret=True,
                default="",
            ),
            SettingField(
                key="EBAY_OAUTH_REFRESH_TOKEN",
                label="OAuth refresh token",
                help_text=(
                    "USER refresh token from the authorization-code grant flow. "
                    "Used to mint short-lived access tokens automatically."
                ),
                required=True,
                secret=True,
                default="",
            ),
            SettingField(
                key="EBAY_OAUTH_SCOPES",
                label="OAuth scopes",
                help_text=(
                    "Space-separated, full scope URLs (each must start with "
                    "https://api.ebay.com/oauth/), not short-form keywords."
                ),
                required=True,
                secret=False,
                default=(
                    "https://api.ebay.com/oauth/api_scope "
                    "https://api.ebay.com/oauth/api_scope/sell.inventory "
                    "https://api.ebay.com/oauth/api_scope/commerce.media"
                ),
            ),
            SettingField(
                key="EBAY_MARKETPLACE_ID",
                label="Marketplace ID",
                help_text="The marketplace listings are published to (e.g. EBAY_US).",
                required=True,
                secret=False,
                default="EBAY_US",
            ),
            SettingField(
                key="EBAY_FULFILLMENT_POLICY_ID",
                label="Fulfillment policy ID",
                help_text="Business policy ID referenced by every createOffer call.",
                required=True,
                secret=False,
                default="",
            ),
            SettingField(
                key="EBAY_PAYMENT_POLICY_ID",
                label="Payment policy ID",
                help_text="Business policy ID referenced by every createOffer call.",
                required=True,
                secret=False,
                default="",
            ),
            SettingField(
                key="EBAY_RETURN_POLICY_ID",
                label="Return policy ID",
                help_text="Business policy ID referenced by every createOffer call.",
                required=True,
                secret=False,
                default="",
            ),
            SettingField(
                key="EBAY_INVENTORY_LOCATION_KEY",
                label="Inventory location key",
                help_text="Merchant inventory location key required by createOffer/publishOffer.",
                required=True,
                secret=False,
                default="",
            ),
            SettingField(
                key="EBAY_DEFAULT_CATEGORY_ID",
                label="Default category ID",
                help_text=(
                    "Applied to assembled listings; the operator may override "
                    "per item in the review UI. Leave blank to force a manual set."
                ),
                required=False,
                secret=False,
                default="",
            ),
        ),
    ),
    SettingsGroup(
        service="storage",
        title="State storage",
        fields=(
            SettingField(
                key="STATE_STORE_DB_PATH",
                label="SQLite database path",
                help_text=(
                    "Relative (to the app data directory) or absolute path to "
                    "the dedup/resume state database."
                ),
                required=False,
                secret=False,
                default="data/state/lister_bridge.db",
            ),
        ),
    ),
)


def _all_fields():
    """Yield every SettingField across all groups, in schema order."""
    for group in SETTINGS_SCHEMA:
        yield from group.fields


# Flat lookup: key -> SettingField, built once at import time from the schema
# above (single source of truth — never hand-duplicated).
_FIELDS_BY_KEY: dict = {f.key: f for f in _all_fields()}


# ── Portal links ───────────────────────────────────────────────────────────────

# Per-service credential portals plus draft-platform posting links. Grouped the
# same way as SETTINGS_SCHEMA service ids where applicable; the two draft
# platforms (facebook_marketplace, mercari) have no credential fields, only links.
PORTAL_LINKS: dict = {
    "google_drive": (
        PortalLink(
            label="Google Cloud service accounts console",
            url="https://console.cloud.google.com/iam-admin/serviceaccounts",
            guidance=(
                "Create a service account, download its JSON key, and share your "
                "staging/archive Drive folders with its email address."
            ),
        ),
    ),
    "gemini": (
        PortalLink(
            label="Google AI Studio API keys",
            url="https://aistudio.google.com/apikey",
            guidance="Create a free-tier API key for GEMINI_API_KEY.",
        ),
    ),
    "ebay": (
        PortalLink(
            label="eBay developer portal (keys)",
            url="https://developer.ebay.com/my/keys",
            guidance=(
                "Find your Client ID / Client secret here, and generate a user "
                "OAuth refresh token via the authorization-code grant flow."
            ),
        ),
    ),
    "facebook_marketplace": (
        PortalLink(
            label="Facebook Marketplace — create listing",
            url="https://www.facebook.com/marketplace/create/item",
            guidance=(
                "No credentials needed — drafts are generated locally; open this "
                "link to paste the generated listing in manually."
            ),
        ),
    ),
    "mercari": (
        PortalLink(
            label="Mercari — sell",
            url="https://www.mercari.com/sell/",
            guidance=(
                "No credentials needed — drafts are generated locally; open this "
                "link to paste the generated listing in manually."
            ),
        ),
    ),
}


# ── Validation result ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ValidationResult:
    """
    Uniform result of a per-service credential validation check.

    Attributes:
        ok: True if the live check succeeded.
        message: Human-readable outcome message (no tracebacks; exception text
            is truncated to _MESSAGE_TRUNCATE_LEN characters).

    FMEA Constraints:
        None directly — this is the shared shape the Setup UI renders via
        st.success/st.error.
    """

    ok: bool
    message: str


def _truncate(text: str, limit: int = _MESSAGE_TRUNCATE_LEN) -> str:
    """
    Truncate a diagnostic string to `limit` characters, appending an ellipsis.

    Args:
        text: The raw string (typically str(exc)).
        limit: Maximum length before truncation.

    Returns:
        The original string if within limit, else the first `limit` characters
        followed by "...".

    Side Effects:
        None.
    """
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


# ── .env path resolution ──────────────────────────────────────────────────────


def settings_env_path() -> Path:
    """
    Return the .env path that Setup reads from and writes to.

    Mirrors src.core.paths.load_app_dotenv's search order so what Setup writes
    is what the running app actually loads:
      - Frozen (PyInstaller onefile): %APPDATA%/ListerBridge/.env — the same
        frozen anchor directory load_app_dotenv() checks (its second candidate,
        and the one guaranteed to exist/be writable across runs).
      - Not frozen: <project-root>/.env — the same cwd-independent location
        every other module in this codebase treats as "the" project .env.

    Args:
        None

    Returns:
        Path to the target .env file (may not exist yet).

    Side Effects:
        When frozen, ensures the %APPDATA%/ListerBridge directory exists (via
        src.core.paths._frozen_anchor_dir(), the same helper load_app_dotenv
        uses). Does not create the .env file itself.

    FMEA Constraints:
        R-STATE — reusing the exact same anchor directory as load_app_dotenv's
        frozen branch means a value Setup writes is guaranteed to be found by
        the app's own .env discovery, instead of two independently-drifting
        path computations.
    """
    if getattr(sys, "frozen", False):
        return _frozen_anchor_dir() / ".env"
    return _PROJECT_ROOT / ".env"


def shadowing_env_path() -> "Path | None":
    """
    Return a higher-precedence .env that would shadow the Setup-written file.

    load_app_dotenv()'s frozen search order tries Path(sys.executable).parent
    / ".env" (next to the .exe) BEFORE the %APPDATA%/ListerBridge/.env that
    Setup writes. python-dotenv does not override already-set variables, so if
    an exe-adjacent .env exists, values saved via the Setup tab are silently
    ignored on the next launch. The Setup UI uses this to warn the operator.

    Args:
        None

    Returns:
        The exe-adjacent .env Path if (and only if) the app is frozen, that
        file exists, and it is not the same file Setup writes to; else None.

    Side Effects:
        None (read-only filesystem check).

    FMEA Constraints:
        R-STATE — closes the gap between "Setup saved successfully" and "the
        app actually loads those values": precedence conflicts are surfaced
        instead of failing silently.
    """
    if not getattr(sys, "frozen", False):
        return None
    # First candidate in load_app_dotenv's frozen search order: next to the .exe.
    exe_env = Path(sys.executable).parent / ".env"
    if exe_env.exists() and exe_env != settings_env_path():
        return exe_env
    return None


# ── Read / write ───────────────────────────────────────────────────────────────


def _parse_env_text(text: str) -> dict:
    """
    Parse simple KEY=VALUE .env text into a dict, preserving unknown keys.

    Args:
        text: Raw .env file contents.

    Returns:
        dict[str, str] mapping every KEY=VALUE line found. Blank lines and
        lines starting with '#' (after stripping leading whitespace) are
        skipped. Values are not quote-unescaped beyond simple surrounding
        quote stripping, matching the minimal format .env.example itself uses.

    Side Effects:
        None.
    """
    values: dict = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip one layer of matching surrounding quotes, if present.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def read_settings() -> dict:
    """
    Read the current settings from the target .env file.

    Args:
        None

    Returns:
        dict[str, str]: every key in SETTINGS_SCHEMA mapped to its current
        value — from the on-disk .env if present, else its schema default
        (missing entirely -> ""). Any additional/unknown keys found in the
        file are also included (preserved for round-tripping by write_settings).

    Side Effects:
        Reads settings_env_path() from disk if it exists.

    FMEA Constraints:
        R-STATE — reads from the exact path settings_env_path() resolves, so
        this always reflects what the running app would itself load.
    """
    path = settings_env_path()
    on_disk: dict = {}
    if path.is_file():
        on_disk = _parse_env_text(path.read_text(encoding="utf-8"))

    # Start from schema defaults so every known key is always present, then
    # overlay whatever was actually found on disk (including unknown keys).
    values = {key: field_.default for key, field_ in _FIELDS_BY_KEY.items()}
    values.update(on_disk)
    return values


def write_settings(values: dict) -> Path:
    """
    Write `values` to the target .env file atomically.

    Args:
        values: dict[str, str] of env-var values to write. Unknown keys (not
            present in SETTINGS_SCHEMA) are preserved as-is, alongside the
            schema-known keys.

    Returns:
        Path: the .env file that was written (same as settings_env_path()).

    Side Effects:
        Creates the parent directory if needed. Writes to a temp file in the
        same directory, then replaces the target atomically (same
        temp-file + Path.replace() pattern as drive_fetcher._save_cache_manifest,
        so a mid-write interruption never leaves a partially-written .env).
        NEVER logs or prints any value (secret or not).

    FMEA Constraints:
        R-STATE — atomic replace avoids a corrupt/truncated .env if the process
        is interrupted mid-write, mirroring the manifest-write safety pattern
        already established in drive_fetcher.py.
    """
    path = settings_env_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Generated by Lister-Bridge Setup — do not edit while the app is running.",
        "",
    ]
    for key, value in values.items():
        lines.append(f"{key}={value}")
    content = "\n".join(lines) + "\n"

    tmp_path = path.parent / (path.name + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)
    return path


def missing_required(values: dict) -> list:
    """
    Return the required schema keys whose value is empty/missing.

    Args:
        values: dict[str, str] as returned by read_settings() (or an in-progress
            edit of it from the Setup UI).

    Returns:
        list[str]: required keys (schema order) with an empty/whitespace-only
        or absent value.

    Side Effects:
        None.

    FMEA Constraints:
        None directly — this feeds the startup warning banner so an operator
        with an incomplete .env sees exactly what's missing instead of a later,
        less legible failure deep in the pipeline.
    """
    missing = []
    for field_ in _all_fields():
        if not field_.required:
            continue
        value = (values.get(field_.key) or "").strip()
        if not value:
            missing.append(field_.key)
    return missing


# ── Validators ───────────────────────────────────────────────────────────────


def validate_drive(values: dict, drive_service=None) -> ValidationResult:
    """
    Validate Google Drive credentials by listing the staging folder's parent.

    Args:
        values: dict[str, str] of entered settings (GOOGLE_SERVICE_ACCOUNT_JSON,
            DRIVE_STAGING_FOLDER_ID used).
        drive_service: Optional injected Drive v3 service resource (tests pass
            a fake with a `.files().list(...).execute()` chain). When None, a
            real service is built from the JSON key path (same construction
            as drive_fetcher._get_drive_service).

    Returns:
        ValidationResult(ok=True, message=...) on a successful files.list call;
        ValidationResult(ok=False, message=...) if the JSON path is missing/
        invalid, or the API call raises.

    Side Effects:
        When drive_service is None: reads the service account JSON from disk
        and performs one live Drive API call (files().list, pageSize=1).

    FMEA Constraints:
        None directly — this is an operator-triggered Setup check, not part of
        the PI-001-covered pipeline path (no retry/backoff here by design; a
        single failed Test click is meant to surface the problem immediately).
    """
    sa_path = (values.get("GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
    staging_id = (values.get("DRIVE_STAGING_FOLDER_ID") or "").strip()

    if drive_service is None:
        if not sa_path:
            return ValidationResult(False, "GOOGLE_SERVICE_ACCOUNT_JSON is not set.")
        if not os.path.exists(sa_path):
            return ValidationResult(
                False, f"Service account file not found: {sa_path}"
            )
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            credentials = service_account.Credentials.from_service_account_file(
                sa_path, scopes=["https://www.googleapis.com/auth/drive"]
            )
            drive_service = build("drive", "v3", credentials=credentials)
        except Exception as exc:  # building the client itself failed
            return ValidationResult(
                False, f"Could not build Drive client: {_truncate(exc)}"
            )

    try:
        query = f"'{staging_id}' in parents and trashed = false" if staging_id else None
        request = drive_service.files().list(q=query, pageSize=1, fields="files(id)")
        request.execute()
    except Exception as exc:
        return ValidationResult(False, f"Drive check failed: {_truncate(exc)}")

    return ValidationResult(True, "Drive credentials look good.")


def validate_gemini(values: dict, client=None) -> ValidationResult:
    """
    Validate Gemini credentials with the cheapest possible live call.

    Args:
        values: dict[str, str] of entered settings (GEMINI_API_KEY, GEMINI_MODEL
            used).
        client: Optional injected google-genai Client (tests pass a fake with a
            `.models.count_tokens(...)` method). When None, a real client is
            constructed from GEMINI_API_KEY.

    Returns:
        ValidationResult(ok=True, ...) if the client accepts a count_tokens call
        for GEMINI_MODEL; ValidationResult(ok=False, ...) if the API key is
        missing or the call raises.

    Side Effects:
        When client is None: imports google.genai and constructs a real Client,
        then performs one count_tokens call (cheapest available check — no
        content generation, so no output-token billing).

    FMEA Constraints:
        R-COST — count_tokens is used deliberately instead of generate_content
        so a Setup "Test" click never incurs a generation cost.
    """
    api_key = (values.get("GEMINI_API_KEY") or "").strip()
    model = (values.get("GEMINI_MODEL") or "").strip() or "gemini-3.5-flash"

    if client is None:
        if not api_key:
            return ValidationResult(False, "GEMINI_API_KEY is not set.")
        try:
            from google import genai

            client = genai.Client(api_key=api_key)
        except Exception as exc:
            return ValidationResult(
                False, f"Could not build Gemini client: {_truncate(exc)}"
            )

    try:
        client.models.count_tokens(model=model, contents="ping")
    except Exception as exc:
        return ValidationResult(False, f"Gemini check failed: {_truncate(exc)}")

    return ValidationResult(True, "Gemini credentials look good.")


def validate_ebay(values: dict, session=None) -> ValidationResult:
    """
    Validate eBay credentials by requesting an OAuth access token.

    Constructs an EbayAuth directly from the entered values (NOT ambient env),
    so this validates exactly what is about to be saved rather than whatever
    happens to already be loaded into os.environ.

    Args:
        values: dict[str, str] of entered settings (EBAY_ENV, EBAY_CLIENT_ID,
            EBAY_CLIENT_SECRET, EBAY_OAUTH_REFRESH_TOKEN, EBAY_OAUTH_SCOPES used).
        session: Optional injected requests.Session (tests pass a FakeSession).
            When None, EbayAuth builds a real requests.Session internally.

    Returns:
        ValidationResult(ok=True, ...) if a token is successfully minted;
        ValidationResult(ok=False, ...) on a validation/config error (e.g. bad
        scope format) or a failed refresh call.

    Side Effects:
        Performs one HTTPS POST to the eBay OAuth token endpoint (via EbayAuth),
        unless the constructor itself raises before any network call.

    FMEA Constraints:
        R-AUTH — reuses EbayAuth (the single implementation of the refresh_token
        grant + scope validation) rather than re-implementing OAuth here.
    """
    from src.api.ebay_auth import EbayAuth, EbayAuthError

    kwargs = dict(
        env=(values.get("EBAY_ENV") or "sandbox").strip(),
        client_id=(values.get("EBAY_CLIENT_ID") or "").strip(),
        client_secret=(values.get("EBAY_CLIENT_SECRET") or "").strip(),
        refresh_token=(values.get("EBAY_OAUTH_REFRESH_TOKEN") or "").strip(),
        scopes=(values.get("EBAY_OAUTH_SCOPES") or "").strip(),
    )
    if session is not None:
        kwargs["session"] = session

    try:
        auth = EbayAuth(**kwargs)
        auth.get_access_token(force_refresh=True)
    except (EbayAuthError, ValueError) as exc:
        return ValidationResult(False, f"eBay check failed: {_truncate(exc)}")
    except Exception as exc:  # transport-level or unexpected failure
        return ValidationResult(False, f"eBay check failed: {_truncate(exc)}")

    return ValidationResult(True, "eBay credentials look good.")
