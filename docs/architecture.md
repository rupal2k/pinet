# PINET Architecture

A battery-powered Raspberry Pi 3B appliance: five coexisting subsystems sharing one board, coordinated by a proactive load-shedding daemon to stay within the Pi 3B's tight 5 V power budget.

## Stack

| Layer | Technology |
|---|---|
| OS | Debian 13 "trixie" (64-bit) · kernel 6.18 · systemd |
| Compositor | labwc (Wayland) + wf-panel-pi on the 7" DSI touchscreen |
| Scripting | Python 3.11+ (stdlib only for tests) · Bash |
| Web portal | Flask (pinet-board) · SQLite · Werkzeug |
| Auth | PBKDF2-SHA256 passwords (200 k rounds) · per-scheme Flask session cookie |
| Hardware | INA219 I²C (`0x43`) · Waveshare 2.13" e-Paper (SPI0) · 7" DSI · RTL8821AU USB Wi-Fi |
| Tests | stdlib `unittest` · 301 tests · 12 test files · Linux-only |

## System overview

```
┌─────────────────── Pi 3B (single 5 V rail) ─────────────────────┐
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  e-ink panel │  │ DSI kiosks / │  │  pinet-board (Flask) │   │
│  │  (SPI0)      │  │ photo frame  │  │  SQLite · HTTPS      │   │
│  │  pi-eink-    │  │ labwc/Wayland│  │  pinet-board user    │   │
│  │  dashboard   │  │              │  │  port 443 + 80       │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘   │
│         │                 │                       │               │
│  ┌──────▼─────────────────▼───────────────────────▼───────────┐  │
│  │               /run tmpfs coordination bus                   │  │
│  │  kiosk-mode · pentest-mode · pinet-ups-low · stopped.json  │  │
│  │  flock /run/power-shed.lock  (shared mutex)                │  │
│  └──────┬────────────────────────────────────────────────────┘  │
│         │                                                         │
│  ┌──────▼───────────────────────────┐  ┌────────────────────┐   │
│  │  pi-power-manager (root Python)  │  │ pinet-ups-guard    │   │
│  │  Monitors kiosk flags → sheds 9  │  │ (root Python)      │   │
│  │  services → voltage-gates restore│  │ INA219 I²C 0x43    │   │
│  └──────────────────────────────────┘  │ 3.3 V cutoff       │   │
│                                         └────────────────────┘   │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ wlan0 (AP)   │  │ wlan1 uplink │  │  eth0 (optional NAT  │   │
│  │ 10.10.10.1   │  │ /monitor mode│  │  router via nmcli)   │   │
│  │ hostapd +    │  │ RTL8821AU    │  │  eth-share (root)    │   │
│  │ dnsmasq      │  │              │  │                      │   │
│  │ nftables drop│  │              │  │                      │   │
│  │ SSH+VNC inbound                                           │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

## Five subsystems

| # | Name | Entry point | Process owner |
|---|---|---|---|
| 1 | **e-ink dashboard** | `eink-dashboard/src/dashboard.py` · `pi-eink-dashboard.service` | user (rupal) |
| 2 | **PINET hotspot + board** | `pinet-board/app.py` · `pinet-board.service` | `pinet-board` system user |
| 3 | **DSI kiosk / photo frame** | `scripts/bin/dsi-kiosk.sh`, `dsi-photo-frame.sh`, `dsi-lock.py` | user (rupal) / labwc session |
| 4 | **Wi-Fi auditing** | `scripts/bin/kali-launcher` · `scripts/sbin/wifi-pentest-start` | user / root |
| 5 | **Ethernet share** | `scripts/sbin/eth-share` | root (via pkexec) |

## Auth and session flow (pinet-board)

1. All routes sit behind `require_login` (`@app.before_request`); only `/login` and `/static` are exempt.
2. `POST /login` → PBKDF2-SHA256 compare against `/etc/pinet-board/board.conf` (admin) or `guest.conf` (guest).
3. On success: `session["authed"] = True`, `session["role"]`, `session["cred"] = sha256(conf_file_bytes)` — the credential tag invalidates every session the moment the password file changes.
4. Cookie: Flask `SecureCookieSession` (HMAC-SHA256 signed); `Secure` flag when request is over HTTPS; `session.permanent = True`.
5. On every subsequent request: `_session_valid()` re-checks `session["cred"]` against the current conf file hash — a password change ends all sessions server-side without storing a revocation list.

## Trust boundaries

| Boundary | What crosses it | How it's enforced |
|---|---|---|
| Open hotspot → host | TCP on wlan0 | nftables drops port 22 (SSH) and 5900 (VNC) inbound on wlan0 |
| Guest HTTP → HTTPS | Login page, session cookie | `needs_https()` redirects HTTP from non-loopback to `https://10.10.10.1`; loopback (kiosk) exempt |
| Guest → admin actions | File delete, message delete | `is_admin()` checks `session["role"] == "admin"` on every destructive route |
| User → root daemons | Power shed, eth-share | `pi-power-manager` and `pinet-ups-guard` run as root systemd services; `eth-share start/stop` requires `pkexec` (polkit) |
| pinet-board → filesystem | Uploads, DB writes | Runs as unprivileged `pinet-board:pinet-board` system user; `AmbientCapabilities=CAP_NET_BIND_SERVICE` for port 443 only |

## Known risks and assumptions

- **Open Wi-Fi hotspot**: `wlan0` has no WPA. Any device nearby can join. Auth is enforced at the web layer (pinet-board login), not the RF layer. The nftables rule only drops SSH/VNC; it does not prevent guest-to-guest traffic on 10.10.10.0/24.
- **Self-signed TLS cert**: The Pi serves HTTPS with a cert covering `10.10.10.1` and `pinet.local`. Mobile browsers will show a certificate warning. Guests must accept it to use the portal over HTTPS.
- **No rate limiting on wlan1 uplink check**: `eth-share start` calls `nmcli` and `ip route` synchronously; these can hang on a flaky interface.
- **Marginal PSU**: The Pi 3B has browned out at 3.57 V under combined load. The power manager mitigates this but does not eliminate the risk.
- **Password files are device-only secrets**: `/etc/pinet-board/board.conf` and `guest.conf` are never in the repo. If the SD card is imaged, the hashes are exposed to offline cracking (PBKDF2 with 200 k rounds provides meaningful resistance).

## Repository layout

```
eink-dashboard/   Standalone e-ink dashboard (its own README + install script)
etc/              System config: hostapd, dnsmasq, nftables, NetworkManager
pinet-board/      Flask portal (app.py, set_password.py, set_guest_password.py)
scripts/
  bin/            /usr/local/bin: user-facing apps and daemons
  sbin/           /usr/local/sbin: privileged daemons and power scripts
systemd/          Service units (system + user)
tests/            stdlib unittest suite (301 tests; Linux-only)
tools/            Dev utilities (icon generators, graph refreshers)
docs/             Architecture guides, hardware notes, fix logs, images
```

## Related documents

| Document | Purpose |
|---|---|
| [flows.md](flows.md) | Step-by-step journeys with auth checks and trust-boundary crossings |
| [permissions.md](permissions.md) | Role × resource × operation matrix; network isolation rules |
| [variables.md](variables.md) | Config, secrets, gitignored files, pre-deploy checklist |
| [Device Overview.md](Device%20Overview.md) | Full device description for operators |
