# USB Storage Encryption

PINET optionally encrypts the USB flash drive (`/dev/sda`) with LUKS2.
All photos, uploads, backup data, and graph files are encrypted at rest.

On each boot, a full-screen PIN pad appears on the DSI touchscreen **before
the photo frame loads**, so the PIN is the only thing standing between the
device and its content.

---

## How it works

| Layer | Detail |
|---|---|
| Encryption | LUKS2 — AES-256-XTS, Argon2id KDF |
| PIN | Same 4-digit code as the dsi-lock screen (`/etc/dsi-lock/passcode`) |
| PIN entry | `pinet-luks-unlock` — full-screen GTK layer-shell touchpad |
| Unlock timing | Early in the graphical session, before `dsi-photo-frame.service` |
| Mount path | `/mnt/pinet-media` (unchanged) — all scripts work without modification |
| Auto-lock | Drive is locked automatically when the Pi shuts down |

### Boot sequence with encryption

```
kernel loads
  └─ e-ink dashboard initializes (pi-eink-dashboard.service)
       └─ DSI backlight enabled after e-ink stabilizes (dsi-backlight-enable.service)
            └─ systemd starts user session (labwc Wayland compositor)
                 └─ pinet-luks-unlock.service starts (Type=notify, TimeoutStartSec=0)
                      └─ PIN pad shown fullscreen on DSI touchscreen (layer-shell OVERLAY)
                           ↓ correct PIN
                      └─ cryptsetup open /dev/sda pinet-media
                      └─ mount /mnt/pinet-media
                      └─ systemd-notify --ready (unblocks After= units immediately)
                           ↓
                 └─ dsi-photo-frame.service starts in background while PIN pad smoothly holds
                      └─ pqiv slideshow maps fullscreen
                           ↓
                 └─ pinet-luks-unlock exits cleanly (RemainAfterExit=yes)
                      └─ seamless cross-fade to photo frame (desktop never flashes)
                           ↓ user taps 'X' close button on photo frame
                 └─ dsi-lock-show raises screen lock overlay (dsi-lock.py)
                      └─ PIN entered → desktop revealed!
```

---

## Setup

Complete **Steps 1–3** and **Step 4** (set the DSI PIN) before running:

```bash
sudo apt install cryptsetup
sudo pinet-media-encrypt
```

The script is interactive: it shows what it will do and asks for `YES`
before touching the drive. It handles the entire migration:

1. Stops dependent services (photo frame, pinet-board, Docker)
2. Backs up all USB data to the SD card
3. Formats the USB drive as LUKS2
4. Restores all data to the encrypted drive
5. Updates `/etc/fstab` and `/etc/crypttab`
6. Installs `pinet-luks-unlock.service` and enables it
7. Adds a drop-in so `dsi-photo-frame` waits for the unlock
8. Removes the SD card backup

---

## Files installed

| File | Purpose |
|---|---|
| `/usr/local/bin/pinet-luks-unlock` | GTK PIN dialog; calls `cryptsetup open` + `mount` |
| `~/.config/systemd/user/pinet-luks-unlock.service` | User service (`Type=notify`, `TimeoutStartSec=0`, `RemainAfterExit=yes`) |
| `~/.config/systemd/user/dsi-photo-frame.service.d/10-after-luks.conf` | Ordering drop-in |
| `/etc/sudoers.d/pinet-luks` | Allows rupal to run cryptsetup/mount/reboot without a password |
| `/etc/pinet-luks` | Marker file — prevents re-running setup |

---

## Recovery

### If the PIN dialog does not appear

Connect over SSH and unlock manually:

```bash
sudo cryptsetup open /dev/sda pinet-media
sudo mount /mnt/pinet-media
```

Then tell systemd the service is satisfied:

```bash
systemctl --user start pinet-luks-unlock.service
```

### If you forget the PIN

The LUKS container **cannot be unlocked without the PIN** — there is no
backdoor. The only recovery is to reformat the drive (all data lost) and
start fresh with `pinet-media-encrypt`.

To change the PIN:

```bash
OLD_PIN=$(sudo cat /etc/dsi-lock/passcode)
echo -n "$NEW_PIN" | sudo tee /etc/dsi-lock/passcode > /dev/null
echo -n "$OLD_PIN" | sudo cryptsetup luksChangeKey --key-file - /dev/sda
echo -n "$NEW_PIN" | sudo cryptsetup luksAddKey --new-keyfile - /dev/sda
```

### Manual open / close

```bash
# Open
echo -n "$(sudo cat /etc/dsi-lock/passcode)" | sudo cryptsetup open --key-file - /dev/sda pinet-media
sudo mount /mnt/pinet-media

# Close (unmount first)
sudo umount /mnt/pinet-media
sudo cryptsetup close pinet-media
```

---

## Disabling encryption

```bash
# Decrypt back to plain ext4 (runs the migration in reverse)
sudo cryptsetup open /dev/sda pinet-media
BACKUP=/home/rupal/usb-plain-backup
mkdir -p "$BACKUP"
sudo cp -a /mnt/pinet-media/. "$BACKUP/"
sudo umount /mnt/pinet-media
sudo cryptsetup close pinet-media
sudo mkfs.ext4 -L pinet-media /dev/sda
UUID=$(sudo blkid -s UUID -o value /dev/sda)
# Restore original fstab UUID line (replace with your UUID)
sudo sed -i "s|/dev/mapper/pinet-media.*|UUID=$UUID  /mnt/pinet-media  ext4  defaults,nofail  0  2|" /etc/fstab
sudo mount /mnt/pinet-media
sudo cp -a "$BACKUP/." /mnt/pinet-media/
sudo rm -rf "$BACKUP"
sudo sed -i "/pinet-media/d" /etc/crypttab
sudo rm -f /etc/sudoers.d/pinet-luks /etc/pinet-luks
systemctl --user disable --now pinet-luks-unlock.service
rm -rf ~/.config/systemd/user/dsi-photo-frame.service.d/10-after-luks.conf
systemctl --user daemon-reload
```

---

## Security notes

- **No secrets in source**: the LUKS passphrase is only in `/etc/dsi-lock/passcode` (mode 600, root:root), never in the repo.
- **5-attempt lockout**: `pinet-luks-unlock` reboots after 5 wrong PINs, preventing offline brute-force through the touchscreen UI.
- **Argon2id KDF**: makes offline dictionary attacks on the LUKS header computationally expensive.
- **Not hardware-bound**: the passphrase is a PIN — if someone extracts the PIN (e.g. over SSH) they can unlock the drive on another machine. For higher assurance, use a TPM or Clevis/Tang policy.
- **SSH risk**: if SSH is accessible and password authentication is enabled, an attacker with SSH access can run `cryptsetup open` directly. Use SSH key-only auth (`PasswordAuthentication no` in sshd_config).
