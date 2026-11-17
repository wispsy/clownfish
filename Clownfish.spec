# -*- mode: python ; coding: utf-8 -*-
"""Portable PyInstaller specification for Clownfish.app."""

import os
from PyInstaller.utils.hooks import collect_all

spec_root = os.path.abspath(SPECPATH)
src_dir = os.path.join(spec_root, "src")
icon_icns = os.path.join(spec_root, "assets", "Clownfish.icns")
icon_png = os.path.join(src_dir, "clownfish", "clownfish.png")

datas = [(icon_png, "clownfish")]
binaries = []
hiddenimports = []
tmp_ret = collect_all("clownfish")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

a = Analysis(
    [os.path.join(src_dir, "clownfish", "main.py")],
    pathex=[src_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Clownfish",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[icon_icns] if os.path.exists(icon_icns) else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Clownfish",
)
app = BUNDLE(
    coll,
    name="Clownfish.app",
    icon=icon_icns if os.path.exists(icon_icns) else None,
    bundle_identifier="tech.wispsy.clownfish",
)
