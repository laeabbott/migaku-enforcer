---
# migaku-enforcer-bax9
title: Two copies of the enforcer run at once (no single-instance guard)
status: in-progress
type: bug
priority: normal
tags:
    - someday
created_at: 2026-11-16T03:56:40Z
updated_at: 2026-11-24T05:46:14Z
---

Found 2 MigakuEnforcer.exe instances running: one started 2026-11-15 12:47 outside Task Scheduler (manual/relaunch), one started 2026-11-16 12:47 by Task Scheduler catching up the missed daily reset-hour trigger (StartWhenAvailable, event 114). MultipleInstancesPolicy=IgnoreNew only knows about the task's own instances, so it can't see a copy launched any other way.

- [x] Add app-level single-instance lock (Windows named mutex, Linux flock)
- [x] Scheduled launches exit quietly if already running; interactive launches tell the user
- [x] Verify with two concurrent launches
- [x] Rebuild/reinstall local install (needs user + UAC)

## Log (2026-11-20)
Single-instance lock (named mutex on Windows, flock on Linux; test/debug runs exempt) committed as found in the working tree, not yet tested live: run two copies to confirm the second exits.
