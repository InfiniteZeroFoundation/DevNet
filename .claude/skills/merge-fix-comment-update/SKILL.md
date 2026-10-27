---
name: merge-fix-comment-update
description: Use per-file, after `din-pr-review` has posted its verification and merge-proposal comments for a PR — "merge and fix <path>", "apply the fix for <path>", "land <path> per the merge proposal". Input is one relative file path (e.g. `foundry/src/DinCoordinator.sol`); invoke it again for each other file. For that one file it applies the fix described in "Pending proposal" and records what it did in the PR's merge-fix log. Path A (default, any maintainer, Developer/MAINTAINING.md No. 4.4): the fix goes onto the PR branch in the review worktree, and `din-pr-merge` later pushes it onto the PR. Path B (Umer only): the PR's diff is applied into the `develop` checkout per "Recommended merge proposal", then the fix on top. Code changes only — it does NOT build, run forge/pytest, commit, or edit the GitHub comment; once every file is through, the operator runs `din-merge-build-test`, which builds/tests everything, fixes until green, and then updates the comment for all files. Stops and asks the operator whenever the row's proposal implies a decision, a conflict, or a judgment call — never guesses through those. Not for merging a whole PR at once (use `din-pr-merge`) and not for the initial review (use `din-pr-review`).
---

# Merge-fix-comment-update

`din-pr-review` produces a merge-proposal comment (Template 2) with one table
per changed file: what the diff does, a recommended merge proposal, and (for
files that need work) a pending proposal describing the fix. This skill does
the file-by-file follow-through on that table, one file per invocation: apply
its fix, log what was done — never a whole-PR merge, never more than the one
file passed in.

"The operator" means the maintainer running the skill (the active `gh` user).
The process is [`Developer/MAINTAINING.md`](../../../Developer/MAINTAINING.md);
setup is [`.claude/scripts/README.md`](../../scripts/README.md).

**This skill only changes code.** No `forge build`, no `forge test`, no
`pytest`, no commit, no comment PATCH. Building and testing per file wasted
minutes on every pass (a full `via_ir` build each time) and re-tested the same
tree over and over. The pipeline is:

1. `merge-fix-comment-update <path>` — once per file (this skill).
2. `din-merge-build-test` — once, after every file is through: full build +
   forge tests + pytest, fix whatever breaks until everything is green, then
   update "Actual merge proposal"/"Pending proposal" for all files in one
   comment edit.
3. `din-pr-merge` — the commit and push, after the operator reviews.

**Where the fix goes depends on the merge path** (MAINTAINING No. 4.4,
`din-pr-merge`):

| | Path A — default, any maintainer | Path B — Umer only |
|---|---|---|
| Target tree (`$TARGET`) | The review worktree `$DIN_WORK/PRs/PRreview_<N>`, on `pr-<N>-review` at the PR head | The `develop` checkout `$DIN_REPO` |
| The PR's own diff | Already there — skip step 3 | Applied file by file (step 3) |
| What happens next | `din-pr-merge` A1 commits the fixes and pushes them onto the PR branch; someone else then gives the final approval (the last-push rule) | `din-pr-merge` B lands the merge plus a deviation commit |

Path A is the default. Use B only if the operator says so and
`python3 .claude/scripts/din_peer_check.py admin` passes. Either way the
operator must first pass `python3 .claude/scripts/din_peer_check.py pr <N>`
(nobody fixes and lands their own PR).

## 0. Hard rules

- **Never commit or push.** This skill only ever leaves changes sitting
  uncommitted in `$TARGET`. Committing and pushing them is `din-pr-merge`'s
  job, after the operator has reviewed every file.
- **Never build or run test suites.** No `forge build`/`forge test`/
  `pytest`/`npx hardhat`. If you're tempted to "just quickly check it
  compiles", don't — that's `din-merge-build-test`'s job, and it will catch
  it. Reading code and grepping for call sites is fine and expected.
- **Never edit the GitHub comment.** Reading it is fine (step 2); writing it
  is `din-merge-build-test`'s job, done once for all files after tests pass.
- **Touch only the one file** (plus anything step 4's fix genuinely requires,
  e.g. a caller of a changed signature — and say so in the log). Don't
  pre-emptively fix other files from the same PR; they get their own pass.
- **When in doubt, stop and ask the operator** — this skill's whole point is
  to do the mechanical, unambiguous part of landing a fix and hand back
  control the moment a real decision shows up. See step 5 for what counts.

## 1. Establish context

You need: the PR number, the path (A or B), its review worktree
(`$DIN_WORK/PRs/PRreview_<N>`, created by `din-pr-review`), and the live
merge-proposal comment's id/URL. If any of these aren't already established in
the conversation, ask the operator rather than guessing which PR a bare file
path belongs to — the same path can appear in more than one open PR's review.

```bash
source .claude/scripts/din-env.sh
N=<N>
WT=$DIN_WORK/PRs/PRreview_$N
LOG=$DIN_WORK/PRs/PRreview_$N-merge-fix-log.md   # outside the worktree, so its git status stays clean
TARGET=$WT                                        # path A; for path B: TARGET=$DIN_REPO
cd "$WT" && git status   # confirm the worktree exists and is on pr-$N-review
```

**Path A: make sure the worktree is at the PR's current head** before fixing
anything, or the fix lands on a stale base and the push is rejected:

```bash
git fetch origin "pull/$N/head"
[ "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)" ] || echo "worktree is not at the PR head"
```

