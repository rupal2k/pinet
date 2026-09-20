"""Shared helpers for the pinet test suite (stdlib only).

The appliance code imports things that are not installed on a dev box
(flask, werkzeug, PIL, psutil, requests, qrcode, waveshare_epd, ...), and some
modules have import-time side effects (pinet-board writes a secret key under
/etc and mkdirs /mnt/pinet-media). So tests either:

* ``load_defs``   -- pull selected top-level defs/assignments out of a file with
                     ``ast`` and exec only those (no module-level side effects), or
* ``load_script`` -- import a whole file (including extension-less scripts such
                     as ``scripts/sbin/pi-power-manager``) with missing third-party
                     modules replaced by ``types.ModuleType`` stubs.

No bytecode is ever written (``sys.dont_write_bytecode``), so the repo stays
clean even when run without ``python3 -B``.
"""
import ast
import contextlib
import importlib.machinery
import importlib.util
import shutil
import stat
import subprocess
import sys
import tempfile
import types
from pathlib import Path

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parent.parent


def repo_path(*parts):
    return REPO.joinpath(*parts)


# --------------------------------------------------------------------------
# Loading Python code
# --------------------------------------------------------------------------

def load_defs(path, names, globals_=None, modname=None):
    """Exec only the named top-level functions/classes/assignments of *path*.

    Decorators are dropped (e.g. ``@app.template_filter``), line numbers are
    preserved so tracebacks point at the real source. *globals_* supplies the
    names the extracted code refers to (e.g. ``time``, ``os``, ``Path``).
    """
    path = Path(path)
    tree = ast.parse(path.read_text(), filename=str(path))
    wanted = set(names)
    body = []
    found = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in wanted:
                node.decorator_list = []
                body.append(node)
                found.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            tnames = {t.id for t in targets if isinstance(t, ast.Name)}
            if tnames & wanted:
                body.append(node)
                found |= tnames & wanted
    missing = wanted - found
    if missing:
        raise LookupError(f"{path}: not found at top level: {sorted(missing)}")
    mod = types.ModuleType(modname or f"_defs_{path.stem.replace('-', '_')}")
    mod.__file__ = str(path)
    if globals_:
        mod.__dict__.update(globals_)
    code = compile(ast.Module(body=body, type_ignores=[]), str(path), "exec")
    exec(code, mod.__dict__)
    return mod


@contextlib.contextmanager
def stub_modules(stubs):
    """Temporarily install ``{name: module}`` into sys.modules."""
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        yield
    finally:
        for name, old in saved.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


