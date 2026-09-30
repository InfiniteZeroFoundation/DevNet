# din-push-develop

A Claude Code skill for pushing to `develop` with CI checks before and after the push. It runs a local copy of CI on the exact commit, pushes only if that's green, then watches the GitHub `push` run and alerts if it goes red or never starts.

The instructions Claude follows are in [`SKILL.md`](SKILL.md). This README covers setup: what you need on your machine to use it.

Background: [PR No. 168](https://github.com/InfiniteZeroFoundation/DevNet/pull/168) added the `push` trigger to CI. [Discussion No. 170](https://github.com/InfiniteZeroFoundation/DevNet/discussions/170) is the incident log and backup-maintainer rota for red or missing `develop` runs.

## Files

| File | What it does |
|---|---|
| [`SKILL.md`](SKILL.md) | The skill: gate → local precheck → push → background watch → alert |
| [`scripts/precheck.sh`](scripts/precheck.sh) | Mirrors `.github/workflows/ci.yml` on a given commit in a separate worktree, with an empty `HOME` |
| [`scripts/watch-push-run.sh`](scripts/watch-push-run.sh) | Waits for the GitHub `push` run of a SHA; last line is `RESULT <conclusion> <url>` or `NO_RUN <sha>` |
| [`scripts/guard.py`](scripts/guard.py) | `PreToolUse` hook that blocks Claude from a raw `git push` to `develop` |

## Setup

### 1. Register the guard hook (per machine, not committed)

The skill is committed and loads automatically. The **hook is not**: it lives in `.claude/settings.local.json`, which is untracked. Without it the skill still works, but Claude can push to `develop` without going through it.

Add this under `"hooks"` in `.claude/settings.local.json`, and create the file if it doesn't exist:

```json
"PreToolUse": [
  {
    "matcher": "Bash",
    "hooks": [
      {
        "type": "command",
        "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/skills/din-push-develop/scripts/guard.py\"",
        "timeout": 10
      }
    ]
  }
]
```

To check it's active, ask Claude to run `git push --dry-run origin develop`. It should be blocked with *"pushes to develop go through the din-push-develop skill"*.

It only affects Claude's Bash tool. Pushes you type in your own terminal are never blocked.

### 2. Adjust machine-specific paths

`precheck.sh` hard-codes paths from the maintainer's machine. Change them at the top of the script if yours differ:

| Variable / path | Default | Needs |
|---|---|---|
| `REPO` | `~/projects/devnet` | the main checkout |
| `WT` | `~/tempdir/DIN/push-check` | reusable detached worktree (created on first run) |
| `PY` | `~/my_venvs/torchenv/bin/python` | a Python 3.12 venv with `torch` and `pip install -e ".[test]"` |
| logs | `~/tempdir/DIN/push-check-logs/<sha>.log` | full output of each precheck |
| `~/.nvm/nvm.sh` | sourced for the Solidity job | Node 20 (`npm`, `npx`) |

You also need `forge` on `PATH` (the version CI pins is `FOUNDRY_VERSION` in `ci.yml`) and an authenticated `gh` for the watcher.

## Running the scripts by hand

```bash
bash .claude/skills/din-push-develop/scripts/precheck.sh              # HEAD
bash .claude/skills/din-push-develop/scripts/precheck.sh --all <sha>  # force the Solidity job
bash .claude/skills/din-push-develop/scripts/watch-push-run.sh <sha>  # after a push
```

- `precheck.sh` exits non-zero on the first failing step and prints the tail of its log.
- The Solidity job, with its real `via_ir` build, takes several minutes. Docs + Python take about 1–3.

## Known limits

- **Ruff and forge lint are skipped.** They are advisory (`continue-on-error`) in CI too.
- **The precheck only predicts CI.** Runner-only failures (network, action versions, caching) still show up only in the watched GitHub run.
- **The Solidity job runs only for some changes.** It's skipped unless `foundry/`, `hardhat/` or `.github/` changed; use `--all` when in doubt.
