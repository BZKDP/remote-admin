# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules

# spec лежит в build/, исходник агента — в ../agent/
ROOT = os.path.abspath(os.path.join(os.path.dirname(SPECPATH), "."))
AGENT = os.path.join(ROOT, "agent", "agent.py")
VERSION = os.path.join(SPECPATH, "version_info.txt")

hiddenimports = ['PIL']
hiddenimports += collect_submodules('pynput')
hiddenimports += collect_submodules('mss')


a = Analysis(
    [AGENT],
    pathex=[],
    binaries=[],
    datas=[],
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
    a.binaries,
    a.datas,
    [],
    name='RemoteAdminAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=VERSION,
)
