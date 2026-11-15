Migaku Enforcer for Linux
=========================

Blocks distracting websites and apps until your daily Migaku reviews are done.

Install
-------
Open a terminal in this folder and run (as your normal user, not with sudo):

    ./install.sh

The installer:
  * offers to install missing system packages with pacman, apt or dnf
    (Python's Tk module, plus optional tray-icon and notification packages),
  * installs the app and its own Python environment into
    ~/.local/share/migaku-enforcer,
  * adds a "Migaku Enforcer" app-menu entry and the commands
    migaku-enforcer and migaku-enforcer-uninstall in ~/.local/bin,
  * asks for your sudo password once, to install the small helper that edits
    /etc/hosts (the only part that needs root).

You also need Google Chrome (Arch: the AUR package google-chrome). The app uses it
in the background to check your review count.

Run
---
Start "Migaku Enforcer" from your app menu, or run:

    migaku-enforcer --test     try it out; nothing gets blocked
    migaku-enforcer            normal mode

The first launch opens a setup wizard for your Migaku login and what to block.
"Start automatically" in the wizard or in Settings adds a systemd user service.

Upgrade
-------
Download the new version and run its ./install.sh. Your settings are kept.
Also re-run install.sh after a major Python upgrade from your distro
(for example 3.13 to 3.14), which breaks the app's Python environment.

Uninstall
---------
    migaku-enforcer-uninstall

Your settings and login stay in ~/.config/migaku-enforcer until you delete that
folder.

More details, including tray-icon setup on Hyprland/Sway:
https://github.com/laeabbott/migaku-enforcer#linux-arch-and-others
