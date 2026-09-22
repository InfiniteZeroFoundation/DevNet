---
name: merge-fix-comment-update
description: Use per-file, after `din-pr-review` has posted its verification and merge-proposal comments for a PR — "merge and fix <path>", "apply the fix for <path>", "land <path> per the merge proposal". Input is one relative file path (e.g. `foundry/src/DinCoordinator.sol`); invoke it again for each other file. For that one file: applies the PR's diff into the `develop` cwd per the merge-proposal comment's "Recommended merge proposal", applies the fix described in "Pending proposal", verifies (build/tests), then updates that file's "Actual merge proposal" and "Pending proposal" rows in the live merge-proposal comment. Stops and asks Umer whenever the row's proposal implies a decision, a conflict, or a judgment call — never guesses through those. Not for merging a whole PR at once (use `din-pr-merge`) and not for the initial review (use `din-pr-review`).
---

# Merge-fix-comment-update

`din-pr-review` produces a merge-proposal comment (Template 2) with one table
per changed file: what the diff does, a recommended merge proposal, and (for
files that need work) a pending proposal describing the fix. This skill does
the file-by-file follow-through on that table, one file per invocation:
apply the file into `develop`, apply its fix, verify, then update that same
file's row in the comment to say what actually happened — never a whole-PR
merge, never more than the one file passed in.

This is the same shape of work as `din-pr-merge`, but scoped to a single file
landing directly on top of `develop`'s working tree (uncommitted, for Umer to
review) rather than a real merge commit of the whole PR. Use `din-pr-merge`
once every file's fix has actually been reviewed and Umer is ready to
actually commit/push the PR.

## 0. Hard rules — same gates as `din-pr-review` / `din-pr-merge`

- **Never commit or push.** This skill only ever leaves changes sitting
  uncommitted in the `develop` cwd. Landing them as a real commit is
  `din-pr-merge`'s job, after Umer has reviewed every file.
- **Never fabricate a GitHub-assigned ID.** Comment id, commit SHA — always
  fetch (`gh api .../comments/<id>`, `git rev-parse`), never pattern-match.
- **`gh api` file-sourced comment bodies need `-F body=@<path>`, not `-f`.**
  Re-fetch after every PATCH and diff it against what you intended to post —
  not just the exit status.
- **`git status --short` + `git diff --stat` repo-wide before posting any
  comment update.** A stray edit from local verification must never leak into
  what you claim was done.
- **Never write `#N`** for the PR number inside anything GitHub renders.
- **Touch only the one file's block in the comment.** Read the live body,
  locate the exact table for the target file, edit only its "Actual merge
  proposal" and "Pending proposal" rows (string-replace with an exact,
  uniqueness-asserted match — see step 5), leave every other file's block and
  every other row byte-for-byte untouched. Confirm this with a diff against
  the pre-edit body before posting.
- **When in doubt, stop and ask Umer** — this skill's whole point is to do
  the mechanical, unambiguous part of landing a fix and hand back control the
  moment a real decision shows up. See step 6 for what counts.

## 1. Establish context

You need: the PR number, its review worktree (`~/tempdir/DIN/PRs/PRreview_<N>`,
created by `din-pr-review`), and the live merge-proposal comment's id/URL. If
any of these aren't already established in the conversation, ask Umer rather
than guessing which PR a bare file path belongs to — the same path can appear
in more than one open PR's review.

```bash
N=<N>
WT=~/tempdir/DIN/PRs/PRreview_$N
cd "$WT" && git status   # confirm the worktree exists and is on pr-$N-review
```

If `develop` has moved since the worktree was set up, re-verify mergeability
before trusting the diff you're about to apply (same check as
`din-pr-review` step 1):

```bash
git fetch origin develop
git merge-tree --write-tree --name-only origin/develop pr-$N-review
gh pr view $N --json mergeable,mergeStateStatus
```

If local and GitHub disagree, or the file you're about to touch was hit by
develop's drift since the branch was cut (`git log --oneline <merge-base>..origin/develop -- <path>`),
stop and tell Umer before applying anything.

## 2. Read that file's row out of the live comment

Fetch the current comment body fresh (don't trust a copy from earlier in the
conversation — someone may have edited it since):

```bash
gh api repos/InfiniteZeroFoundation/DevNet/issues/comments/<comment-id> --jq .body > /tmp/.../comment_live.md
```

