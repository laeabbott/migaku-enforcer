#!/bin/bash
# Migaku Enforcer - Linux installer.
#
#   ./install.sh            (run as your normal user, NOT with sudo)
#   ./install.sh --yes      don't ask before installing system packages
#   ./install.sh --no-system-packages   never touch the package manager
#
# Installs the app for the current user only:
#   ~/.local/share/migaku-enforcer/       app files + its own Python venv
#   ~/.local/bin/migaku-enforcer          launcher
#   ~/.local/bin/migaku-enforcer-uninstall
#   ~/.local/share/applications/migaku-enforcer.desktop   app-menu entry
#
# The only root step is the one-time /etc/hosts helper setup (linux/install.sh),
# which asks for your sudo password. Re-running this script upgrades in place;
# your settings in ~/.config/migaku-enforcer are never touched.

# Everything runs inside main(), so bash has parsed the whole file before any
# of it executes.
set -euo pipefail

VERSION="@VERSION@"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
PREFIX="$DATA_HOME/migaku-enforcer"
APP="$PREFIX/app"
VENV="$PREFIX/venv"
BIN="$HOME/.local/bin"
DESKTOP_FILE="$DATA_HOME/applications/migaku-enforcer.desktop"
ICON_FILE="$DATA_HOME/icons/hicolor/256x256/apps/migaku-enforcer.png"
UNIT_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/migaku-enforcer.service"
PY_PACKAGES=(selenium psutil pystray Pillow)

ASSUME_YES=false
SYSTEM_PACKAGES=true
WARNINGS=()

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mWarning:\033[0m %s\n' "$*" >&2; WARNINGS+=("$*"); }
die()  { printf '\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }

# ask "question" -> 0 for yes. Defaults to yes; with no terminal (and no --yes) it's no.
ask() {
    $ASSUME_YES && return 0
    [[ -t 0 ]] || return 1
    local reply
    read -r -p "$1 [Y/n] " reply
    [[ -z "$reply" || "$reply" =~ ^[Yy] ]]
}

usage() {
    sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# ---------------------------------------------------------------- system packages

have_tk()       { python3 -c 'import tkinter' >/dev/null 2>&1; }
have_venv()     { python3 -c 'import venv, ensurepip' >/dev/null 2>&1; }
have_tray()     {
    python3 - >/dev/null 2>&1 <<'EOF'
import gi
for name in ("AyatanaAppIndicator3", "AppIndicator3"):
    try:
        gi.require_version(name, "0.1")
        __import__("gi.repository." + name)
        raise SystemExit(0)
    except (ValueError, ImportError):
        pass
raise SystemExit(1)
EOF
}
have_notify()   { command -v notify-send >/dev/null 2>&1; }

detect_pm() {
    if command -v pacman >/dev/null 2>&1; then echo pacman
    elif command -v apt-get >/dev/null 2>&1; then echo apt
    elif command -v dnf >/dev/null 2>&1; then echo dnf
    else echo unknown
    fi
}

# pm_install <pacman|apt|dnf> pkg...   (returns non-zero on failure, never exits)
pm_install() {
    local pm="$1"; shift
    local yes=()
    case "$pm" in
        pacman) $ASSUME_YES && yes=(--noconfirm); sudo pacman -S --needed "${yes[@]}" "$@" ;;
        apt)    $ASSUME_YES && yes=(-y); sudo apt-get install "${yes[@]}" "$@" ;;
        dnf)    $ASSUME_YES && yes=(-y); sudo dnf install "${yes[@]}" "$@" ;;
        *)      return 1 ;;
    esac
}

