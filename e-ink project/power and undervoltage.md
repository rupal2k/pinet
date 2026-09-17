---
tags: [project, raspberry-pi, e-ink, hardware, power]
---

# Power / under-voltage investigation (2026-09-06)

Chronological record of a persistent under-voltage condition found on the
Pi 3B, separate from the software fixes in [[fixes session log]]. Started
from a routine "check the Pi's voltage" request; escalated into a real
hardware investigation once the flag turned out not to clear on its own.

## Symptom

`vcgencmd get_throttled` reports `0x50005` continuously:

| Bit | Meaning | State |
|---|---|---|
| 0 (`0x1`) | Under-voltage detected (live) | **set** |
| 2 (`0x4`) | Currently throttled (live) | **set** |
| 16 (`0x10000`) | Under-voltage has occurred | set (sticky) |
| 18 (`0x40000`) | Throttling has occurred | set (sticky) |

Bits 0 and 2 are live/real-time flags, not just boot-time latches — they
should clear on their own within seconds of the input rail recovering,
without needing a reboot. They did not clear across any test below, some
of which ran 15-17+ minutes at near-idle CPU load. This rules out both
"boot inrush blip" and "CPU-load-driven brownout" as explanations.

`vcgencmd measure_volts core` reads a constant `1.2000V` throughout —
this is the internal ARM/GPU core regulator output, fixed by design
regardless of input rail quality on this board. **It is not diagnostic
for input power problems and can be ignored for this issue.**

## What was ruled out

Four different power sources were tested, each requiring a Pi reboot
(power-cycle) to switch. All four produced the identical `0x50005`
signature, persisting well past boot with the Pi idle:

1. Original setup, cable swapped (same charger) — no change.
2. UGREEN 65W GaN USB-PD charger — no change.
3. A OnePlus/VOOC-family fast-charge charger — no change.
4. A basic non-fast-charge dual-port 5V/3A charger — no change (bit 0
   still active live, without even requiring a fresh reboot to detect —
   confirmed via `dmesg`/`/proc/uptime` showing this was the *same* boot
   as test 3, meaning the live flag was still failing to clear on its own
   under a charger that should, in principle, be adequate).

**Working theory going in**: chargers 2-3 both require a digital
handshake (PD / VOOC) that the Pi 3B's non-negotiating micro-USB input
can't perform, so they might fall back to a lower default current. That
theory predicted charger 4 (a plain 5V/3A supply with no negotiation
protocol) should have fixed it. It didn't — which weakens the
"wrong charger type" theory and points at something else: possibly the
Pi's own micro-USB power connector (solder joints on this connector are a
documented Pi 3B failure point, especially on a board that gets moved
around, per [[pi-eink-dashboard-access]] noting this Pi is portable), or
excess current draw from the TP-Link Archer T2U Plus USB Wi-Fi adapter
(see [[pi-eink-dashboard-hotspot]]) that persists regardless of supply.

Cross-reference: the Overview note's earlier power budget analysis
(section "Power (researched 2026-09-06)") calculated ~750mA idle /
~1100mA peak against a 2.5A rating with a DSI touchscreen — comfortable
headroom on paper. That analysis didn't originally account for the
TP-Link USB adapter's actual draw, which is untested here.

## Diagnostic dead ends

The Pi 3 Model B exposes **no software-readable current draw** at all:

- `vcgencmd pmic_read_adc` → `error=1 error_msg="Command not registered"`
  — that command (and the PMIC current/voltage ADC it reads) only exists
  on Pi 4/5, which have a smarter PMIC.
- `/sys/class/hwmon/hwmon1` (`rpi_volt`) only exposes
  `in0_lcrit_alarm` — the same binary under-voltage flag as
  `get_throttled`, not an amperage reading.
- No `/sys/class/power_supply/` entries.

To get an actual current-draw number, external hardware is required: an
inline USB power meter, or a multimeter across the input rail. Not yet
done.

## Hotspot activation test (result)

Tested whether bringing up the `PINET` hotspot on `wlan0` (see
[[pi-eink-dashboard-hotspot]] — `hostapd`+`dnsmasq`, found **disabled and
inactive** at test time despite earlier notes saying it had been
`systemctl enable`d; unclear why it reverted, worth checking if that was
intentional) changes the under-voltage state.

Started manually (`sudo systemctl start pinet-ap-network hostapd dnsmasq`,
in that order — sudo was not passwordless at the time, user ran these
directly). All three came up `active` cleanly with no freeze/crash (the
Pi stayed on the same boot/uptime throughout — a good sign, since the
*original* NetworkManager/`nmcli`-based AP mode attempt had frozen the Pi
solid once, requiring a physical power cycle; this hostapd-based method
continues to be freeze-free). `wlan0` came up with `10.10.10.1/24` as
expected.

