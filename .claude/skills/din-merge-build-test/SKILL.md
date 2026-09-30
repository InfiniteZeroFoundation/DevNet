---
name: din-merge-build-test
description: Use once per PR, after `merge-fix-comment-update` has been run on every file of a DevNet PR's merge-proposal comment — "build and test the merge", "run din-merge-build-test", "now test everything and update the comment". Builds and tests the uncommitted merged tree in the `develop` cwd the way CI does (forge build on the real via_ir profile, full forge test, pytest -m "not integration", plus ABI regeneration / doc-link check / hardhat when relevant), fixes whatever breaks and re-runs until everything is green, then updates the "Actual merge proposal" and "Pending proposal" rows for every file in the live merge-proposal comment in one edit. Never commits or pushes. Not for the per-file code changes (use `merge-fix-comment-update`), the initial review (`din-pr-review`), or the real merge commit (`din-pr-merge`).
---

# DIN merge build & test

Second stage of landing a reviewed PR:

1. `merge-fix-comment-update <path>` — per file, code changes only, logged to
   `~/tempdir/DIN/PRs/PRreview_<N>-merge-fix-log.md`.
2. **`din-merge-build-test`** (this skill) — build + test the whole merged
   tree once, fix until green, then write the outcome into the comment for
   every file.
3. `din-pr-merge` — the real commit, after Umer reviews.

Everything here happens on the **uncommitted working tree of the `develop`
cwd** (`/home/umerm/projects/devnet`), which is where stage 1 left the
changes.

## 0. Hard rules

- **Never commit or push.** Fixes stay uncommitted in the `develop` cwd.
- **Never install packages into Umer's venvs** — if something's missing,
  report the exact `pip install` command and stop.
- **Never `sed`/edit `foundry.toml`** to toggle `via_ir` or anything else.
  The plain (non-via_ir) build doesn't compile on `develop` — always use the
  real profile.
- **Never fabricate a GitHub-assigned ID.** Fetch the comment id/URL, SHAs.
- **`gh api` file-sourced bodies need `-F body=@<path>`, not `-f`.** Re-fetch
  after the PATCH and diff against what you meant to post.
- **`git status --short` + `git diff --stat` repo-wide before the PATCH** —
  every changed path must be explained by the merge-fix log or by a fix made
  in step 4. Pre-existing unrelated edits (already dirty before stage 1) are
  fine but must not be claimed as part of the PR.
- **Never write `#N`** in anything GitHub renders — "No. N".
- **Only touch the "Actual merge proposal" and "Pending proposal" rows** in
  the comment. Every other row and every other part of the body stays
  byte-for-byte identical.
- **Don't update the comment until everything is green**, unless Umer tells
  you to post a partial result.

## 1. Preconditions

```bash
N=<N>
WT=~/tempdir/DIN/PRs/PRreview_$N
LOG=~/tempdir/DIN/PRs/PRreview_$N-merge-fix-log.md
cd /home/umerm/projects/devnet
git status --short && git diff --stat
```

- The log must exist and have an entry for **every** `#### \`<path>\`` block
  in the live merge-proposal comment (fetch it fresh with `gh api
  repos/InfiniteZeroFoundation/DevNet/issues/comments/<id> --jq .body`). If
  any file is missing, stop and tell Umer which — those still need
  `merge-fix-comment-update`.
- Anything logged as "Open" or "deferred" (e.g. generated ABIs) is handled
  here — note them.
- `dincli` must resolve to this checkout: `~/my_venvs/torchenv/bin/python -c
  'import dincli; print(dincli.__file__)'` → under
  `/home/umerm/projects/devnet`. If not, stop and report.

## 2. Build + test (CI-equivalent)

Run the two independent tracks in parallel (both backgrounded — the via_ir
build takes minutes; wait for the process to actually exit, don't poll a log
for a success string):

**Solidity** (skip only if nothing under `foundry/` changed and no ABI is
pending regeneration):
```bash
source ~/.nvm/nvm.sh >/dev/null
cd foundry && npm ci --silent        # must precede forge test (upgrades-core FFI)
forge clean && forge build           # full real via_ir build; clean avoids stale build-info
forge test                           # full suite, incl. UpgradeValidation.t.sol
```

**Python** (empty HOME like the CI runner — catches tests reading
`~/.config/dincli`):
```bash
CIHOME=$(mktemp -d)
HOME="$CIHOME" XDG_CONFIG_HOME="$CIHOME/.config" \
  ~/my_venvs/torchenv/bin/python -m pytest -m "not integration" -q -p no:cacheprovider
```
Don't run the `integration`-marked / `tests/dincli/` suite — it's stale
against foundry and needs live services; it isn't verification.

