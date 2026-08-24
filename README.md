# Migaku Enforcer

A Windows tool that blocks distracting websites and closes distracting apps until
you've finished your [Migaku](https://migaku.com) flashcard reviews for the day.

Not officially associated with Migaku — this is an independent, unofficial tool made by
a user for personal accountability, released here in case it's useful to others.

## What it does

- Checks your review count on study.migaku.com periodically (Chrome, headless).
- While reviews are pending: blocks a list of websites you choose (via the hosts file)
  and closes a list of apps/processes you choose.
- Once you hit 0 reviews remaining, or a daily review goal you set, restrictions lift
  until a reset time you choose (default 4 AM).
- A small number of monthly "Emergency Passes" for genuine emergencies, each requiring
  a moment of confirmation before use.
- The main window can't be closed without a short reflection exercise, so it can't be
  casually dismissed mid-restriction.

## Download

Grab the latest installer from the [Releases page](../../releases/latest) —
`MigakuEnforcerSetup.exe`. It installs per-user (no admin needed to install), then walks
you through a setup wizard: your Migaku login, which sites/apps to block, your daily
goal, and whether to start automatically at login.

**Requirements:** Windows 10/11, Google Chrome installed. The app itself needs
administrator privileges to run (it edits the hosts file and closes processes), so
Windows will prompt for that the first time you launch it.

### A note on your credentials

Your Migaku email/password are stored locally in `%APPDATA%\MigakuEnforcer\config.json`,
in plain text, restricted to your Windows user account's file permissions. This is a
deliberate tradeoff for a single-user local tool — see the tradeoffs below — but it does
mean: don't use this on a shared or public computer.

## Configuring it later

Once reviews are done for the day, a **Settings** button unlocks on the main window
(deliberately locked while restrictions are active — otherwise you could just remove
your own blocks). From there you can change blocked sites/apps, your daily goal, reset
time, check interval, emergency pass settings, and startup behavior.

## Building from source

```bash
pip install -r requirements.txt
python migaku_enforcer.py --test      # run in test mode: GUI shown, nothing actually blocked
```

To build the packaged installer yourself:

```bash
pyinstaller migaku_enforcer.spec      # -> dist/MigakuEnforcer.exe
iscc installer.iss                    # requires Inno Setup: https://jrsoftware.org/isinfo.php
                                       # -> Output/MigakuEnforcerSetup.exe
```

## Design notes / known tradeoffs

- **Plaintext credentials, not a credential manager**: the threat model for a
  single-user local tool doesn't really change by adding encryption — anyone with local
  file access to read the config already has full control of the machine. Keyring/DPAPI
  would add a real packaging-fragility risk for little practical benefit here.
- **Windows only.** Uses the Windows hosts file, Task Scheduler, and UAC elevation
  directly.
- **Chrome required** — review checking uses Selenium against a headless Chrome. If
  Chrome isn't found, the setup wizard's "Test Login" step will tell you.
- Blocked-app matching is substring-based by default (blocking "steam" also matches any
  process containing that text); an exact-match mode is available in Settings.

## License

[MIT](LICENSE)
