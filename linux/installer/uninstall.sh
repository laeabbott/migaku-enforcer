#!/bin/bash
# Migaku Enforcer - Linux uninstaller.
#
#   migaku-enforcer-uninstall          (or ./uninstall.sh from the installer folder)
#   migaku-enforcer-uninstall --yes    don't ask for confirmation
#
# Removes what install.sh set up: the start-at-login service, the app files and
# venv, the launcher and app-menu entry, and (with sudo) the /etc/hosts helper,
# its sudoers rule and any active block entries. Your settings and login in
# ~/.config/migaku-enforcer are kept; delete that folder yourself to remove them.

# Everything runs inside main(): this file deletes itself partway through, so
# bash must have parsed all of it first.
set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
PREFIX="$DATA_HOME/migaku-enforcer"
APP="$PREFIX/app"
BIN="$HOME/.local/bin"
DESKTOP_FILE="$DATA_HOME/applications/migaku-enforcer.desktop"
ICON_FILE="$DATA_HOME/icons/hicolor/256x256/apps/migaku-enforcer.png"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/migaku-enforcer"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mWarning:\033[0m %s\n' "$*" >&2; }

main() {
    local assume_yes=false
    while (($#)); do
        case "$1" in
            -y|--yes) assume_yes=true ;;
            -h|--help) sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
            *) echo "Unknown option: $1" >&2; exit 1 ;;
        esac
        shift
    done

    if [[ $EUID -eq 0 ]]; then
        echo "Run this as your normal user, not with sudo. It asks for sudo itself." >&2
        exit 1
    fi
    if [[ ! -d "$PREFIX" ]]; then
        echo "Migaku Enforcer doesn't seem to be installed (no $PREFIX)." >&2
        exit 1
    fi

    if ! $assume_yes; then
        local reply
        read -r -p "Uninstall Migaku Enforcer? This also lifts any active website blocks. [y/N] " reply
        [[ "$reply" =~ ^[Yy] ]] || { echo "Cancelled."; exit 0; }
    fi

    if command -v systemctl >/dev/null 2>&1; then
        say "Removing the start-at-login service"
        systemctl --user disable --now migaku-enforcer.timer >/dev/null 2>&1 || true
        systemctl --user disable --now migaku-enforcer.service >/dev/null 2>&1 || true
        rm -f "$UNIT_DIR/migaku-enforcer.service" "$UNIT_DIR/migaku-enforcer.timer"
        systemctl --user daemon-reload >/dev/null 2>&1 || true
    fi

    say "Stopping Migaku Enforcer if it's running"
    pkill -u "$(id -u)" -f "$APP/migaku_enforcer.py" 2>/dev/null || true

    say "Removing the /etc/hosts helper and any active blocks (needs sudo)"
    if [[ -f "$APP/linux/uninstall.sh" ]]; then
        if ! sudo bash "$APP/linux/uninstall.sh"; then
            # Keep the files: that root script is what removes the helper and blocks.
            warn "Removing the hosts helper failed, so the app files were left in place. Run migaku-enforcer-uninstall again to retry."
            exit 1
        fi
    fi

    say "Removing app files"
    rm -f "$BIN/migaku-enforcer" "$BIN/migaku-enforcer-uninstall" "$DESKTOP_FILE" "$ICON_FILE"
    command -v update-desktop-database >/dev/null 2>&1 \
        && update-desktop-database "$(dirname "$DESKTOP_FILE")" >/dev/null 2>&1 || true
    rm -rf "$PREFIX"

    echo
    say "Migaku Enforcer has been uninstalled."
    if [[ -d "$CONFIG_DIR" ]]; then
        echo "    Your settings and Migaku login are still in $CONFIG_DIR"
        echo "    Remove them too with:  rm -rf \"$CONFIG_DIR\""
    fi
}

main "$@"
