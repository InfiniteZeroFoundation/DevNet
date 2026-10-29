---
name: din-pr-review
description: Use when reviewing a pull request against InfiniteZeroFoundation/DevNet's `develop` branch — "review PR #N", "review this branch for merge", or evaluating a contributor's PR before merging it into this repo. Any maintainer can run it, as long as they aren't the PR's author or a co-author (checked first with `.claude/scripts/din_peer_check.py`). Encodes this repo's standing 3-comment GitHub workflow (verification → merge-proposal table → post-merge outcome), the review-depth rule from Developer/MAINTAINING.md No. 4.2 (green CI counts as evidence; reproduce locally only what CI doesn't cover), the approve / request changes / recuse step, and this project's gotchas (via_ir build, GitHub-ID/attribution rules, table format). Not for generic diff review with no PR/GitHub-posting context — use the general `code-review` skill for that.
---

# DIN DevNet PR review

This repo (`InfiniteZeroFoundation/DevNet`) reviews every PR the same
way: verify (not just read), post a per-file merge-proposal table, then
close the loop with what actually happened once it's merged. This skill is the
GitHub-posting workflow layered on top of code review — it assumes you've
already read the diff and formed an opinion; it's about how that opinion gets
verified and communicated in this repo specifically.

The process itself is [`Developer/MAINTAINING.md`](../../../Developer/MAINTAINING.md).
"The operator" below means the maintainer running this skill, i.e. the active
`gh` user (`gh api user --jq .login`). Setup: [`.claude/scripts/README.md`](../../scripts/README.md).

## 0. Hard rules — check these before every step, not just at the end

- **Peer check first, and again before approving.**
  ```bash
  python3 .claude/scripts/din_peer_check.py pr <N>
  ```
  `REFUSE` means the operator is the author or a co-author (MAINTAINING No. 1,
  No. 7). Stop, say so, and name a reviewer from MAINTAINING No. 3 instead.
  Re-run it right before `gh pr review --approve`: new commits can add
  co-authors. Never switch `gh` accounts to get past it.
- **Never commit, push, approve or merge without the operator's go-ahead.**
  Prepare the result, summarize file-by-file, and ask first. A `git commit` on
  `develop` has been observed to appear pushed already — treat commit and push
  as one gated step.
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
- **"Actual merge proposal" belongs to whoever performs the merge**
  (MAINTAINING No. 4.3). On the initial merge-proposal comment it is always
  literally `Soon` in every row — grep the drafted body for
  `Actual merge proposal | ` and confirm before posting. Put any verification
  detail from your own trial merge in "Recommended merge proposal" instead.
- **Check closing keywords before approving** (MAINTAINING No. 4.3). `develop`
  is the default branch, so `Closes`/`Fixes`/`Resolves #N` in the PR body or
  any commit message closes issue N on merge. Grep both
  (`gh pr view <N> --json body,commits`). For each hit, check the PR against
  the issue's full scope: its body plus the `din-approve-issue` amendments. If
  the PR is partial, say so in the verification comment and ask the author to
  change it to `Part of #N` before merge.

## 1. Set up an isolated review

Every review gets its own git worktree under `$DIN_WORK/PRs/`, on a branch
named `pr-<N>-review`. Never `gh pr checkout` in the main repo checkout and
never work directly on `develop` — the main checkout stays clean so `git
status` there means something. Do this as the first step of every review, even
if the PR is small or you only plan to read the diff; `$DIN_WORK/PRs/` is
the record of what has been reviewed.

```bash
source .claude/scripts/din-env.sh        # DIN_REPO, DIN_WORK, DIN_PY (see .claude/scripts/README.md)
N=<N>
WT=$DIN_WORK/PRs/PRreview_$N
mkdir -p "$DIN_WORK/PRs"
cd "$DIN_REPO"
git fetch origin develop "pull/$N/head:pr-$N-review"     # fork PRs work too — pull/N/head is a GitHub ref
git worktree add "$WT" "pr-$N-review"                    # branch pr-<N>-review, dir PRreview_<N>
cd "$WT"

git merge-tree --write-tree --name-only origin/develop pr-$N-review  # local conflict check: exit 0 = clean, 1 = conflicts (lists files)
gh pr view $N --json mergeable,mergeStateStatus          # GitHub's own verdict — must agree
```

Use `--write-tree`, not the old three-argument `git merge-tree <base> <a> <b>`:
that form prints conflicts as `+<<<<<<<` diff lines, so grepping for
`^<<<<<<<` finds nothing and reports a false "clean" (this happened on PR 146,
which GitHub correctly showed as `CONFLICTING`). If the two verdicts disagree,
don't proceed — find out why first.

Run all verification (build, tests, `git status`/`git diff` checks) from `$WT`.
The worktree has its own `foundry/node_modules`, so `npm ci` runs again there.

