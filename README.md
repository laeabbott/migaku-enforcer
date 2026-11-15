# Migaku Enforcer

A Windows (and Linux) tool that blocks distracting websites and closes distracting apps until
you've finished your [Migaku](https://migaku.com) flashcard reviews for the day.

**Not officially associated with Migaku**—this is an independent, unofficial tool I made to combat my 
own avoidant tendencies, released here in case it's useful to others.

## What it does

- Checks your review count on study.migaku.com periodically using Selenium + headless Chrome. If
  Chrome isn't found, the setup wizard's "Test Login" step will tell you..
- While reviews are unfinished, it blocks a pre-chosen list of websites you choose
  and closes a list of apps/processes you choose.
- Once you hit 0 reviews remaining, or a daily review goal you set (e.g. finish 100 cards), restrictions lift
  until a reset time you choose (default 4 AM).
- **Vacation mode:** if Migaku is showing its vacation page ("Enjoy Your Time Off!" / Edit Schedule), nothing is
  due, so nothing is blocked. It's re-checked on your normal check interval, so restrictions come back within that
  window if vacation ends or is switched off mid-day.
- A small number of monthly "Emergency Passes" for genuine emergencies, each requiring
  a moment of confirmation before use.
- The main window can't be closed without a short reflection exercise to increase friction, so it can't be
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

Your Migaku email/password are stored locally in APPDATA in plain text, 
restricted to your Windows user account's file permissions, so be careful about using this 
on a shared or public computer.

## Linux (Arch and others)

Linux is supported from source (no packaged installer). The app runs as your normal
user; only the `/etc/hosts` edit needs root, and that is handled by a tiny helper
you install once.

```bash
# 1. System packages (Arch): Tk for the GUI, Chrome for the review check
sudo pacman -S tk python
#    plus google-chrome (AUR) or chromium; Selenium downloads a matching chromedriver itself

# 2. Python deps in a venv
python -m venv .venv
.venv/bin/pip install selenium psutil pystray Pillow

# 3. One-time root setup: installs /usr/local/lib/migaku-enforcer/hosts-helper and a
#    sudoers rule letting *your user* run only that file without a password
sudo ./linux/install.sh

# 4. Run it (--test = GUI only, nothing blocked)
.venv/bin/python migaku_enforcer.py --test
.venv/bin/python migaku_enforcer.py
```

The setup wizard's "start automatically" option (or `--install`) creates a systemd
**user** service plus a timer for the daily reset hour — no root needed. Check it with
`systemctl --user status migaku-enforcer.timer`. The service needs your graphical
session's `WAYLAND_DISPLAY`/`DISPLAY` in the systemd user environment; Plasma and GNOME
do this for you. On Hyprland/Sway/etc. put this in your compositor config:

```
exec-once = dbus-update-activation-environment --systemd WAYLAND_DISPLAY DISPLAY XDG_CURRENT_DESKTOP
```

Notes:
- Config and logs live in `~/.config/migaku-enforcer/` (config is `chmod 600`).
- The helper only writes `127.0.0.1 <domain>` lines tagged `# MIGAKU_ENFORCER_BLOCKED`
  and validates every domain, so it can't be used to edit anything else in `/etc/hosts`.
  Remove everything with `sudo ./linux/uninstall.sh`.
- The tray icon only works with a StatusNotifier tray (needs `python-gobject` +
  `libayatana-appindicator`; use `--system-site-packages` for the venv). Without one,
  the window just stays open (un-pinned) once your goal is met instead of hiding.
- The window asks to stay on top, which Wayland compositors treat as a hint. On Hyprland
  add a rule such as `windowrule = float, title:^Migaku Enforcer`.
- Blocked apps are matched against the process name as shown by `ps` (e.g. `steam`,
  `discord`, `firefox`).

## Configuring it later

Once reviews are done for the day, a **Settings** button unlocks on the main window
(deliberately locked while restrictions are active, otherwise you could just remove
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
- **Windows only.** Uses the Windows hosts file, Task Scheduler, and UAC elevation
  directly.
- Blocked-app matching is substring-based by default (blocking "steam" also matches any
  process containing that text); an exact-match mode is available in Settings.

## License

[MIT](LICENSE)
