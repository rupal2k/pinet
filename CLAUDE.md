# PINET — Dual-Screen Raspberry Pi 3B Cyber-Deck

## What this is
A battery-powered Raspberry Pi 3B appliance: offline captive-portal hotspot, 2.13" e-ink rear panel, 7" DSI touchscreen kiosks, Wi-Fi auditing station, and wireless media centre.  
Target OS: **Debian 13 trixie 64-bit** on a Raspberry Pi 3B.  
Primary language: **Python 3.11+** (scripts) + **Bash** (system scripts).

## Repository layout
```
scripts/bin/     user-land Python + shell scripts (run as normal user)
scripts/sbin/    privileged shell scripts (run as root via sudo)
systemd/         systemd unit files (system + user)
config/          labwc Wayland compositor, GTK, wf-panel config
desktop/         .desktop launchers + icons
plymouth/        boot splash theme
boot/            Pi firmware / config notes
tests/           stdlib unittest suite (301 tests, Linux-only)
tools/           dev-only helpers (diagram generators)
docs/            architecture write-up, design notes
```

## Development constraints
- **No pip dependencies** — the test suite uses only stdlib; scripts use only system packages.
- **Tests are Linux/Raspberry Pi only** — they rely on forward-slash paths, Linux shell stubs, and POSIX behaviour. Run them on Linux/WSL2, not native Windows.
- Run tests: `python3 -B -m unittest discover -s tests -v`
- Shell scripts must pass `bash -n` (syntax check).
- Python files must pass `py_compile`.

## Key subsystems
| Subsystem | Entry point | Privilege |
|---|---|---|
| E-ink dashboard | `eink-dashboard/src/dashboard.py` | user (rupal) |
| Power manager | `scripts/sbin/pi-power-manager` | root system service |
| Battery guard | `scripts/sbin/pinet-ups-guard` | root system service |
| pinet-board portal | `pinet-board/app.py` | `pinet-board` system user |
| DSI camera server | `scripts/bin/dsi-cam-server.py` | user |
| Ethernet share | `scripts/sbin/eth-share` | root via pkexec |
| Screen lock | `scripts/bin/dsi-lock.py` | user |
| Kiosk launcher | `scripts/bin/dsi-kiosk.sh` | user (flock with root power manager) |

## Trust boundaries — do not bypass
- **`/run` tmpfs flags are the coordination bus.** Never write flag files outside `/run`; the power manager and battery guard poll `/run` exclusively.
- **`flock /run/power-shed.lock`** must be held while reading or writing `stopped.json`, `pentest-shed.list`, or `handoff.list`. Both `pi-power-manager` and `kali-power-shed` hold this lock — taking it without the lock causes a race.
- **pinet-board runs as `pinet-board` system user**, not root. Do not add `sudo` calls or capability escalations beyond `CAP_NET_BIND_SERVICE`.
- **nftables `pinet_ap` table** — dropping or modifying this table while `wlan0` AP is up exposes SSH (22) and VNC (5900) to hotspot guests. Never remove it without stopping hostapd first.
- **TLS secrets** (`tls.key`, `secret_key`) live in `/etc/pinet-board/` — never log, print, or expose these paths in web responses.

## Branches
- `main` — primary development
- `feat/cyber-icons` — icon design work
- `feat/display-assets` — display asset work
- `obsidian-vault` — Obsidian notes (do not merge)

## Notes
- `board.conf` and `guest.conf` are gitignored secrets — never commit.
- Agent artefacts (`.claude-flow/`, `ruvector.db`, etc.) are gitignored.
- Obsidian vault notes are tracked; workspace layout files are gitignored.

## System documentation
| Doc | Purpose |
|---|---|
| `docs/architecture.md` | System overview, stack, trust boundaries |
| `docs/flows.md` | Step-by-step journeys with auth checks |
| `docs/permissions.md` | Role × resource × operation matrix; nftables rules |
| `docs/variables.md` | Config, secrets, `/run` flags, pre-deploy checklist |
| `docs/Device Overview.md` | Full device description for operators |
