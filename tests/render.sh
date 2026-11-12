#!/usr/bin/env bash
# Renders the template in each of its variants into work/render/, as a fresh
# git repository, and runs that repository's own release gate on it: every
# branch of the template has to produce a repository whose check passes.
#
#   tests/render.sh [copier]     # the copier executable, default .venv/bin/copier
set -euo pipefail
cd "$(dirname "$0")/.."

COPIER="${1:-.venv/bin/copier}"
OUT=work/render
rm -rf "$OUT"
mkdir -p "$OUT"

commit() { # commit <dir>: everything in it, as the gate reads tracked files
  git -C "$1" add -A
  git -C "$1" -c user.name=test -c user.email=test@example.com commit --quiet -m test
}

# A gate that passes is only worth something if it fails on what it is for.
expect_fail() { # expect_fail <dir> <what>
  if (cd "$1" && ./scripts/check.sh > /dev/null 2>&1); then
    echo "FAIL: the gate in $1 passed with $2" >&2
    exit 1
  fi
  echo "OK: the gate in $1 fails on $2"
}

render() { # render <name> <copier --data arguments...>
  local name="$1" dst="$OUT/$1"
  shift
  printf '\n##### variant: %s\n' "$name"
  "$COPIER" copy --quiet --defaults --vcs-ref HEAD "$@" --data "repo_name=$name" . "$dst"
  git -C "$dst" init --quiet --initial-branch=main
  commit "$dst"
  (cd "$dst" && ./scripts/check.sh)
}

render plain --data visibility=private --data ansible=false --data python_pin=false
printf '<<<<<<< before updating\nx\n>>>>>>> after updating\n' > "$OUT/plain/merged.txt"
commit "$OUT/plain"
expect_fail "$OUT/plain" "an unresolved merge conflict"
git -C "$OUT/plain" rm --quiet merged.txt
commit "$OUT/plain"

# A venv that lost its pip is rebuilt, not trusted.
rm -rf "$OUT"/plain/.venv/lib/python3*/site-packages/pip
(cd "$OUT/plain" && ./scripts/check.sh > /dev/null)
echo "OK: a venv without pip is rebuilt"

# Put together here, so this file does not trip the template repository's own scan.
printf -- '-----BEGIN OPENSSH %s-----\n' 'PRIVATE KEY' > "$OUT/plain/key.txt"
commit "$OUT/plain"
expect_fail "$OUT/plain" "a private key"

render ansible-public --data visibility=public --data ansible=true --data galaxy=false \
  --data python_pin=true --data "python_version=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
mkdir -p "$OUT/ansible-public/host_vars/somehost"
touch "$OUT/ansible-public/host_vars/somehost/local.yml"
git -C "$OUT/ansible-public" check-ignore -q host_vars/somehost/local.yml
echo "OK: a host's local.yml is ignored"
echo "server: 203.0.114.$((4 + 1))" > "$OUT/ansible-public/host.txt"
commit "$OUT/ansible-public"
expect_fail "$OUT/ansible-public" "a LAN-like IPv4 address"
printf '# The test address.\n203\\.0\\.114\\.5\n' >> "$OUT/ansible-public/.secret-allow"
commit "$OUT/ansible-public"
(cd "$OUT/ansible-public" && ./scripts/check.sh > /dev/null)
echo "OK: .secret-allow lets the address through"

render python --data visibility=private --data python_project=true --data python_pin=false
printf 'def double(x: int) -> int:\n    return x * 2\n\n\nhalf: str = double(2)\n' > "$OUT/python/typed.py"
commit "$OUT/python"
expect_fail "$OUT/python" "a type error (pyright)"
printf 'import os\n\n\ndef double(x: int) -> int:\n    return x * 2\n' > "$OUT/python/typed.py"
commit "$OUT/python"
expect_fail "$OUT/python" "an unused import (ruff)"
printf 'def double(x: int) -> int:\n    return x * 2\n' > "$OUT/python/typed.py"
commit "$OUT/python"
(cd "$OUT/python" && ./scripts/check.sh > /dev/null)
echo "OK: the same module passes once it is clean"

render ansible-galaxy --data visibility=private --data ansible=true --data galaxy=true \
  --data python_pin=true --data python_version=3.13

printf '\nAll variants passed.\n'