If it isn't, and the worktree has no uncommitted fixes yet,
`git reset --hard FETCH_HEAD`. If it already has fixes, stop and ask.

If `develop` has moved since the worktree was set up, re-verify mergeability
before trusting the diff (same check as `din-pr-review` step 1):

```bash
git fetch origin develop
git merge-tree --write-tree --name-only origin/develop pr-$N-review
gh pr view $N --json mergeable,mergeStateStatus
```

If local and GitHub disagree, or the file you're about to touch was hit by
develop's drift since the branch was cut (`git log --oneline <merge-base>..origin/develop -- <path>`),
stop and tell the operator before applying anything.

## 2. Read that file's row out of the live comment

Fetch the current comment body fresh (don't trust a copy from earlier in the
conversation — someone may have edited it since):

```bash
gh api repos/InfiniteZeroFoundation/DevNet/issues/comments/<comment-id> --jq .body > <scratchpad>/comment_live.md
```

Find the `#### \`<path>\`` block and read:
- **Change** — New or Modified (decides step 3's mechanism in path B).
- **Recommended merge proposal** — what should land.
- **Pending proposal** — the fix still to apply (or `None`).

## 3. Apply the file into `develop` (path B only)

Path A: skip this step. The PR's diff is already in the worktree.

**New file:** copy it from the worktree at the exact relative path:
```bash
cp "$WT/<path>" "$DIN_REPO/<path>"
```

**Modified file:** diff the file between the PR's merge-base and its head in
the worktree, then apply that diff to the `develop` checkout's current copy:
```bash
git -C "$WT" diff <merge-base> <pr-head> -- "<path>" > <scratchpad>/file.patch
cd "$DIN_REPO" && git apply --check <scratchpad>/file.patch && git apply <scratchpad>/file.patch
```
If `--check` fails, that's a real conflict — don't force it (`git apply -3`
or hand-resolution) without asking the operator first; this is exactly the
kind of thing step 5 exists for. If the row said "contingent on
`<other file>`'s fix landing first," confirm that other file's fix is actually
in the `develop` checkout already before applying this one — if it isn't, stop
and ask.

**Generated files** (e.g. `dincli/abis/*.json` where the row says
"regenerate from the merged build"): don't hand-edit or apply the PR's
version. Log it as **deferred to `din-merge-build-test`** — regenerating needs
a build, which this skill doesn't run. (Same in path A.)

## 4. Apply the fix from "Pending proposal"

If Pending proposal is `None`, skip to step 6 — "Recommended merge proposal"
already said "merged as-is" and there's nothing further to do.

Otherwise, apply exactly what the row describes, in `$TARGET`. This is real
code-review follow-through, not a mechanical patch — read the file, understand
the described defect (cross-reference the verification comment for the full
repro if the pending-proposal line is terse), and write the fix the way you
would for any other bug: matching the file's existing idiom, updating
affected natspec/docstrings, and checking for other call sites the fix's
signature or behavior change touches (grep the rest of `src/`/`script/`/
`test/`/`dincli/` for the changed symbol — don't assume the file is used in
isolation). If the fix calls for a new/updated test, write it now; it gets
run in `din-merge-build-test`.

Before finishing, eyeball the result: `git diff -- <path>` in `$TARGET`, and
`git status --short` repo-wide to confirm nothing else changed unexpectedly.

## 5. Stop and ask the operator whenever —

- The diff doesn't apply cleanly, or develop's drift since the branch was cut
  touched this same file in a way that changes what "the fix" should even do.
- The pending-proposal text names a design trade-off rather than a concrete
  fix (e.g. "coordinate merge order across PRs", "union of both sides" where
  the union isn't mechanical, "decide whether to fold X in or track
  separately", anything requiring a call on tokenomics/fee parameters). That's
  asking for a decision — a mechanism one needs the mechanism sign-off
  (MAINTAINING No. 4.2) — not describing a fix to apply.
- The fix changes a public function's signature or removes/renames state that
  other files reference — confirm the blast radius is actually contained
  before treating it as done.
- Anything about the fix feels underspecified enough that two reasonable
  people could implement it differently — say what the options are and let
  the operator pick, don't silently choose one.
- Path A and the fix is substantial: pushing it makes the operator a co-author
  (MAINTAINING No. 7). Ask whether to push it onto the PR, ask the author to
  make it, or open a follow-up PR instead.

## 6. Append to the merge-fix log

`din-merge-build-test` writes the comment from this log, so it must say what
actually happened, per file. Append (create the file on first use, with a
`# PR <N> merge-fix log` header, the path (A or B), the comment URL and the PR
head SHA):

```markdown
## `<path>`
- Applied: <path A: already on the PR branch / path B: PR diff applied cleanly / copied new file / deferred (generated)>
- Fix: <what was changed and why, one or two lines — or "None (as-is)">
- Other files touched: <paths, or "none">
- Tests added/changed: <names, or "none">
- Open: <anything left for din-merge-build-test or the operator, or "none">
```

If this file already has an entry (a second pass), update that entry in place
rather than appending a duplicate.

## 7. Report back

Summarize for the operator: what was applied, what was fixed and how, any
other files touched, and anything left open. State plainly that nothing was
built or tested yet and nothing was committed — the files are uncommitted in
`$TARGET` (the review worktree for path A, the `develop` checkout for path B).
List which files from the merge-proposal comment are still without a log
entry; when none are left, the next step is `din-merge-build-test`.
