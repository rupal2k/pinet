---
tags: [project, raspberry-pi, e-ink, module]
---

# `systemd/pi-eink-dashboard.service`

```ini
[Unit]
Description=Raspberry Pi e-Paper status dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/pi-eink-dashboard
ExecStart=/usr/bin/python3 /home/pi/pi-eink-dashboard/src/dashboard.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## ⚠️ The repo copy of this file is a template, not what's deployed

This checked-in unit file still says `User=pi` and `/home/pi/...`, but the
Pi's actual login user is **`rupal`**, so the file **actually installed** at
`/etc/systemd/system/pi-eink-dashboard.service` (and running right now) has
those paths patched to `/home/rupal/pi-eink-dashboard` / `User=rupal` — done
automatically by `scripts/install.sh` via `sed` (see
[[deploy and install scripts]]). Confirmed live: `systemctl status` shows
the running process's cgroup as
`/usr/bin/python3 /home/rupal/pi-eink-dashboard/src/dashboard.py`.

**If you ever re-run the installer or edit the unit file by hand**, remember
this substitution happens at install time — editing
`systemd/pi-eink-dashboard.service` in the repo does **not** affect the
live service until you re-run `scripts/install.sh` (or manually re-copy +
`daemon-reload`).

## Operating it

```bash
sudo systemctl status pi-eink-dashboard --no-pager   # is it running?
sudo systemctl restart pi-eink-dashboard             # apply a code/config change
journalctl -u pi-eink-dashboard -f                   # live logs
journalctl -u pi-eink-dashboard -n 50 --no-pager     # recent logs
```

Every carousel phase flip and every early-refresh network-change event
(see [[dashboard.py]] → `get_network_fingerprint`) is logged at INFO level,
so `journalctl` is the fastest way to confirm a fix actually took effect
live, e.g.:
```
INFO Network changed ('192.168.29.151', True) -> ('192.168.29.166', False), refreshing early
```

---

## Update 2026-09-12 -- new drop-ins, disabled units, journald persistence

Full context in [[fixes session log]] (2026-09-12 session) and
[[power and undervoltage]].

**journald persistent storage** (fixes session log entry 12):
`/etc/systemd/journald.conf.d/99-persistent-storage.conf` -- `Storage=persistent`
+ `SystemMaxUse=100M`. Overrides the RPi OS vendor drop-in
`/usr/lib/systemd/journald.conf.d/40-rpi-volatile-storage.conf`
(`Storage=volatile`); an `/etc` `99-` drop-in wins and survives apt updates.
Also tracked in the `pi-eink-dashboard` git repo (`systemd/journald.conf.d/`
+ install.sh step, commit `cc2d6c6`).

**Boot-timing staggering** (entry 15) -- flatten the boot power spike:
- `/etc/systemd/system/lightdm.service.d/10-stagger.conf` -> `ExecStartPre=
  -/bin/sleep 20` (delay the ~215MB desktop past the early-boot storm).
- `wayvnc.service` override.conf changed to `sleep 50` + `[Unit] After=
  lightdm.service` (was `sleep 35`) -- keep the VNC load off the desktop spike.
- `cloud-init` disabled via `/etc/cloud/cloud-init.disabled` (~19s early load).
- `NetworkManager-wait-online.service` disabled (17s boot block).

**`pinet-ap-network.service` RF-kill fix** (entry 17):
`/etc/systemd/system/pinet-ap-network.service.d/10-rfkill-wait.conf` adds
`ExecStartPre` steps to unblock radios via sysfs
(`echo 0 > /sys/class/rfkill/*/soft`; `rfkill` CLI not installed) and wait ≤15s
for wlan0, before the `ip` commands -- the cloud-init disable had exposed a race
where this ran while wlan0 was still rfkilled.

**Disabled/masked services** (power, entry 14): `docker`, `containerd`
(disabled), `packagekit` (masked), `rpcbind`, `nfs-blkmap` (disabled). Docker is
started on demand for the Kali toolbox.

---

## Update 2026-09-12 -- these drop-ins are version-controlled

The hand-authored drop-ins above are tracked in a git repo at **`/etc/systemd`**
(commit `9a13018`), scoped by a `.gitignore` so ONLY the custom files are tracked
(`journald.conf.d/99-persistent-storage.conf`,
`system/lightdm.service.d/10-stagger.conf`,
`system/wayvnc.service.d/override.conf`,
`system/pinet-ap-network.service.d/10-rfkill-wait.conf`) -- vendor defaults and
enable-state symlinks are ignored. Root-owned; use `sudo git -C /etc/systemd`.
The journald drop-in is *also* tracked in the pi-eink-dashboard repo (its install
source). NOT captured by this repo (they live outside `/etc/systemd`): the
cloud-init disable (`/etc/cloud/cloud-init.disabled`) and the
NetworkManager-wait-online disable (a removed symlink).

## Update 2026-09-15 -- firewall and DSI units

- **`nftables.service` enabled** (was disabled with the stock empty config).
  `/etc/nftables.conf` drops only `iifname "wlan0" tcp dport { 22, 5900 }`
  -- PINET hotspot guests can't reach SSH or VNC; everything else accepted.
- DSI user units: `dsi-photo-frame.service` (now `SuccessExitStatus=143`),
  `dsi-photo-sync.timer`, `dsi-idle-sleep.service`, `dsi-tap-wake.service`;
  system: `dsi-backlight-enable.service`, `pi-power-manager.service`. See
  [[dsi photo frame]].
- Removed with Docker: `docker`, `containerd` units no longer exist.
