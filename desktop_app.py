"""
Module: desktop_app.py
Purpose: Desktop entry point (v1.2) — launches the Streamlit review/approve GUI in
         a native window via streamlit-desktop-app (pywebview). This is both the
         dev launcher (`python desktop_app.py`) and the script PyInstaller bundles
         into the standalone .exe.
Primary Responsibilities:
  - Resolve the Streamlit app path whether running from source or a frozen exe.
  - Start the desktop window pointing at src/ui/app.py.
Key Interfaces:
  - Input: none (reads .env at runtime like the rest of the app).
  - Output: a native desktop window hosting the Streamlit UI.
FMEA Constraints Enforced:
  - None directly; this is the packaging shell around the existing UI.

Build the .exe:  python scripts/build_desktop.py   (see README "Desktop build").
"""

from __future__ import annotations

import os
import sys


def _app_script_path() -> str:
    """
    Return the absolute path to the Streamlit app script.

    Works both from source (repo layout) and from a PyInstaller bundle, where
    data files are unpacked under sys._MEIPASS.

    Returns:
        Absolute path to src/ui/app.py.
    """
    # PyInstaller sets sys._MEIPASS to the temp extraction dir of the frozen app.
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "src", "ui", "app.py")


def main() -> None:
    """
    Launch the Streamlit GUI inside a native desktop window.

    Side Effects:
        Opens a pywebview window and runs the Streamlit server in-process. Imports
        streamlit_desktop_app lazily so this module imports even when the build
        dependency is not installed (e.g. during tests).

    Raises:
        ImportError: If streamlit-desktop-app is not installed (build dep). The
            message points at requirements-build.txt.
    """
    try:
        from streamlit_desktop_app import start_desktop_app
    except ImportError as exc:  # pragma: no cover - build-time dependency
        raise ImportError(
            "streamlit-desktop-app is not installed. Install the build deps:\n"
            "    pip install -r requirements.txt -r requirements-build.txt"
        ) from exc

    start_desktop_app(
        _app_script_path(),
        title="Lister-Bridge",
        width=1280,
        height=900,
    )


if __name__ == "__main__":
    main()
