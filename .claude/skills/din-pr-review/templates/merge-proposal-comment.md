# Template 2 — Merge-proposal table comment

Posted after (or alongside) the verification comment, before merging. Goal: a
per-file breakdown a maintainer can act on, predicting what merging will look
like before it happens.

```
## Files changed (<N>) — as of `<PR-head-sha>` (PR head)

Diffed against merge-base `<sha>` (`develop`). <Note on how far develop has
moved since the branch was cut, and which of this PR's files actually overlap
with what develop picked up in that window.> **GitHub agrees: `mergeable:
<value>`, `mergeStateStatus: <value>`.** <Confirmed with a local
`git merge-tree` dry run: clean / lists real conflicts.>

#### `<file path>`

| Field | Value |
|---|---|
| Change | New / Modified |
| Lines | +X/-Y |
| Diff (what exactly is in this PR) | <what this file's diff actually does> |
| Functionality — how & why | **How:** <the actual mechanism — what runs, in what order, what it reads/writes, grounded in the real source (not the PR description's own wording)>. **Why:** <the underlying reason this change was made — the problem it closes, the invariant it protects, who/what would break without it>. |
| Diff vs current `develop` HEAD | <None — untouched since merge-base / describes the real overlap and whether it's a true conflict or disjoint hunks> |
| Recommended merge proposal | <Merged as-is / union of both sides / needs a fix — with the verification evidence inline> |
| Actual merge proposal | Soon |
| Pending proposal | <None, or what's still undecided> |
| Local merge conflict | Yes / No |
| GitHub merge conflict | Yes / No |

<repeat per file — combine files that share the exact same mechanism/rationale
into one shared block rather than repeating near-identical prose>

### Verification

<Summary of build/test commands run and their results, or a pointer to the
deep-verification comment for full detail.>

**Local vs. GitHub agree**: <one line on whether local conflict analysis
matches GitHub's own status.>
```

## Hard rules for this template

- **Default to this transposed per-file key/value table**, not one wide table
  with a row per file — only use a normal wide table when the field list is
  genuinely short (2-4 columns).
- **Every "Actual merge proposal" cell is literally `Soon`** on this initial
  post. This is Umer's field to fill later, per-file, once he's made a call —
  never pre-populate it with your own trial-merge outcome. Grep the drafted
  body for `Actual merge proposal | ` and confirm every row says `Soon`
  before posting.
- The "Functionality — how & why" row sits right after "Diff" and is filled in
  on the initial post (it's your own analysis of the diff, not a
  prediction/outcome field — unlike "Actual merge proposal").
