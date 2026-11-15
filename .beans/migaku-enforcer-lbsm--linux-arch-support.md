---
# migaku-enforcer-lbsm
title: Linux (Arch) support
status: completed
type: feature
priority: normal
created_at: 2026-11-15T02:56:13Z
updated_at: 2026-11-15T03:27:05Z
---

Make Migaku Enforcer run on Arch Linux: hosts file, privilege check, process killing, startup (systemd/XDG), config dir, chromedriver cache, notifications, tray, packaging.

## Todo
- [ ] Audit Windows-specific code
- [ ] Platform abstraction: config dir, hosts path, flush DNS, admin check
- [ ] Startup install/uninstall via systemd user unit or XDG autostart
- [ ] Process killing / protected names on Linux
- [ ] Notifications and tray on Linux
- [ ] Privilege model (root needed for /etc/hosts)
- [ ] Docs, requirements, packaging (PKGBUILD or run script)
- [x] Test on real machine: tk installed, install.sh run, helper block/unblock verified against real /etc/hosts, wizard renders on Hyprland
- [x] User ran the wizard with a real Migaku login and enabled startup (systemd user service + timer enabled)

## Summary of Changes
App runs as the normal user; only /etc/hosts needs root, via linux/migaku-hosts-helper (validated domains, marker lines only) allowed through a sudoers rule installed by linux/install.sh. Platform gating in migaku_enforcer.py (IS_WINDOWS/IS_LINUX) keeps Windows behaviour unchanged. Linux: ~/.config/migaku-enforcer (0600), systemd user service+timer for startup, notify-send, linux64 chromedriver cache, tray only when an AppIndicator backend exists (else window stays open), pystray import made failure-tolerant (it raises ValueError when gi lacks AppIndicator). Verified: helper logic on scratch hosts file, process kill, config perms, systemd-analyze verify of units, headless Chrome via setup_webdriver. Not verified: Tk GUI (tk not installed), real sudo install.
