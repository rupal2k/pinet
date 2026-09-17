---
tags: [project, raspberry-pi, linkedin, writing]
---

# LinkedIn post about the project (drafted 2026-09-15)

Hardware story first, then the offline network. Short version (1,009
characters), chosen by the user over a longer 2,195-character draft. Passed the
`linkedin-content` skill's linter (96/100, SHIP). Not yet posted as of this note.

**Before posting**: the Claude Code line is optional, reword or delete it. Add a
real photo of the setup with alt text (LinkedIn doesn't add it). No hashtags or
links; if linking a write-up, put it in the first comment.

Suggested alt text: *A Raspberry Pi with a small black-and-white e-ink screen
showing the time and weather, next to a 7-inch touchscreen showing a photo
slideshow.*

---

A 2016-era Raspberry Pi 3B now runs an e-ink status screen, a touchscreen photo frame, a live camera and its own offline Wi-Fi network.

The e-ink panel shows the time, weather, system stats and a QR code to join the Wi-Fi. The 7-inch touchscreen is a photo frame that sleeps after 90 seconds and wakes on a double tap.

The hard part was power. The board reports under-voltage from boot, and new cables and chargers didn't change it. Heavy load reset it five times in one day. So a small power manager now pauses the hotspot and other services whenever the camera is on screen.

The network is called PINET: private Wi-Fi with no internet, by design. Join it and your phone opens a sign-in page on its own, with an anonymous message board and file sharing up to 1GB. Nothing posted there leaves the room.

I built it with Claude Code as my pair programmer. I made the decisions; it wrote most of the code.

If you've run a Pi 3B with a screen and a camera attached: which power supply finally made it stable?

---

Facts behind it: see [[dsi photo frame]], [[power and undervoltage]],
[[pinet-board]] and [[pinet-captive-portal]]. "Five times in one day" = the 5
unclean resets on 2026-09-15.
