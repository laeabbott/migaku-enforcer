---
# migaku-enforcer-pdl2
title: Linux installer (tarball + install.sh)
status: in-progress
type: feature
created_at: 2026-11-15T04:03:39Z
updated_at: 2026-11-15T04:03:39Z
---

Downloadable Linux installer to sit next to MigakuEnforcerSetup.exe on releases.

- [x] linux/installer/install.sh: per-user install to ~/.local/share/migaku-enforcer with venv, launcher, .desktop entry, icon, hosts helper via sudo, optional pacman/apt/dnf system packages, re-points an existing systemd unit
- [x] linux/installer/uninstall.sh (installed as migaku-enforcer-uninstall)
- [x] linux/build_tarball.py: builds Output/migaku-enforcer-linux-<ver>.tar.gz from Windows or Linux (LF endings, 755 modes, PNG icon from the .ico)
- [x] README + in-app setup hints mention the installer; .gitattributes keeps Linux scripts LF
- [ ] Test install/upgrade/uninstall on a real Arch machine (no Linux available on the Windows dev box: no WSL/Docker)
- [ ] Attach tarball to the GitHub release
