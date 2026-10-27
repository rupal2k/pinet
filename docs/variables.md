# PINET Variables

> Configuration, secrets, and gitignored files mapped to risk.

## Gitignored secrets (NEVER commit)

| File | Used by | Risk | Notes |
|---|---|---|---|
| `/etc/pinet-board/board.conf` | `pinet-board/app.py` | **CRITICAL** | Admin password hash (`salt:pbkdf2_sha256_hex`). Exposure enables offline cracking. |
| `/etc/pinet-board/guest.conf` | `pinet-board/app.py` | **HIGH** | Guest password hash. Absence disables guest login entirely (only admin can log in). |
| `/etc/pinet-board/secret_key` | Flask session signing | **CRITICAL** | 32-byte random secret. Exposure allows session cookie forgery. Auto-generated on first start if absent. |
| `/etc/pinet-board/tls-fullchain.pem` | Flask TLS listener | **HIGH** | Self-signed cert for 10.10.10.1 and pinet.local. |
| `/etc/pinet-board/tls.key` | Flask TLS listener | **CRITICAL** | TLS private key. |
| `/etc/dsi-lock/passcode` | `dsi-lock.py` | **MEDIUM** | Numeric PIN for the touchscreen lock screen. Mode 0600. |
| `config/board.conf` (in repo) | *repo root only* | — | Template only. Never contains real values. |
| `config/guest.conf` (in repo) | *repo root only* | — | Template only. |

Also gitignored per `eink-dashboard/.gitignore`:
- `eink-dashboard/src/__pycache__/`
- Any local config overrides in `eink-dashboard/config/`

## pinet-ups-guard environment variables

| Variable | Default | Used by | Notes |
|---|---|---|---|
| `UPS_SHUTDOWN_V` | `3.3` | `pinet-ups-guard` | Cell voltage cutoff (V). Waveshare default is 3.15 V; raised to 3.3 V after a 3.57 V brownout. |
| `UPS_SHUTDOWN_GRACE` | `60` | `pinet-ups-guard` | Seconds of low voltage before shutdown. |
| `UPS_LOW_FLAG` | `/run/pinet-ups-low` | `pinet-ups-guard`, e-ink | Monotonic deadline written when countdown starts; read by e-ink for display. |
| `UPS_ARM_MARK` | `/run/pinet-ups-arm-boot` | `pinet-ups-guard`, `pinet-ups-arm` shutdown hook | Marker that tells the shutdown hook to arm the MCU. |
| `UPS_READER` | `/usr/local/bin/pinet-battery` | `pinet-ups-guard` | Path to the battery reader module (loaded dynamically). |

## eth-share environment variables

| Variable | Default | Used by | Notes |
|---|---|---|---|
| `ETH_SHARE_FLAG` | `/run/eth-share` | `eth-share` | Presence = sharing active. |
| `ETH_SHARE_LEASES` | `/var/lib/NetworkManager/dnsmasq-<iface>.leases` | `eth-share status` | DHCP lease file for client count. |
| `PENTEST_FLAG` | `/run/pentest-mode` | `eth-share` | If present, `eth-share start` is blocked. |
| `UPS_LOW_FLAG` | `/run/pinet-ups-low` | `eth-share` | If present, `eth-share start` is blocked. |
| `ETH_SHARE_BATTERY` | `/usr/local/bin/pinet-battery` | `eth-share` | Battery reader binary for pre-start check. |
| `ETH_SHARE_MIN_PCT` | `25` | `eth-share` | Minimum battery % to allow sharing on battery. |
| `ETH_ADFREE_FLAG` | `/run/eth-share-adfree` | `eth-share` | Presence = Pi-hole ad-blocking active. |
| `ETH_ADFREE_CONF` | `/etc/NetworkManager/dnsmasq-shared.d/pinet-adfree.conf` | `eth-share` | Drop-in that forwards DNS to FTL. |
| `ETH_PIHOLE_SERVICE` | `pihole-FTL` | `eth-share` | systemd service name for Pi-hole. |
| `ETH_PIHOLE_PORT` | `5335` | `eth-share` | FTL loopback port. |
| `ETH_PIHOLE_API` | `http://127.0.0.1:8089/api/stats/summary` | `eth-share` | FTL stats endpoint. |

## /run tmpfs coordination flags