**Re-review after the author pushes fixes:** reuse the existing worktree —
don't create a second one. The branch is throwaway, so hard-reset it to the new
head (this also survives force-pushes):

```bash
cd $DIN_WORK/PRs/PRreview_$N
git fetch origin "pull/$N/head" && git reset --hard FETCH_HEAD
```

If `git worktree add` says the branch or path already exists, run `git worktree
list` first — the review may already be set up.

## 2. What to run locally — and what CI already covers

**Review depth (MAINTAINING No. 4.2).** Required checks green against an
up-to-date `develop` count as evidence for anything CI covers: cite the run
(`gh pr checks <N>`, link the job) instead of re-running it. **Reproduce
locally only what CI doesn't cover:**

- storage layout and upgrade safety in `foundry/src/**`
- deploy and upgrade scripts in `foundry/script/**`
- `dincli` flows against a live chain or IPFS, until the integration job is a
  required check (MAINTAINING No. 4.9)
- any claimed behaviour that no test exercises

If CI on the PR is red, stale against `develop`, or never ran, CI isn't
evidence: say so, and either ask the author to update the branch or run the
relevant suite yourself.

When you do run things locally:

- **Foundry:** `cd foundry && npm ci` first (see root `CLAUDE.md` — `forge
  test`'s FFI shells out to `npx @openzeppelin/upgrades-core` and races
  without a populated `node_modules`). Use the real profile: `forge build` /
  `forge test`. The plain (non-`via_ir`) build no longer compiles `develop`
  (stack too deep), so `FOUNDRY_VIA_IR=false` is not a shortcut any more.
  **Never `sed`/edit the tracked `foundry.toml`.**
- **dincli:** `"$DIN_PY" -m pytest -m "not integration"` from the worktree
  root (editable install via `pip install -e .` if not already done in the
  venv).
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
   — verification. A "Claimed / Verified" pair for every checkable claim in
   the PR. A claim is verified by linking the CI job that covers it, or by a
   real local command where step 2 requires one (run it, don't just read it).
   Where you do reproduce, prefer going beyond the PR's own verification
   (forced edge cases + real sampling, break-then-fix a regression test, exact
   link/AST counts). Never accept "done" or "landed" in a comment as proof.
2. **[`templates/merge-proposal-comment.md`](templates/merge-proposal-comment.md)**
   — per-file breakdown. One small key/value table per file (`#### \`path\``
   heading + 2-column table), not one wide multi-column table — this repo's
   default once a table would need more than ~4-5 columns.
3. **[`templates/outcome-comment.md`](templates/outcome-comment.md)** — posted
   after the merge actually lands on `develop`, replacing the table's
   predictions with the real commit SHAs and any deviation needed.

After comments 1–2 are posted, add the `Reviewed` label
(`gh pr edit <N> --add-label Reviewed`).

**Trivial PRs** (typo, dead link, comment fix): skip the three comments and go
straight to step 4 with an approval that says "trivial" (MAINTAINING No. 4.3).

## 4. Approve, request changes, or recuse

Once comments 1–2 are up, record the verdict on GitHub — the `develop` ruleset
counts only a GitHub approval:

```bash
python3 .claude/scripts/din_peer_check.py pr <N>     # again: commits may have changed
gh pr review <N> --approve -b "<one line: what was verified, at <head sha>>"
gh pr review <N> --request-changes -b "<the blocking items, by number>"
```

- **Recusal is a valid outcome.** If the PR is outside the operator's depth,
  don't approve. Post "out of my depth — @<someone>" and stop (MAINTAINING No. 3).
- **`foundry/src/**` needs two keys** (MAINTAINING No. 4.2): the peer's
  approval plus a second sign-off from @umeradl or @abrahamnash, or a security
  reviewer they route it to. If the operator is the peer, request the second
  key; don't merge on one.
- **Mechanism changes** (slashing, tokenomics, fees, scoring) also need the
  mechanism sign-off (MAINTAINING No. 4.2): @umeradl's approval, or
  @abrahamnash's for Umer's own PRs.
- **If you pushed fixes onto the PR**, you're now a co-author: the final
  approval has to come from someone else (MAINTAINING No. 7). The peer check
  will say so.

Get the operator's go-ahead before submitting the review.

## 5. Re-review after fixes

If the author pushes fixes after Comment 1/2, cite both SHAs in the follow-up:
`gh api repos/InfiniteZeroFoundation/DevNet/pulls/<N>/commits` to find the
commit that was HEAD when you last reviewed vs. current HEAD — e.g. "Reviewed
the fix commits: `d8dc1c8` (reviewed) → `eb68952` (current HEAD)." State "no
new commits since review — still at `<sha>`" if nothing changed.

## 6. Merging

Merging is `din-pr-merge`: path A (GitHub-side merge commit by the reviewer,
the default) or path B (local merge, Umer only). Attribution rules for any
commit the merger writes are there too.
