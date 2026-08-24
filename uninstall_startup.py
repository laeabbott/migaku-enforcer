#!/usr/bin/env python3
"""
Run this script once to remove Migaku Enforcer from Windows startup.
It will ask for administrator permission via the UAC prompt.
"""
import sys
import os
import ctypes
from pathlib import Path


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def relaunch_as_admin():
    script = os.path.abspath(__file__)
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, f'"{script}"', None, 1
    )
    return int(ret) > 32


if not is_admin():
    print("Requesting administrator privileges...")
    if relaunch_as_admin():
        sys.exit(0)
    else:
        print("UAC prompt was cancelled or failed.")
        input("Press Enter to exit.")
        sys.exit(1)

# --- Running as admin ---
enforcer_dir = Path(__file__).parent
sys.path.insert(0, str(enforcer_dir))

from migaku_enforcer import uninstall_startup

print("=" * 50)
print("Migaku Enforcer - Startup Removal")
print("=" * 50)
print()

uninstall_startup()

print()
print("Done! Migaku Enforcer will no longer start automatically.")
print()
input("Press Enter to close this window.")
