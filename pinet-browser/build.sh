#!/bin/bash
# Cross-compile pinet-browser for the Pi (aarch64) in Docker, optionally deploy.
#   ./build.sh                    build ./pinet-browser (and refresh Cargo.lock)
#   ./build.sh --deploy user@pi   build, install to /usr/local/bin and the
#                                 desktop entry, and make it the default browser
# The source goes in and the binary comes out through tar on stdin/stdout, so
# no bind mount is needed (Docker Desktop may not share the drive). Crates and
# build output live in named volumes, so rebuilds are incremental.
set -euo pipefail
cd "$(dirname "$0")"

IMAGE=pinet-browser-builder
docker image inspect "$IMAGE" >/dev/null 2>&1 || docker build -t "$IMAGE" .

tar -cf - Cargo.toml Cargo.lock src |
    MSYS_NO_PATHCONV=1 docker run -i --rm \
        -v pinet-cargo-registry:/root/.cargo/registry \
        -v pinet-browser-target:/target -e CARGO_TARGET_DIR=/target \
        "$IMAGE" sh -c '
            mkdir -p /src && cd /src && tar -xf - &&
            cargo build --release --target aarch64-unknown-linux-gnu >&2 &&
            cp /target/aarch64-unknown-linux-gnu/release/pinet-browser . &&
            tar -cf - pinet-browser Cargo.lock' |
    tar -xf -
echo "built: $(ls -l pinet-browser)"

if [[ "${1:-}" == --deploy ]]; then
    host="${2:?usage: $0 --deploy user@host}"
    scp -q pinet-browser pinet-browser.desktop pinet-browser.svg "$host:/tmp/"
    ssh "$host" 'set -e
        sudo install -m 755 /tmp/pinet-browser /usr/local/bin/pinet-browser
        sudo install -m 644 /tmp/pinet-browser.desktop /usr/share/applications/pinet-browser.desktop
        sudo install -D -m 644 /tmp/pinet-browser.svg /usr/share/icons/hicolor/scalable/apps/pinet-browser.svg
        rm -f /tmp/pinet-browser /tmp/pinet-browser.desktop /tmp/pinet-browser.svg
        sudo gtk-update-icon-cache -q /usr/share/icons/hicolor || true
        sudo update-desktop-database -q /usr/share/applications || true
        xdg-settings set default-web-browser pinet-browser.desktop
        xdg-mime default pinet-browser.desktop x-scheme-handler/http x-scheme-handler/https text/html application/xhtml+xml
        echo "deployed; default browser: $(xdg-settings get default-web-browser)"'
fi
