# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec (v1.2) — reproducible single-file build of the Lister-Bridge
desktop app, as an alternative to `python scripts/build_desktop.py`.

Build:
    pip install -r requirements.txt -r requirements-build.txt
    pyinstaller packaging/lister_bridge.spec
Output:
    dist/lister-bridge.exe  (one file)

Notes:
- Entry point is desktop_app.py, which hosts src/ui/app.py in a pywebview window.
- collect_all() pulls in Streamlit + streamlit-desktop-app data/binaries/hidden
  imports; the `src` package is bundled as importable code AND shipped as data so
  desktop_app._app_script_path() can resolve src/ui/app.py at runtime (sys._MEIPASS).
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = []

# Streamlit + the desktop wrapper bring large data trees and many hidden imports.
for _pkg in ("streamlit", "streamlit_desktop_app", "pydantic"):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

# Our own package: bundle every submodule as importable code, and ship the tree
# as data so the Streamlit script (src/ui/app.py) is present at runtime.
hiddenimports += collect_submodules("src")
datas += [("src", "src")]

block_cipher = None

a = Analysis(
    ["desktop_app.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
