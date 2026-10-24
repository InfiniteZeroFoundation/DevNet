---
name: din-push-develop
description: Use whenever an admin pushes directly to `develop` on InfiniteZeroFoundation/DevNet — "push to develop", "push it", "go ahead and push" after a path-B merge/commit on develop (din-pr-merge B7) or an emergency fix. The `develop` ruleset blocks direct pushes for everyone except the admin bypass (Developer/MAINTAINING.md No. 4.4), so non-admins merge through PRs instead (din-pr-merge path A). Runs a local mirror of CI on the exact commit being pushed (in a dedicated worktree, empty HOME like the runner), pushes only if it's green, logs the bypass reason in Discussion 170, then watches the GitHub Actions `push` run in the background and alerts the operator if it goes red or never starts. A PreToolUse hook blocks raw `git push` to develop so this skill is the only path. Not for pushing feature/PR branches, and never a substitute for the operator's go-ahead to push.
---

# Push to develop, CI-checked

Normal merges land through a PR (`din-pr-merge` path A), where the `develop` ruleset requires an approval, `CI OK` and an up-to-date branch. A direct push skips all of that, so it's reserved for admins using the bypass: path-B local merges and emergency fixes (Developer/MAINTAINING.md No. 4.4). This skill puts the missing checks back around such a push: a local CI mirror before it, and a watch on the GitHub `push` run after it.

The rule ([Developer/MAINTAINING.md](../../../Developer/MAINTAINING.md) No. 4.6, [discussion No. 170](https://github.com/InfiniteZeroFoundation/DevNet/discussions/170)): whoever pushes or merges owns that push's CI run and makes sure it's fixed the same working day. If a red run is left unaddressed for ~6h and more commits land on top, the other maintainers open an incident thread in No. 170.

"The operator" means the maintainer running the skill (the active `gh` user). Setup: [`README.md`](README.md) and [`.claude/scripts/README.md`](../../scripts/README.md).

## 0. Gate

- **Admins only.** `python3 .claude/scripts/din_peer_check.py admin`. `REFUSE` → don't push; open a PR and use `din-pr-merge` path A.
  A path B merge push also needs `python3 .claude/scripts/din_peer_check.py path-b` (path B is Umer only, MAINTAINING No. 4.4); other admins push directly only for emergencies.
- **Only run this after the operator has said to push.** Invoking the skill is not permission to push; the "wait for review before commit/push" rule still applies. If the push request came from a flow like din-pr-merge, make sure the file-by-file review already happened.
- **Every bypass gets a reason.** Before pushing, have a one-line reason ready (e.g. "path B merge of PR No. N: ABI regeneration against moved develop", "emergency fix for red develop at <sha>"). Step 2 logs it in Discussion 170.
- Confirm you are pushing `develop` → `origin/develop` from `$DIN_REPO`, and that it is a fast-forward:
  ```bash
  source .claude/scripts/din-env.sh
  cd "$DIN_REPO" && git fetch -q origin develop
  git branch --show-current                                  # must be develop
  git merge-base --is-ancestor origin/develop develop && echo ff-ok
  git log --oneline origin/develop..develop                  # exactly what will land
  ```
  If it's not a fast-forward (someone pushed in between), stop and ask the operator. Never force-push develop (the ruleset blocks it anyway).
- Uncommitted WIP in the main checkout is normal here and is **not** pushed. The precheck runs on the commit, not the working tree.

## 1. Local CI mirror on the exact commit

```bash
bash .claude/skills/din-push-develop/scripts/precheck.sh            # HEAD of develop
bash .claude/skills/din-push-develop/scripts/precheck.sh --all      # force the Solidity job too
```

What it does:
- Checks out the commit in a reusable detached worktree, `$DIN_WORK/push-check`, and mirrors `.github/workflows/ci.yml`:
  - **Docs:** `check_doc_links.py Documentation`
  - **Python:** `$DIN_PY -m pytest -m "not integration"` with an **empty HOME**, so tests that read `~/.config/dincli` fail here the way they fail on the runner
  - **Solidity:** only if `foundry/`, `hardhat/` or `.github/` changed. Uses the **real `via_ir` profile** and the contract size gate, as CI does.
- The log goes to `$DIN_WORK/push-check-logs/<sha>.log`.
- Ruff and forge lint are advisory in CI, so they are skipped here.

Run it with `run_in_background` when the Solidity job is included (it takes several minutes).

**If it fails:** don't push. Report the failing step and the key error lines to the operator, and propose a fix commit. Don't create one without their go-ahead.

## 2. Push, and log the bypass

```bash
cd "$DIN_REPO" && DIN_PUSH_DEVELOP=1 git push origin develop
SHA=$(git rev-parse develop)
```

The `DIN_PUSH_DEVELOP=1` prefix is what lets the guard hook (below) pass. Only use it from this step.

Then post the reason as a one-line comment in [Discussion 170](https://github.com/InfiniteZeroFoundation/DevNet/discussions/170): `Admin bypass: <short sha> — <reason>.` Use `gh api graphql` `addDiscussionComment` with `-F body=@<file>`, and re-fetch to check it posted.

## 3. Watch the GitHub push run in the background

First check that the trigger exists on develop. If PR 168 isn't merged yet, there is no push run to wait for:

```bash
git show origin/develop:.github/workflows/ci.yml | grep -qE '^  push:' && echo push-trigger-present
```

If it's present, start the watcher with Bash `run_in_background: true`:

```bash
bash .claude/skills/din-push-develop/scripts/watch-push-run.sh "$SHA"
```

Tell the operator in one line that the push landed and the run is being watched, then carry on with other work. You are re-invoked when the watcher exits. Its last line is one of:

| Last line | Meaning | Do |
|---|---|---|
| `RESULT success <url>` | green | One-line confirmation with the SHA and run URL. No notification. |
| `RESULT failure <url>` (or `cancelled`, `timed_out`) | red | **`PushNotification`**, e.g. `develop CI red on <short-sha>: Python test_x failed`. Then pull the failing job's log (`gh run view <id> --log-failed`, or `gh api .../actions/jobs/<job>/logs` if that's empty), name the failing step/test, and propose a fix commit. |
| `WATCH_ERROR <url> <status>` | the watcher couldn't read a final result (GitHub unreachable for ~10 min, or the run is still going after ~90 min). **Not a CI verdict.** | No notification. Check the run yourself (`gh run view <id> --json status,conclusion,jobs`), and re-run the watcher if it's still in progress. Then handle the real result as in the rows above. |
| `NO_RUN <sha>` | no push run started within ~5 min | **`PushNotification`**: `develop push <short-sha> has no CI run`. Check the Actions tab for a disabled workflow, a YAML error, or a runner outage. |

For red or missing runs, remind the operator of the clock: fix it the same working day (MAINTAINING No. 4.6); if it's not fixed within ~6h and more commits land on top, the other maintainers open a thread in discussion No. 170.

## Guard hook

`scripts/guard.py` is registered as a `PreToolUse` Bash hook in `.claude/settings.local.json`. It blocks any `git push` whose destination is `develop`, whether given explicitly, as `HEAD:develop`, or as a bare `git push` while on develop, unless the command carries `DIN_PUSH_DEVELOP=1`. If you get blocked, that's the signal to use this skill.

It only covers Claude's Bash tool. Pushes typed in your own terminal are unaffected (the GitHub ruleset still applies to them).

`settings.local.json` is untracked, so the hook has to be registered on each machine. If a push to develop is *not* blocked when it should be, the hook is missing: see [`README.md`](README.md) for the snippet and the machine-specific paths `precheck.sh` expects.
