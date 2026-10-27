# PINET Permissions

> Who is allowed to do what, and where that is enforced.

## Roles

| Role | Scope | How granted |
|---|---|---|
| **guest** | Read board, post messages, upload/download files | Correct guest password (`/etc/pinet-board/guest.conf`) |
| **admin** | All guest actions + delete files + delete messages | Correct admin password (`/etc/pinet-board/board.conf`) |
| **root** (system) | Power management, network configuration, system services | Processes run as root: `pi-power-manager`, `pinet-ups-guard`, `pinet-splash-guard`, `wifi-pentest-start/stop` |
| **pinet-board** (system user) | Read/write `/opt/pinet-board/data/`, `/mnt/pinet-media/uploads/`, `/etc/pinet-board/` | Service runs as `pinet-board:pinet-board`; `AmbientCapabilities=CAP_NET_BIND_SERVICE` for ports 80/443 |

## pinet-board: resource × operation × role matrix

| Resource | Operation | guest | admin | unauthenticated |
|---|---|---|---|---|
| Message board | View | ✅ | ✅ | ❌ → login |
| Message board | Post | ✅ | ✅ | ❌ → login |
| Message board | Delete | ❌ → redirect to board (no error shown) | ✅ | ❌ → login |
| Files | View / download | ✅ | ✅ | ❌ → login |
| Files | Upload | ✅ | ✅ | ❌ → login |
| Files | Delete | ❌ → redirect to board (no error shown) | ✅ | ❌ → login |
| `/view/<id>` inline | Viewable types (image, video, audio, pdf, text) | ✅ | ✅ | ❌ → login |
| `/view/<id>` inline | Scriptable types (html, svg, js…) | ❌ forced download | ❌ forced download | ❌ → login |
| `/api/state` | Storage stats poller | ✅ | ✅ | 401 (no redirect) |
| `/login` | GET / POST | open | open | open |
| `/static/*` | CSS, logo | open | open | open |

## Code-enforced checks

### Session validity (`_session_valid()`)
Re-derived on every request. Checks:
1. `session["authed"]` is truthy.
2. `_cred_tag(conf_path)` — `sha256(conf_file_bytes)` — matches `session["cred"]`. Changing the password file ends all sessions immediately without a revocation list.
3. The conf file must be readable (deleting it ends all sessions for that role).

### Admin gate (`is_admin()`)
```python
def is_admin():
    return session.get("role") == "admin"
```
Called explicitly on every delete route. There is no implicit admin-by-URL; the check is in the handler.

### Brute-force lockout
5 incorrect attempts from one IP → 60 s lockout. Implemented in-process (`_attempts` dict, monotonic clock). **No persistence across restarts** — a server restart resets all lockout state.

### Upload path safety
`werkzeug.utils.secure_filename()` strips path traversals (`../`, absolute paths) from the user-supplied filename before storage. Files are stored as `<random_token>_<safe_name>` so original names cannot be used to enumerate or overwrite.

### HTTPS enforcement
`needs_https()` redirects non-loopback HTTP clients to HTTPS when `HTTPS_ON` is set. Serves an informational page rather than a bare 301, because mobile captive-portal UIs may refuse to follow a redirect to a self-signed cert.

## Network isolation (nftables)

File: `etc/nftables/pinet-ap.nft` — loaded by `pinet-ap-network.service`.

```
table inet pinet_ap {
    chain input {
        type filter hook input priority filter; policy accept;
        iifname "wlan0" tcp dport { 22, 5900 } drop
    }
}
```

| From | To | Port | Rule |
|---|---|---|---|
| wlan0 guests | Pi SSH | 22 | **drop** |
| wlan0 guests | Pi VNC | 5900 | **drop** |
| wlan0 guests | Pi HTTP | 80 | allowed (captive portal probes) |
| wlan0 guests | Pi HTTPS | 443 | allowed (portal) |
| wlan0 guests | dnsmasq DNS | 53 | allowed (by default policy accept) |
| wlan0 guests | each other | any | not restricted (guest-to-guest traffic is not blocked) |
| wlan1 / eth0 | all | any | untouched by this table |

**Gap:** guest-to-guest traffic on the 10.10.10.0/24 subnet is not restricted. Guests can reach each other directly.

## System-level privilege boundaries

| Script / daemon | Privilege required | How obtained |
|---|---|---|
| `pi-power-manager` | root (reads debugfs, stops/starts system services) | Runs as root via `pi-power-manager.service` (no `User=` directive) |
| `pinet-ups-guard` | root (I²C bus, `systemctl poweroff`) | Runs as root via `pinet-ups-guard.service` |
| `eth-share start/stop` | root (nmcli connection management, nftables) | User invokes via `pkexec`; `_require_root()` exits if `euid != 0` |
| `wifi-pentest-start/stop` | root (iw monitor mode, ip link) | Runs as root; launched from user session via pkexec or sudoers |
| `dsi-install-guard` | root (dpkg hook) | Runs as root during apt operations |
| `pinet-board` Flask app | `pinet-board` system user | `User=pinet-board` in service unit; `CAP_NET_BIND_SERVICE` for ports |
| `pi-eink-dashboard` | user (rupal) | Runs as user service; reads `/run` flags written by root daemons |
