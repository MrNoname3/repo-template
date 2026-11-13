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
printf 'url: https://%s:%s@example.com/\n' user secret > "$OUT/plain/remote.txt"
commit "$OUT/plain"
expect_fail "$OUT/plain" "credentials in a URL"
git -C "$OUT/plain" rm --quiet remote.txt
commit "$OUT/plain"
printf -- '-----BEGIN OPENSSH %s-----\n' 'PRIVATE KEY' > "$OUT/plain/key.txt"
commit "$OUT/plain"
expect_fail "$OUT/plain" "a private key"

render ansible-public --data visibility=public --data ansible=true --data galaxy=false \
  --data python_pin=true --data python_version=3.14
mkdir -p "$OUT/ansible-public/host_vars/somehost"
touch "$OUT/ansible-public/host_vars/somehost/local.yml"
git -C "$OUT/ansible-public" check-ignore -q host_vars/somehost/local.yml
echo "OK: a host's local.yml is ignored"
printf 'path: /%s/someone/notes\n' home > "$OUT/ansible-public/home.txt"
commit "$OUT/ansible-public"
expect_fail "$OUT/ansible-public" "a home directory path"
git -C "$OUT/ansible-public" rm --quiet home.txt
commit "$OUT/ansible-public"
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

# Without the shared gate: the shared files only, nothing of the gate.
printf '\n##### variant: own-gate\n'
"$COPIER" copy --quiet --defaults --vcs-ref HEAD --data repo_name=own-gate --data shared_gate=false . "$OUT/own-gate"
for f in .editorconfig CLAUDE.md .gitignore .gitea/default_merge_message/MERGE_TEMPLATE.md work/.gitkeep; do
  [ -e "$OUT/own-gate/$f" ] || { echo "FAIL: own-gate lacks $f" >&2; exit 1; }
done
for f in scripts .github/workflows/ci.yml requirements.txt .python-version .secret-allow .shellcheckrc; do
  [ ! -e "$OUT/own-gate/$f" ] || { echo "FAIL: own-gate has $f" >&2; exit 1; }
done
echo "OK: own-gate has the shared files and none of the gate"

render ansible-galaxy --data visibility=private --data ansible=true --data galaxy=true \
  --data python_pin=true --data python_version=3.13

printf '\nAll variants passed.\n'
