# -*- mode: python ; coding: utf-8 -*-
#
# Build with:  pyinstaller migaku_enforcer.spec
# Output:      dist/MigakuEnforcer.exe  (single file — no COLLECT step below, so
#              this is a onefile build: everything bundled into the one exe)
#
# console=False + uac_admin=True together mean: no console window ever, and an
# embedded manifest requesting requireAdministrator so Windows elevates via UAC
# the instant the exe launches — no runtime ShellExecuteW relaunch dance needed.

block_cipher = None

a = Analysis(
    ['migaku_enforcer.py'],
    pathex=[],
    binaries=[],
    datas=[],
    # pystray dispatches its backend by platform at import time, and win10toast's
    # toast module is imported lazily inside a try/except in migaku_enforcer.py —
    # both are patterns PyInstaller's static import scanner can miss.
    hiddenimports=['pystray._win32', 'win10toast'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MigakuEnforcer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # --windowed: no console window, ever
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,      # embeds requireAdministrator manifest
    icon='assets/migaku_enforcer.ico',
)
