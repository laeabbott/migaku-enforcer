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

Grab the latest installer from the [Releases page](../../releases/latest):

- **Windows:** `MigakuEnforcerSetup.exe`
- **Linux:** `migaku-enforcer-linux-<version>.tar.gz` (see [Linux](#linux-arch-and-others) below)

The Windows installer installs per-user (no admin needed to install), then walks
you through a setup wizard: your Migaku login, which sites/apps to block, your daily
goal, and whether to start automatically at login.

**Windows requirements:** Windows 10/11, Google Chrome installed. The app itself needs
administrator privileges to run (it edits the hosts file and closes processes), so
Windows will prompt for that the first time you launch it.

### A note on your credentials

Your Migaku email/password are stored locally in APPDATA in plain text, 
restricted to your Windows user account's file permissions, so be careful about using this 
on a shared or public computer.

## Linux (Arch and others)

The app runs as your normal user; only the `/etc/hosts` edit needs root, and that is
handled by a tiny helper that the installer sets up once.

### Installer (recommended)

Download `migaku-enforcer-linux-<version>.tar.gz` from the
[Releases page](../../releases/latest), then:

```bash
tar xf migaku-enforcer-linux-*.tar.gz
cd migaku-enforcer-linux-*/
./install.sh            # as your normal user, not with sudo
```

It offers to install missing system packages with pacman, apt or dnf (Python's Tk
module, plus python-gobject/libayatana-appindicator for the tray icon and libnotify),
puts the app and its own Python venv in `~/.local/share/migaku-enforcer`, adds a
"Migaku Enforcer" app-menu entry plus `migaku-enforcer` / `migaku-enforcer-uninstall`
in `~/.local/bin`, and asks for your sudo password once to install the hosts helper.
You also need Google Chrome (Arch: AUR `google-chrome`).

Then start it from the app menu, or `migaku-enforcer --test` to try it with nothing
blocked. To upgrade, run the new version's `install.sh` (settings are kept); also
re-run it after a major distro Python upgrade (e.g. 3.13 to 3.14), which breaks the
app's venv. Uninstall with `migaku-enforcer-uninstall`.

### From source

```bash
# 1. System packages (Arch): Tk for the GUI, Chrome for the review check
sudo pacman -S tk python python-gobject libayatana-appindicator
#    plus google-chrome (AUR) or chromium; Selenium downloads a matching chromedriver itself
#    (python-gobject + libayatana-appindicator are only for the tray icon; optional)

# 2. Python deps in a venv (--system-site-packages lets it see python-gobject for the tray)
python -m venv --system-site-packages .venv
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
  Remove everything with `sudo ./linux/uninstall.sh` (the installer's
  `migaku-enforcer-uninstall` runs this for you).
- The tray icon needs a StatusNotifier tray (Quickshell, Waybar's tray module, Plasma, ...)
  plus the two packages above. Without them, "Exit (Minimize to Tray)" just un-pins the
  window and leaves it open instead of hiding it, so it can never get lost.
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
python linux/build_tarball.py         # -> Output/migaku-enforcer-linux-<version>.tar.gz
```

Both take their version number from `MyAppVersion` in `installer.iss`. The tarball
script works on Windows too (it fixes line endings and file modes itself).

## Design notes / known tradeoffs
- **Windows and Linux.** Windows uses the hosts file, Task Scheduler and UAC
  elevation directly; Linux uses a sudoers-limited hosts helper and systemd user units.
  No macOS support.
- Blocked-app matching is substring-based by default (blocking "steam" also matches any
  process containing that text); an exact-match mode is available in Settings.

## License

[MIT](LICENSE)
