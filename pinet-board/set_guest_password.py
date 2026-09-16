#!/usr/bin/env python3
"""Sets/changes the PINET board's GUEST-tier password, stored separately from
the admin password (board.conf). Guests can view/post/upload but CANNOT delete
uploaded files -- that's admin-only. Run with sudo:

    sudo /opt/pinet-board/set_guest_password.py

Writes both the salted hash (guest.conf, checked by the web app) and a plaintext
copy (guest_password_plaintext.txt, 640 root:rupal) that the e-ink hotspot
screen displays next to the Wi-Fi join QR -- same 'physical display only' trust
model as the admin password's display file. Keeping both in sync here means the
e-ink screen never shows a stale guest password after a change.

Delete /etc/pinet-board/guest.conf to disable guest login entirely; the app
treats an absent file as 'no guest tier'."""
import getpass
import hashlib
import os
import secrets
import shutil

GUEST_CONF = "/etc/pinet-board/guest.conf"
GUEST_PLAINTEXT = "/etc/pinet-board/guest_password_plaintext.txt"


def main():
    pw = getpass.getpass("New PINET guest password: ")
    if len(pw) < 6:
        print("Password too short (min 6 characters).")
        return
    if pw != getpass.getpass("Confirm: "):
        print("Passwords didn't match.")
        return

    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
    with open(GUEST_CONF, "w") as f:
        f.write(f"{salt}:{digest}\n")
    os.chmod(GUEST_CONF, 0o640)
    try:
        shutil.chown(GUEST_CONF, group="pinet-board")  # app (user pinet-board) reads it
    except Exception:
        print("WARNING: could not set group pinet-board on", GUEST_CONF)

    # plaintext copy for the e-ink hotspot screen (dashboard.py runs as rupal)
    with open(GUEST_PLAINTEXT, "w") as f:
        f.write(pw + "\n")
    os.chmod(GUEST_PLAINTEXT, 0o640)
    try:
        shutil.chown(GUEST_PLAINTEXT, group="rupal")
    except Exception:
        print("WARNING: could not set group rupal on", GUEST_PLAINTEXT)

    print(f"Guest password set ({GUEST_CONF} + {GUEST_PLAINTEXT}).")


if __name__ == "__main__":
    main()
