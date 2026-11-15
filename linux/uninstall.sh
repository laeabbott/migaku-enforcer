#!/bin/bash
# Removes what linux/install.sh set up, and clears any active Migaku Enforcer
# entries from /etc/hosts.
#
#   sudo ./linux/uninstall.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run this with sudo:  sudo $0" >&2
    exit 1
fi

LIB_DIR=/usr/local/lib/migaku-enforcer
HELPER="$LIB_DIR/hosts-helper"

if [[ -x "$HELPER" ]]; then
    "$HELPER" unblock || true
else
    sed -i '/# MIGAKU_ENFORCER_BLOCKED/d' /etc/hosts
fi

rm -f /etc/sudoers.d/migaku-enforcer
rm -rf "$LIB_DIR"
echo "Removed helper, sudoers rule and any hosts entries."
