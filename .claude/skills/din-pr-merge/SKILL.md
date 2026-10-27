---
name: din-pr-merge
description: Use when actually merging a PR into InfiniteZeroFoundation/DevNet's `develop` — "merge PR #N", "merge this into develop", or any request to land a PR after it's been reviewed. Any maintainer who isn't the PR's author or a co-author can run it (checked first with `.claude/scripts/din_peer_check.py`). Path A (the default, per Developer/MAINTAINING.md No. 4.4): push any review fixes onto the PR branch, then merge on GitHub with a merge commit once the approval, `CI OK` and up-to-date gates pass. Path B (Umer only per MAINTAINING No. 4.4, exceptional): the local stash-merge-pop flow plus a deviation commit, pushed through `din-push-develop` with the admin bypass. Either way it ends with the merger watching `develop` CI and posting the outcome comment (`outcome-comment.md`). Runs after `din-pr-review`. Not for reviewing a PR (use `din-pr-review`) and not for generic git merges outside this repo's PR workflow.
---

# DIN DevNet PR merge

`din-pr-review` produces a verification comment, a merge-proposal table and a
GitHub review. This skill lands the PR on `develop` and posts the outcome
comment once it's real.

"The operator" means the maintainer running the skill (the active `gh` user).
The process is [`Developer/MAINTAINING.md`](../../../Developer/MAINTAINING.md);
setup is [`.claude/scripts/README.md`](../../scripts/README.md).

## Which path

