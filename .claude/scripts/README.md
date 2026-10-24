# Shared scripts for the `din-*` skills

The `din-*` Claude Code skills under [`../skills/`](../skills/) implement the maintainer workflow in [`Developer/MAINTAINING.md`](../../Developer/MAINTAINING.md). Any maintainer can run them. These scripts hold the parts that every skill shares.

| File | What it does |
|---|---|
| [`din_peer_check.py`](din_peer_check.py) | The peer-rule check ([MAINTAINING No. 1](../../Developer/MAINTAINING.md#1-the-rule)). It refuses when the active `gh` user is the author, assignee, implementer or a co-author of the PR, issue or task. Every skill that approves, merges or closes runs it first. |
| [`din-maintainers.json`](din-maintainers.json) | Maps each person to their GitHub logins and display name. Logins listed together count as one person (Umer: `umeradl` + `umermjd11`). Add an entry when someone joins. |
| [`din-env.sh`](din-env.sh) | Machine-specific paths (`DIN_REPO`, `DIN_WORK`, `DIN_PY`, `DIN_NVM`). Source it. Override any value by exporting it first. |

## Setup (once per machine)

1. **`gh` logged in as yourself.** The skills act as whoever `gh api user` returns. They never switch accounts for you.
2. **Paths.** Check the defaults in [`din-env.sh`](din-env.sh). If yours differ, export your own values in your shell profile, for example:
   ```bash
   export DIN_REPO=~/code/DevNet
   export DIN_WORK=~/din-work
   export DIN_PY=~/venvs/din/bin/python
   ```
   `DIN_PY` needs Python 3.12, `torch`, and `pip install -e ".[test]"` of this repo.
3. **Tools.** `forge` on `PATH` at the version `ci.yml` pins (`FOUNDRY_VERSION`), and Node 20 (`npm`, `npx`).
4. **Optional: the push guard hook.** Only admins push to `develop` directly. If that's you, register the hook described in [`../skills/din-push-develop/README.md`](../skills/din-push-develop/README.md).

## Running the peer check by hand

```bash
python3 .claude/scripts/din_peer_check.py whoami
python3 .claude/scripts/din_peer_check.py pr 264              # before reviewing, approving or merging
python3 .claude/scripts/din_peer_check.py issue-approve 223   # before an approval verdict
python3 .claude/scripts/din_peer_check.py issue-close 227     # before closing as completed
python3 .claude/scripts/din_peer_check.py task Developer/tasks/task_240926_17.md
python3 .claude/scripts/din_peer_check.py admin               # the emergency bypass needs the admin role
python3 .claude/scripts/din_peer_check.py path-b              # merge path B: Umer only, plus the admin role
```

It exits with 0 when the action is OK, 1 when it's refused (the reasons are printed), and 2 on an error.

The check is deliberately conservative. For `issue-close`, everyone who worked on a merged PR that cross-references the issue counts as an implementer: its author and each commit's author, committer and `Co-Authored-By` co-authors. If a refusal looks wrong because the mention was incidental, hand the issue to a peer anyway. Don't work around the check.
