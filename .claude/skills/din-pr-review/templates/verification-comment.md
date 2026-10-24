# Template 1 — Deep verification / review comment

Posted first, before the merge-proposal table. Goal: a "Claimed / Verified"
pair for every checkable claim in the PR. A claim is verified by linking the
CI job that covers it (green against an up-to-date `develop`), or by running it
locally where `Developer/MAINTAINING.md` No. 4.2 requires that: storage layout
and upgrade safety in `foundry/src/**`, deploy/upgrade scripts, `dincli` flows
against a live chain or IPFS, and any behaviour no test exercises.

```
Reviewed against `develop` in an isolated worktree (branch applies cleanly on
top of current tip, `<merge-base-sha>`, <N> commit(s), no conflicts — confirmed
by both `git merge-tree` locally and GitHub's own `mergeable`/
`mergeStateStatus`). CI on `<head sha>`: [`CI OK` green](<run url>) — covers
<what it covers for this PR>. Reproduced locally: <the parts CI doesn't cover>.

**Claimed:** <the PR's own claim, quoted or paraphrased precisely>

**Verified — <one-line verdict>:** <either the CI job that covers it (link),
or what was actually run/reproduced locally, with real numbers/output — forced
edge cases, real-sampling stress tests, AST diffs, independent link/count
checks, etc. Where you reproduce, prefer going *beyond* the PR's own
verification, not just repeating it.>

<repeat per claim>

**Not independently re-verified:** <anything read but not run, and why — e.g.
"nothing to run to confirm">

---

<Closing paragraph: whether every checkable claim held up, and a
recommendation ("looks good to merge" / "mergeable as-is" / flag anything
that didn't hold up).>
```

## Notes

- If the fix is adversarial/boundary-case in nature (e.g. a `-inf`/NaN bug),
  verify both the forced-boundary case *and* real unforced sampling at scale —
  a single forced repro is weaker evidence than showing it also happens (or is
  now fixed) under genuine randomness.
- If a "this proves itself" test exists (anti-tautology test, regression
  gate), break the mechanism it guards on purpose, confirm the test actually
  fails, then restore and confirm it passes again. Don't just trust that a
  test *would* catch a regression.
- Structural claims (AST equivalence, "this file doesn't exist on `develop`
  yet", link/reference counts) are cheap to verify exactly — do it with a
  real command, cite the exact output, don't approximate.
- For Solidity changes run locally, use the real `via_ir` profile
  (`forge build` / `forge test`); the plain build no longer compiles `develop`
  — see the main SKILL.md.
