---
name: din-push-develop
description: Use whenever Umer says to push to `develop` on InfiniteZeroFoundation/DevNet — "push to develop", "push it", "go ahead and push" after a merge/commit on develop, or the push step at the end of din-pr-merge. Runs a local mirror of CI on the exact commit being pushed (in a dedicated worktree, empty HOME like the runner), pushes only if it's green, then watches the GitHub Actions `push` run in the background and alerts Umer if it goes red or never starts. A PreToolUse hook blocks raw `git push` to develop so this skill is the only path. Not for pushing feature/PR branches, and never a substitute for Umer's go-ahead to push.
---

# Push to develop, CI-checked

`develop` has two gaps this skill closes:
- Most merges land by local merge + direct push, and admins bypass the required `CI OK` check.
- Until PR No. 168, pushes had no CI run at all.

The rule (PR 168 action item 2, [discussion No. 170](https://github.com/InfiniteZeroFoundation/DevNet/discussions/170)): Umer makes sure every `develop` push passes CI, or adds a fix commit on top. If a red run is left unaddressed for ~6h and more commits land on top, Santiago and Robbert open an incident thread in No. 170. This skill is how Umer keeps his half of that rule.

## 0. Gate

- **Only run this after Umer has said to push.** Invoking the skill is not permission to push; the "wait for review before commit/push" rule still applies. If the push request came from a flow like din-pr-merge, make sure the file-by-file review already happened.
- Confirm you are pushing `develop` → `origin/develop` from `~/projects/devnet`, and that it is a fast-forward:
  ```bash
  cd ~/projects/devnet && git fetch -q origin develop
  git branch --show-current                                  # must be develop
  git merge-base --is-ancestor origin/develop develop && echo ff-ok
  git log --oneline origin/develop..develop                  # exactly what will land
  ```
  If it's not a fast-forward (someone pushed in between), stop and ask Umer. Never force-push develop.
- Uncommitted WIP in the main checkout is normal here and is **not** pushed. The precheck runs on the commit, not the working tree.

## 1. Local CI mirror on the exact commit

```bash
bash .claude/skills/din-push-develop/scripts/precheck.sh            # HEAD of develop
bash .claude/skills/din-push-develop/scripts/precheck.sh --all      # force the Solidity job too
```

What it does:
- Checks out the commit in a reusable detached worktree, `~/tempdir/DIN/push-check`, and mirrors `.github/workflows/ci.yml`:
  - **Docs:** `check_doc_links.py Documentation`
  - **Python:** `python -m pytest -m "not integration"` with an **empty HOME** (torchenv), so tests that read `~/.config/dincli` fail here the way they fail on the runner
  - **Solidity:** only if `foundry/`, `hardhat/` or `.github/` changed. Uses the **real `via_ir` profile**, not the fast review path, because the goal is to predict CI exactly.
- The log goes to `~/tempdir/DIN/push-check-logs/<sha>.log`.
- Ruff and forge lint are advisory in CI, so they are skipped here.

Run it with `run_in_background` when the Solidity job is included (it takes several minutes).

**If it fails:** don't push. Report the failing step and the key error lines to Umer, and propose a fix commit. Don't create one without his go-ahead.

## 2. Push

```bash
cd ~/projects/devnet && DIN_PUSH_DEVELOP=1 git push origin develop
SHA=$(git rev-parse develop)
```

The `DIN_PUSH_DEVELOP=1` prefix is what lets the guard hook (below) pass. Only use it from this step.

## 3. Watch the GitHub push run in the background

First check that the trigger exists on develop. If PR 168 isn't merged yet, there is no push run to wait for:

```bash
git show origin/develop:.github/workflows/ci.yml | grep -qE '^  push:' && echo push-trigger-present
```

If it's present, start the watcher with Bash `run_in_background: true`:

```bash
bash .claude/skills/din-push-develop/scripts/watch-push-run.sh "$SHA"
```

Tell Umer in one line that the push landed and the run is being watched, then carry on with other work. You are re-invoked when the watcher exits. Its last line is one of:

| Last line | Meaning | Do |
|---|---|---|
| `RESULT success <url>` | green | One-line confirmation with the SHA and run URL. No notification. |
| `RESULT failure <url>` (or `cancelled`, `timed_out`) | red | **`PushNotification`**, e.g. `develop CI red on <short-sha>: Python test_x failed`. Then pull the failing job's log (`gh run view <id> --log-failed`, or `gh api .../actions/jobs/<job>/logs` if that's empty), name the failing step/test, and propose a fix commit. |
| `NO_RUN <sha>` | no push run started within ~5 min | **`PushNotification`**: `develop push <short-sha> has no CI run`. Check the Actions tab for a disabled workflow, a YAML error, or a runner outage. |

For red or missing runs, remind Umer of the clock: if it's not fixed within ~6h and more commits land on top, the backup maintainers will open a thread in discussion No. 170.

## Guard hook

`scripts/guard.py` is registered as a `PreToolUse` Bash hook in `.claude/settings.local.json`. It blocks any `git push` whose destination is `develop`, whether given explicitly, as `HEAD:develop`, or as a bare `git push` while on develop, unless the command carries `DIN_PUSH_DEVELOP=1`. If you get blocked, that's the signal to use this skill.

It only covers Claude's Bash tool. Umer's own terminal pushes are unaffected.

`settings.local.json` is untracked, so the hook has to be registered on each machine. If a push to develop is *not* blocked when it should be, the hook is missing: see [`README.md`](README.md) for the snippet and the machine-specific paths `precheck.sh` expects.