def make_module(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    return mod


def load_script(path, modname, stubs=None):
    """Import *path* (any extension, or none) as module *modname*.

    Third-party imports are satisfied from *stubs* for the duration of the
    import only; the loaded module keeps its references to the stub objects.
    """
    path = Path(path)
    loader = importlib.machinery.SourceFileLoader(modname, str(path))
    spec = importlib.util.spec_from_loader(modname, loader)
    mod = importlib.util.module_from_spec(spec)
    with stub_modules(stubs or {}):
        loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# Fakes used by several test files
# --------------------------------------------------------------------------

class FakeClock:
    """Stands in for the ``time`` module: monotonic() + sleep() that advances.

    ``stop_after`` raises KeyboardInterrupt from sleep() once the clock would
    pass that point, which is how the infinite service loops are ended.
    """

    def __init__(self, start=1000.0, stop_after=None):
        self.now = float(start)
        self.start = float(start)
        self.stop_after = stop_after
        self.sleeps = []

    def monotonic(self):
        return self.now

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        if self.stop_after is not None and (self.now + seconds - self.start) > self.stop_after:
            raise KeyboardInterrupt
        self.now += seconds

    @property
    def elapsed(self):
        return self.now - self.start


class FakeFont:
    def __init__(self, path, size):
        self.path = path
        self.size = size


class FakeDraw:
    """textbbox width = characters * font size (deterministic 'font metrics')."""

    def textbbox(self, xy, text, font=None):
        size = font.size if font is not None else 10
        return (0, 0, len(text) * size, size)


def pil_stubs():
    """PIL + friends as ModuleType stubs sufficient for importing dashboard.py."""
    image = make_module("PIL.Image")
    draw = make_module("PIL.ImageDraw", Draw=lambda img: FakeDraw())
    font = make_module("PIL.ImageFont", truetype=lambda path, size: FakeFont(path, size),
                       load_default=lambda: FakeFont("default", 10))
    ops = make_module("PIL.ImageOps")
    pil = make_module("PIL", Image=image, ImageDraw=draw, ImageFont=font, ImageOps=ops)
    return {"PIL": pil, "PIL.Image": image, "PIL.ImageDraw": draw,
            "PIL.ImageFont": font, "PIL.ImageOps": ops}


def dashboard_stubs():
    stubs = pil_stubs()
    for name in ("psutil", "qrcode", "requests", "icons"):
        stubs[name] = make_module(name)
    return stubs


# --------------------------------------------------------------------------
# Shell-script harness
# --------------------------------------------------------------------------

STUBS = {
    # systemctl: tracks an "active" set in $FAKE_DIR/active, logs every call.
    "systemctl": r"""#!/bin/bash
d="$FAKE_DIR"; echo "systemctl $*" >> "$d/calls.log"
[ "${1:-}" = --user ] && shift
cmd=${1:-}; shift
while [ "${1:-}" = --quiet ] || [ "${1:-}" = --runtime ] || [ "${1:-}" = --no-block ]; do shift; done
u=${1:-}
touch "$d/active"
case "$cmd" in
  is-active) grep -qxF -- "$u" "$d/active" ;;
  stop) grep -vxF -- "$u" "$d/active" > "$d/active.tmp"; mv "$d/active.tmp" "$d/active" ;;
  start) grep -qxF -- "$u" "$d/active" || echo "$u" >> "$d/active"; echo "$u" >> "$d/started" ;;
  *) : ;;
esac
""",
    # runuser -u USER -- CMD...  -> run CMD (env/systemctl resolve via PATH)
    "runuser": r"""#!/bin/bash
echo "runuser $*" >> "$FAKE_DIR/calls.log"
while [ $# -gt 0 ] && [ "$1" != -- ]; do shift; done
shift
exec "$@"
""",
    "id": r"""#!/bin/bash
if [ "${1:-}" = -u ]; then echo "${FAKE_UID:-0}"; else exec /usr/bin/id "$@"; fi
""",
    "sleep": "#!/bin/bash\necho \"sleep $*\" >> \"$FAKE_DIR/calls.log\"\nexit 0\n",
    "sync": "#!/bin/bash\necho sync >> \"$FAKE_DIR/calls.log\"\nexit 0\n",
    "iw": r"""#!/bin/bash
echo "iw $*" >> "$FAKE_DIR/calls.log"
if [ -n "${FAKE_NO_WLAN1:-}" ]; then echo "command failed: No such device (-19)" >&2; exit 237; fi
case "$*" in *info*) printf 'Interface wlan1\n\ttype monitor\n' ;; esac
exit 0
""",
    "ip": r"""#!/bin/bash
echo "ip $*" >> "$FAKE_DIR/calls.log"
if [ -n "${FAKE_NO_WLAN1:-}" ]; then echo 'Cannot find device "wlan1"' >&2; exit 1; fi
exit 0
""",
    "nmcli": r"""#!/bin/bash
echo "nmcli $*" >> "$FAKE_DIR/calls.log"
case "$*" in "device status") printf 'DEVICE  TYPE  STATE\nwlan1   wifi  connected\n' ;; esac
exit 0
""",
}

# Stand-ins for the repo's own helpers installed under /usr/local/{bin,sbin}.
LOGGING_STUBS = ("kali-power-shed", "dsi-sleep.sh", "dsi-wake.sh", "dsi-backlight.sh")


class ShellHarness:
    """A temp dir with PATH stubs and a path-rewritten copy of a repo script.

    The scripts hard-code /run, /sys and /usr/local paths; the copy rewrites
    those to paths inside the temp dir, so the logic under test is unchanged
    but nothing outside the temp dir is touched.
    """

    def __init__(self, script_rel, rewrites=None):
        self.dir = Path(tempfile.mkdtemp(prefix="pinet-sh-"))
        self.bin = self.dir / "stubbin"
        self.bin.mkdir()
        (self.dir / "active").touch()
        (self.dir / "calls.log").touch()
        for name, body in STUBS.items():
            self._write_exec(self.bin / name, body)
        for name in LOGGING_STUBS:
            self._write_exec(self.bin / name,
                             f'#!/bin/bash\necho "{name} $*" >> "$FAKE_DIR/calls.log"\nexit 0\n')
        src = repo_path(script_rel).read_text()
        rw = {"/usr/local/sbin/": f"{self.bin}/", "/usr/local/bin/": f"{self.bin}/"}
        rw.update({k: v.format(tmp=self.dir) for k, v in (rewrites or {}).items()})
        for old, new in rw.items():
            src = src.replace(old, new)
        self.script = self.dir / Path(script_rel).name
        self._write_exec(self.script, src)

    @staticmethod
    def _write_exec(path, body):
        path.write_text(body)
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def set_active(self, *units):
        (self.dir / "active").write_text("".join(u + "\n" for u in units))

    def active(self):
        return [l for l in (self.dir / "active").read_text().splitlines() if l]

    def started(self):
        p = self.dir / "started"
        return [l for l in p.read_text().splitlines() if l] if p.exists() else []

    def calls(self):
        return (self.dir / "calls.log").read_text().splitlines()

    def run(self, *args, env=None, timeout=30):
        e = {"PATH": f"{self.bin}:/usr/bin:/bin", "FAKE_DIR": str(self.dir),
             "HOME": str(self.dir), "LC_ALL": "C"}
        e.update(env or {})
        return subprocess.run(["/bin/bash", str(self.script), *args], env=e,
                              capture_output=True, text=True, timeout=timeout)

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def _first_line(p):
    try:
        with p.open("rb") as f:
            return f.readline(64)
    except OSError:
        return b""


def bash_scripts():
    """Every tracked shell script (by shebang), relative to the repo root."""
    out = []
    for p in sorted(REPO.rglob("*")):
        if not p.is_file() or "tests" in p.relative_to(REPO).parts:
            continue
        if p.suffix in {".md", ".ttf", ".png", ".svg", ".crt", ".css", ".js", ".html"}:
            continue
        first = _first_line(p)
        if first.startswith(b"#!") and b"bash" in first:
            out.append(p)
    return out


def python_files():
    out = []
    for p in sorted(REPO.rglob("*")):
        if not p.is_file() or "tests" in p.relative_to(REPO).parts:
            continue
        if p.suffix == ".py":
            out.append(p)
        elif p.suffix == "":
            first = _first_line(p)
            if first.startswith(b"#!") and b"python" in first:
                out.append(p)
    return out
