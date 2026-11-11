#!/usr/bin/env bash
# Release gate — the single entry point for every repo check.
#
#   ./scripts/check.sh
#
# CI (.github/workflows/ci.yml) runs exactly this script, so a local pass means
# a CI pass. The shared steps come from scripts/lib/gate.sh (managed by
# repo-template); this repository's own step renders the template in each of
# its variants and runs every rendered repository's gate (tests/render.sh).
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=lib/gate.sh
. scripts/lib/gate.sh

gate_toolchain
gate_shellcheck

step "forge.toml (scripts/sync.py, no token: the file only)"
env -u SYNC_TOKEN "$VENV/bin/python" scripts/sync.py

step "template variants (tests/render.sh)"
tests/render.sh

gate_secret_scan
gate_done
