#!/usr/bin/env python3
"""Apply forge.toml and the template's newest tag to the owner's repositories.

For every repository built from this template (its .copier-answers.yml names
the template): the [repository] settings, the default branch's [protection],
the [[collaborator]]s, and, when the template has a newer tag than the one the
repository was last updated to, a pull request with `copier update` to it.
For every repository with a renovate.json: the [[label]]s.

Without --apply it prints what it would do and changes nothing. It never
deletes anything. Reads GITHUB_API_URL, GITHUB_SERVER_URL,
GITHUB_REPOSITORY_OWNER and SYNC_TOKEN (repository and issue read-write).
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request

TEMPLATE_ALIAS = "https://forge.invalid/MrNoname3/repo-template.git"
TEMPLATE_REPO = "repo-template"
ALIAS_PREFIX = "https://forge.invalid/"
TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
COLOR = re.compile(r"^[0-9a-f]{6}$")
q = urllib.parse.quote


def load_config(path):
    with open(path, "rb") as f:
        config = tomllib.load(f)
    unknown = set(config) - {"repository", "protection", "collaborator", "label"}
    if unknown:
        sys.exit(f"{path}: unknown sections {sorted(unknown)}")
    names = set()
    for label in config.get("label", []):
        if set(label) - {"name", "color", "description", "repos"}:
            sys.exit(f"{path}: label {label.get('name')}: unknown keys")
        if not label.get("name") or label["name"] in names:
            sys.exit(f"{path}: a label has no name, or its name is used twice")
        if not COLOR.match(label.get("color", "")):
            sys.exit(f"{path}: label {label['name']}: color must be six lower-case hex digits")
        names.add(label["name"])
    for collaborator in config.get("collaborator", []):
        if collaborator.get("permission") not in ("read", "write", "admin") or not collaborator.get("name"):
            sys.exit(f"{path}: a collaborator needs a name and a read, write or admin permission")
    return config


def parse_answers(text):
    """The top-level `key: value` pairs of a .copier-answers.yml."""
    answers = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z_][\w]*):\s*(.*)$", line)
        if m:
            answers[m.group(1)] = m.group(2).strip().strip("'\"")
    return answers


class Forge:
    def __init__(self, api, token):
        self.api, self.token = api.rstrip("/"), token

    def call(self, method, path, body=None):
        request = urllib.request.Request(
            self.api + path, method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Authorization": f"token {self.token}",
                     "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return 404, None
            sys.exit(f"{method} {path}: HTTP {error.code}: {error.read().decode(errors='replace')}")

    def get(self, path):
        return self.call("GET", path)[1]

    def pages(self, path):
        page = 1
        while True:
            sep = "&" if "?" in path else "?"
            items = self.get(f"{path}{sep}limit=50&page={page}")
            items = items.get("data", items) if isinstance(items, dict) else items
            if not items:
                return
            yield from items
            page += 1

    def file(self, owner, repo, path):
        content = self.get(f"/repos/{q(owner)}/{q(repo)}/contents/{q(path)}")
        return None if content is None else base64.b64decode(content["content"]).decode()


class Sync:
    def __init__(self, forge, owner, server, token, config, apply):
        self.forge, self.owner, self.server = forge, owner, server.rstrip("/")
        self.token, self.config, self.apply = token, config, apply
        self.changes = 0

    def change(self, repo, what, method, path, body):
        self.changes += 1
        print(f"{repo}: {what}")
        if self.apply:
            self.forge.call(method, path, body)

    def settings(self, repo, current):
        want = self.config.get("repository", {})
        diff = {k: v for k, v in want.items() if current.get(k) != v}
        if diff:
            self.change(repo, f"settings {diff}", "PATCH", f"/repos/{q(self.owner)}/{q(repo)}", diff)

    def description(self, repo, current, answers):
        if not current.get("description") and answers.get("description"):
            self.change(repo, "description from .copier-answers.yml", "PATCH",
                        f"/repos/{q(self.owner)}/{q(repo)}", {"description": answers["description"]})

    def protection(self, repo, branch):
        """The default branch's rule; only where Actions runs, which reports its check."""
        want = dict(self.config.get("protection", {}))
        if not want:
            return
        want["enable_status_check"] = bool(want.get("status_check_contexts"))
        base = f"/repos/{q(self.owner)}/{q(repo)}/branch_protections"
        rules = {r["rule_name"]: r for r in self.forge.get(base) or []}
        have = rules.get(branch)
        if have is None:
            self.change(repo, f"protect {branch}", "POST", base,
                        {"rule_name": branch, "enable_push": True, **want})
            return
        diff = {k: v for k, v in want.items()
                if (sorted(have.get(k) or []) if isinstance(v, list) else have.get(k))
                != (sorted(v) if isinstance(v, list) else v)}
        if diff:
            self.change(repo, f"protection of {branch} {diff}", "PATCH", f"{base}/{q(branch)}", diff)

    def collaborators(self, repo):
        for c in self.config.get("collaborator", []):
            path = f"/repos/{q(self.owner)}/{q(repo)}/collaborators/{q(c['name'])}"
            have = self.forge.get(f"{path}/permission")
            if not have or have.get("permission") not in (c["permission"], "admin", "owner"):
                self.change(repo, f"collaborator {c['name']} ({c['permission']})", "PUT", path,
                            {"permission": c["permission"]})

    def labels(self, repo):
        base = f"/repos/{q(self.owner)}/{q(repo)}/labels"
        existing = {label["name"]: label for label in self.forge.pages(base)}
        for label in self.config.get("label", []):
            if "repos" in label and repo not in label["repos"]:
                continue
            want = {"name": label["name"], "color": "#" + label["color"],
                    "description": label.get("description", "")}
            have = existing.get(label["name"])
            if have is None:
                self.change(repo, f"create label {label['name']}", "POST", base, want)
            elif (have["color"].lstrip("#").lower(), have.get("description", "")) != \
                    (label["color"], want["description"]):
                self.change(repo, f"update label {label['name']}", "PATCH", f"{base}/{have['id']}", want)

    def git_env(self):
        """Git reads the template alias as the forge, and authenticates to it."""
        credentials = base64.b64encode(f"{self.owner}:{self.token}".encode()).decode()
        env = dict(os.environ)
        env.update({
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": f"url.{self.server}/.insteadOf", "GIT_CONFIG_VALUE_0": ALIAS_PREFIX,
            "GIT_CONFIG_KEY_1": f"http.{self.server}/.extraHeader",
            "GIT_CONFIG_VALUE_1": f"Authorization: Basic {credentials}",
            "GIT_AUTHOR_NAME": "repo-sync", "GIT_AUTHOR_EMAIL": "repo-sync@example.com",
            "GIT_COMMITTER_NAME": "repo-sync", "GIT_COMMITTER_EMAIL": "repo-sync@example.com",
            "GIT_TERMINAL_PROMPT": "0",
        })
        return env

    def close_stale(self, repo, keep):
        """Close the open template pull requests other than `keep`, and delete their branches."""
        base = f"/repos/{q(self.owner)}/{q(repo)}"
        for pr in self.forge.pages(f"{base}/pulls?state=open"):
            ref = pr["head"]["ref"]
            if ref.startswith("template/") and ref != keep:
                self.change(repo, f"close #{pr['number']} ({ref}), superseded", "PATCH",
                            f"{base}/pulls/{pr['number']}", {"state": "closed"})
                self.change(repo, f"delete branch {ref}", "DELETE",
                            f"{base}/branches/{q(ref, safe='')}", None)

    def update_behind(self, repo, branch, head):
        """Merge the base into the open template pull request when it is behind:
        a protected branch accepts only an up-to-date one."""
        base = f"/repos/{q(self.owner)}/{q(repo)}"
        for pr in self.forge.pages(f"{base}/pulls?state=open"):
            if pr["head"]["ref"] != head:
                continue
            behind = self.forge.get(f"{base}/compare/{q(pr['head']['sha'])}...{q(branch)}")
            if behind and behind.get("total_commits"):
                self.change(repo, f"update #{pr['number']} ({head}), {behind['total_commits']} behind {branch}",
                            "POST", f"{base}/pulls/{pr['number']}/update?style=merge", None)

    def template_update(self, repo, branch, answers, latest, copier):
        if not latest:
            return
        head = f"template/{latest}"
        self.close_stale(repo, None if answers.get("_commit") == latest else head)
        if answers.get("_commit") == latest:
            return
        if self.forge.call("GET", f"/repos/{q(self.owner)}/{q(repo)}/branches/{q(head, safe='')}")[0] != 404:
            self.update_behind(repo, branch, head)
            return
        self.changes += 1
        print(f"{repo}: pull request updating {answers.get('_commit')} -> {latest}")
        if not self.apply:
            return
        env = self.git_env()
        with tempfile.TemporaryDirectory() as tmp:
            url = f"{self.server}/{q(self.owner)}/{q(repo)}.git"

            def git(*args):
                subprocess.run(["git", "-C", tmp, *args], check=True, env=env)

            subprocess.run(["git", "clone", "--quiet", "--branch", branch, url, tmp], check=True, env=env)
            git("checkout", "--quiet", "-b", head)
            subprocess.run([copier, "update", "--defaults", "--vcs-ref", latest, "--conflict", "inline"],
                           cwd=tmp, check=True, env=env)
            git("add", "-A")
            conflicts = subprocess.run(["git", "-C", tmp, "grep", "-l", "--cached", "-e", "^<<<<<<< "],
                                       capture_output=True, text=True, env=env).stdout.split()
            git("commit", "--quiet", "-m", f"Update to {TEMPLATE_REPO} {latest}")
            git("push", "--quiet", "origin", head)
        title = f"Update to {TEMPLATE_REPO} {latest}"
        body = (f"`copier update` from {answers.get('_commit')} to {latest}: the files "
                f"{TEMPLATE_REPO} manages, merged with this repository's own lines.\n\n"
                "CI runs the repository's `scripts/check.sh` on it.")
        if conflicts:
            title = "[conflicts] " + title
            body += "\n\n**Merge conflicts** to resolve by hand in: " + ", ".join(f"`{c}`" for c in conflicts)
        _, pr = self.forge.call("POST", f"/repos/{q(self.owner)}/{q(repo)}/pulls",
                                {"head": head, "base": branch, "title": title, "body": body})
        labels = {label["name"]: label["id"] for label in
                  self.forge.pages(f"/repos/{q(self.owner)}/{q(repo)}/labels")}
        if pr and "template" in labels:
            self.forge.call("POST", f"/repos/{q(self.owner)}/{q(repo)}/issues/{pr['number']}/labels",
                            {"labels": [labels["template"]]})

    def latest_tag(self):
        tags = [t["name"] for t in self.forge.pages(f"/repos/{q(self.owner)}/{TEMPLATE_REPO}/tags")]
        tags = [t for t in tags if TAG.match(t)]
        return max(tags, key=lambda t: tuple(map(int, TAG.match(t).groups())), default=None)

    def run(self, only, copier):
        latest = self.latest_tag()
        print(f"{TEMPLATE_REPO}: newest tag {latest}")
        for repo in self.forge.pages("/repos/search?q="):
            name = repo["name"]
            if repo["owner"]["login"].lower() != self.owner.lower() or repo["archived"] \
                    or repo["mirror"] or repo["empty"] or (only and name not in only):
                continue
            answers_text = self.forge.file(self.owner, name, ".copier-answers.yml")
            answers = parse_answers(answers_text) if answers_text else {}
            if answers.get("_src_path") == TEMPLATE_ALIAS:
                branch = repo["default_branch"]
                self.settings(name, repo)
                self.description(name, repo, answers)
                if repo.get("has_actions"):
                    self.protection(name, branch)
                else:
                    # Nothing on the forge would ever report the required check.
                    print(f"{name}: Actions off, so no required check on {branch}")
                self.collaborators(name)
                self.template_update(name, branch, answers, latest, copier)
            if self.forge.call("GET", f"/repos/{q(self.owner)}/{q(name)}/contents/renovate.json")[0] != 404:
                self.labels(name)
        print(f"{self.changes} change(s){'' if self.apply else ' planned; --apply makes them'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="make the changes")
    parser.add_argument("--config", default="forge.toml")
    parser.add_argument("--copier", default=".venv/bin/copier")
    parser.add_argument("repos", nargs="*", help="only these repositories")
    args = parser.parse_args()

    config = load_config(args.config)
    print(f"{args.config}: OK")
    token = os.environ.get("SYNC_TOKEN")
    if not token:
        if args.apply:
            sys.exit("SYNC_TOKEN is not set")
        print("No SYNC_TOKEN: checked the file only.")
        return
    owner = os.environ["GITHUB_REPOSITORY_OWNER"]
    Sync(Forge(os.environ["GITHUB_API_URL"], token), owner, os.environ["GITHUB_SERVER_URL"],
         token, config, args.apply).run(set(args.repos), os.path.abspath(args.copier))


if __name__ == "__main__":
    main()
