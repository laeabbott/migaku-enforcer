---
# migaku-enforcer-bdif
title: Confirm the bounded-restart/stale-process fix has actually held up
status: todo
type: task
priority: low
created_at: 2026-09-27T10:14:49Z
updated_at: 2026-09-27T10:14:49Z
---

2026-08-26 session fixed a real bug: the scheduled task's RestartOnFailure was unbounded
(Count=999), so a crash-loop plus IgnoreNew not recognizing a 2-day-stale process across sleep
cycles let 4 duplicate MigakuEnforcer.exe processes pile up. Fixed live: killed all stale
processes, reconfigured the task to Count=3/Interval=PT2M. Session ended with "let me know how
it looks tomorrow morning" - no confirmation found in later history. A month of quiet since
suggests it's fine, but never explicitly verified. Low priority - close this out next time
you're in this codebase if it's been fine, or reopen if the stacking recurs.
