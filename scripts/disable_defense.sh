#!/bin/bash
# Reverts scripts/enable_defense.sh: disables mod_reqtimeout and removes
# the per-IP connlimit rule, putting Apache back into the undefended lab
# config (same as right after scripts/setup_apache.sh).
#
# Run with: bash scripts/disable_defense.sh
# Needs sudo - it will prompt for your password.

set -e

ATTACKER_IP="127.0.0.2"
CONN_LIMIT=10
TARGET_PORT=80

sudo a2dismod reqtimeout

sudo iptables -D INPUT -p tcp --dport "$TARGET_PORT" -s "$ATTACKER_IP" \
    -m connlimit --connlimit-above "$CONN_LIMIT" --connlimit-mask 32 -j REJECT 2>/dev/null || true

sudo systemctl restart apache2

echo "--- reqtimeout enabled? ---"
apache2ctl -M 2>/dev/null | grep reqtimeout || echo "(disabled, as expected)"
echo "--- iptables rule ---"
sudo iptables -L INPUT -n | grep "$ATTACKER_IP" || echo "(removed, as expected)"
echo "Defense disabled: back to the undefended baseline config."
