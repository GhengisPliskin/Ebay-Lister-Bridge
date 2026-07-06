"""
Module: test_paths.py
Purpose: Tests for src/core/paths.py — the shared frozen-safe path anchor
         helper (resolve_app_path) and the frozen-aware .env loader
         (load_app_dotenv). No network, no real PyInstaller build.
FMEA Constraints Enforced (asserted): R-STATE.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core import paths


# ── resolve_app_path ──────────────────────────────────────────────────────────


def test_non_frozen_anchors_to_project_root(monkeypatch):
    """
    Non-frozen mode anchors a relative path to the project root, exactly as
    the pre-existing `Path(__file__).parent.parent.parent` logic did.
    """
    # Ensure we exercise the non-frozen branch regardless of the real runtime.
    monkeypatch.delattr(paths.sys, "frozen", raising=False)

    resolved = paths.resolve_app_path("data/state/lister_bridge.db")

    expected_root = Path(paths.__file__).parent.parent.parent
    assert resolved == expected_root / "data/state/lister_bridge.db"


def test_frozen_anchors_to_appdata(monkeypatch, tmp_path):
    """
    Frozen mode (sys.frozen = True) anchors a relative path under
    %APPDATA%/ListerBridge instead of the project root (R-STATE: this is the
    directory that survives process exit, unlike sys._MEIPASS).
    """
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    resolved = paths.resolve_app_path("data/cache/images")

    expected = tmp_path / "ListerBridge" / "data/cache/images"
    assert resolved == expected
    # The anchor directory itself must have been created.
    assert (tmp_path / "ListerBridge").is_dir()


def test_frozen_falls_back_to_home_when_appdata_unset(monkeypatch, tmp_path):
    """When frozen but APPDATA is unset, anchor under the home directory."""
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))

    resolved = paths.resolve_app_path("data/x.db")

    assert resolved == tmp_path / "ListerBridge" / "data/x.db"


def test_absolute_path_passthrough_non_frozen(monkeypatch, tmp_path):
    """An absolute path is returned unchanged when not frozen."""
    monkeypatch.delattr(paths.sys, "frozen", raising=False)
    # Built from tmp_path (not a hardcoded POSIX literal like "/tmp/...") so the
    # input is genuinely absolute per pathlib on whichever OS runs the suite —
    # on Windows, a driveless "/tmp/..." string is NOT `.is_absolute()`.
    abs_input = str(tmp_path / "somewhere" / "state.db")
    assert paths.resolve_app_path(abs_input) == Path(abs_input)


def test_absolute_path_passthrough_frozen(monkeypatch, tmp_path):
    """An absolute path is returned unchanged even when frozen."""
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    # Distinct from the APPDATA dir above so passthrough can't be confused with
    # the frozen anchor; see test_absolute_path_passthrough_non_frozen for why
    # this must be tmp_path-derived rather than a hardcoded POSIX literal.
    abs_input = str(tmp_path / "elsewhere" / "state.db")
    assert paths.resolve_app_path(abs_input) == Path(abs_input)


def test_accepts_path_object_input(monkeypatch):
    """resolve_app_path also accepts a Path (not just str) as input."""
    monkeypatch.delattr(paths.sys, "frozen", raising=False)
    resolved = paths.resolve_app_path(Path("data") / "x.db")
    expected_root = Path(paths.__file__).parent.parent.parent
    assert resolved == expected_root / "data" / "x.db"


# ── load_app_dotenv ───────────────────────────────────────────────────────────


def test_load_app_dotenv_non_frozen_calls_plain_load_dotenv(monkeypatch):
    """Non-frozen mode is unchanged: a single plain load_dotenv() call."""
    monkeypatch.delattr(paths.sys, "frozen", raising=False)
    calls = []
    monkeypatch.setattr(paths, "load_dotenv", lambda *a, **kw: calls.append((a, kw)))

    paths.load_app_dotenv()

    assert calls == [((), {})]


def test_load_app_dotenv_frozen_prefers_exe_dir(monkeypatch, tmp_path):
    """
    Frozen mode: a .env next to sys.executable is loaded first, ahead of the
    %APPDATA%/ListerBridge candidate and the default cwd search.
    """
    exe_dir = tmp_path / "exe_dir"
    exe_dir.mkdir()
    (exe_dir / ".env").write_text("FOO=bar\n", encoding="utf-8")
    appdata_dir = tmp_path / "appdata"
    appdata_dir.mkdir()

    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "executable", str(exe_dir / "lister-bridge.exe"))
    monkeypatch.setenv("APPDATA", str(appdata_dir))

    calls = []
    monkeypatch.setattr(
        paths, "load_dotenv", lambda *a, **kw: calls.append((a, kw))
    )

    paths.load_app_dotenv()

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert kwargs.get("dotenv_path") == exe_dir / ".env"


def test_load_app_dotenv_frozen_falls_back_to_appdata(monkeypatch, tmp_path):
    """
    Frozen mode: when no .env sits next to the exe, the %APPDATA%/ListerBridge
    candidate is tried next.
    """
    exe_dir = tmp_path / "exe_dir"
    exe_dir.mkdir()
    appdata_dir = tmp_path / "appdata"
    appdata_dir.mkdir()
    (appdata_dir / "ListerBridge").mkdir()
    (appdata_dir / "ListerBridge" / ".env").write_text("FOO=bar\n", encoding="utf-8")

    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "executable", str(exe_dir / "lister-bridge.exe"))
    monkeypatch.setenv("APPDATA", str(appdata_dir))

    calls = []
    monkeypatch.setattr(
        paths, "load_dotenv", lambda *a, **kw: calls.append((a, kw))
    )

    paths.load_app_dotenv()

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert kwargs.get("dotenv_path") == appdata_dir / "ListerBridge" / ".env"


def test_load_app_dotenv_frozen_falls_back_to_default_search(monkeypatch, tmp_path):
    """
    Frozen mode: when neither the exe-dir nor the APPDATA candidate exists,
    fall back to the default (cwd-upward) load_dotenv() search.
    """
    exe_dir = tmp_path / "exe_dir"
    exe_dir.mkdir()
    appdata_dir = tmp_path / "appdata"
    appdata_dir.mkdir()

    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "executable", str(exe_dir / "lister-bridge.exe"))
    monkeypatch.setenv("APPDATA", str(appdata_dir))

    calls = []
    monkeypatch.setattr(
        paths, "load_dotenv", lambda *a, **kw: calls.append((a, kw))
    )

    paths.load_app_dotenv()

    assert calls == [((), {})]
