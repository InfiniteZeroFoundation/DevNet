#!/usr/bin/env python3
"""Peer-rule check for the din-* skills (Developer/MAINTAINING.md No. 1).

Nobody approves, merges or closes their own work. Every din-* skill that
approves, merges or closes runs this first, as the active `gh` user, and stops
if it prints REFUSE.

Usage:
  din_peer_check.py whoami              print the active gh login and person name
  din_peer_check.py pr <N>              may I review / approve / merge PR <N>?
  din_peer_check.py issue-approve <N>   may I approve issue <N>'s plan?
  din_peer_check.py issue-close <N>     may I close issue <N> as completed?
  din_peer_check.py task <task-file>    may I close this task's Discussion?
  din_peer_check.py admin               do I hold the repo admin role (emergency bypass)?
  din_peer_check.py path-b              may I use merge path B? (Umer only, plus the admin role)

Exit status: 0 = OK, 1 = REFUSE (reasons printed), 2 = error.

One person can have several GitHub logins (Umer: umeradl + umermjd11). Those
are listed in din-maintainers.json next to this script and count as the same
person, so umeradl can't approve a umermjd11 PR.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

CONFIG = json.loads((Path(__file__).with_name("din-maintainers.json")).read_text())
REPO = CONFIG["repo"]
PEOPLE = CONFIG["people"]
BOTS = {"web-flow", "github-actions[bot]", "dependabot[bot]", "Copilot", "claude"}


def gh(*args):
    out = subprocess.run(["gh", *args], capture_output=True, text=True)
    if out.returncode != 0:
        print(f"ERROR: gh {' '.join(args)}: {out.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return out.stdout


def gh_json(*args):
    return json.loads(gh(*args) or "null")


def gh_list(endpoint):
    """Every item of a paginated list endpoint (works on gh versions without --slurp)."""
    out = gh("api", "--paginate", endpoint, "--jq", ".[]")
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def person(ident):
    """Canonical person key for a login or display name; unknown idents map to themselves."""
    key = (ident or "").strip().lower()
    for p in PEOPLE:
        if key == p["name"].lower() or key in (l.lower() for l in p["logins"]):
            return p["name"]
    return ident.strip()


def from_email(email):
    m = re.match(r"^(?:\d+\+)?([^@]+)@users\.noreply\.github\.com$", email or "", re.I)
    return m.group(1) if m else None


def co_authors(message):
    found = []
    for name, email in re.findall(r"^co-authored-by:\s*(.+?)\s*<([^>]*)>", message, re.I | re.M):
        if email.lower() == "noreply@anthropic.com":  # AI-attribution trailer, not a person
            continue
        login = from_email(email)
        found.append(login or name)
    return found


def me():
    return gh("api", "user", "--jq", ".login").strip()


def verdict(actor, involved, what):
    """involved: {person: [reasons]}"""
    mine = person(actor)
    hits = involved.get(mine, [])
    if hits:
        print(f"REFUSE: {actor} ({mine}) can't {what}: {'; '.join(sorted(set(hits)))}.")
        print("Hand it to a peer (Developer/MAINTAINING.md No. 1, No. 7).")
        return 1
    others = ", ".join(sorted(involved)) or "nobody"
    print(f"OK: {actor} ({mine}) may {what}. Involved: {others}.")
    return 0


def add(involved, ident, reason):
    if ident and ident not in BOTS:
        involved.setdefault(person(ident), []).append(reason)


def pr_contributors(involved, n, author, suffix=""):
    """Add PR <n>'s author and every commit author, committer and co-author."""
    add(involved, author, f"author of PR No. {n}")
    for c in gh_list(f"repos/{REPO}/pulls/{n}/commits"):
        sha = c["sha"][:7]
        if c.get("author"):
            add(involved, c["author"]["login"], f"authored commit {sha}{suffix}")
        else:
            add(involved, c["commit"]["author"]["name"], f"authored commit {sha}{suffix}")
        if c.get("committer"):
            add(involved, c["committer"]["login"], f"committed {sha}{suffix}")
        for ca in co_authors(c["commit"]["message"]):
            add(involved, ca, f"co-author on {sha}{suffix}")


def check_pr(n):
    actor = me()
    pr = gh_json("api", f"repos/{REPO}/pulls/{n}")
    involved = {}
    pr_contributors(involved, n, pr["user"]["login"])
    return verdict(actor, involved, f"review, approve or merge PR No. {n}")


def issue_people(n, closing):
    issue = gh_json("api", f"repos/{REPO}/issues/{n}")
    if issue.get("pull_request"):
        print(f"ERROR: No. {n} is a PR; use `pr {n}`.", file=sys.stderr)
        sys.exit(2)
    involved = {}
    if not closing:
        add(involved, issue["user"]["login"], f"opened issue No. {n}")
    for a in issue.get("assignees") or []:
        add(involved, a["login"], f"assigned to issue No. {n}")
    if closing:
        for e in gh_list(f"repos/{REPO}/issues/{n}/timeline"):
            src = (e.get("source") or {}).get("issue") or {}
            if e.get("event") == "cross-referenced" and (src.get("pull_request") or {}).get("merged_at"):
                m = src["number"]
                pr_contributors(involved, m, src["user"]["login"], f" of merged PR No. {m}")
    return involved


def check_issue(n, closing):
    actor = me()
    what = f"close issue No. {n} as completed" if closing else f"approve issue No. {n}"
    return verdict(actor, issue_people(n, closing), what)


def check_task(path):
    actor = me()
    text = Path(path).read_text()
    m = re.search(r"^\*\*Assigned to:\*\*\s*(.+)$", text, re.M)
    if not m:
        print(f"ERROR: no '**Assigned to:**' line in {path}", file=sys.stderr)
        return 2
    line = m.group(1)
    involved = {}
    handles = re.findall(r"@([A-Za-z0-9-]+)", line)
    for h in handles:
        add(involved, h, f"assigned to {Path(path).name}")
    if not handles:
        for name in re.split(r",| and |/", re.sub(r"\(.*?\)", "", line)):
            if name.strip():
                add(involved, name.strip(), f"assigned to {Path(path).name}")
    return verdict(actor, involved, f"close {Path(path).name}")


def check_admin():
    actor = me()
    role = gh("api", f"repos/{REPO}/collaborators/{actor}/permission", "--jq", ".role_name").strip()
    if role == "admin":
        print(f"OK: {actor} holds the admin role (emergency bypass allowed).")
        return 0
    print(f"REFUSE: {actor} has '{role}', not admin. Use merge path A (Developer/MAINTAINING.md No. 4.4).")
    return 1


def check_path_b():
    """Merge path B is Umer only (MAINTAINING No. 4.4), and needs the admin bypass."""
    actor = me()
    if person(actor) not in CONFIG["path_b"]:
        print(f"REFUSE: {actor} ({person(actor)}) can't use merge path B; it's reserved for "
              f"{', '.join(CONFIG['path_b'])} (Developer/MAINTAINING.md No. 4.4). Use path A.")
        return 1
    return check_admin()


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "whoami":
        actor = me()
        print(f"{actor} ({person(actor)})")
        return 0
    if cmd == "admin":
        return check_admin()
    if cmd == "path-b":
        return check_path_b()
    if not rest:
        print(__doc__)
        return 2
    if cmd == "pr":
        return check_pr(int(rest[0]))
    if cmd in ("issue-approve", "issue-close"):
        return check_issue(int(rest[0]), cmd == "issue-close")
    if cmd == "task":
        return check_task(rest[0])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
