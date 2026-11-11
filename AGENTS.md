# AGENTS.md

Instructions for coding agents working on this repository.

## Keep it publishable

The repository is private but kept as if it were public: it may be
mirrored, and history is forever. No secret, address, MAC, domain, user name
or absolute home path goes into a commit, comment or document; examples use
placeholders (`<your-forge>`, `<lan-subnet>`, `~/…`). `scripts/check.sh` scans
tracked files for them; put private patterns in the untracked
`.secret-patterns.local`.

## This repository is the template and one of its repositories

`template/` and `copier.yml` are what every repository is built from; the
rest of the files are this repository's own copy of the template, kept up to
date with `copier update` like any other. A change to `template/` reaches the
repositories only through a new tag, so it must pass `tests/render.sh` first:
`./scripts/check.sh` runs it.

Nothing in `template/` may name a real host, address or account other than
`MrNoname3`; a repository's private values stay in that repository.

## Working files go in work/

An agent's own temp directory is not on the host's filesystem, so a path
reported from there is one the user cannot open. Downloads, test harnesses and
captured logs go into `work/`: the directory is committed, its contents are
gitignored, and anything in it can be deleted at any time. Secrets stay out
of it. Files the work keeps needing go into the repository.

## A check shows the result, not that something ran

A change passes on the outcome it is for, compared with a known-good
reference. That a command exited 0 does not show it worked. Write "works" or
"done" into the repository only from such a check.

## Before a commit and a push

- `./scripts/check.sh` must pass; CI runs the same script.
- Stage files by name and look at `git diff --cached --stat` before committing.
- Files marked "Managed by repo-template" are overwritten by the template's
  next update: change them in repo-template instead.
