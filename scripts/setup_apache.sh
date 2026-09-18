#!/bin/bash
# Sets up Apache as the vulnerable target for the Slowloris lab:
# prefork MPM, a small worker pool, mod_status enabled, and
# mod_reqtimeout explicitly disabled (no defense yet).
#
# Run with: bash scripts/setup_apache.sh
# Needs sudo - it will prompt for your password.

set -e

sudo apt-get update
sudo apt-get install -y apache2

# use the prefork MPM (one process per connection - the vulnerable model)
sudo a2dismod mpm_event mpm_worker 2>/dev/null || true
sudo a2enmod mpm_prefork
sudo a2enmod status

# small worker pool so exhaustion is reachable in minutes/seconds
sudo tee /etc/apache2/mods-available/mpm_prefork.conf > /dev/null << 'CONF'
<IfModule mpm_prefork_module>
	StartServers	     5
	MinSpareServers	     5
	MaxSpareServers      10
	MaxRequestWorkers    30
	MaxConnectionsPerChild 0
</IfModule>
CONF

# expose mod_status at /server-status, reachable from localhost only
sudo tee /etc/apache2/conf-available/server-status.conf > /dev/null << 'CONF'
<Location /server-status>
    SetHandler server-status
    Require local
</Location>
CONF
sudo a2enconf server-status

# no request timeout module - this is the undefended baseline
sudo a2dismod reqtimeout 2>/dev/null || true

sudo systemctl restart apache2
sudo systemctl status apache2 --no-pager | head -10

echo "---checking server-status---"
curl -s "http://127.0.0.1/server-status?auto"
