# Template 1 — Deep verification / review comment

Posted first, before the merge-proposal table. Goal: reproduce every checkable
claim in the PR with real execution, not just reading.

```
Reviewed against `develop` in an isolated worktree (branch applies cleanly on
top of current tip, `<merge-base-sha>`, <N> commit(s), no conflicts — confirmed
by both `git merge-tree` locally and GitHub's own `mergeable`/
`mergeStateStatus`). Ran the actual <fix/behavior> rather than just reading it.

**Claimed:** <the PR's own claim, quoted or paraphrased precisely>

**Verified — <one-line verdict>:** <what was actually run/reproduced, with
real numbers/output — forced edge cases, real-sampling stress tests, AST
diffs, independent link/count checks, etc. Prefer going *beyond* the PR's own
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
- For Solidity changes, use the fast build path (`FOUNDRY_VIA_IR=false`)
  unless validating deploy-exact behavior (gas numbers, bytecode) — see the
  main SKILL.md.
