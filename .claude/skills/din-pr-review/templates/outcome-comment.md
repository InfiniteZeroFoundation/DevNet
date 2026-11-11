# Template 3 — Actual-outcome comment (post-merge, after pushing)

Posted by the merger, only after the merge has actually landed on `develop`.
Goal: replace the table's predictions with what actually happened. Works for
both merge paths (`din-pr-merge`): path A (GitHub-side merge commit, fixes
pushed onto the PR branch first) and path B (local merge + deviation commit).

```
## Actual outcome — PR No. <N> merged [+ fixes / deviation applied]

This supersedes the [pre-merge review comment](<url of Template 2's comment>)
above with what actually happened when resolving this PR against `develop`.

**<One/Two> commit(s), <both/all> on `origin/develop`:**

1. **[`<merge-commit-sha>`](<github commit URL>)** — real merge of this PR
   (merge commit, not squash; path A: merged on GitHub by <merger> after
   <approver>'s approval of `<head sha>`). <Conflict count vs. what was
   predicted, resolution method.> GitHub agrees: PR shows **MERGED**.
2. **[`<fix-or-deviation-commit-sha>`](<github commit URL>)** — path A: the
   review-fix commit pushed onto the PR branch before the merge; path B: the
   follow-up deviation commit on `develop`. (omit if none was needed)

### Files unchanged from the PR (<n> of <N>)

<files that landed exactly as authored, no further changes>

### Files with a real conflict, resolved as a pure union (<n> of <N>) (omit if none)

<files where both sides' additions coexist untouched>

### Files changed by `<fix-or-deviation-commit-sha>` (<n> of <N>) (omit if none)

| File | What changed vs. this PR's merged version |
|---|---|
| `<path>` | <what broke due to develop drift invisible to git's conflict detection, and the fix applied> |

### Why the deviations

<root cause — usually: a net-new file/reference invisible to git's conflict
detection broke against an API/fact that changed on develop after this
branch was cut.>

### Verification

<Path A: the PR's green `CI OK` run on the merged head (link) plus the
`develop` push run. Path B: final local build/test numbers against the
actually-pushed state — full suite counts, not just the touched files — plus
the `develop` push run.>

**Local vs. GitHub agree**: <conflicts resolved as predicted, or note any
surprise.>
```

## Rules that keep biting if skipped

- **Never fabricate a commit hash** — always `git rev-parse <ref>` before
  writing it into the comment, even for a commit made two tool calls ago.
- **Verify by re-fetching after every post/patch** — a `gh api` PATCH can
  silently post the wrong content (`-F` vs `-f`, see main SKILL.md); check
  length/content, not just the command's exit status or returned URL.
- **`git status` repo-wide before posting** — catch stray edits from local
  verification steps (config toggles, scratch files) before they leak into
  what you're claiming as "verified."
- If the PR being closed-in-favor-of-another or landed at a different path
  than its own diff (e.g. relocated docs, superseded PR), say so explicitly
  and note that GitHub's own merge-detection won't fire — don't let the
  comment imply an auto-merge that didn't happen.