`get_throttled` stayed at `0x50005` — unchanged from immediately before
activation. **Caveat: this test is not fully conclusive.** The
under-voltage flag was already active before the hotspot was started, so
there was no clean 0→1 transition to attribute to the hotspot
specifically, and there's no higher-severity bit it could have escalated
to even if the hotspot did add meaningful extra draw. This only shows
the hotspot didn't visibly worsen an already-bad state, not that it
draws zero extra current. A clean test would require running this
against a Pi that is *not* already under-voltage.

## Boot-sequencing tests (2026-09-06, all negative)

Tried spreading out boot-time current draw on the theory that overlapping
startup spikes (not sustained draw) were tripping the flag. None of these
changed `get_throttled` from `0x50005`:

- **Staggered non-essential services**: added `ExecStartPre=/bin/sleep N`
  drop-ins to `bluetooth`, `avahi-daemon`, `rpcbind`, `udisks2`, `cups`,
  `wayvnc` (10-35s offsets), leaving `NetworkManager`/`wpa_supplicant`/
  `ssh`/`pi-eink-dashboard` untouched. Verified all came up correctly on
  their delays — no change to the flag.
- **Hotspot (`PINET`) activation**: found `hostapd`/`dnsmasq`/
  `pinet-ap-network` disabled despite earlier notes saying they'd been
  enabled (worth checking with the user whether that was intentional).
  Started manually — came up cleanly, no freeze (confirms the
  hostapd-based approach from [[pi-eink-dashboard-hotspot]] remains
  freeze-free) — no change to the flag, though this test is inherently
  inconclusive since the flag was already active before the hotspot
  started (no 0→1 transition to attribute).
- **Delayed Wi-Fi adapter (`wlan1`, TP-Link Archer T2U Plus) driver
  load**: blacklisted `rtw88_8821au` from auto-loading
  (`/etc/modprobe.d/wifi-adapter-delay-blacklist.conf`) and added a
  `wifi-adapter-delay.timer` (`OnBootSec=45s`) +
  `wifi-adapter-delay.service` to `modprobe` it back in 45s after boot —
  well after the staggered services above. Confirmed working exactly as
  designed: `wlan1` didn't exist at all for the first ~20-40s of boot,
  then the driver loaded, associated to home Wi-Fi, and got its normal
  IP (`192.168.29.125`) with zero connectivity loss. **Still no change**
  to `get_throttled` — still `0x50005`. **Reverted afterward** (blacklist
  file and both units removed, `daemon-reload`d) since it didn't help and
  isn't worth the added boot complexity — Wi-Fi now loads normally at
  boot again with no delay.
- **An Ethernet cable was connected during this round of testing**
  (`192.168.29.166`, confirmed carrier up) specifically as a fallback in
  case the delayed Wi-Fi driver load broke remote access — it didn't end
  up being needed, but is worth knowing it's now available as a second
  network path for future sessions if `wlan1` ever fails to associate.

**Conclusion**: across cable, 4 chargers, hotspot activation, staggered
service startup, and delayed Wi-Fi driver load — 7 independent variables
— `get_throttled` has never once cleared. This strongly rules out
"overlapping boot-time current spikes" as the mechanism. The condition
looks like a **sustained baseline** issue, not a transient one.

## First observed functional failure, not just the flag (2026-09-06, ~16:10-16:32)

Until now, the persistent `0x50005` had only ever shown up as a status
flag with no observed functional consequence. That changed: while PINET
had 2 real devices connected and bridged to the internet (see
[[pinet-captive-portal]]), `dmesg` showed, in this order:

1. `16:10:07` — `sdhost-bcm2835 3f202000.mmc: timeout waiting for
   hardware interrupt` + `mmc0: Card stuck being busy!` (the SD card
   controller itself glitching -- a different subsystem than anything
   tested before).
2. `16:29:20`/`16:29:28` — `rtw88_8821au: failed to get tx report from
   firmware` (the TP-Link USB Wi-Fi adapter, `wlan1`, the WAN uplink).
