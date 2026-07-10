"""
Module: test_settings.py
Purpose: Tests for src/core/settings.py — the Streamlit-free Setup wizard logic
         (schema/.env.example lockstep, .env read/write round-trip, atomic write,
         frozen-vs-non-frozen path resolution, missing_required, and each
         validator's success/failure path via injected fakes). No streamlit
         import, no network.
FMEA Constraints Enforced (asserted): R-STATE, R-AUTH.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.core import settings


# ── SETTINGS_SCHEMA <-> .env.example lockstep ─────────────────────────────────

_ENV_EXAMPLE_PATH = Path(__file__).resolve().parent.parent / ".env.example"


def _keys_in_env_example() -> set:
    """Parse .env.example and return the set of KEY names it defines."""
    text = _ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    keys = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", stripped)
        if match:
            keys.add(match.group(1))
    return keys


def test_schema_covers_every_env_example_var():
    """SETTINGS_SCHEMA's key set exactly matches .env.example's key set."""
    schema_keys = {f.key for f in settings._all_fields()}
    assert schema_keys == _keys_in_env_example()


def test_schema_groups_match_expected_services():
    """The schema is grouped by the four documented services, in order."""
    services = [g.service for g in settings.SETTINGS_SCHEMA]
    assert services == ["google_drive", "gemini", "ebay", "storage"]


def test_secret_fields_flagged_correctly():
    """Only the three documented keys are flagged secret."""
    secret_keys = {f.key for f in settings._all_fields() if f.secret}
    assert secret_keys == {
        "GEMINI_API_KEY",
        "EBAY_CLIENT_SECRET",
        "EBAY_OAUTH_REFRESH_TOKEN",
    }


def test_every_field_has_label_and_help_text():
    """Every schema field carries a non-empty label and help text."""
    for f in settings._all_fields():
        assert f.label
        assert f.help_text


# ── PORTAL_LINKS ───────────────────────────────────────────────────────────────


def test_portal_links_cover_required_services():
    """Portal links exist for every credentialed service plus the two draft platforms."""
    assert set(settings.PORTAL_LINKS) == {
        "google_drive",
        "gemini",
        "ebay",
        "facebook_marketplace",
        "mercari",
    }


def test_portal_links_have_url_and_guidance():
    for links in settings.PORTAL_LINKS.values():
        for link in links:
            assert link.url.startswith("https://")
            assert link.guidance


def test_portal_link_urls_match_spec():
    """Spot-check the exact URLs named in the feature spec."""
    assert settings.PORTAL_LINKS["google_drive"][0].url == (
        "https://console.cloud.google.com/iam-admin/serviceaccounts"
    )
    assert settings.PORTAL_LINKS["gemini"][0].url == "https://aistudio.google.com/apikey"
    assert settings.PORTAL_LINKS["ebay"][0].url == "https://developer.ebay.com/my/keys"
    assert settings.PORTAL_LINKS["facebook_marketplace"][0].url == (
        "https://www.facebook.com/marketplace/create/item"
    )
    assert settings.PORTAL_LINKS["mercari"][0].url == "https://www.mercari.com/sell/"


# ── settings_env_path (frozen vs non-frozen) ──────────────────────────────────


def test_settings_env_path_non_frozen_is_project_root(monkeypatch):
    """Non-frozen: settings_env_path is <project-root>/.env."""
    monkeypatch.delattr(settings.sys, "frozen", raising=False)
    resolved = settings.settings_env_path()
    assert resolved == settings._PROJECT_ROOT / ".env"


def test_settings_env_path_frozen_is_appdata(monkeypatch, tmp_path):
    """Frozen: settings_env_path is %APPDATA%/ListerBridge/.env (R-STATE)."""
    monkeypatch.setattr(settings.sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    resolved = settings.settings_env_path()

    assert resolved == tmp_path / "ListerBridge" / ".env"
    # The anchor directory must exist (created by _frozen_anchor_dir()).
    assert (tmp_path / "ListerBridge").is_dir()


def test_settings_env_path_matches_load_app_dotenv_frozen_candidate(monkeypatch, tmp_path):
    """
    The frozen settings_env_path() must be one of load_app_dotenv's own search
    candidates, so what Setup writes is guaranteed to be found by the app.
    """
    from src.core import paths

    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(settings.sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    settings_path = settings.settings_env_path()
    appdata_candidate = paths._frozen_anchor_dir() / ".env"

    assert settings_path == appdata_candidate


def test_shadowing_env_path_none_when_not_frozen(monkeypatch):
    """Non-frozen: no shadowing is possible; helper returns None."""
    monkeypatch.delattr(settings.sys, "frozen", raising=False)
    assert settings.shadowing_env_path() is None


def test_shadowing_env_path_detects_exe_adjacent_env(monkeypatch, tmp_path):
    """
    Frozen with an .env next to the .exe: helper returns that path, because
    load_app_dotenv loads it BEFORE the %APPDATA% file Setup writes (R-STATE).
    """
    exe_dir = tmp_path / "exe_dir"
    exe_dir.mkdir()
    (exe_dir / ".env").write_text("GEMINI_API_KEY=shadow\n")

    monkeypatch.setattr(settings.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        settings.sys, "executable", str(exe_dir / "lister-bridge.exe"), raising=False
    )
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    assert settings.shadowing_env_path() == exe_dir / ".env"


def test_shadowing_env_path_none_when_no_exe_env(monkeypatch, tmp_path):
    """Frozen but no exe-adjacent .env: nothing shadows; helper returns None."""
    exe_dir = tmp_path / "exe_dir"
    exe_dir.mkdir()

    monkeypatch.setattr(settings.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        settings.sys, "executable", str(exe_dir / "lister-bridge.exe"), raising=False
    )
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    assert settings.shadowing_env_path() is None


# ── read_settings / write_settings round-trip ─────────────────────────────────


@pytest.fixture
def isolated_env_path(monkeypatch, tmp_path):
    """Point settings_env_path() at a scratch project root for read/write tests."""
    monkeypatch.delattr(settings.sys, "frozen", raising=False)
    monkeypatch.setattr(settings, "_PROJECT_ROOT", tmp_path)
    return tmp_path / ".env"


def test_read_settings_missing_file_returns_defaults(isolated_env_path):
    """With no .env on disk, read_settings returns schema defaults."""
    values = settings.read_settings()
    assert values["EBAY_ENV"] == "sandbox"
    assert values["GEMINI_MODEL"] == "gemini-3.5-flash"
    assert values["GEMINI_API_KEY"] == ""


def test_write_then_read_round_trip(isolated_env_path):
    """write_settings persists values that read_settings then reads back."""
    values = settings.read_settings()
    values["GEMINI_API_KEY"] = "secret-key-123"
    values["EBAY_CLIENT_ID"] = "my-client-id"

    written_path = settings.write_settings(values)
    assert written_path == isolated_env_path
    assert written_path.is_file()

    reread = settings.read_settings()
    assert reread["GEMINI_API_KEY"] == "secret-key-123"
    assert reread["EBAY_CLIENT_ID"] == "my-client-id"


def test_write_settings_preserves_unknown_keys(isolated_env_path):
    """An unrecognized key already present is preserved across a write."""
    isolated_env_path.write_text("SOME_FUTURE_KEY=keepme\nEBAY_ENV=sandbox\n", encoding="utf-8")

    values = settings.read_settings()
    assert values["SOME_FUTURE_KEY"] == "keepme"

    values["EBAY_ENV"] = "production"
    settings.write_settings(values)

    reread = settings.read_settings()
    assert reread["SOME_FUTURE_KEY"] == "keepme"
    assert reread["EBAY_ENV"] == "production"


def test_write_settings_includes_generated_header(isolated_env_path):
    """The written file includes a generated header comment."""
    settings.write_settings(settings.read_settings())
    text = isolated_env_path.read_text(encoding="utf-8")
    assert text.startswith("# Generated by Lister-Bridge Setup")


def test_write_settings_never_writes_temp_file_left_behind(isolated_env_path):
    """The atomic-write temp file does not remain after a successful write."""
    settings.write_settings(settings.read_settings())
    tmp_candidate = isolated_env_path.parent / (isolated_env_path.name + ".tmp")
    assert not tmp_candidate.exists()
    assert isolated_env_path.exists()


def test_write_settings_is_atomic_replace(isolated_env_path, monkeypatch):
    """write_settings writes to a temp file then replaces (Path.replace), not in place."""
    calls = []
    original_replace = Path.replace

    def spy_replace(self, target):
        calls.append((str(self), str(target)))
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", spy_replace)

    settings.write_settings(settings.read_settings())

    assert len(calls) == 1
    src, dst = calls[0]
    assert src.endswith(".tmp")
    assert dst == str(isolated_env_path)


# ── missing_required ───────────────────────────────────────────────────────────


def test_missing_required_lists_empty_required_keys():
    values = {f.key: f.default for f in settings._all_fields()}
    values["GEMINI_API_KEY"] = ""  # required, blank
    values["EBAY_CLIENT_ID"] = ""  # required, blank
    values["DRIVE_CACHE_DIR"] = ""  # NOT required, blank

    missing = settings.missing_required(values)

    assert "GEMINI_API_KEY" in missing
    assert "EBAY_CLIENT_ID" in missing
    assert "DRIVE_CACHE_DIR" not in missing


def test_missing_required_empty_when_all_required_filled():
    values = {f.key: (f.default or "placeholder") for f in settings._all_fields()}
    assert settings.missing_required(values) == []


def test_missing_required_treats_whitespace_as_missing():
    values = {f.key: (f.default or "x") for f in settings._all_fields()}
    values["GEMINI_API_KEY"] = "   "
    assert "GEMINI_API_KEY" in settings.missing_required(values)


# ── validate_drive ──────────────────────────────────────────────────────────────


class _FakeDriveRequest:
    def __init__(self, result=None, exc=None):
        self._result = result or {"files": []}
        self._exc = exc

    def execute(self):
        if self._exc:
            raise self._exc
        return self._result


class _FakeDriveFiles:
    def __init__(self, request):
        self._request = request

    def list(self, **kwargs):
        return self._request


class _FakeDriveService:
    def __init__(self, request):
        self._request = request

    def files(self):
        return _FakeDriveFiles(self._request)


def test_validate_drive_success_with_injected_service():
    service = _FakeDriveService(_FakeDriveRequest(result={"files": []}))
    result = settings.validate_drive(
        {"GOOGLE_SERVICE_ACCOUNT_JSON": "/x.json", "DRIVE_STAGING_FOLDER_ID": "F1"},
        drive_service=service,
    )
    assert result.ok is True
    assert isinstance(result, settings.ValidationResult)


def test_validate_drive_failure_with_injected_service_raising():
    service = _FakeDriveService(_FakeDriveRequest(exc=RuntimeError("boom")))
    result = settings.validate_drive(
        {"GOOGLE_SERVICE_ACCOUNT_JSON": "/x.json", "DRIVE_STAGING_FOLDER_ID": "F1"},
        drive_service=service,
    )
    assert result.ok is False
    assert "boom" in result.message


def test_validate_drive_missing_json_path_fails_without_service():
    result = settings.validate_drive({"GOOGLE_SERVICE_ACCOUNT_JSON": ""})
    assert result.ok is False
    assert "GOOGLE_SERVICE_ACCOUNT_JSON" in result.message


def test_validate_drive_nonexistent_json_path_fails_without_service(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    result = settings.validate_drive({"GOOGLE_SERVICE_ACCOUNT_JSON": str(missing)})
    assert result.ok is False
    assert "not found" in result.message.lower()


# ── validate_gemini ─────────────────────────────────────────────────────────────


class _FakeGeminiModels:
    def __init__(self, exc=None):
        self._exc = exc
        self.calls = []

    def count_tokens(self, model, contents):
        self.calls.append((model, contents))
        if self._exc:
            raise self._exc
        return {"total_tokens": 1}


class _FakeGeminiClient:
    def __init__(self, exc=None):
        self.models = _FakeGeminiModels(exc)


def test_validate_gemini_success_with_injected_client():
    client = _FakeGeminiClient()
    result = settings.validate_gemini(
        {"GEMINI_API_KEY": "k", "GEMINI_MODEL": "gemini-3.5-flash"}, client=client
    )
    assert result.ok is True
    assert client.models.calls == [("gemini-3.5-flash", "ping")]


def test_validate_gemini_failure_with_injected_client_raising():
    client = _FakeGeminiClient(exc=RuntimeError("bad key"))
    result = settings.validate_gemini({"GEMINI_API_KEY": "k"}, client=client)
    assert result.ok is False
    assert "bad key" in result.message


def test_validate_gemini_missing_api_key_fails_without_client():
    result = settings.validate_gemini({"GEMINI_API_KEY": ""})
    assert result.ok is False
    assert "GEMINI_API_KEY" in result.message


# ── validate_ebay (reuses EbayAuth; follows test_ebay_auth.py FakeSession) ─────

_VALID_SCOPES = (
    "https://api.ebay.com/oauth/api_scope "
    "https://api.ebay.com/oauth/api_scope/sell.inventory "
    "https://api.ebay.com/oauth/api_scope/commerce.media"
)


def _ebay_values(**overrides):
    values = dict(
        EBAY_ENV="sandbox",
        EBAY_CLIENT_ID="cid",
        EBAY_CLIENT_SECRET="csecret",
        EBAY_OAUTH_REFRESH_TOKEN="rtoken",
        EBAY_OAUTH_SCOPES=_VALID_SCOPES,
    )
    values.update(overrides)
    return values


def test_validate_ebay_success_with_injected_session(fake_session, fake_response):
    sess = fake_session(
        [fake_response(200, {"access_token": "AT-1", "expires_in": 7200})]
    )
    result = settings.validate_ebay(_ebay_values(), session=sess)
    assert result.ok is True


def test_validate_ebay_uses_entered_values_not_ambient_env(
    fake_session, fake_response, monkeypatch
):
    """validate_ebay must use the passed-in values, not os.environ, for creds."""
    monkeypatch.setenv("EBAY_CLIENT_ID", "WRONG-FROM-ENV")
    monkeypatch.setenv("EBAY_CLIENT_SECRET", "WRONG-FROM-ENV")
    monkeypatch.setenv("EBAY_OAUTH_REFRESH_TOKEN", "WRONG-FROM-ENV")

    sess = fake_session(
        [fake_response(200, {"access_token": "AT-1", "expires_in": 7200})]
    )
    settings.validate_ebay(_ebay_values(EBAY_CLIENT_ID="RIGHT"), session=sess)

    call = sess.calls[0]
    # Basic auth header is base64(client_id:client_secret) — assert the entered
    # client id was used by checking it's NOT the ambient-env sentinel value.
    import base64

    header = call["headers"]["Authorization"]
    decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
    assert decoded.startswith("RIGHT:")


def test_validate_ebay_failure_on_non_200(fake_session, fake_response):
    sess = fake_session([fake_response(401, {}, text="invalid_client")])
    result = settings.validate_ebay(_ebay_values(), session=sess)
    assert result.ok is False
    assert "eBay check failed" in result.message


def test_validate_ebay_failure_on_bad_scope_format(fake_session):
    sess = fake_session([])
    result = settings.validate_ebay(
        _ebay_values(EBAY_OAUTH_SCOPES="sell.inventory"), session=sess
    )
    assert result.ok is False
    assert len(sess.calls) == 0  # fails fast at construction, no network call


def test_validate_ebay_failure_on_missing_credentials(fake_session):
    sess = fake_session([])
    result = settings.validate_ebay(
        _ebay_values(EBAY_CLIENT_ID="", EBAY_CLIENT_SECRET="", EBAY_OAUTH_REFRESH_TOKEN=""),
        session=sess,
    )
    assert result.ok is False


# ── ValidationResult message truncation ────────────────────────────────────────


def test_truncate_long_exception_message():
    long_text = "x" * 500
    truncated = settings._truncate(long_text)
    assert len(truncated) == settings._MESSAGE_TRUNCATE_LEN + 3  # + "..."
    assert truncated.endswith("...")


def test_truncate_short_message_unchanged():
    assert settings._truncate("short") == "short"
