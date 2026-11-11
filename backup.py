#!/usr/bin/env python3
"""github-repo-backup: mirror-clone all your GitHub repositories."""
import argparse
import base64
import fnmatch
import json
import os
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

API = "https://api.github.com"


def api_get(url, token):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-repo-backup",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def list_repos(token, org=None):
    repos, page = [], 1
    while True:
        if org:
            url = f"{API}/orgs/{org}/repos?type=all&per_page=100&page={page}"
        else:
            url = f"{API}/user/repos?affiliation=owner&per_page=100&page={page}"
        batch = api_get(url, token)
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return repos


def matches(name, patterns):
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def git(args, token, cwd=None):
    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    cmd = ["git", "-c", f"http.extraheader=Authorization: Basic {auth}"] + args
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def backup_repo(repo, dest, token, archive):
    target = dest / f"{repo['name']}.git"
    if target.exists():
        res = git(["remote", "update", "--prune"], token, cwd=target)
        action = "updated"
    else:
        res = git(["clone", "--mirror", repo["clone_url"], str(target)], token)
        action = "cloned"
    if res.returncode != 0:
        print(f"  FAILED: {res.stderr.strip().splitlines()[-1] if res.stderr.strip() else 'unknown error'}")
        return False
    if archive:
        with tarfile.open(dest / f"{repo['name']}.tar.gz", "w:gz") as tar:
            tar.add(target, arcname=target.name)
    print(f"  {action}")
    return True


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dest", default="backups")
    p.add_argument("--org")
    p.add_argument("--skip-forks", action="store_true")
    p.add_argument("--skip-archived", action="store_true")
    p.add_argument("--include", action="append", default=[])
    p.add_argument("--exclude", action="append", default=[])
    p.add_argument("--archive", action="store_true")
    args = p.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Set the GITHUB_TOKEN environment variable.", file=sys.stderr)
        return 2

    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    repos = list_repos(token, args.org)
    selected = []
    for r in repos:
        if args.skip_forks and r["fork"]:
            continue
        if args.skip_archived and r["archived"]:
            continue
        if args.include and not matches(r["name"], args.include):
            continue
        if args.exclude and matches(r["name"], args.exclude):
            continue
        selected.append(r)

    print(f"Backing up {len(selected)} repo(s) to {dest.resolve()}")
    failed = 0
    for i, r in enumerate(selected, 1):
        print(f"[{i}/{len(selected)}] {r['full_name']}")
        if not backup_repo(r, dest, token, args.archive):
            failed += 1

    print(f"\nDone. {len(selected) - failed} ok, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