3. `16:29:33` — `wlan1` deauthenticated and had to re-associate.
4. `16:29:44` — `wlan1` deauthenticated *again*, "by local choice"
   (the Pi's own driver chose to drop it, not the router).
5. `16:29:54` — `wlan1` re-associated successfully.
6. `16:29:56` — `ieee80211 phy0: brcmf_proto_bcdc_query_dcmd... failed
   w/status -110` (ETIMEDOUT) -- `phy0` is the **onboard** Broadcom chip
   that drives `wlan0`/PINET, a firmware communication timeout on a
   *third* radio distinct from the USB adapter that had just been
   flapping.
7. `16:29:57` and `16:31:39` — hostapd logged both real connected PINET
   clients disassociating, ~90s apart -- this is the user-visible
   failure ("connection failed") that prompted investigating this.

By ~16:35 everything had recovered on its own: `wlan1` reconnected,
internet reachability from the Pi confirmed via `ping 8.8.8.8` +
`getent hosts google.com`, `hostapd`/`wlan0` reported healthy, bridge
config (`ip_forward=1`, NAT rule) was untouched and still correct. No
reboot occurred (`uptime` continuous throughout). The user's devices
needed to manually reconnect to PINET afterward; the AP itself didn't
recover their sessions on its own.

**Why this matters**: three different subsystems (SD/MMC controller,
USB Wi-Fi adapter, onboard Wi-Fi chip) glitched within a 20-minute
window, all consistent with a shared root cause (marginal power) rather
than three unrelated coincidences. This raises the real-world stakes of
the still-unresolved investigation above from "a flag that's always
been there" to "this can and will drop active guest connections."

## Escalation to actual crashes (2026-09-06, ~16:40-16:50)

Shortly after the functional failure above, the Pi became unreachable for
an extended period (~10 minutes total, across two separate episodes) in a
way qualitatively different from every earlier blip this session:

1. Mid-way through an unrelated remote command, core binaries started
   failing with `Input/output error` (`sudo`) and "command not found"
   (`ls`, `cat`, `df`, `id`) -- a classic SD-card/storage-read-failure
   signature, not a software bug.
2. `uptime` showed the Pi had already silently rebooted once
   (`up 3 min` when it should have shown much longer).
3. After reconnecting and attempting to finish an in-progress task, it
   became unreachable *again* -- this time SSH's TCP handshake itself
   started resetting (`kex_exchange_identification: Connection reset by
   peer`) for several minutes, then degraded further to full connection
   timeouts, then `No route to host` (the device stopped answering ARP
   entirely -- genuinely off the network, not just a stressed service).
4. It came back on its own after ~10 more minutes, `up 0 min` (another
   silent reboot). This boot showed `EXT4-fs: orphan cleanup on readonly
   fs` -- confirms the prior shutdown was unclean/a crash, not graceful --
   but the journal replay handled it cleanly with no corruption evidence
   found afterward (`df` healthy at 67% used/4.5G free, all binaries
   resolved fine, filesystem mounted rw normally).

**Why this matters**: this is the first time in the whole session's
investigation that the persistent under-voltage condition produced an
actual system crash with a filesystem-level symptom, not just a status
flag or a dropped Wi-Fi association. The user was in the middle of
removing the [[pinet-captive-portal]] feature and had 2 real guest
devices connected to PINET at the time -- worth noting as a possible
contributing factor (more concurrent load/radio activity than most of
today's earlier tests), though not confirmed causal.

**This raises the priority of the still-open investigation significantly.**
The two remaining untested leads (inline USB power meter for a real
current reading; physically inspecting the micro-USB power connector's
solder joints) are no longer just diagnostic curiosity -- this Pi can now
apparently crash and become briefly unreachable under real usage, which
is a genuine reliability problem for whatever this device is meant to do
day-to-day.

## Next steps not yet tried

- Inline USB power meter or multimeter to get a real current number —
  now the highest-value remaining test, since software-side theories
  (charger type, boot sequencing) are largely exhausted.
- Temporarily unplug the TP-Link USB adapter entirely (not just delay
  its driver — physically remove it) and recheck `get_throttled` in
  isolation, to rule out a genuinely faulty adapter/cable drawing
  excess current even when the driver isn't bound.
- Physically inspect the micro-USB power connector/solder joints on the
  Pi board itself — now a stronger suspect given how many other
  variables have been ruled out.
- Test the same charger/cable combination on a different Pi 3B board, if
  one is available, to isolate charger/cable vs. this specific board.

## Passwordless sudo now enabled (2026-09-06)

`rupal ALL=(ALL) NOPASSWD:ALL` added via `/etc/sudoers.d/010-rupal-nopasswd`
(mode `0440`) — sudo no longer needs an interactive password for this
user, which had been the main friction slowing down testing all session
(see [[pi-eink-dashboard-access]]). While fixing this, also found and
fixed `/etc/sudoers.d/pi-eink-wifi-qr` (grants passwordless `nmcli` for
reading the Wi-Fi PSK, used by the dashboard's QR screen) had bad
permissions (`644` instead of required `0440`) — sudo was silently
ignoring that entire file, so the QR screen's PSK lookup may have been
failing silently. Fixed to `0440`; `visudo -c` now parses everything OK.

---

## Update 2026-09-12 -- optimization pass, captured brownout loop, and a lesson

**First actual brownout RESET captured** (only visible because the journal is
now persistent -- see [[systemd service]] / [[fixes session log]] entry 12).
During a reboot cycle the Pi went into a brownout **loop**: `journalctl
--list-boots` shows a boot that lasted exactly **1 second** (12:45:19→12:45:20)
before resetting, with no shutdown sequence (clean reboots log "Syncing
filesystems… Journal stopped"; this just cut off). It cycled ~13 min unreachable
before catching a stable boot on its own. This is the chronic under-voltage
(`0x50005`) biting at the highest-draw moment -- boot.

**Power/RAM trims (persistent, reversible)**: disabled `docker`+`containerd`
(no containers; Kali toolbox starts it on demand), masked `packagekit` (was
~20% CPU), disabled `rpcbind`+`nfs-blkmap` (NFS unused). ~524MB RAM available
afterward (was ~455).

**Boot-timing staggering (keep the GUI)** to stop everything powering up at
once: disabled `cloud-init` and `NetworkManager-wait-online`, delayed `lightdm`
20s and `wayvnc` 50s (details in [[systemd service]]). Aim: separate the big
load phases (base+appliance, then desktop, then VNC) so their peaks don't sum.

**LESSON -- do NOT force a reboot on this Pi to test a power fix.** The reboot
above was self-inflicted (rebooting to "validate" the staggering) and triggered
the loop. Apply boot changes and let them take effect on the next NATURAL
reboot. Software staggering only lowers the odds; the real cure is unchanged:
a known-good 5V/3A supply + short thick cable. The staggering's actual
brownout-prevention benefit is not yet proven across a clean reboot.

## Update 2026-09-12 (later) -- staggering VALIDATED across a real reboot

Rebooted on request to validate the boot staggering (entry 15 / [[systemd service]]).
Result: **one clean boot, no brownout loop** -- back on the network in ~24s (vs.
the ~13-min brownout-loop recovery earlier the same day), a single new boot id
with NO 1-second reset boot preceding it, `system-running=running`, 0 failed
units, desktop up (labwc). Staggering behaved as designed (lightdm delayed
~20.4s, wayvnc after its 50s). The `pinet-ap-network` RF-kill fix also held
across the reboot (active, wlan0 got 10.10.10.1, no RF-kill error).

**Honest caveat (n=1 + a confound)**: `throttled=0x0` this boot -- the
under-voltage flag was already CLEAR before the reboot (it had been 0x50005 all
session), so the power supply appears to have improved independently (cable/PSU
change or conditions). A clean boot with no undervoltage present does NOT by
itself prove the staggering alone prevents brownouts -- it confirms the config
is correct and the boot is healthy, but the improved supply is likely the bigger
factor. Real cure remains a good PSU; the staggering is belt-and-suspenders.

## Update 2026-09-15 -- load-triggered resets, shedding helps, Docker gone

- **5 unclean resets in one day** (2026-09-15): two from Chromium, one from a
  Firefox kiosk, one from a qt6 apt install and one from a multi-package
  `dpkg --verify`. Heavy load or heavy SD I/O stalls the SD controller
  ("Card stuck being busy") and the board resets. Mitigations: pi-power-manager
  sheds services during kiosks, an APT install guard, small dirty write-back.
  See [[dsi photo frame]].
- **Shedding measurably helps**: during the QA run of the Ezykam kiosk, live
  under-voltage cleared (`0x50005` → `0x50000`) while the hotspot, VNC,
  Bluetooth and slideshow were stopped.
- **Docker is now purged** (was only disabled): docker.io, containerd, runc,
  buildx, cli and their orphans removed at the user's request; Firefox too.
- Real cure unchanged: a known-good 5V/3A supply + short thick cable.

## Update 2026-09-17 -- LOW VOLTAGE message debounced

The carousel's phase-2 header showed LOW VOLTAGE/THROTTLED on any single
instantaneous `get_power_status()` read with bit0/bit2 set. Now `main()` samples
every loop iteration and only shows it after `undervoltage_min_readings`
(config.ini, default 3) consecutive active reads -- a one-time spike is ignored,
the chronic sustained `0x50005` still shows. `get_power_status()` already excluded
the sticky "has occurred" bits (16/18). Checked 2026-09-17: still `0x50005` with
the ARM clock pinned at 600 MHz (actively throttled) -- genuinely undervolted right
now, not a spike. See [[dashboard.py]], [[fixes session log]] entry 43.