install_system_packages() {
    local pm required=() optional=()
    pm="$(detect_pm)"

    # Required: Python 3 with Tk (the GUI) and venv. Optional: tray icon + notifications.
    case "$pm" in
        pacman)
            command -v python3 >/dev/null 2>&1 && have_tk || required+=(python tk)
            have_tray   || optional+=(python-gobject libayatana-appindicator)
            have_notify || optional+=(libnotify) ;;
        apt)
            command -v python3 >/dev/null 2>&1 || required+=(python3)
            have_tk   || required+=(python3-tk)
            have_venv || required+=(python3-venv)
            have_tray   || optional+=(python3-gi gir1.2-ayatanaappindicator3-0.1)
            have_notify || optional+=(libnotify-bin) ;;
        dnf)
            command -v python3 >/dev/null 2>&1 && have_tk || required+=(python3 python3-tkinter)
            have_tray   || optional+=(python3-gobject libayatana-appindicator-gtk3)
            have_notify || optional+=(libnotify) ;;
    esac

    if [[ "$pm" == unknown ]]; then
        say "Unknown package manager - skipping system packages."
        return
    fi

    if ((${#required[@]})); then
        if ! $SYSTEM_PACKAGES; then
            warn "Missing required packages (not installed because of --no-system-packages): ${required[*]}"
        elif ask "Install required system packages (${required[*]}) with $pm?"; then
            pm_install "$pm" "${required[@]}" || warn "Installing ${required[*]} failed."
        else
            warn "Skipped required packages: ${required[*]}"
        fi
    fi

    if ((${#optional[@]})); then
        if ! $SYSTEM_PACKAGES; then
            say "Optional packages for the tray icon/notifications: ${optional[*]}"
        elif ask "Install optional packages for the tray icon and notifications (${optional[*]})?"; then
            pm_install "$pm" "${optional[@]}" \
                || warn "Installing ${optional[*]} failed (only the tray icon/notifications need them)."
        fi
    fi
}

check_python() {
    command -v python3 >/dev/null 2>&1 \
        || die "python3 not found. Install Python 3.8 or newer and re-run this installer."
    python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 8))' \
        || die "Python 3.8 or newer is required (found $(python3 --version 2>&1))."
    have_tk || die "Python's Tk module (tkinter) is missing. Install it (Arch: tk, Debian/Ubuntu: python3-tk, Fedora: python3-tkinter) and re-run."
    have_venv || die "Python's venv module is missing. Install it (Debian/Ubuntu: python3-venv) and re-run."
}

check_chrome() {
    local b
    for b in google-chrome-stable google-chrome; do
        if command -v "$b" >/dev/null 2>&1; then
            say "Found Google Chrome for the review check: $b"
            return
        fi
    done
    if command -v chromium >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1; then
        warn "Only Chromium was found. If the review check fails, install Google Chrome (Arch: AUR package google-chrome)."
    else
        warn "Google Chrome was not found. The review check needs it: install google-chrome (Arch: AUR package google-chrome)."
    fi
}

# ---------------------------------------------------------------- app install

install_app_files() {
    say "Installing app files to $APP"
    mkdir -p "$PREFIX"
    rm -rf "$APP.new"
    cp -r "$HERE/app" "$APP.new"
    rm -rf "$APP"
    mv "$APP.new" "$APP"
    chmod 755 "$APP/linux/install.sh" "$APP/linux/uninstall.sh" "$APP/linux/migaku-hosts-helper"
    install -m 755 "$HERE/uninstall.sh" "$PREFIX/uninstall.sh"
    echo "$VERSION" > "$PREFIX/VERSION"
}

venv_ok() {
    [[ -x "$VENV/bin/python" ]] || return 1
    # A distro Python upgrade (e.g. 3.13 -> 3.14 on Arch) breaks an existing venv.
    [[ "$("$VENV/bin/python" -c 'import sys; print(sys.version_info[:2])' 2>/dev/null)" == \
       "$(python3 -c 'import sys; print(sys.version_info[:2])')" ]]
}

setup_venv() {
    if ! venv_ok; then
        say "Creating Python environment in $VENV"
        rm -rf "$VENV"
        # --system-site-packages lets the venv see the distro's python-gobject (tray icon).
        python3 -m venv --system-site-packages "$VENV"
    fi
    say "Installing Python packages: ${PY_PACKAGES[*]}"
    "$VENV/bin/python" -m pip install --upgrade --quiet --disable-pip-version-check "${PY_PACKAGES[@]}" \
        || die "pip install failed. Check your internet connection and re-run the installer."
    "$VENV/bin/python" -c 'import selenium, psutil, pystray, PIL, tkinter' \
        || die "The Python environment is incomplete after install (see errors above)."
}

install_launcher() {
    mkdir -p "$BIN"
    cat > "$BIN/migaku-enforcer" <<EOF
#!/bin/bash
# Launcher installed by the Migaku Enforcer Linux installer ($VERSION).
VENV="$VENV"
APP="$APP"
if ! "\$VENV/bin/python" -c 'import selenium, pystray' >/dev/null 2>&1; then
    msg="Migaku Enforcer's Python environment is broken (usually after a Python upgrade). Re-run the Linux installer (install.sh) to fix it."
    echo "\$msg" >&2
    command -v notify-send >/dev/null 2>&1 && notify-send "Migaku Enforcer" "\$msg"
    exit 1
fi
exec "\$VENV/bin/python" "\$APP/migaku_enforcer.py" "\$@"
EOF
    chmod 755 "$BIN/migaku-enforcer"
    ln -sf "$PREFIX/uninstall.sh" "$BIN/migaku-enforcer-uninstall"
}

install_desktop_entry() {
    mkdir -p "$(dirname "$DESKTOP_FILE")" "$(dirname "$ICON_FILE")"
    install -m 644 "$APP/assets/migaku-enforcer.png" "$ICON_FILE"
    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Migaku Enforcer
Comment=Blocks distracting sites and apps until your Migaku reviews are done
Exec="$BIN/migaku-enforcer"
Icon=migaku-enforcer
Terminal=false
Categories=Education;Utility;
StartupNotify=false
EOF
    chmod 644 "$DESKTOP_FILE"
    command -v update-desktop-database >/dev/null 2>&1 \
        && update-desktop-database "$(dirname "$DESKTOP_FILE")" >/dev/null 2>&1 || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 \
        && gtk-update-icon-cache -q -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
}

install_hosts_helper() {
    say "Setting up the /etc/hosts helper (needs your sudo password once)"
    if ! sudo bash "$APP/linux/install.sh"; then
        warn "The hosts helper setup failed, so website blocking won't work. Fix the error above, then re-run this installer."
    fi
}

# If "start at login" was enabled from an older install or a source checkout, the
# systemd unit still points there. Re-register it so it runs this install.
refresh_startup_unit() {
    [[ -f "$UNIT_FILE" ]] || return 0
    grep -qF "$APP/migaku_enforcer.py" "$UNIT_FILE" && return 0
    say "Updating the start-at-login service to use this install"
    APP="$APP" "$VENV/bin/python" - <<'EOF' || warn "Could not update $UNIT_FILE - turn 'Start at login' off and on again in Settings."
import json, os, sys
from pathlib import Path
app = os.environ["APP"]
sys.path.insert(0, app)
os.chdir(app)
import migaku_enforcer as m
cfg_dir = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "migaku-enforcer"
try:
    reset_hour = json.loads((cfg_dir / "config.json").read_text())["reset_hour"]
except Exception:
    reset_hour = m.DEFAULT_RESET_HOUR
m.install_startup(int(reset_hour))
EOF
}

main() {
    while (($#)); do
        case "$1" in
            -y|--yes) ASSUME_YES=true ;;
            --no-system-packages) SYSTEM_PACKAGES=false ;;
            -h|--help) usage; exit 0 ;;
            *) die "Unknown option: $1 (see --help)" ;;
        esac
        shift
    done

    [[ $EUID -ne 0 ]] || die "Run this as your normal user, not with sudo. It asks for sudo itself when needed."
    [[ "$(uname -s)" == Linux ]] || die "This installer is for Linux. On Windows, use MigakuEnforcerSetup.exe."
    [[ -f "$HERE/app/migaku_enforcer.py" ]] || die "Installer files are incomplete: run install.sh from the extracted folder."
    command -v sudo >/dev/null 2>&1 || die "sudo is required (for the /etc/hosts helper)."

    say "Installing Migaku Enforcer $VERSION for user $USER"
    install_system_packages
    check_python
    check_chrome
    install_app_files
    setup_venv
    install_launcher
    install_desktop_entry
    install_hosts_helper
    refresh_startup_unit

    echo
    say "Migaku Enforcer $VERSION is installed."
    echo "    Start it from your app menu (\"Migaku Enforcer\") or run:  migaku-enforcer"
    echo "    Try it safely first (nothing gets blocked):              migaku-enforcer --test"
    echo "    Uninstall:                                               migaku-enforcer-uninstall"
    echo "    The first launch opens a setup wizard for your Migaku login."
    case ":$PATH:" in
        *":$BIN:"*) ;;
        *) echo; warn "$BIN is not on your PATH, so the commands above need the full path ($BIN/migaku-enforcer). The app-menu entry works either way." ;;
    esac
    if pgrep -u "$(id -u)" -f "migaku_enforcer.py" >/dev/null 2>&1; then
        echo; warn "Migaku Enforcer is running right now. The new version takes effect the next time it starts."
    fi
    if ((${#WARNINGS[@]})); then
        echo; echo "Finished with ${#WARNINGS[@]} warning(s):"
        printf '  - %s\n' "${WARNINGS[@]}"
    fi
}

main "$@"
