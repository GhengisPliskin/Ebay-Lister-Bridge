"""
Module: paths.py
Purpose: Single shared helper that anchors relative app paths (SQLite DB, image
         cache, etc.) to a directory that survives the process exiting, whether
         running from source or from a frozen PyInstaller onefile .exe. Also
         provides the frozen-aware .env discovery helper used by every module
         that calls load_dotenv().
Primary Responsibilities:
  - Detect whether the current process is a frozen PyInstaller build
    (sys.frozen) and pick the correct anchor directory for that case.
  - Frozen: anchor to %APPDATA%\\ListerBridge (a stable, writable, per-user
    directory outside the onefile temp-extraction dir), creating it if needed.
  - Not frozen: anchor to the project root exactly as the pre-existing
    `Path(__file__).parent.parent.parent` logic did, so dev/test behavior is
    unchanged.
  - Pass absolute inputs through unchanged in both cases.
  - When frozen, additionally try loading a .env from the executable's own
    directory and from %APPDATA%/ListerBridge before falling back to the
    default cwd-relative search python-dotenv performs.
Key Interfaces:
  - Input: a relative or absolute path (str or Path) from callers such as
    state_store.py (SQLite DB) and drive_fetcher.py (image cache dir).
  - Output: an absolute Path anchored appropriately for the runtime mode; or,
    for load_app_dotenv(), the side effect of populating os.environ.
FMEA Constraints Enforced:
  - R-STATE — under PyInstaller onefile, `Path(__file__).parent.parent.parent`
    resolves inside `sys._MEIPASS`, the temp extraction dir PyInstaller deletes
    when the process exits. Anchoring the dedup SQLite DB and the image cache
    there means both are silently wiped every run, defeating crash-and-resume
    dedup (R-STATE requires offer_id/listing_id + cache state to survive across
    runs). This helper is the single fix point for that failure mode. The same
    MEIPASS problem applies to plain `load_dotenv()` cwd-relative discovery —
    a frozen .exe launched via double-click has an unpredictable cwd, so the
    .env (which carries STATE_STORE_DB_PATH / DRIVE_CACHE_DIR, among others)
    may silently fail to load at all.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Project root as seen from THIS file's location (src/core/paths.py):
#   src/core/paths.py -> src/core -> src -> project root.
# This mirrors the anchor previously duplicated in state_store.py and
# drive_fetcher.py, so non-frozen behavior is byte-for-byte identical.
_PROJECT_ROOT = Path(__file__).parent.parent.parent

# Application name used for the frozen-mode per-user data directory.
_APP_DIR_NAME = "ListerBridge"


def _frozen_anchor_dir() -> Path:
    """
    Return (and create) the per-user directory used to anchor paths when frozen.

    Args:
        None

    Returns:
        Path to %APPDATA%/ListerBridge (or $HOME/ListerBridge if APPDATA is
        unset, e.g. non-Windows testing of the frozen branch).

    Side Effects:
        Creates the directory tree if it does not already exist.

    FMEA Constraints:
        R-STATE — this directory is NOT the PyInstaller onefile temp extraction
        dir (sys._MEIPASS), so files written here survive process exit and are
        available again on the next launch.
    """
    # APPDATA is the standard per-user, non-roaming-safe writable directory on
    # Windows; fall back to the home directory if it's ever unset (e.g. running
    # a frozen-mode test on a non-Windows CI box).
    base = Path(os.environ.get("APPDATA", str(Path.home())))
    anchor = base / _APP_DIR_NAME
    anchor.mkdir(parents=True, exist_ok=True)
    return anchor


def resolve_app_path(relative: "Path | str") -> Path:
    """
    Resolve a possibly-relative app path to an absolute, run-safe location.

    Args:
        relative: A relative or absolute path (str or Path). Relative paths are
            anchored per the current runtime mode (see below); absolute paths
            are returned unchanged (as a Path).

    Returns:
        An absolute Path:
          - If `relative` is already absolute: returned unchanged (as a Path).
          - If frozen (getattr(sys, "frozen", False) is True): anchored under
            %APPDATA%/ListerBridge (created if missing).
          - Otherwise: anchored under the project root, exactly matching the
            previous `Path(__file__).parent.parent.parent` behavior.

    Side Effects:
        May create the frozen-mode anchor directory (%APPDATA%/ListerBridge).
        Does NOT create the final target's parent directory — callers that
        need the immediate parent to exist (e.g. for a DB file) still create
        it themselves, matching prior behavior.

    FMEA Constraints:
        R-STATE — this is the sole anchoring implementation for the SQLite
        dedup DB (state_store.py) and the Drive image cache (drive_fetcher.py),
        replacing the two duplicated, MEIPASS-vulnerable copies.
    """
    path_obj = Path(relative)

    # Absolute inputs are never re-anchored — pass through unchanged.
    if path_obj.is_absolute():
        return path_obj

    # Frozen (PyInstaller onefile): anchor to a stable per-user directory that
    # is NOT deleted when the bootloader tears down sys._MEIPASS on exit.
    if getattr(sys, "frozen", False):
        return _frozen_anchor_dir() / path_obj

    # Not frozen (source / test run): anchor to the project root, identical to
    # the pre-existing behavior in state_store.py and drive_fetcher.py.
    return _PROJECT_ROOT / path_obj


def load_app_dotenv() -> None:
    """
    Load the .env file, trying frozen-safe locations first when applicable.

    Every module that previously called `load_dotenv()` directly (state_store,
    drive_fetcher, ebay_auth, ebay_client) should call this instead so .env
    discovery is centralized and frozen-aware in one place.

    Args:
        None

    Returns:
        None

    Side Effects:
        Populates os.environ from the first .env file found (python-dotenv's
        load_dotenv does not override already-set variables). When frozen, up
        to two extra candidate paths are tried, in order, before falling back
        to python-dotenv's own default (cwd-upward) search:
          1. Path(sys.executable).parent / ".env"  (next to the .exe)
          2. %APPDATA%/ListerBridge/.env            (the frozen anchor dir)
          3. load_dotenv() with no args              (default cwd search)
        When NOT frozen, behavior is unchanged: a single plain load_dotenv()
        call (default cwd-upward search), exactly as before this fix.

    FMEA Constraints:
        R-STATE — a frozen .exe's working directory is not guaranteed to be
        the install directory, so the plain cwd-relative load_dotenv() search
        can silently miss the user's .env (and therefore STATE_STORE_DB_PATH /
        DRIVE_CACHE_DIR / credentials). Trying the exe's own directory and the
        frozen anchor directory first makes .env discovery deterministic for
        the packaged app.
    """
    # Non-frozen (source / test run): behavior is completely unchanged.
    if not getattr(sys, "frozen", False):
        load_dotenv()
        return

    # Frozen: try the executable's own directory first (the most natural place
    # for a user to drop a .env next to lister-bridge.exe), then the frozen
    # anchor directory (%APPDATA%/ListerBridge), then fall back to the default
    # cwd-upward search so no previously-working setup regresses.
    candidates = [
        Path(sys.executable).parent / ".env",
        _frozen_anchor_dir() / ".env",
    ]
    for candidate in candidates:
        if candidate.is_file():
            load_dotenv(dotenv_path=candidate)
            return

    # Neither frozen-specific candidate exists — fall back to the default
    # search so a cwd-relative .env still works if the user happens to launch
    # the .exe from a directory containing one.
    load_dotenv()
