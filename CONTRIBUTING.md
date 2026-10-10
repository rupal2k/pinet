# Contributing to PINET

Thanks for your interest. PINET is a personal single-device project, so the
most useful contributions are bug reports with logs, fixes that keep the Pi 3B
within its power budget, and improvements that others can adapt to their own
hardware.

By taking part you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
To report a security problem, see [SECURITY.md](SECURITY.md); please don't
open a public issue for it.

## Reporting a bug

Open an issue using the **Bug report** template. The most helpful reports
include:

- what you did, what you expected, and what happened instead;
- your hardware (Pi model, screen, HATs);
- logs: `journalctl -u <service>`, `journalctl --user -t media-centre`, or the
  output of `vcgencmd get_throttled` for power problems.

Remove passwords, IP addresses and anything personal from logs before posting.

## Making a change

1. Fork the repository and create a branch from `main`.
2. Make the change. Match the style of the file you are editing: comments
   explain *why*, not *what*. New shell scripts should start with `set -u` or
   stricter.
3. Add or update a test when you change logic (see below).
4. Run the test suite:

   ```bash
   python3 -B -m unittest discover -s tests
   ```

5. If you can, try the change on a Pi and include screenshots for anything
   that appears on the 800×480 touchscreen.
6. Open a pull request and fill in the template.

## Tests

- Tests use only the Python standard library, so they run on any machine
  without the Pi's hardware.
- GUI apps import GTK lazily: keep parsing and decision logic in plain
  functions at module level so they can be tested without a display.
- Shell scripts are tested with `tests/_support.py`'s `ShellHarness`, which
  replaces system commands with stubs and records the calls.
- `tests/test_consistency.py` checks that every installed path a script
  refers to (`/usr/local/bin/...`, `/opt/pinet-board/...`) exists in the
  repository. If you add a file that gets installed, it must be covered by its
  `INSTALL_MAP`.

## Ground rules for the device

- **Power first.** The Pi 3B runs on a marginal supply. Avoid anything that
  keeps the CPU busy in the background, and don't start services at boot
  unless they must run all the time.
- **Offline by design.** The PINET hotspot and portal must keep working with
  no internet connection.
- **No secrets in the repository.** Passwords, keys and passcodes live only
  on the device. Use placeholders in committed config.
- **Authorised use only.** Changes to the Wi-Fi auditing tools must keep them
  aimed at networks the user owns or is authorised to test.

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
