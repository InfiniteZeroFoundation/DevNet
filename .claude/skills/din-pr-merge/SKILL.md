---
name: din-pr-merge
description: Use when actually merging a contributor PR into InfiniteZeroFoundation/DevNet's `develop` — "merge PR #N", "merge this into develop", or any request to land a PR after it's been reviewed. Runs after `din-pr-review` (assumes the 2-comment verification/merge-proposal review already happened) and produces the 3rd comment (`outcome-comment.md`) once the merge is actually pushed. Encodes the stash-merge-pop flow for merging in a cwd that already has unrelated local WIP, plus this repo's attribution/no-push-without-review rules. Not for reviewing a PR (use `din-pr-review`) and not for generic git merges outside this repo's PR workflow.
---

# DIN DevNet PR merge

`din-pr-review` produces a verification comment and a merge-proposal table.
This skill is the next step: actually landing the PR on `develop` in this cwd
and posting the outcome comment once it's real. It assumes the review already
happened (or is happening in parallel) and Umer has said to go ahead and
merge PR `<N>`.

The devnet cwd routinely has unrelated uncommitted WIP sitting on `develop`
(other in-flight tasks, doc edits, scratch config toggles). This flow never
merges into a dirty tree and never lets that WIP silently ride along inside
the merge commit — it stashes it out of the way, merges cleanly, then pops it
back and treats whatever breaks as a distinct, separately-commented deviation.

## 0. Hard rules — same gates as `din-pr-review`

- **Never commit or push without Umer reviewing first.** Get to "ready to
  push" (merge commit made, deviation commit made, build/tests green, outcome
  comment drafted), then stop and summarize file-by-file before `git push` or
  posting anything. A `git commit` on `develop` has been observed to appear
  pushed already — treat commit and push as one gated step.
- **Never fabricate a GitHub-assigned ID.** Always `git rev-parse <ref>` for
  every SHA that goes in the outcome comment, and `gh api
  repos/InfiniteZeroFoundation/DevNet/pulls/<N>/commits` for the contributor's
  real commits — never pattern-match a nearby real one.
- **Preserve real attribution on the merge commit.** Fetch the PR ref and read
  the contributor's real identity before committing:
  ```bash
  git fetch origin refs/pull/<N>/head
  git log --format='%an <%ae>' -1 FETCH_HEAD
  git commit --author="<contributor name> <their email>" ...
  ```
  Trailers: `Co-Authored-By: umeradl <umermajeed.cto@gmail.com>` for anything
  Umer/Claude fixed on top, plus this session's standard Claude attribution
  trailer. Don't credit the contributor in prose only.
- **`gh api` file-sourced comment bodies need `-F body=@<path>`, not `-f`.**
  Lowercase posts the literal string `@/path/...`. Re-fetch after every
  post/PATCH and check the actual body content, not just exit status.
- **`git status --short` + `git diff --stat` repo-wide before posting the
  outcome comment.** Catches stray edits (from the stash pop, from rebuilding)
  before they leak into a "verified" claim.
- **Never write `#N`** for the PR number in anything GitHub renders — write
  "PR No. `<N>`" or similar; `#N` auto-links to an unrelated issue.

## 1. Baseline: confirm cwd builds and tests pass *before* touching anything

Run this against the current `develop` HEAD, dirty tree and all — this is the
control measurement. If it's already red, stop and tell Umer; don't let a
pre-existing failure get attributed to the PR later.

```bash
cd foundry && npm ci   # populate node_modules before any forge test (see root CLAUDE.md)
FOUNDRY_VIA_IR=false forge build && FOUNDRY_VIA_IR=false forge test
cd .. && pytest
```

Use the fast build path (`FOUNDRY_VIA_IR=false`) for this go/no-go check per
`din-pr-review`'s guidance — same repo, same shortcut. Don't edit
`foundry.toml` to toggle it.

## 2. Stash whatever is currently dirty

```bash
git status --short   # see what's here
git stash push -u -m "pre-merge-pr-<N>"   # only if the tree is dirty; -u for untracked
```

If `git status --short` is empty, skip the stash — there's nothing to protect
the merge from and nothing to pop back later. Note in your own head (not a
comment yet) whether you stashed something, so step 4 isn't a surprise.

## 3. Merge the PR into develop

Prefer `gh pr merge <N> --merge` (real merge commit, not squash) when GitHub
reports `mergeable: MERGEABLE` and the local dry run agrees:

```bash
gh pr view <N> --json mergeable,mergeStateStatus
git merge-tree $(git merge-base develop origin/pull/<N>/head) develop origin/pull/<N>/head
```

If there's a real conflict, or the review already established this needs a
manual merge (see `din-pr-review` SKILL.md section 5), do it by hand instead —
fetch the PR ref, merge with the contributor's real `--author`, resolve
conflicts, commit. Either way, end this step with a real merge commit on
`develop`; capture its SHA with `git rev-parse HEAD` immediately (don't defer
this — it's easy to lose track once the stash pop starts moving the tree
around again).

## 4. Pop the stash

```bash
git stash pop
```

This is where develop-drift-vs-local-WIP interactions surface. Two distinct
things can happen and they're not the same:

- **Git-level conflict markers from the pop itself** — resolve these first,
  they're mechanical.
- **Silent deviations** — code that applies cleanly but is now wrong because
  the PR changed something the stashed WIP depended on (an API, a contract
  interface, a manifest field, a test fixture). These won't show up as
  conflict markers; find them by actually re-running the build/test suite
  (step 5), not by re-reading the diff.

If nothing was stashed in step 2, there's nothing to pop — go straight to
step 5 to confirm the merge alone is green.

## 5. Rebuild and retest against the combined state

Same commands as step 1, now against merge + popped WIP:

```bash
cd foundry && FOUNDRY_VIA_IR=false forge build && FOUNDRY_VIA_IR=false forge test
cd .. && pytest
```

Compare against the step-1 baseline numbers. Anything newly broken here is a
deviation to fix, not a PR defect to report back to the contributor — the PR
itself already passed review.

## 6. Commit the deviations

Once fixed and green, commit the deviation as its own commit — never amend
the merge commit:

```bash
git add <specific files>   # never -A; review `git status` first
git commit -m "$(cat <<'EOF'
<what changed and why — the develop-drift root cause, not just "fix">

Co-Authored-By: umeradl <umermajeed.cto@gmail.com>
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
git rev-parse HEAD   # capture the real deviation SHA — never guess it later
```

If step 4/5 needed no fixes at all, there's no deviation commit — say so
explicitly in the outcome comment rather than omitting the section
ambiguously.

## 7. Stop and get Umer's review before pushing

Summarize file-by-file (merge commit contents + deviation commit contents),
then wait. Do not `git push` until Umer says to.

## 8. Post the outcome comment

Once pushed, use
[`../din-pr-review/templates/outcome-comment.md`](../din-pr-review/templates/outcome-comment.md)
(same template `din-pr-review` defines as its 3rd comment — this skill is
what actually produces the state that template describes). Fill in:

- The real merge-commit and deviation-commit SHAs (`git rev-parse`, never
  fabricated), linked to their GitHub commit URLs.
- `gh pr view <N> --json state,mergedAt` to confirm GitHub agrees the PR shows
  **MERGED**.
- The deviation section populated from what step 4/5 actually found — root
  cause phrased as "develop moved since this branch was cut, in a way git's
  conflict detection couldn't see," matching the template's own framing.
- Final build/test numbers from step 5, not step 1.

Post via `gh api ... -F body=@<path>` (capital `-F`), then re-fetch and check
the body content matches before considering this done.
