---
# migaku-enforcer-n5pw
title: Fix tray icon never appearing on Linux
status: completed
type: bug
created_at: 2026-11-15T03:37:38Z
updated_at: 2026-11-15T03:37:38Z
---

Exit (Minimize to Tray) reported 'No System Tray Available' (libayatana-appindicator missing), and once installed the icon still would never have registered: pystray's GTK/AppIndicator backends make run_detached() only prepare for a host GLib loop, which Tk never runs.

## Todo
- [x] Install/verify libayatana-appindicator backend selected
- [x] Run icon loop in own thread on Linux; keep one persistent icon and toggle visibility (stopped AppIndicator items stay registered until process exit)
- [x] Tooltip/log say 'vacation day' vs 'goal met'
- [x] Test hide/restore/hide with real Tk window against Quickshell's StatusNotifierWatcher

## Summary of Changes
MigakuStatusWindow._start_tray_icon/_make_tray_icon/_stop_tray; Windows path unchanged. README setup updated (python-gobject, libayatana-appindicator, venv --system-site-packages).
