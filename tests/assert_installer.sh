#!/usr/bin/env bash
# Installer assertions — runs INSIDE the Docker container after install.sh finishes.
# Called by Dockerfile.installer-test's CMD (or by test_installer.sh via docker run).
set -euo pipefail

RED='\033[0;31m'; GRN='\033[0;32m'; NC='\033[0m'
FAILURES=0
pass() { echo -e "${GRN}  PASS${NC}  $*"; }
fail() { echo -e "${RED}  FAIL${NC}  $*"; FAILURES=$((FAILURES+1)); }
check() {
    local desc="$1" cmd="$2"
    if eval "$cmd" >/dev/null 2>&1; then pass "$desc"; else fail "$desc"; fi
}

check "Flask app at /opt/pinet-board/app.py"     "test -f /opt/pinet-board/app.py"
check "Templates present"                         "test -d /opt/pinet-board/templates"
check "Static dir present"                        "test -d /opt/pinet-board/static"
check "Data dir created"                          "test -d /opt/pinet-board/data"
check "Secrets dir /etc/pinet-board"              "test -d /etc/pinet-board"
check "TLS key generated"                         "test -f /etc/pinet-board/tls.key"
check "TLS cert generated"                        "test -f /etc/pinet-board/tls-fullchain.pem"
check "TLS cert is valid X.509"                   "openssl x509 -noout -in /etc/pinet-board/tls-fullchain.pem"
check "TLS SAN covers 10.10.10.1"                 "openssl x509 -noout -text -in /etc/pinet-board/tls-fullchain.pem | grep -q '10.10.10.1'"
check "TLS SAN covers pinet.local"                "openssl x509 -noout -text -in /etc/pinet-board/tls-fullchain.pem | grep -q 'pinet.local'"
check "TLS cert valid >=3000 days"                "openssl x509 -noout -checkend \$((3000*86400)) -in /etc/pinet-board/tls-fullchain.pem"
check "Session secret key written"                "test -f /etc/pinet-board/secret_key"
check "Secret key >=32 bytes"                     "test \$(wc -c < /etc/pinet-board/secret_key) -ge 32"
check "Admin hash written"                        "test -f /etc/pinet-board/board.conf"
check "Guest hash written"                        "test -f /etc/pinet-board/guest.conf"
check "Admin hash PBKDF2 format (32:64 hex)"      "grep -qE '^[0-9a-f]{32}:[0-9a-f]{64}' /etc/pinet-board/board.conf"
check "Guest hash PBKDF2 format"                  "grep -qE '^[0-9a-f]{32}:[0-9a-f]{64}' /etc/pinet-board/guest.conf"
check "Admin password verifies" "python3 -c \"
import hashlib, sys
line = open('/etc/pinet-board/board.conf').read().strip()
salt, h = line.split(':')
got = hashlib.pbkdf2_hmac('sha256', b'admintest', bytes.fromhex(salt), 200_000).hex()
sys.exit(0 if got == h else 1)
\""
check "Guest password verifies" "python3 -c \"
import hashlib, sys
line = open('/etc/pinet-board/guest.conf').read().strip()
salt, h = line.split(':')
got = hashlib.pbkdf2_hmac('sha256', b'guesttest', bytes.fromhex(salt), 200_000).hex()
sys.exit(0 if got == h else 1)
\""
check "Lock PIN written"                          "test -f /etc/dsi-lock/passcode"
check "Lock PIN matches 5678"                     "test \"\$(cat /etc/dsi-lock/passcode)\" = '5678'"
check "hostapd.conf written"                      "test -f /etc/hostapd.conf"
check "hostapd SSID=PINET_TEST"                   "grep -q 'ssid=PINET_TEST' /etc/hostapd.conf"
check "dnsmasq captive DNS config"                "test -f /etc/dnsmasq.d/wlan0-ap-captive.conf"
check "dnsmasq AP DHCP config"                    "test -f /etc/dnsmasq.d/wlan0-ap.conf"
check "nftables AP rules"                         "test -f /etc/nftables/pinet-ap.nft"
check "scripts in /usr/local/bin (dsi-sleep.sh)"  "test -x /usr/local/bin/dsi-sleep.sh"
check "scripts in /usr/local/sbin (pinet-start)"  "test -x /usr/local/sbin/pinet-start"
check "Media uploads dir"                         "test -d /mnt/pinet-media/uploads"
check "Media tmp dir"                             "test -d /mnt/pinet-media/tmp"
check "pinet-board system user exists"            "id pinet-board"
check "pinet-board user has nologin shell"        "getent passwd pinet-board | grep -q nologin"
check "CA cert in app static dir"                 "test -f /opt/pinet-board/static/pinet-ca.crt"
check "CA cert is valid X.509"                    "openssl x509 -noout -in /opt/pinet-board/static/pinet-ca.crt"
check "systemctl enable called (stub log)"           "grep -q 'systemctl enable' /tmp/pinet-stub-calls.log"
check "systemctl start pinet-board called"          "grep -q 'systemctl start pinet-board' /tmp/pinet-stub-calls.log"
check "pinet-captive.service installed"             "test -f /etc/systemd/system/pinet-captive.service"
check "systemctl start pinet-captive called"        "grep -q 'systemctl start pinet-captive' /tmp/pinet-stub-calls.log"
check "data dir owned by pinet-board"             "stat -c '%U' /opt/pinet-board/data | grep -q pinet-board"
check "secret_key mode 640"                       "stat -c '%a' /etc/pinet-board/secret_key | grep -q 640"
check "tls.key mode 640"                          "stat -c '%a' /etc/pinet-board/tls.key | grep -q 640"

echo ""
if [[ "$FAILURES" -eq 0 ]]; then
    echo -e "${GRN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GRN}  All installer sandbox checks passed.${NC}"
    echo -e "${GRN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    exit 0
else
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}  $FAILURES check(s) failed.${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    exit 1
fi
