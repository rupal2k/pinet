#!/usr/bin/env bash
# Installer sandbox test — builds a Debian container with the repo baked in,
# runs install.sh followed by assert_installer.sh in the same session.
#
# Usage (from repo root):
#   bash tests/test_installer.sh
#
# Requires: Docker running and accessible as the current user.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."   # repo root

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${YLW}[test]${NC}  $*"; }

IMAGE="pinet-installer-test:latest"

# ---------------------------------------------------------------------------
# Build image (repo baked in, no volume mounts)
# ---------------------------------------------------------------------------
info "Building test image ..."
docker build -q -f tests/Dockerfile.installer-test -t "$IMAGE" . \
    && info "Image ready." \
    || { echo -e "${RED}[test] Docker build failed${NC}"; exit 1; }

# ---------------------------------------------------------------------------
# Run install.sh then assert_installer.sh in one container session.
# No polling, no race conditions, no pipe-buffering surprises.
# ---------------------------------------------------------------------------
info "Running install.sh + assertions in CI mode ..."
docker run --rm \
    -e PINET_CI=1 \
    -e PINET_PIN=5678 \
    -e PINET_ADMIN_PW=admintest \
    -e PINET_GUEST_PW=guesttest \
    -e PINET_SSID=PINET_TEST \
    "$IMAGE" \
    bash -c "bash /repo/install.sh && bash /repo/tests/assert_installer.sh"
