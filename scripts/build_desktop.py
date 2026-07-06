"""
Module: build_desktop.py
Purpose: One-command builder (v1.3) for the standalone Lister-Bridge desktop .exe.
         Invokes PyInstaller against the canonical spec file
         (packaging/lister_bridge.spec) so there is exactly one build route —
         this script is now a thin, reproducible wrapper around it rather than a
         second, divergent PyInstaller invocation targeting a different entry
         point.
Primary Responsibilities:
  - Verify the build dependency (pyinstaller) is installed; if not, print how
    to install it.
  - Invoke `pyinstaller packaging/lister_bridge.spec` from the repo root
    non-interactively.
Key Interfaces:
  - Input: packaging/lister_bridge.spec (which itself references desktop_app.py
    and the `src` package — see that file for the canonical build definition).
  - Output: dist/lister-bridge.exe (on success).
FMEA Constraints Enforced:
  - None; build tooling.

Run:  python scripts/build_desktop.py
Requires the build deps:  pip install -r requirements.txt -r requirements-build.txt

HISTORY: prior to this fix, this script drove `streamlit-desktop-app build`
against src/ui/app.py directly, while packaging/lister_bridge.spec built
desktop_app.py — two divergent routes producing different artifacts. The spec
is now the single source of truth for the build; this script only shells out
to it.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

# The canonical spec file. Kept relative to this script's own location (not
# the caller's cwd) so `python scripts/build_desktop.py` works regardless of
# where it is invoked from; the spec is then run with cwd=_REPO_ROOT so its
# own SPECPATH-relative path resolution (see the .spec file) behaves the same
# way it would from a plain `pyinstaller packaging/lister_bridge.spec` run at
# the repo root.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SPEC_PATH = os.path.join("packaging", "lister_bridge.spec")
_APP_NAME = "lister-bridge"


def _build_dep_available() -> bool:
    """Return True if PyInstaller is importable (the actual build driver now)."""
    return importlib.util.find_spec("PyInstaller") is not None


def main() -> int:
    """
    Build the desktop .exe by running PyInstaller against the canonical spec.

    Returns:
        0 on a successful build; 1 if the build dependency is missing or the
        build command fails.

    Side Effects:
        Spawns `pyinstaller packaging/lister_bridge.spec` (cwd=repo root),
        which writes dist/lister-bridge.exe and the build/ work directory.
    """
    if not _build_dep_available():
        print(
            "[build] PyInstaller is not installed.\n"
            "        Install the build deps and re-run:\n"
            "          pip install -r requirements.txt -r requirements-build.txt\n"
            "          python scripts/build_desktop.py"
        )
        return 1

    # A single canonical invocation: PyInstaller against the spec file. All
    # entry-point / data-file / hidden-import decisions live in the .spec
    # (packaging/lister_bridge.spec), not duplicated here as CLI flags.
    cmd = [sys.executable, "-m", "PyInstaller", _SPEC_PATH]
    print(f"[build] running: {' '.join(cmd)} (cwd={_REPO_ROOT})")
    completed = subprocess.run(cmd, cwd=_REPO_ROOT, check=False)
    if completed.returncode == 0:
        print(f"[build] done -> dist/{_APP_NAME}.exe")
    else:
        print(f"[build] FAILED (exit {completed.returncode}).")
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
