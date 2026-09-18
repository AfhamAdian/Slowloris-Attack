#!/bin/bash
# Flips the SAME Apache install from the undefended lab config into the
# defended one:
#   1. Header timeout cap: enables mod_reqtimeout with a bounded,
#      adaptive timeout on the header stage (Section 11, primary fix).
#   2. Per-source-IP concurrent connection limit: an iptables rule that
#      caps how many simultaneous connections one IP may hold open on
#      port 80 (Section 11, secondary fix).
#
# Everything else (prefork MPM, MaxRequestWorkers=30, mod_status) is left
# untouched, so the only difference from the undefended run is these two
# defenses.
#
# Run with: bash scripts/enable_defense.sh
# Needs sudo - it will prompt for your password.
#
# The attacker must be run with --source-ip 127.0.0.2 (see
# core/attacker.py) so the connection-limit rule can tell it apart from
# the legitimate client, which stays on 127.0.0.1. run_experiment.py's
# --attacker-source-ip flag does this for you.

set -e

ATTACKER_IP="127.0.0.2"
CONN_LIMIT=10          # max simultaneous connections allowed from ATTACKER_IP on port 80
TARGET_PORT=80

# --- 1. header timeout cap (mod_reqtimeout) ---------------------------------
sudo tee /etc/apache2/mods-available/reqtimeout.conf > /dev/null << 'CONF'
<IfModule reqtimeout_module>
    RequestReadTimeout header=10-20,MinRate=500
    RequestReadTimeout body=20,MinRate=500
</IfModule>
CONF
sudo a2enmod reqtimeout

# --- 2. per-source-IP concurrent connection limit (iptables) ----------------
# remove a previous copy of this rule first, so re-running is safe
sudo iptables -D INPUT -p tcp --dport "$TARGET_PORT" -s "$ATTACKER_IP" \
    -m connlimit --connlimit-above "$CONN_LIMIT" --connlimit-mask 32 -j REJECT 2>/dev/null || true

sudo iptables -I INPUT -p tcp --dport "$TARGET_PORT" -s "$ATTACKER_IP" \
    -m connlimit --connlimit-above "$CONN_LIMIT" --connlimit-mask 32 -j REJECT

sudo systemctl restart apache2

echo "--- reqtimeout enabled? ---"
apache2ctl -M 2>/dev/null | grep reqtimeout
echo "--- iptables rule ---"
sudo iptables -L INPUT -n --line-numbers | grep "$ATTACKER_IP" || echo "(rule not found - something went wrong)"
echo "Defense enabled: header timeout capped, connections from $ATTACKER_IP on port $TARGET_PORT capped at $CONN_LIMIT."
