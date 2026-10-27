#!/usr/bin/env bash
# PINET captive-portal installer for stock Raspberry Pi OS / Debian
#
# One-line install (fresh Pi):
#   bash <(curl -fsSL https://raw.githubusercontent.com/rupal2k/pinet/main/install.sh)
#
# From an existing clone:
#   bash install.sh
#
# What this script installs:
#   - captive portal web app (pinet-board) on HTTPS 443 at 10.10.10.1
#   - open Wi-Fi hotspot (hostapd + dnsmasq, SSID: PINET)
#   - nftables rules that block SSH/VNC from the hotspot interface
#   - all helper scripts under /usr/local/bin/ and /usr/local/sbin/
#   - self-signed TLS cert for 10.10.10.1 / pinet.local
#   - interactive prompts for board password, guest password, lock PIN
#
# DSI touchscreen (cyberdeck) extras are NOT installed automatically;
# instructions print at the end for those.

set -euo pipefail

REPO_URL="https://github.com/rupal2k/pinet.git"
CLONE_DIR="/opt/pinet"          # where repo is placed if not already cloned
BOARD_APP="/opt/pinet-board"    # Flask app destination (matches app.py BASE_DIR)
SECRETS="/etc/pinet-board"      # passwords + TLS key (root-owned, 640)
MEDIA="/mnt/pinet-media"        # uploads / photos / tmp
SSID="${PINET_SSID:-PINET}"     # override with env var if desired

