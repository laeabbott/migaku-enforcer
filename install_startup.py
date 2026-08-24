#!/usr/bin/env python3
"""
Run this script once to register Migaku Enforcer as a startup task.
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
    """Re-run this script with UAC elevation."""
    script = os.path.abspath(__file__)
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, f'"{script}"', None, 1
    )
    # ShellExecuteW returns > 32 on success
    return int(ret) > 32


if not is_admin():
    print("Requesting administrator privileges...")
    if relaunch_as_admin():
        sys.exit(0)
    else:
        print("UAC prompt was cancelled or failed.")
        input("Press Enter to exit.")
        sys.exit(1)

# --- We are now running as admin ---
# Import and call the enforcer's install function
enforcer_dir = Path(__file__).parent
sys.path.insert(0, str(enforcer_dir))

from migaku_enforcer import install_startup, check_admin_privileges, MigakuEnforcer, DEFAULT_RESET_HOUR

print("=" * 50)
print("Migaku Enforcer - Startup Installation")
print("=" * 50)
print()

if not check_admin_privileges():
    print("ERROR: Still not running as administrator. Cannot continue.")
    input("Press Enter to exit.")
    sys.exit(1)

reset_hour = MigakuEnforcer().config.get('reset_hour', DEFAULT_RESET_HOUR)
install_startup(reset_hour)

print()
print("Done! Migaku Enforcer will now start automatically when you log in.")
print("The GUI window will appear ~30 seconds after login.")
print()
input("Press Enter to close this window.")