These files live in `/run` (tmpfs) — they never persist across reboots.

| Path | Written by | Read by | Meaning |
|---|---|---|---|
| `/run/user/1000/kiosk-mode.d/<name>` | `dsi-kiosk.sh` | `pi-power-manager` | Each entry = one open kiosk. All gone = no kiosk. |
| `/run/user/1000/kiosk-mode` | legacy `dsi-kiosk.sh` | `pi-power-manager` | Single flag (older format). |
| `/run/pentest-mode` | `wifi-pentest-start` | `pi-power-manager`, `eth-share`, e-ink | Pentest mode active. |
| `/run/pentest-shed.list` | `kali-power-shed`, `pi-power-manager` | `wifi-pentest-stop` | Units held down for pentest; `wifi-pentest-stop` restores them. |
| `/run/pinet-stopped` | `pinet-stop` | `pi-power-manager` | Deliberate PINET stop — keeps PINET units down after kiosk restore. |
| `/run/power-shed.lock` | `pi-power-manager`, `kali-power-shed` | both | flock mutex; prevents simultaneous shed/restore. |
| `/run/pi-power-manager/stopped.json` | `pi-power-manager` | `pi-power-manager` | List of shed units; atomic write. |
| `/run/pi-power-manager/mode` | `pi-power-manager` | e-ink dashboard | `"normal"` / `"kiosk"` / `"restoring"`. |
| `/run/pi-power-manager/under-voltage` | `pi-power-manager` | e-ink dashboard | `"1"` or `"0"` — live PWR_LOW_N pin state. |
| `/run/pinet-ups-low` | `pinet-ups-guard` | e-ink, `eth-share` | Monotonic shutdown deadline. |
| `/run/pinet-ups-arm-boot` | `pinet-ups-guard` | `pinet-ups-arm` shutdown hook | Trigger: arm MCU for boot-on-power. |
| `/run/eth-share` | `eth-share start` | `eth-share status` | Ethernet sharing active. |
| `/run/eth-share-adfree` | `eth-share adfree-on` | `eth-share status` | Pi-hole active. |

## pinet-board Flask config (set in code, not env)

| Name | Value | Notes |
|---|---|---|
| `MAX_CONTENT_LENGTH` | 1 GiB | Werkzeug rejects bodies larger than this before reaching app code. |
| `MIN_FREE_BYTES` | 500 MiB | Always kept free on `/mnt/pinet-media` after an upload. |
| `LOW_FREE_BYTES` | 1 GiB | Below this, the header warns that the next upload may not fit. |
| `MAX_MESSAGE_LEN` | 2000 chars | Max message body length. |
| `MAX_ATTEMPTS` | 5 | Login attempts before lockout. |
| `LOCKOUT_SECONDS` | 60 | Lockout duration in seconds. |
| `HTTPS_PORT` | 443 | Flask TLS listener port. |
| `SECURE_ORIGIN` | `https://10.10.10.1` | HTTPS redirect target. |
| `TMPDIR` (env) | `/mnt/pinet-media/tmp` | Set in `pinet-board.service`; overrides `/tmp` (463 MB tmpfs) for Werkzeug upload spooling. |

## Pre-deploy checklist

- [ ] Set admin password: `sudo python3 /opt/pinet-board/set_password.py`
- [ ] Set guest password: `sudo python3 /opt/pinet-board/set_guest_password.py` (or delete `guest.conf` to disable guest login)
- [ ] Set touchscreen PIN: `echo -n "1234" | sudo tee /etc/dsi-lock/passcode > /dev/null && sudo chmod 600 /etc/dsi-lock/passcode`
- [ ] Generate or install TLS cert for `10.10.10.1` / `pinet.local` at `/etc/pinet-board/tls-fullchain.pem` and `tls.key`
- [ ] Verify `/etc/pinet-board/secret_key` exists (auto-generated on first start; back it up)
- [ ] Confirm `/mnt/pinet-media/tmp` directory exists (needed for Werkzeug upload spooling)
- [ ] Confirm `TMPDIR=/mnt/pinet-media/tmp` is set in `pinet-board.service` (it is by default)
- [ ] Verify nftables rule is loaded: `sudo nft list ruleset | grep pinet_ap`
- [ ] Confirm `avoid_warnings=2` in `/boot/firmware/config.txt` (full CPU clock; required for Pi 3B under load)
