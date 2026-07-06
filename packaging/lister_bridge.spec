# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec (v1.3) — reproducible single-file build of the Lister-Bridge
desktop app. This spec is the SINGLE canonical build route: scripts/build_desktop.py
now just invokes `pyinstaller packaging/lister_bridge.spec` rather than driving a
second, divergent PyInstaller invocation of its own.

Build:
    pip install -r requirements.txt -r requirements-build.txt
    pyinstaller packaging/lister_bridge.spec
    (equivalently: python scripts/build_desktop.py)
Output:
    dist/lister-bridge.exe  (one file)

Notes:
- Entry point is desktop_app.py, which hosts src/ui/app.py in a pywebview window.
- collect_all() pulls in Streamlit + streamlit-desktop-app data/binaries/hidden
  imports; the `src` package is bundled as importable code AND shipped as data so
  desktop_app._app_script_path() can resolve src/ui/app.py at runtime (sys._MEIPASS).
- googleapiclient (Drive API client) also ships discovery-document/data files
  that plain hidden-import collection misses, so it is collect_all()'d too —
  without this, Drive API `build("drive", "v3", ...)` fails at runtime in the
  frozen build even though it imports fine from source.
- All paths fed to Analysis()/datas are built from SPECPATH (the directory
  PyInstaller sets to this .spec file's own directory), NOT relative to the
  process's current working directory. PyInstaller resolves bare relative
  strings (e.g. "desktop_app.py", ("src", "src")) against the spec file's own
  directory, so without this fix `pyinstaller packaging/lister_bridge.spec` run
  from the repo root looked for packaging/desktop_app.py and packaging/src —
  neither of which exist; the real ones live at the repo root.
- win_no_prefer_redirects / win_private_assemblies / cipher= were removed from
  Analysis()/PYZ() in PyInstaller 6.0 (requirements-build.txt pins >=6.0), so
  passing them raises a TypeError at spec-parse time. They are omitted below.
"""

import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

# SPECPATH is injected by PyInstaller's spec-file exec environment: the
# directory containing THIS .spec file (packaging/). The repo root is one
# level up. Building every path from this, rather than a bare relative
# string, makes the build location-independent of the caller's cwd.
_REPO_ROOT = os.path.join(SPECPATH, "..")
_ENTRY_SCRIPT = os.path.join(_REPO_ROOT, "desktop_app.py")
_SRC_DIR = os.path.join(_REPO_ROOT, "src")

datas = []
binaries = []
hiddenimports = []

# Streamlit + the desktop wrapper bring large data trees and many hidden
# imports; googleapiclient ships Drive API discovery/data files that hidden
# imports alone would miss (fixes silent Drive-API failures in the frozen build).
for _pkg in ("streamlit", "streamlit_desktop_app", "pydantic", "googleapiclient"):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

# Our own package: bundle every submodule as importable code, and ship the tree
# as data so the Streamlit script (src/ui/app.py) is present at runtime.
hiddenimports += collect_submodules("src")
datas += [(_SRC_DIR, "src")]

a = Analysis(
    [_ENTRY_SCRIPT],
    pathex=[_REPO_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="lister-bridge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI app — no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