Find the `#### \`<path>\`` block and read:
- **Change** — New or Modified (decides step 3's mechanism).
- **Recommended merge proposal** — what should land.
- **Pending proposal** — the fix still to apply (or `None`).

## 3. Apply the file into `develop`

**New file:** copy it from the worktree at the exact relative path:
```bash
cp "$WT/<path>" "/home/umerm/projects/devnet/<path>"
```

**Modified file:** diff the file between the PR's merge-base and its head in
the worktree, then apply that diff to the `develop` cwd's current copy:
```bash
git -C "$WT" diff <merge-base> <pr-head> -- "<path>" > /tmp/.../file.patch
cd /home/umerm/projects/devnet && git apply --check /tmp/.../file.patch
```
If `--check` fails, that's a real conflict — don't force it (`git apply -3`
or hand-resolution) without asking Umer first; this is exactly the kind of
thing step 6 exists for. If the row said "contingent on `<other file>`'s fix
landing first," confirm that other file's fix is actually in the `develop`
cwd already before applying this one — if it isn't, stop and ask.

## 4. Apply the fix from "Pending proposal"

If Pending proposal is `None`, skip to step 5 — "Recommended merge proposal"
already said "merged as-is" and there's nothing further to do.

Otherwise, apply exactly what the row describes. This is real code-review
follow-through, not a mechanical patch — read the file, understand the
described defect (cross-reference the verification comment for the full
repro if the pending-proposal line is terse), and write the fix the way you
would for any other bug: matching the file's existing idiom, updating
affected natspec/docstrings, and checking for other call sites the fix's
signature or behavior change touches (grep the rest of `src/`/`script/` for
the changed symbol — don't assume the file is used in isolation).

## 5. Verify

```bash
cd foundry
forge build --contracts <path>            # standalone compile check first
forge test --match-contract <RelevantSuite>   # if a test suite covers it
git status --short && git diff --stat         # repo-wide — catch stray edits
```

For a file with broad downstream usage (anything other than a brand-new,
self-contained contract), also grep the rest of the tree for references to
symbols you changed, and run the full `forge build`/relevant test suites, not
just the touched file — a signature change can compile in isolation and still
break a caller elsewhere.

**If any test in the run is an `Upgrades.validateImplementation`/
`validateUpgrade` FFI test (`UpgradeValidation.t.sol`), always run
`forge clean && forge build` (the full project, not `--contracts <path>`)
immediately before it — a preceding partial `--contracts` build leaves stale
build-info JSON behind and the OZ FFI tool fails with `Found multiple
contracts with name ...`, which reads like a real regression but isn't one.**
This is expensive (a full `via_ir=true` build of the whole project takes a
couple of minutes) — background it and wait for the process to actually exit
before re-running tests, don't just check the log for a success string while
it's still compiling.

## 6. Stop and ask Umer whenever —

- The diff doesn't apply cleanly, or develop's drift since the branch was cut
  touched this same file in a way that changes what "the fix" should even do.
- The pending-proposal text names a design trade-off rather than a concrete
  fix (e.g. "coordinate merge order across PRs", "union of both sides" where
  the union isn't mechanical, anything requiring a call on tokenomics/fee
  parameters — see the `p3-issues-defer-fee-changes` memory). That's asking
  for a decision, not describing a fix to apply.
- The fix changes a public function's signature or removes/renames state that
  other files reference — confirm the blast radius is actually contained
  before treating it as done.
- Verification turns up something new (a test fails for a reason unrelated to
  the fix you just made, a downstream file needs its own change) that the
  merge-proposal comment didn't already anticipate.
- Anything about the fix feels underspecified enough that two reasonable
  people could implement it differently — say what the options are and let
  Umer pick, don't silently choose one.

## 7. Update the comment

Edit only this file's "Actual merge proposal" and "Pending proposal" rows in
the fetched body. Build `old` from whatever text is *actually* sitting in
those two rows right now (don't assume it's still the literal `Soon` and the
original pending-proposal text from step 2's read — this may be the second
or third pass over this file, and an earlier pass may have already updated
one or both cells). Python string-replace, asserting `count == 1` before
writing — never a blind sed across the whole body:

```python
old = "| Actual merge proposal | <current text, copied verbatim from the fetched body> |\n| Pending proposal | <current text, copied verbatim> |"
new = "| Actual merge proposal | <what you actually did, plumbing in verification evidence — compiles clean / N tests pass / still needs X> |\n| Pending proposal | ~~<original ask>~~ **Done:** <one line> |"
assert body.count(old) == 1
body = body.replace(old, new)
```

If only one of the two rows needs updating this pass, edit just that one row
(same exact-match-then-replace pattern) rather than touching both.

Note explicitly in "Actual merge proposal" that the change is **sitting
uncommitted in the `develop` cwd only** — not committed, not pushed, not
shared with the PR author — until Umer says otherwise (`din-pr-merge` is the
next step once every file is through this flow). If step 4 left a residual
task (e.g. a regression test still to write), say so in the same cell rather
than marking the file fully done.

Post with `-F body=@<path>` (capital F), then re-fetch and diff against the
intended content before considering the post done (a trailing-newline-only
diff from GitHub is fine; anything else means the post went wrong).

## 8. Report back

Summarize for Umer: what was applied, what was fixed and how, verification
results, and the exact comment update posted (with its URL). End by stating
plainly that nothing was committed — the files are uncommitted in the
`develop` cwd, waiting for review.
