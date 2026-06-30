"""
Module: build_desktop.py
Purpose: One-command builder (v1.2) for the standalone Lister-Bridge desktop .exe.
         Wraps the streamlit-desktop-app CLI (which drives PyInstaller) with the
         options needed to bundle the Streamlit GUI + the `src` package.
Primary Responsibilities:
  - Verify the build dependency is installed; if not, print how to install it.
  - Invoke `streamlit-desktop-app build` non-interactively with reproducible options.
Key Interfaces:
  - Input: the repo tree (src/ui/app.py + the src package).
  - Output: dist/lister-bridge.exe (on success).
FMEA Constraints Enforced:
  - None; build tooling.

Run:  python scripts/build_desktop.py
Requires the build deps:  pip install -r requirements.txt -r requirements-build.txt
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

# The Streamlit script the desktop window hosts.
_APP_SCRIPT = os.path.join("src", "ui", "app.py")
_APP_NAME = "lister-bridge"


def _build_dep_available() -> bool:
    """Return True if streamlit-desktop-app is importable."""
    return importlib.util.find_spec("streamlit_desktop_app") is not None


def main() -> int:
    """
    Build the desktop .exe; return a process exit code.

    Returns:
        0 on a successful build; 1 if the build dependency is missing or the
        build command fails.

    Side Effects:
        Spawns the streamlit-desktop-app CLI (PyInstaller) which writes to dist/.
    """
    if not _build_dep_available():
        print(
            "[build] streamlit-desktop-app is not installed.\n"
            "        Install the build deps and re-run:\n"
            "          pip install -r requirements.txt -r requirements-build.txt\n"
            "          python scripts/build_desktop.py"
        )
        return 1

    # PyInstaller options so the frozen app can import the `src` package and find
    # the Streamlit app script at runtime (see desktop_app._app_script_path).
    #   --paths=.                     resolve `src` imports at build time
    #   --collect-submodules=src      bundle every src.* module as importable code
    #   --add-data "src;src"          ship the src tree (incl. ui/app.py) as data
    # On non-Windows the --add-data separator is ":" not ";".
    sep = ";" if os.name == "nt" else ":"
    pyinstaller_opts = (
        f"--paths=. --collect-submodules=src --add-data src{sep}src"
    )

    cmd = [
        sys.executable, "-m", "streamlit_desktop_app", "build",
        "--script", _APP_SCRIPT,
        "--name", _APP_NAME,
        "--pyinstaller-options", pyinstaller_opts,
    ]
    print(f"[build] running: {' '.join(cmd)}")
    completed = subprocess.run(cmd, check=False)
    if completed.returncode == 0:
        print(f"[build] done -> dist/{_APP_NAME}.exe")
    else:
        print(f"[build] FAILED (exit {completed.returncode}).")
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
