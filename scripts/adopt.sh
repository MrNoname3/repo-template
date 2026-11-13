#!/usr/bin/env bash
# Builds an existing repository from the template: `copier copy --overwrite`
# into its clean checkout, at the template's newest tag unless --vcs-ref says
# otherwise. The overwritten .gitignore must keep ignoring whatever it ignored
# before, so the script lists the ignored files first and fails, before
# anything is committed, if one of them shows up afterwards.
#
#   scripts/adopt.sh <repo-dir> [copier copy options, e.g. --data ansible=true]
#
# Then: look at `git diff`, put the repository's own lines back into the
# managed files, move check.sh onto scripts/lib/gate.sh, run it, commit.
set -euo pipefail
cd "$(dirname "$0")/.."

dst="${1:?usage: scripts/adopt.sh <repo-dir> [copier options]}"
shift
if [ -n "$(git -C "$dst" status --porcelain)" ]; then
  echo "ERROR: $dst has uncommitted changes" >&2
  exit 1
fi

ignored_before="$(git -C "$dst" ls-files --others --ignored --exclude-standard --directory | sort)"
./scripts/ensure-venv.sh
.venv/bin/copier copy --overwrite --defaults "$@" \
  https://forge.invalid/MrNoname3/repo-template.git "$dst"
ignored_after="$(git -C "$dst" ls-files --others --ignored --exclude-standard --directory | sort)"

exposed="$(comm -23 <(printf '%s\n' "$ignored_before") <(printf '%s\n' "$ignored_after") | grep . || true)"
if [ -n "$exposed" ]; then
  printf '%s\n' "$exposed"
  echo "ERROR: the template's .gitignore no longer ignores these; put their" >&2
  echo "patterns back into $dst/.gitignore before anything else" >&2
  exit 1
fi
git -C "$dst" status --short
