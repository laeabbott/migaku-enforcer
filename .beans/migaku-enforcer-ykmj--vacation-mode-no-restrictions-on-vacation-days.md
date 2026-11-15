---
# migaku-enforcer-ykmj
title: 'Vacation mode: no restrictions on vacation days'
status: completed
type: feature
priority: normal
created_at: 2026-11-15T03:21:12Z
updated_at: 2026-11-15T03:25:59Z
---

Migaku added a vacation mode: no cards shown, page has an 'Edit Schedule' button. On vacation days the enforcer must apply NO restrictions.

## Todo
- [ ] Understand current review-count detection and the states it produces
- [ ] Detect vacation mode on the study page
- [ ] Treat vacation as 'no restrictions' for the day (and lift existing blocks)
- [ ] Show it in GUI/status
- [x] Test

## Summary of Changes
Study page in vacation mode has a HomeDayOff panel (Enjoy Your Time Off! / Edit Schedule) but still lists per-deck 'N reviews', which the old scraper misread as due reviews. Added _is_vacation_day (visible .HomeDayOff element, or heading AND Edit Schedule text; never the button alone), checked before the count regex. New sentinel REVIEW_COUNT_VACATION=-2 handled in enforcement, GUI manual check, console check, wizard/settings/setup_credentials Test Login. Vacation does not use restrictions_disabled_until: re-checked each interval so it ends promptly; a failed re-check on a day that saw vacation stays unrestricted (config vacation_day). Verified in real Chrome on saved page + 6 edge cases, live against the account with a config copy, and GUI screenshot.