# CI / non-interactive mode: set PINET_CI=1 to skip all prompts.
# Passwords are taken from env vars (defaults generate random values).
PINET_CI="${PINET_CI:-}"
PINET_PIN="${PINET_PIN:-1234}"              # lock PIN used in CI mode
PINET_ADMIN_PW="${PINET_ADMIN_PW:-}"       # empty → random in CI
PINET_GUEST_PW="${PINET_GUEST_PW:-}"       # empty → random in CI

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GRN}[pinet]${NC} $*"; }
warn()  { echo -e "${YLW}[pinet]${NC} $*"; }
die()   { echo -e "${RED}[pinet] ERROR:${NC} $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Checks
# ---------------------------------------------------------------------------
[[ "$(id -u)" -eq 0 ]] || die "Run with sudo: sudo bash install.sh"
command -v apt-get >/dev/null 2>&1 || die "apt-get not found — Raspberry Pi OS / Debian required"

arch=$(uname -m)
[[ "$arch" == arm* || "$arch" == aarch64 ]] || warn "Not running on ARM — proceeding anyway (for testing)"

# Interactive prompts need the real terminal even when piped.
if [[ -t 0 ]]; then
    TTY=/dev/stdin
else
    TTY=/dev/tty
fi

# ---------------------------------------------------------------------------
# 2. Locate the repo (clone if not already present)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-/dev/null}")" 2>/dev/null && pwd || echo "")"
if [[ -f "$SCRIPT_DIR/pinet-board/app.py" ]]; then
    REPO="$SCRIPT_DIR"
    info "Using existing clone at $REPO"
else
    if [[ -f "$CLONE_DIR/pinet-board/app.py" ]]; then
        REPO="$CLONE_DIR"
        info "Using existing clone at $REPO"
    else
        info "Cloning $REPO_URL → $CLONE_DIR"
        apt-get install -y git >/dev/null
        git clone --depth 1 "$REPO_URL" "$CLONE_DIR"
        REPO="$CLONE_DIR"
    fi
fi

# ---------------------------------------------------------------------------
# 3. System packages
# ---------------------------------------------------------------------------
info "Installing packages (hostapd dnsmasq python3-flask python3-qrcode python3-pil ...)"
apt-get update -qq
apt-get install -y \
    hostapd dnsmasq nftables \
    python3-flask python3-qrcode python3-pil \
    gunicorn \
    openssl ca-certificates \
    >/dev/null

# On modern Raspberry Pi OS, hostapd is masked by default — unmask it.
systemctl unmask hostapd 2>/dev/null || true

# NetworkManager (bookworm default) must not fight us for wlan0.
NM_CONF="/etc/NetworkManager/conf.d/99-pinet-unmanaged.conf"
if systemctl is-active --quiet NetworkManager 2>/dev/null; then
    warn "NetworkManager detected — marking wlan0 as unmanaged"
    cat > "$NM_CONF" <<'EOF'
[keyfile]
unmanaged-devices=interface-name:wlan0
EOF
    systemctl reload NetworkManager 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# 4. pinet-board system user
# ---------------------------------------------------------------------------
if ! id pinet-board &>/dev/null; then
    info "Creating pinet-board system user"
    useradd --system --no-create-home --shell /usr/sbin/nologin pinet-board
fi

# ---------------------------------------------------------------------------
# 5. Secrets directory
# ---------------------------------------------------------------------------
install -d -o root -g pinet-board -m 750 "$SECRETS"

# Generate random session secret if missing.
# Pre-create with mode 640 before writing so the file is never world-readable.
if [[ ! -f "$SECRETS/secret_key" ]]; then
    info "Generating session secret key"
    install -m 640 -o root -g pinet-board /dev/null "$SECRETS/secret_key"
    python3 -c "import secrets, sys; sys.stdout.buffer.write(secrets.token_bytes(32))" \
        > "$SECRETS/secret_key"
fi

# ---------------------------------------------------------------------------
# 6. TLS certificate for 10.10.10.1 / pinet.local
# ---------------------------------------------------------------------------
if [[ ! -f "$SECRETS/tls.key" ]]; then
    info "Generating self-signed TLS certificate (10.10.10.1, pinet.local)"
    openssl req -x509 -newkey ec \
        -pkeyopt ec_paramgen_curve:P-256 \
        -days 3650 -nodes \
        -keyout "$SECRETS/tls.key" \
        -out "$SECRETS/tls-fullchain.pem" \
        -subj "/CN=pinet.local/O=PINET" \
        -addext "subjectAltName=IP:10.10.10.1,DNS:pinet.local" \
        2>/dev/null
    chmod 640 "$SECRETS/tls.key" "$SECRETS/tls-fullchain.pem"
    chown root:pinet-board "$SECRETS/tls.key" "$SECRETS/tls-fullchain.pem"
    # Embed the new CA cert into the app's static directory so clients can install it.
    cp "$SECRETS/tls-fullchain.pem" "$REPO/pinet-board/static/pinet-ca.crt"
    info "CA cert written to $REPO/pinet-board/static/pinet-ca.crt (serve to clients)"
fi

# ---------------------------------------------------------------------------
# 7. Scripts
# ---------------------------------------------------------------------------
info "Installing scripts → /usr/local/bin/ and /usr/local/sbin/"
install -m 755 "$REPO"/scripts/bin/*  /usr/local/bin/
install -m 755 "$REPO"/scripts/sbin/* /usr/local/sbin/

# ---------------------------------------------------------------------------
# 8. System-wide config files
# ---------------------------------------------------------------------------
info "Installing network config (hostapd, dnsmasq, nftables)"

# hostapd — keep existing if already configured; otherwise install ours
if [[ ! -f /etc/hostapd.conf ]] || ! grep -q "^ssid=" /etc/hostapd.conf 2>/dev/null; then
    sed "s/^ssid=.*/ssid=$SSID/" "$REPO/etc/hostapd.conf" > /etc/hostapd.conf
else
    warn "Keeping existing /etc/hostapd.conf (SSID=$(grep '^ssid=' /etc/hostapd.conf | cut -d= -f2))"
fi
# Tell hostapd to use this file (some distros need DAEMON_CONF set)
sed -i 's|^#\?DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd.conf"|' /etc/default/hostapd 2>/dev/null || true

install -d -m 755 /etc/dnsmasq.d
cp "$REPO/etc/dnsmasq.d/"*.conf /etc/dnsmasq.d/

install -d -m 755 /etc/nftables
cp "$REPO/etc/nftables/pinet-ap.nft" /etc/nftables/pinet-ap.nft

cp "$REPO/etc/NetworkManager/dispatcher.d/90-pinet-net-changed" \
   /etc/NetworkManager/dispatcher.d/90-pinet-net-changed 2>/dev/null || true

# ---------------------------------------------------------------------------
# 9. Flask web app
# ---------------------------------------------------------------------------
info "Installing pinet-board app → $BOARD_APP"
install -d -o root -g root -m 755 "$BOARD_APP"
cp -r "$REPO/pinet-board/"* "$BOARD_APP/"

# Data dir is writable by pinet-board; BASE_DIR is root-owned (app.py comment).
install -d -o pinet-board -g pinet-board -m 700 "$BOARD_APP/data"
chown -R root:root "$BOARD_APP"
chown -R pinet-board:pinet-board "$BOARD_APP/data"

# ---------------------------------------------------------------------------
# 10. Media storage dirs
# ---------------------------------------------------------------------------
info "Creating media directories under $MEDIA"
install -d -m 755 "$MEDIA"
install -d -o pinet-board -g pinet-board -m 775 "$MEDIA/uploads"
install -d -o pinet-board -g pinet-board -m 775 "$MEDIA/tmp"
install -d -m 775 "$MEDIA/camera" "$MEDIA/slideshow"
# Give the running user read/write on camera and slideshow
RUNNING_USER="$(logname 2>/dev/null || echo "pi")"
chown -R "$RUNNING_USER:$RUNNING_USER" "$MEDIA/camera" "$MEDIA/slideshow" 2>/dev/null || true

# ---------------------------------------------------------------------------
# 11. systemd system services
# ---------------------------------------------------------------------------
info "Installing and enabling system services"
cp "$REPO/systemd/pinet-board.service"        /etc/systemd/system/
cp "$REPO/systemd/pinet-captive.service"      /etc/systemd/system/
cp "$REPO/systemd/pinet-ap-network.service"   /etc/systemd/system/
cp "$REPO/systemd/dsi-backlight-enable.service" /etc/systemd/system/
cp -r "$REPO/systemd/pinet-ap-network.service.d" /etc/systemd/system/ 2>/dev/null || true
cp -r "$REPO/systemd/raspotify.service.d"     /etc/systemd/system/    2>/dev/null || true
cp -r "$REPO/systemd/system-shutdown"         /etc/systemd/system/    2>/dev/null || true
systemctl daemon-reload
systemctl enable pinet-ap-network.service hostapd dnsmasq pinet-board.service pinet-captive.service

# ---------------------------------------------------------------------------
# 12. Set passwords
# ---------------------------------------------------------------------------
install -d -o root -g root -m 700 /etc/dsi-lock
install -m 644 "$REPO/desktop/icons/pinet-logo.png" /etc/dsi-lock/logo.png

_write_pw_hash() {
    local conf="$1" pw="$2"
    # Pass the password via stdin, not argv, so it never appears in ps/cmdline.
    printf '%s' "$pw" | python3 - "$conf" <<'PYEOF'
import sys, secrets, hashlib
conf = sys.argv[1]
pw = sys.stdin.readline().rstrip('\n')
salt = secrets.token_hex(16)
digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
with open(conf, "w") as f:
    f.write(f"{salt}:{digest}\n")
import os; os.chmod(conf, 0o640)
PYEOF
    chown root:pinet-board "$conf"
}

if [[ -n "$PINET_CI" ]]; then
    # Non-interactive: use env vars or generate random values.
    info "CI mode — setting credentials from env vars (or random)"
    printf '%s' "$PINET_PIN" > /etc/dsi-lock/passcode
    chmod 600 /etc/dsi-lock/passcode

    ADMIN_PW="${PINET_ADMIN_PW:-$(python3 -c "import secrets; print(secrets.token_hex(8))")}"
    GUEST_PW="${PINET_GUEST_PW:-$(python3 -c "import secrets; print(secrets.token_hex(8))")}"
    _write_pw_hash "$SECRETS/board.conf"  "$ADMIN_PW"
    _write_pw_hash "$SECRETS/guest.conf"  "$GUEST_PW"
    info "Admin password set (len=${#ADMIN_PW}); guest password set (len=${#GUEST_PW})"
else
    info "Setting board credentials — answer the prompts below."
    echo ""

    while true; do
        printf "Enter PINET lock PIN (4–8 digits): " > "$TTY"
        read -r PIN <"$TTY"
        [[ "$PIN" =~ ^[0-9]{4,8}$ ]] && break
        warn "PIN must be 4–8 digits."
    done
    printf '%s' "$PIN" > /etc/dsi-lock/passcode
    chmod 600 /etc/dsi-lock/passcode

    python3 "$BOARD_APP/set_password.py" <"$TTY"
    echo ""
    python3 "$BOARD_APP/set_guest_password.py" <"$TTY"
    echo ""
fi

# ---------------------------------------------------------------------------
# 13. Desktop launcher for PINET Portal
# ---------------------------------------------------------------------------
APPS_DIR="/home/rupal/.local/share/applications"
install -d -o rupal -g rupal -m 755 "$APPS_DIR"
install -o rupal -g rupal -m 644 "$REPO/desktop/pinet-board.desktop" "$APPS_DIR/"
sudo -u rupal update-desktop-database "$APPS_DIR" 2>/dev/null || true

# ---------------------------------------------------------------------------
# 14. Start services
# ---------------------------------------------------------------------------
info "Starting services"
systemctl start pinet-ap-network.service || warn "pinet-ap-network: check 'systemctl status pinet-ap-network'"
systemctl start hostapd    || warn "hostapd: check 'systemctl status hostapd'"
systemctl restart dnsmasq  || warn "dnsmasq: check 'systemctl status dnsmasq'"
systemctl start pinet-board.service   || warn "pinet-board: check 'systemctl status pinet-board'"
systemctl start pinet-captive.service || warn "pinet-captive: check 'systemctl status pinet-captive'"

# ---------------------------------------------------------------------------
# 15. Done
# ---------------------------------------------------------------------------
echo ""
echo -e "${GRN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GRN}  PINET installed.${NC}"
echo -e "${GRN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Wi-Fi SSID : $SSID (open, no password)"
echo "  Portal URL : https://10.10.10.1  (or http://pinet.local after DNS)"
echo "  Admin login: the password you just set"
echo ""
echo "  To install the self-signed CA cert on a phone/laptop:"
echo "    → open https://10.10.10.1/static/pinet-ca.crt"
echo ""
echo "  Service status:"
echo "    systemctl status pinet-board pinet-ap-network hostapd dnsmasq"
echo ""
echo "  Logs:"
echo "    journalctl -u pinet-board -f"
echo ""
echo "  ─── DSI touchscreen / cyberdeck extras (optional) ───────────────"
echo "  Install user services (run as the desktop user, not root):"
echo "    cp $REPO/systemd/user/*.service ~/.config/systemd/user/"
echo "    systemctl --user daemon-reload"
echo "    systemctl --user enable --now pinet-lock dsi-tap-wake ..."
echo ""
echo "  Plymouth boot splash:"
echo "    sudo install -D -m 644 -t /usr/share/plymouth/themes/pinet $REPO/plymouth/pinet/*"
echo "    sudo plymouth-set-default-theme -R pinet"
echo ""
echo "  USB encryption: sudo pinet-media-encrypt  (interactive, erases USB)"
echo ""
