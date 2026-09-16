#!/usr/bin/env python3
"""Sets/changes the PINET board's dedicated password -- unrelated to the
Pi's root/sudo password. Run with sudo (needs to write a root-owned,
group-restricted file).

Also writes a plaintext copy, readable only by `rupal`, purely so
dashboard.py can show it on the e-ink hotspot screen next to the Wi-Fi
join QR -- the same "physical display only" trust model already used for
the Wi-Fi password there (see get_hotspot_passphrase() in dashboard.py).
The hash in PASSWORD_CONF is still the only thing the web app itself
ever checks against; this file exists solely for that one display."""
import getpass
import hashlib
import os
import secrets

PASSWORD_CONF = "/etc/pinet-board/board.conf"
PLAINTEXT_FOR_DISPLAY = "/etc/pinet-board/board_password_plaintext.txt"


def main():
    pw = getpass.getpass("New PINET board password: ")
    if len(pw) < 6:
        print("Password too short (min 6 characters).")
        return
    confirm = getpass.getpass("Confirm: ")
    if pw != confirm:
        print("Passwords didn't match.")
        return

    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()

    with open(PASSWORD_CONF, "w") as f:
        f.write(f"{salt}:{digest}\n")
    os.chmod(PASSWORD_CONF, 0o640)

    with open(PLAINTEXT_FOR_DISPLAY, "w") as f:
        f.write(pw + "\n")
    os.chmod(PLAINTEXT_FOR_DISPLAY, 0o640)

    print(f"Board password updated ({PASSWORD_CONF}).")


if __name__ == "__main__":
    main()
