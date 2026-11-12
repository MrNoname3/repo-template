# repo-template

The [Copier](https://copier.readthedocs.io/) template every repository on the
forge is built from, and the sync that keeps their forge settings in line.
Run the commands below from a host terminal; `scripts/copier` brings its own
Copier, so nothing is installed.

## Recipes

**New repository**

1. Create it on the forge, empty; choose private or public.
2. Clone it into `~/Projects/<name>`, then in it:
   `~/Projects/repo-template/scripts/copier copy https://forge.invalid/MrNoname3/repo-template.git .`
   and answer the questions.
3. `./scripts/check.sh`, commit, push. Within the hour the sync sets up the
   settings, branch protection, the Renovate bot and the labels.

**Existing repository onto the template**

1. `scripts/adopt.sh ~/Projects/<name> --data <answer>=<value> ...` (it stops
   if a file the repository ignored would show up; put those patterns back
   into its `.gitignore`).
2. Put the repository's own lines back where `git diff` shows the template
   overwrote them; move its checks into `scripts/check.sh` after the
   `gate_*` calls.
3. `./scripts/check.sh`, commit, push.

**Change what every repository shares**

1. Edit `template/` here; `./scripts/check.sh` must pass.
2. Commit, push, tag `vX.Y.Z`. The sync opens a pull request labelled
   `template` in every repository; merge them once CI is green.
3. A pull request titled `[conflicts]` fails CI until the markers in the files
   its body names are resolved on its branch.

**Change a forge setting or a label:** edit `forge.toml`, push.

**One repository's own check or secret-scan exception:** its
`scripts/check.sh`, or a regex in its `.secret-allow`, with the reason above it.

**A Renovate rule for every repository:** in the renovate-config repository;
one repository's own rule stays in its `renovate.json`.

**New machine:** set `git_forge_url` in machine-setup's
`host_vars/<host>/local.yml` and run its `git` role, so git reads
`forge.invalid` as the forge.

**When something breaks**

- A template pull request is red: `gitea-api ci log <owner/repo>` shows why;
  fix it on its branch, or here with a new tag.
- No pull requests after a tag: look at this repository's **Sync** run; an
  expired `SYNC_TOKEN` shows as HTTP 401.

## How it works

**Files.** A file with "Managed by repo-template" in its header
(`scripts/lib/gate.sh`, `scripts/ensure-venv.sh`, the CI workflow,
`.editorconfig`, `.shellcheckrc`, `CLAUDE.md`, the merge messages, the first
part of `.gitignore`) is the template's: an update rewrites it and a three-way
merge keeps the lines a repository added. Everything else is created once and
then the repository's own: `scripts/check.sh`, the pins, `renovate.json`,
`README.md`, `AGENTS.md`, `pyproject.toml`, `.secret-allow`. With
`shared_gate: false` a repository with a gate of its own gets only the shared
files and the forge settings.

**Answers** (`copier.yml`): visibility (a public or publishable repository's
secret scan also fails on addresses, MACs, UUIDs and home paths), Ansible,
Ansible collections, Python project (ruff, pyright), pinned Python, CI
timeout. A repository records them in `.copier-answers.yml`.

**The address.** Repositories record the template as
`https://forge.invalid/MrNoname3/repo-template.git`; `.invalid` never
resolves, so no repository names the real host. Git maps it per machine:
`git config --global url."https://<your-forge>/".insteadOf "https://forge.invalid/"`.

**The sync** (`scripts/sync.py`, the **Sync** workflow, hourly and on a tag or
a `forge.toml` change) applies `forge.toml` to every repository built from the
template (branch protection only where Actions runs), the labels to every
repository with a `renovate.json`, and opens the update pull requests, closing
those a newer one replaces and merging the base into one that has fallen
behind, as protection accepts only an up-to-date branch. It never deletes. It
needs the `SYNC_TOKEN` secret (repository and issue read-write); a manual run
can be a dry run.

**Checks.** `./scripts/check.sh` here renders every variant
(`tests/render.sh`) and runs each one's gate, including that it fails on a
planted secret, a type error, a lint error and a conflict marker.
