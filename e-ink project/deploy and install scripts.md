---
tags: [project, raspberry-pi, e-ink, module]
---

# Install / deploy scripts

Three scripts exist in this project with very different purposes — easy to
confuse, so documented together.

## `scripts/install.sh` — the real installer (run once, on the Pi)

```bash
cd ~/pi-eink-dashboard
chmod +x scripts/install.sh
./scripts/install.sh
```

What it does, in order:
1. `sudo raspi-config nonint do_spi 0` — enables the SPI interface the HAT
   needs.
2. `apt install` — `python3-pip python3-pil python3-numpy python3-venv git
   fonts-dejavu wireless-tools libopenjp2-7`.
3. Clones (or `git pull`s if already present) Waveshare's driver repo to
   `~/e-Paper`.
4. `pip install` (with `--break-system-packages`, falling back without it
   on older pip) the `waveshare_epd` package from that clone, plus
   `pillow`, `psutil`, `requests`.
5. Installs the systemd unit: `sed`-patches
   `/home/pi/pi-eink-dashboard` → the actual project dir and `User=pi` →
   the actual `$USER` (this is why the *deployed* unit file differs from
   the repo copy — see [[systemd service]]), copies it to
   `/etc/systemd/system/`, then `daemon-reload` + `enable --now`.

Safe to re-run any time (idempotent: `git pull` instead of re-clone, etc.).

## `update_pi_eink.sh` and `bootstrap_pi_eink.sh` — ⚠️ stale, do not run

Both are **heredoc bundler scripts** that write out an *old* snapshot of
`config.ini` / `icons.py` / `dashboard.py` (missing the QR carousel, the
`qrcode` import, the network-interface-detection fix, the 12-hour clock,
and the bold icon restyle — i.e. everything covered in
[[fixes session log]]), then restart the service. They look like normal
deploy scripts but **running either one would silently overwrite the
current working dashboard with a much older, buggier version.**

They were left over from an earlier iteration of this project (probably
used to push a first working copy to the Pi before this was a proper
checked-out repo) and are not referenced by `install.sh`, the systemd
service, or anything else. Recommend deleting them once confirmed
unneeded, or at minimum renaming with an `OLD_` prefix — left as-is for now
since removal wasn't requested.

**Current deploy method in practice**: edit locally, `scp` the changed
file(s) directly to `~/pi-eink-dashboard/src/` on the Pi, then
`sudo systemctl restart pi-eink-dashboard`. See [[fixes session log]] for
the exact commands used each time.
