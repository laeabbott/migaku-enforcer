#!/bin/bash
# One-time root setup for Migaku Enforcer on Linux.
#
#   sudo ./linux/install.sh
#
# Installs the /etc/hosts helper somewhere only root can modify and adds a sudoers
# rule letting *your user* run that one file without a password. Everything else
# (the GUI, Chrome, killing apps) runs as you.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run this with sudo:  sudo $0" >&2
    exit 1
fi

TARGET_USER="${SUDO_USER:-}"
if [[ -z "$TARGET_USER" || "$TARGET_USER" == "root" ]]; then
    echo "Could not work out which user to grant access to." >&2
    echo "Run it as your normal user via sudo (not from a root shell)." >&2
    exit 1
fi
if [[ ! "$TARGET_USER" =~ ^[a-z_][a-z0-9_-]*\$?$ ]]; then
    echo "Refusing unusual user name: $TARGET_USER" >&2
    exit 1
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR=/usr/local/lib/migaku-enforcer
HELPER="$LIB_DIR/hosts-helper"
SUDOERS=/etc/sudoers.d/migaku-enforcer

install -d -o root -g root -m 755 "$LIB_DIR"
install -o root -g root -m 755 "$SRC_DIR/migaku-hosts-helper" "$HELPER"

# Write + validate before putting it in place: a broken sudoers file locks you out of sudo.
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
echo "$TARGET_USER ALL=(root) NOPASSWD: $HELPER" > "$TMP"
visudo -cf "$TMP" >/dev/null
install -o root -g root -m 440 "$TMP" "$SUDOERS"

echo "Installed $HELPER"
echo "Granted passwordless access to it for user '$TARGET_USER' ($SUDOERS)"
echo
sudo -u "$TARGET_USER" sudo -n "$HELPER" check && echo "Self-test passed."
