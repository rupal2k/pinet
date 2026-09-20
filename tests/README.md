# pinet tests

Stdlib-only `unittest` suite. Nothing needs installing: flask, PIL, psutil,
requests, qrcode, waveshare_epd and friends are replaced by stub modules
(see `_support.py`), and shell scripts run against PATH stubs for
`systemctl`, `runuser`, `iw`, `ip`, `nmcli`, `id`, `sleep` and `sync`.
Nothing touches the network, real systemd or real `/run`, `/sys` or `/etc`.

| File | Covers |
|---|---|
| `_support.py` | ast-based def extraction, `sys.modules` stubs, loading extension-less scripts, fake clock/font, shell-script harness |
| `test_pinet_board.py` | `filesize_str`, `_file_ext`/`_file_kind`, login lockout (fake monotonic clock), `storage_stats` |
| `test_eink_dashboard.py` | dark mode, config and fallbacks, hotspot passphrase and board-password parsing, kiosk flag, vcgencmd parsing, `fit_text`, the real `main()` loop on a fake clock and fake EPD |
| `test_pi_power_manager.py` | shed/restore order, bluetooth masking, voltage wait, interrupted restore, startup resume, corrupt state |
| `test_shell_scripts.py` | `bash -n` on every shell script, `py_compile` on every Python file, kali-power-shed, dsi-install-guard, wifi-pentest-stop, dsi-backlight.sh |
| `test_consistency.py` | desktop `Exec`/`Icon` targets, systemd `Exec` paths, `/usr/local` references, custom unit files shipped |

## Running

From the repo root:

```sh
python3 -B -m unittest discover -s tests -v
```

The code under test only ever sees temp dirs and stubs, but if you want the
run isolated anyway (no network, read-only host, private `/tmp`), wrap the
same command in bubblewrap, e.g. with the QA wrapper:

```sh
run-sandbox.sh python3 -B -m unittest discover -s tests -v
```

which is `bwrap --unshare-all --die-with-parent --ro-bind / / --tmpfs /tmp
--bind <workspace> <workspace> --dev /dev --proc /proc --clearenv ...` under
`prlimit`/`timeout`.

## Expected failures = known defects

A test marked `@unittest.expectedFailure` asserts the **correct** behaviour
for a defect that exists today. Each one has a comment `QA-<id>: <summary>`
pointing at the QA report. So:

- `OK (expected failures=N)` is the normal, green state.
- `unexpected success` means a defect has been fixed: remove that test's
  `@unittest.expectedFailure` decorator so it guards against regression.
- A plain `FAIL`/`ERROR` is a new regression.
