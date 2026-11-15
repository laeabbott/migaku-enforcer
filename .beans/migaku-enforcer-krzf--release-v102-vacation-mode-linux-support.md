---
# migaku-enforcer-krzf
title: Release v1.0.2 (vacation mode + Linux support)
status: completed
type: task
priority: normal
created_at: 2026-11-15T03:45:54Z
updated_at: 2026-11-15T03:52:33Z
---

Rebuild Windows exe + installer from latest main, update local install, publish GitHub release v1.0.2.

- [x] Pull latest main
- [x] Bump installer version to 1.0.2
- [x] Build exe (pyinstaller) and installer (iscc)
- [x] Update local install on this machine
- [x] Commit, tag, publish GitHub release

## Summary of Changes

Bumped installer to 1.0.2, rebuilt dist/MigakuEnforcer.exe and Output/MigakuEnforcerSetup.exe from main (50c82bb), updated the local per-user install in place (installed exe hash matches the build), and published GitHub release v1.0.2 with the installer attached.