**Conditional extras:**
- **ABIs** — for every contract under `foundry/src/` the merge changed (or
  that the merge-proposal comment says to regenerate), after the build:
  ```bash
  # torchenv has dincli importable but no `dincli` console script, so call the app directly
  ~/my_venvs/torchenv/bin/python -c "import sys; from dincli.main import app; sys.argv=['dincli']+sys.argv[1:]; app()" \
    system dump-abi --artifact foundry/out/<C>.sol/<C>.json --output dincli/abis
  ```
  Then `git diff --stat dincli/abis` — the delta should be exactly the ABI
  surface the PR added (new errors/events/functions, incl. inherited ones
  like `ReentrancyGuardReentrantCall`); anything else unexpected is worth a
  look before moving on.
- **Docs** — if any `.md` changed:
  `~/my_venvs/torchenv/bin/python .github/scripts/check_doc_links.py Documentation`.
- **Hardhat** — only if anything under `hardhat/` changed:
  `cd hardhat && npm ci --silent && npx hardhat compile && npx hardhat test`.

## 3. Triage failures

For each failure, decide which bucket it's in before touching anything:

- **Caused by the merge or a merge-fix change** → fix it (step 4).
- **Pre-existing on `develop`** → confirm by running the same failing
  test/command in a clean `origin/develop` worktree (e.g.
  `git worktree add ~/tempdir/DIN/develop-check origin/develop`, remove it
  afterwards). Don't fix; report it to Umer and carry on with the rest.
- **Environmental** (missing package, npx cache race, RPC/IPFS reach) →
  report, don't paper over it.

## 4. Fix and re-run until green

Fix the way `merge-fix-comment-update` step 4 does: real fix, the file's own
idiom, updated natspec/docstrings, grep for other call sites. Re-run just the
failing piece while iterating (`forge test --match-contract <Suite>`,
`pytest <file>::<test>`) — but if the fix touched a contract, rebuild first
(`forge build`; before any `UpgradeValidation` run, `forge clean && forge
build` again, or the OZ FFI tool fails with "Found multiple contracts with
name ..." and looks like a regression).

Record every fix in the merge-fix log under the affected file's entry (add a
`- Build/test fix:` line), and create an entry for any new file you had to
touch.

**Stop and ask Umer** instead of fixing when:
- The fix would change what a file's merge proposal said should happen, or
  needs a design/tokenomics/fee decision.
- A test fails because the PR's behaviour conflicts with another test's
  expectation and it isn't obvious which one is right.
- The same failure survives three fix attempts.
- The fix spreads into files the PR doesn't touch in a non-trivial way
  (signature changes, storage layout, deploy scripts).

**Final run:** once everything passes in targeted runs, do one full clean run
of every track from step 2 on the final tree (`forge clean && forge build`,
full `forge test`, full pytest, plus whichever extras apply). Only those
numbers go into the comment.

## 5. Update the merge-proposal comment (all files, one edit)

Fetch the live body fresh. For each file's block, replace its two rows. Build
`old` from what's **actually** in those cells now (don't assume `Soon`),
assert `count == 1`, replace:

```python
old = "| Actual merge proposal | <current text verbatim> |\n| Pending proposal | <current text verbatim> |"
new = ("| Actual merge proposal | <what landed, from the log: applied as-is / applied + fix X"
       " / regenerated; + evidence: forge build clean (via_ir), forge test P/F/S, pytest P/F/S>."
       " Uncommitted in the `develop` cwd — not committed or pushed. |\n"
       "| Pending proposal | ~~<original ask>~~ **Done:** <one line> |")   # or "None" if it was None
assert body.count(old) == 1
body = body.replace(old, new)
```

For a file whose shared block covers several paths (e.g. `A` / `B` / `C`),
write one outcome covering all of them. If something is still open for a
file (pre-existing failure, decision Umer deferred), say so in that file's
cells instead of marking it Done.

Then:
1. `git status --short && git diff --stat` repo-wide (hard rule above).
2. Diff the new body against the fetched one — only the intended rows may
   differ.
3. Grep the new body for `#[0-9]`.
4. `gh api -X PATCH repos/InfiniteZeroFoundation/DevNet/issues/comments/<id> -F body=@<path>`.
5. Re-fetch and diff against the intended body (trailing-newline-only
   difference is fine).

## 6. Report back

Summarize for Umer: final test counts per track, every fix made in step 4
(file + one line), any pre-existing/environmental failures, ABI deltas, and
the updated comment URL. State plainly that nothing was committed — the next
step after Umer's review is `din-pr-merge`.
