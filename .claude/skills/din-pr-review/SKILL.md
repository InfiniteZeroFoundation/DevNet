---
name: din-pr-review
description: Use when reviewing a pull request against InfiniteZeroFoundation/DevNet's `develop` branch — "review PR #N", "review this branch for merge", or evaluating a contributor's PR before merging it into this repo. Encodes this repo's standing 3-comment GitHub workflow (deep verification → merge-proposal table → post-merge outcome) plus this project's specific gotchas (fast build path, GitHub-ID/attribution rules, table format). Not for generic diff review with no PR/GitHub-posting context — use the general `code-review` skill for that.
---

# DIN DevNet PR review

This repo (`InfiniteZeroFoundation/DevNet`) reviews every contributor PR the same
way: verify for real (not just read), post a per-file merge-proposal table, then
close the loop with what actually happened once it's merged. This skill is the
GitHub-posting workflow layered on top of code review — it assumes you've
already read the diff and formed an opinion; it's about how that opinion gets
verified and communicated in this repo specifically.

## 0. Hard rules — check these before every step, not just at the end

- **Never commit or push without Umer reviewing first.** Prepare the diff/merge
  result, summarize file-by-file, and ask before `git commit`/`git push`/
  `gh pr merge`. A `git commit` on `develop` has been observed to appear
  pushed already — treat commit and push as one gated step.
- **Never fabricate a GitHub-assigned ID.** Commit SHAs, `issuecomment-N`,
  `discussioncomment-N` — these are opaque and non-sequential per-thread.
  Always fetch the real value (`git rev-parse`, `gh api .../comments --jq
  '.[-1].html_url'`) instead of pattern-matching nearby real ones.
- **`gh api` file-sourced comment bodies need `-F body=@<path>`, not `-f`.**
  Lowercase posts the literal string `@/path/...` and silently wrecks the
  comment. After every post/PATCH, re-fetch and check the body content —
  not just the exit status or returned `html_url`.
- **`git status --short` + `git diff --stat` repo-wide before posting or
  updating any PR comment.** Catches stray edits from local verification
  (toggled config, scratch files) before they leak into a "verified" claim.
- **Never write `#N`** for issue/PR/item numbers inside anything GitHub
  renders (comments, PR bodies, commit messages) — GitHub auto-links it to
  an unrelated issue. Write "No. 2", "No. 3", etc.
- **"Actual merge proposal" is Umer's field.** On the initial merge-proposal
  comment it is always literally `Soon` in every row — grep the drafted
  body for `Actual merge proposal | ` and confirm before posting. Put any
  verification detail from your own trial merge in "Recommended merge
  proposal" instead.

## 1. Set up an isolated review

Every review gets its own git worktree under `~/tempdir/DIN/PRs/`, on a branch
named `pr-<N>-review`. Never `gh pr checkout` in the main repo checkout and
never work directly on `develop` — the main checkout stays clean so `git
status` there means something. Do this as the first step of every review, even
if the PR is small or you only plan to read the diff; `~/tempdir/DIN/PRs/` is
the record of what has been reviewed.

```bash
N=<N>
WT=~/tempdir/DIN/PRs/PRreview_$N
cd ~/projects/devnet
git fetch origin develop "pull/$N/head:pr-$N-review"     # fork PRs work too — pull/N/head is a GitHub ref
git worktree add "$WT" "pr-$N-review"                    # branch pr-<N>-review, dir PRreview_<N>
cd "$WT"

git merge-tree $(git merge-base origin/develop pr-$N-review) origin/develop pr-$N-review  # local conflict check
gh pr view $N --json mergeable,mergeStateStatus          # GitHub's own verdict — must agree
```

Run all verification (build, tests, `git status`/`git diff` checks) from `$WT`.
The worktree has its own `foundry/node_modules`, so `npm ci` runs again there.

**Re-review after the author pushes fixes:** reuse the existing worktree —
don't create a second one. The branch is throwaway, so hard-reset it to the new
head (this also survives force-pushes):

```bash
cd ~/tempdir/DIN/PRs/PRreview_$N
git fetch origin "pull/$N/head" && git reset --hard FETCH_HEAD
```

If `git worktree add` says the branch or path already exists, run `git worktree
list` first — the review may already be set up.

## 2. Fast build/test path

- **Foundry:** `cd foundry && npm ci` first (see root `CLAUDE.md` — `forge
  test`'s FFI shells out to `npx @openzeppelin/upgrades-core` and races
  without a populated `node_modules`). For a go/no-go compile+test check,
  skip `via_ir` — it adds minutes for no signal on most PRs:
  `FOUNDRY_VIA_IR=false forge build` / `forge test`. **Never `sed`/edit the
  tracked `foundry.toml` to toggle this** — env-var override only. If the
  plain build fails, don't call it a PR defect until it's confirmed against
  the real `via_ir = true` profile too (some contract may need it to avoid
  stack-too-deep).
- **dincli:** `pytest` from repo root (editable install via `pip install -e .`
  if not already done in the venv).
- Before evaluating contract-level findings, check
  `Documentation/technical/audits/foundry-src-security-review.md` (Similoluwa's
  baseline audit of `foundry/src/`, findings C-1/C-2/H-1/H-2 etc.) so you don't
  re-report something already tracked there.
- Don't raise "the live Sepolia deployment needs upgrade/migration steps" as a
  finding — nothing on `develop` is deployed. Sepolia's live contracts are the
  older non-upgradeable DevNet 1.0; this repo's upgrade path targets a fresh
  `DeployPlatform.s.sol` deploy, not a migration of what's live.

## 3. The three comments

Post these in order, using the templates in `templates/`. Skip Comment 3 until
the merge is actually pushed.

1. **[`templates/verification-comment.md`](templates/verification-comment.md)**
   — deep verification. Reproduce every checkable claim in the PR with a real
   command (run it, don't just read it); prefer going beyond the PR's own
   verification (forced edge cases + real sampling, break-then-fix a
   regression test, exact link/AST counts).
2. **[`templates/merge-proposal-comment.md`](templates/merge-proposal-comment.md)**
   — per-file breakdown. One small key/value table per file (`#### \`path\``
   heading + 2-column table), not one wide multi-column table — this repo's
   default once a table would need more than ~4-5 columns.
3. **[`templates/outcome-comment.md`](templates/outcome-comment.md)** — posted
   after the merge actually lands on `develop`, replacing the table's
   predictions with the real commit SHAs and any deviation needed.

## 4. Re-review after fixes

If the author pushes fixes after Comment 1/2, cite both SHAs in the follow-up:
`gh api repos/InfiniteZeroFoundation/DevNet/pulls/<N>/commits` to find the
commit that was HEAD when you last reviewed vs. current HEAD — e.g. "Reviewed
the fix commits: `d8dc1c8` (reviewed) → `eb68952` (current HEAD)." State "no
new commits since review — still at `<sha>`" if nothing changed.

## 5. Manual merges (copying files instead of merging the branch)

When merging by hand rather than `gh pr merge` (e.g. resolving conflicts
yourself), preserve real attribution:

```bash
git fetch origin refs/pull/<N>/head
git log --format='%an <%ae>' -1 FETCH_HEAD   # the contributor's real identity
git commit --author="<contributor name> <their email>" ...
```

Trailers on that commit: `Co-Authored-By: umeradl <umermajeed.cto@gmail.com>`
for fixes Umer/Claude applied on top, plus the standard Claude attribution
trailer for this session. Don't credit the contributor in prose only — use the
real `--author` field and `git log` identity, not a guessed noreply address.
