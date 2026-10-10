# Security policy

PINET runs a guest Wi-Fi hotspot, a captive portal with file uploads, and a set
of Wi-Fi auditing tools, so security reports are taken seriously.

## Supported versions

Only the latest commit on `main` is supported. There are no release branches.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Report it privately through GitHub: open the repository's **Security** tab and
choose **Report a vulnerability**. Only the maintainer can see the report.

Include:

- what is affected (file, service, or URL path on the portal),
- how to reproduce it, and
- what an attacker could do with it.

You can expect an acknowledgement within 7 days. Once a fix is on `main`, the
advisory is published with credit to you, unless you ask to stay anonymous.

## Scope

In scope:

- the PINET portal (`pinet-board/`): login, lockout, uploads, sessions, TLS
- scripts that run as root (`scripts/sbin/`, systemd units, sudo rules)
- anything that lets a PINET hotspot guest reach the Pi's SSH, VNC or home network

Out of scope:

- the bundled Kali tools themselves: report those to their upstream projects
- attacks that need physical access to the device or its SD card
- secrets in your own deployment: the repo ships placeholders only (see
  "Secrets" in the README)
