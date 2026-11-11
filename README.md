# repo-template

The [Copier](https://copier.readthedocs.io/) template every repository on the
forge is built from: the release gate's shared steps, the repo-local
toolchain, CI, and the files every repository carries. A repository keeps its
own parts in files the template only creates once, so an update never
overwrites them.

## What the template manages

| Updated by the template | Created once, then the repository's own |
|---|---|
| `scripts/lib/gate.sh` — the shared gate steps | `scripts/check.sh` — calls them, plus the repository's own steps |
| `scripts/ensure-venv.sh` — the repo-local `.venv/` (and pinned Python, Ansible collections) | `requirements.txt`, `requirements-uv.txt`, `.python-version`, `requirements.yml` — the pins Renovate moves |
| `.github/workflows/ci.yml` — runs `scripts/check.sh` | `renovate.json` — extends the shared presets |
| `.gitignore` (the shared part; a repository adds its own lines) | `README.md`, `AGENTS.md`, `LICENSE`, `*.code-workspace` |
| `.editorconfig`, `.shellcheckrc`, `CLAUDE.md`, `.gitea/` merge messages, `work/` | `ansible.cfg`, `inventory.ini`, `site.yml`, `.ansible-lint`, `.secret-allow` |

A managed file says so in its header. Change it here, not in the repository:
the repository's copy is replaced by the next update, except for lines the
repository added, which a three-way merge keeps.

## The template's address

A repository records where its template came from in `.copier-answers.yml`.
That address is `https://forge.invalid/MrNoname3/repo-template.git`: `.invalid`
never resolves, so the file names no real host and the repository can be
mirrored anywhere. Git maps the address to the real forge, once per machine:

```bash
git config --global url."https://<your-forge>/".insteadOf "https://forge.invalid/"
```

## A new repository

Create the repository on the forge, empty, clone it, then in the clone:

```bash
uvx copier copy https://forge.invalid/MrNoname3/repo-template.git .
```

Copier asks the questions in `copier.yml` (visibility, Ansible, pinned Python,
...). Run `./scripts/check.sh`, commit and push.

## An update

Tag a new version here (`vX.Y.Z`). In a repository:

```bash
uvx copier update --defaults
```

takes it to the newest tag with the answers it already has, merging the
template's changes into the repository's. Look at `git diff`, run
`./scripts/check.sh`, commit.

## Checks

`./scripts/check.sh` renders the template in each of its variants
(`tests/render.sh`) and runs every rendered repository's own release gate, on
top of the template repository's own checks.