| | Path A — GitHub-side merge commit | Path B — local merge + deviation commit |
|---|---|---|
| Who | Any maintainer who isn't the author or a co-author | Umer only (MAINTAINING No. 4.4; `din_peer_check.py path-b`) |
| When | The default, for every PR | Exceptional: the PR needs adapting against a `develop` that has moved (renames, ABI regeneration, docs drift) and pushing fixes onto the PR branch isn't practical |
| Fixes | Pushed onto the PR branch (or a small follow-up PR); the last-push rule sends the final approval to someone else | A separate deviation commit on top of the merge, on `develop` |
| Gate | The `develop` ruleset: 1 approval of the latest push, `CI OK`, branch up to date | The admin bypass; log a one-line reason in [Discussion 170](https://github.com/InfiniteZeroFoundation/DevNet/discussions/170) |

Use path A unless the operator explicitly chooses B and is Umer.

## 0. Hard rules — both paths

- **Peer check first.** `python3 .claude/scripts/din_peer_check.py pr <N>`.
  `REFUSE` → stop and name an eligible maintainer (MAINTAINING No. 1, No. 7).
  Never switch `gh` accounts to get past it.
- **Never commit, push or merge without the operator's go-ahead.** Invoking
  this skill is not that go-ahead. `gh pr merge` is a push to `develop`; treat
  it like one. A `git commit` on `develop` has been observed to appear pushed
  already — treat commit and push as one gated step.
- **Merge commits only.** Never squash or rebase (the ruleset refuses them
  anyway). Authorship and history must survive.
- **Attribution** (MAINTAINING No. 4.5). The PR author stays the commit author.
  Any commit the operator writes on someone else's work credits them with a
  `Co-Authored-By: <name> <email>` trailer taken from their real commits
  (`git log --format='%an <%ae>' -1 <their commit>`), never a guessed address.
  The operator's own identity comes from their `git config user.name` /
  `user.email`. Add the session's standard Claude attribution trailer.
- **Never fabricate a GitHub-assigned ID.** `git rev-parse` every SHA and fetch
  every URL that goes in the outcome comment.
- **`gh api` file-sourced comment bodies need `-F body=@<path>`, not `-f`.**
  Re-fetch after every post/PATCH and check the body, not just the exit status.
- **`git status --short` + `git diff --stat` repo-wide before posting** the
  outcome comment.
- **Never write `#N`** for the PR number in anything GitHub renders — write
  "PR No. `<N>`".

---

## Path A — GitHub-side merge commit (default)

### A1. Fixes, if the merge proposal has any

If every file's "Pending proposal" is `None`, skip to A2: the PR merges as-is
and its green `CI OK` is the build/test evidence (MAINTAINING No. 4.2).

Otherwise the fixes go **onto the PR branch**, not onto `develop`:

1. `merge-fix-comment-update <path>` for each file with a pending fix. In path
   A it works in the review worktree `$DIN_WORK/PRs/PRreview_<N>`.
2. `din-merge-build-test` once, in the same worktree. It runs the
   CI-equivalent build and tests on the fixed branch, so the PR doesn't go red
   in public, and fills in the comment rows.
3. Commit the fixes in the worktree (one commit, message naming the review
   items it closes; trailers per section 0), show the operator the diff, and on
   their go-ahead push to the PR's head branch:
   ```bash
   gh pr view <N> --json headRepositoryOwner,headRefName,maintainerCanModify
   git push <head-repo-url> HEAD:<headRefName>
   ```
   For a fork PR this needs `maintainerCanModify: true`. If it's false, don't
   push: ask the author to apply the fixes, or open a small follow-up PR
   against their branch.

**After pushing fixes, the operator can't approve or merge this PR.** They're a
co-author now, and the last-push rule hands the final approval to someone else
(MAINTAINING No. 7). Post a one-line comment saying what was pushed and who
should take the final approval, then stop. That person runs this skill from A2.

### A2. Check the gates

```bash
R=InfiniteZeroFoundation/DevNet
gh pr view <N> -R $R --json headRefOid,mergeStateStatus,reviewDecision,isDraft,reviews \
  --jq '{head: .headRefOid, state: .mergeStateStatus, decision: .reviewDecision, draft: .isDraft,
         approvals: [.reviews[] | select(.state=="APPROVED") | {by: .author.login, at: .commit.oid}]}'
gh pr checks <N> -R $R
```

All of these must hold:

- `isDraft` is false.
- An approval from an eligible peer is **on the current head SHA**.
- `CI OK` is green on that head.
- `mergeStateStatus` is `CLEAN`. `BEHIND` means the branch isn't up to date:
  ask the author to update it, or run `gh pr update-branch <N>`. Updating it
  makes the operator the last pusher, so the approval then has to come from
  someone else.
- **`foundry/src/**` touched?** The second sign-off (MAINTAINING No. 4.2) is
  on the PR, as an approval or a comment from @umeradl, @abrahamnash or a
  security reviewer they named.
- **Mechanism change?** The mechanism sign-off is on the PR (MAINTAINING No. 4.2).
- No unresolved "Changes requested" from anyone (MAINTAINING No. 7).

If any gate fails, report which one and stop. Don't use `--admin`.

### A3. Merge

On the operator's go-ahead:

```bash
gh pr merge <N> -R $R --merge
gh pr view <N> -R $R --json state,mergedAt,mergeCommit --jq '{state, mergedAt, sha: .mergeCommit.oid}'
```

Then the outcome steps: **C1–C2** below.

---

## Path B — local merge + deviation commit (Umer only)

```bash
python3 .claude/scripts/din_peer_check.py path-b  # REFUSE → use path A
source .claude/scripts/din-env.sh
cd "$DIN_REPO"
```

Path B lands the PR in the `develop` checkout, which routinely has unrelated
uncommitted WIP. The flow never merges into a dirty tree and never lets that
WIP ride along inside the merge commit: it stashes it, merges cleanly, pops it
back, and treats whatever breaks as a separate, separately described deviation.

In path B, `merge-fix-comment-update` and `din-merge-build-test` run against the
`develop` checkout instead of the review worktree (each skill's "Path B" notes).

### B1. Baseline: confirm the checkout builds and tests pass before touching anything

Run against the current `develop` HEAD, dirty tree and all. This is the control
measurement. If it's already red, stop and tell the operator; don't let a
pre-existing failure get attributed to the PR later.

```bash
cd foundry && npm ci   # populate node_modules before any forge test (see root CLAUDE.md)
forge build && forge test   # real via_ir profile; the plain build no longer compiles develop
cd .. && "$DIN_PY" -m pytest -m "not integration"
```

Don't edit `foundry.toml`.

### B2. Stash whatever is currently dirty

```bash
git status --short
git stash push -u -m "pre-merge-pr-<N>"   # only if the tree is dirty; -u for untracked
```

If `git status --short` is empty, skip the stash.

### B3. Merge the PR into develop

```bash
gh pr view <N> --json mergeable,mergeStateStatus
git fetch origin refs/pull/<N>/head
git merge-tree --write-tree --name-only develop FETCH_HEAD   # exit 0 = clean
git merge --no-ff --no-commit FETCH_HEAD                    # stage only; resolve any conflicts
git diff --cached --stat
```

**Stop here.** Summarize the staged merge file-by-file (conflicts and how they
were resolved) and wait for the operator's go-ahead. Then commit with the
contributor's real `--author` and a
`merge: PR No. <N> (<owner>/<branch>) into develop` message, and capture the
SHA with `git rev-parse HEAD` immediately.

If the operator wants changes first, `git merge --abort` returns `develop` to
its pre-merge state.

### B4. Pop the stash

```bash
git stash pop
```

- **Conflict markers from the pop** — resolve these first; they're mechanical.
- **Silent deviations** — code that applies cleanly but is now wrong because
  the PR changed something the WIP depended on. Find them by re-running the
  build/tests (B5), not by re-reading the diff.

### B5. Rebuild and retest against the combined state

Same commands as B1. Anything newly broken is a deviation to fix, not a PR
defect — the PR already passed review.

### B6. Commit the deviations

Show the operator the deviation diff, and on their go-ahead commit it as its
own commit — never amend the merge commit:

```bash
git add <specific files>   # never -A; review `git status` first
git commit -m "$(cat <<'EOF'
<what changed and why — the develop-drift root cause, not just "fix">

Co-Authored-By: <PR author name> <their email from their commits>
<the session's standard Claude attribution trailer>
EOF
)"
git rev-parse HEAD
```

If B4/B5 needed no fixes, there's no deviation commit — say so explicitly in
the outcome comment.

### B7. Push

Summarize file-by-file (merge commit + deviation commit) and wait. Push only
on the operator's go-ahead, and only via `din-push-develop` (which uses the
admin bypass and logs the reason in Discussion 170). Then C1–C2.

---

## C1. Own the `develop` CI run (both paths)

The merger owns the CI run for the push to `develop` (MAINTAINING No. 4.6):

```bash
bash .claude/skills/din-push-develop/scripts/watch-push-run.sh <merge sha>   # Bash run_in_background: true
```

`din-push-develop` already does this for path B. If it goes red: ping the PR
author first; if they can't fix it the same working day, the operator fixes it
on top (through a PR) or reverts it (MAINTAINING No. 4.7), and logs it in
Discussion 170.

## C2. Post the outcome comment

Use [`../din-pr-review/templates/outcome-comment.md`](../din-pr-review/templates/outcome-comment.md):

- The real merge-commit SHA, plus any fix or deviation commit SHAs (fetched,
  never fabricated), linked to their GitHub commit URLs.
- `gh pr view <N> --json state,mergedAt` showing **MERGED**.
- What deviated from the PR as opened: path A's fix commits on the branch, or
  path B's deviation commit, with the root cause.
- Final build/test evidence: the PR's green `CI OK` run (path A), or B5's
  numbers (path B), plus the `develop` push run from C1.
- Fill each file's "Actual merge proposal" row in the merge-proposal comment if
  `din-merge-build-test` didn't already. It's the merger's field.
- Set the label: `merged` (path A) or `Merged Locally` (path B).

Post via `gh api ... -F body=@<path>` (capital `-F`), then re-fetch and check
the body matches.
