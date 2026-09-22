---
name: din-task-close
description: Use when deciding whether a Tasks-category GitHub Discussion for a `Developer/tasks/task_*.md` file can be closed — "can task_N be closed", "close discussion #N", "is task_<id> done", or a batch "can tasks 6-10 be closed" ask. Verifies every deliverable in the task file's own checklist and every PR it names against the real state of `develop` (not against discussion comments claiming "done"/"landed" — contributors have said that about unmerged branches before), then either posts a closing comment and closes the discussion as Resolved, or reports exactly what's still blocking and leaves it open. Not for reviewing a PR itself (`din-pr-review`) or for the mechanical per-file merge follow-through (`merge-fix-comment-update`).
---

# DIN task-discussion closure

Every contributor task (`Developer/tasks/task_*.md`) gets one Discussion in the
`Tasks` category, opened when the task is assigned. This skill is the closing
half of that lifecycle: prove every deliverable actually landed on `develop`,
post one comment that recaps the evidence, and close the discussion — or, if
something's still missing, say exactly what and leave it open rather than
closing on the strength of a comment thread that says "done."

**Discussion numbers do not match task numbers 1:1.** task_210726_5 is
discussion #47, task_100926_11 is discussion #135, etc. — always resolve the
number, never assume task N ↔ discussion N.

## 0. Hard rules

- **Verify against code and merge state, never against discussion-thread
  claims.** "Landed"/"implemented" in a comment has meant "pushed to an open,
  unmerged PR branch" before (task_300726_8/#67 — Santiago's comments said
  landed, `git ls-tree origin/develop` showed the directories didn't exist).
  Every deliverable needs its own real check: a `grep`/`sed -n` read of the
  actual file on `develop`, or `gh pr view <N> --json state,mergedAt` showing
  `MERGED`, not a comment saying so.
- **Never fabricate a GitHub-assigned ID.** Discussion node id, `discussioncomment-N`
  URLs, commit SHAs — always fetch fresh (`gh api graphql`, `git rev-parse`),
  never pattern-match nearby real ones.
- **`gh api`/`gh api graphql` file-sourced comment bodies need `-F body=@<path>`,
  not `-f`.** Lowercase posts the literal string `@/path/...`. Re-fetch after
  posting and check the actual body content, not just the mutation's return
  value.
- **`git status --short` + `git diff --stat` repo-wide** before posting the
  closing comment — catches stray edits from local verification before they
  leak into a "verified against develop" claim.
- **Never write `#N`** for issue/PR/discussion numbers inside anything GitHub
  renders — it auto-links to an unrelated item. Write "No. 51", "No. 60", etc.
- **When a deliverable is genuinely unresolved, don't close.** Report the gap
  and stop — same as task_300726_8/#67 and task_220726_7/#50, both explicitly
  left open on a "can these be closed" ask because they depend on PRs still in
  draft. A partial task isn't a reason to close with caveats; it's a reason to
  leave it open and say why.

## 1. Resolve the task file and its discussion number

Given a task id, a discussion number, or a discussion URL, get to both ends:

```bash
# task id -> file
ls Developer/tasks/ | grep <id-or-fragment>

# task id -> discussion number (title always starts "task_<id> — ...")
gh api graphql -f query='
query {
  search(query: "repo:InfiniteZeroFoundation/DevNet task_<id> in:title", type: DISCUSSION, first: 5) {
    nodes { ... on Discussion { number title closed } }
  }
}'

# discussion number -> body, comments, node id (needed later for the mutations)
gh api graphql -f query='
query {
  repository(owner: "InfiniteZeroFoundation", name: "DevNet") {
    discussion(number: <N>) {
      id
      title
      closed
      body
      comments(first: 50) {
        nodes { id body author { login } createdAt
          replies(first: 20) { nodes { body author { login } createdAt } } }
      }
    }
  }
}'
```

If given a bare number with no task file match, or a task with no discussion
found, stop and ask — don't guess which task a number refers to.

## 2. Build the deliverable checklist from the task file itself

Read the task file's own `## Deliverables` section (a `- [ ]` checklist) and
any issues it names (task files typically reference 1-3 GitHub issues in
their title/header). This checklist — not the discussion thread — is the
source of truth for what "done" means. Also note any PRs the discussion
thread names as delivering those deliverables.

## 3. Verify every PR named, against its real merge state

```bash
gh pr view <N> --json state,mergedAt,mergeCommit,baseRefName
```

Must show `"state": "MERGED"` and `baseRefName` = `develop`. A PR still open
or in draft means the deliverables it was supposed to carry are not done,
full stop — regardless of what any comment says about it.

```bash
git log --oneline --all --grep="<N>" -i | grep -i merge   # find the merge commit(s)
```

If Umer's own review comments (posted by `din-pr-review`) flagged blocking
items on that PR, re-check each one was actually fixed on `develop` — read
the fix commit, don't just trust a "fixed" reply in the thread.

## 4. Verify every deliverable against the actual code on `develop`

For each `- [ ]` line in the task file's Deliverables section, check the real
file(s) on `develop` — grep for the function/contract/test named, confirm it
exists and looks like what was asked for (not just that *a* function with a
similar name exists). Common checks for this repo's contract tasks:

```bash
forge build                              # from foundry/ — compiles clean
forge test --match-contract <Suite>      # relevant suite(s) actually pass
grep -n "function <name>" foundry/src/<Contract>.sol
```

**Watch for later deliberate deviations.** Umer sometimes lands a PR then
follows up with his own commit that intentionally changes scope (e.g. scoping
a fee path back to ETH-only after a design direction shifted, per
`p3-issues-defer-fee-changes`/`eth-burn-din-only`-style calls). If a
deliverable that was clearly implemented in the merged PR is now missing on
`develop`, check `git log --oneline -- <path>` for a later commit explaining
why before treating it as a regression — cite that commit in the closing
comment rather than flagging it as broken.

If a deliverable is genuinely missing or a blocking review item was never
actually fixed, stop here — go to step 6, not step 5.

## 5. Post the closing comment

Recap the verification with real evidence — commit SHAs (short, fetched via
`git rev-parse --short`, never guessed), PR numbers, and file/line references
for anything non-obvious. Match the tone/structure of prior closing comments
in this category (discussions #47, #49, #76, #106, #135): a short intro line,
a table or list mapping deliverable → evidence, and an explicit closing
statement. Call out any deliberate deviation caught in step 4 by name.

```bash
gh api graphql -f query='
mutation($discussionId: ID!, $body: String!) {
  addDiscussionComment(input: {discussionId: $discussionId, body: $body}) {
    comment { url }
  }
}' -f discussionId="<id from step 1>" -F body=@<scratchpad path>
```

Re-fetch the comment (`gh api graphql` on the discussion, or the mutation's
own returned `url`) and diff its content against what was intended before
moving on.

## 6a. If everything checks out — close as Resolved

```bash
gh api graphql -f query='
mutation($discussionId: ID!) {
  closeDiscussion(input: {discussionId: $discussionId, reason: RESOLVED}) {
    discussion { closed closedAt stateReason }
  }
}' -f discussionId="<id>"
```

`RESOLVED` is this category's convention (every task discussion closed so far
— #47, #49, #76, #105, #106, #135 — used it; `OUTDATED`/`DUPLICATE` are for
non-task discussions that stopped being relevant rather than got done).

## 6b. If something's still open — report, don't close

State plainly which deliverable/PR is the blocker, cite the evidence (PR
state, missing file/function, unfixed review item), and leave the discussion
open. If asked to close several discussions in one batch and only some
qualify, close the ones that do and report the rest by number with the
specific reason each one stays open — don't silently skip them or close
everything on the strength of the ones that passed. This mirrors the
task_300726_8/#67 and task_220726_7/#50 precedent (left open, flagged, not
closed, on a "6-10 can be closed" instruction that only covered 6-10).

## 7. Report back

Summarize for Umer: which discussion(s) got closed (with links), which PRs/
commits were the evidence, any deliberate deviation called out, and — for
anything left open — the exact blocker. Don't offer to update project memory
yourself unless asked; just make sure the report contains everything needed
for the state to be captured correctly if Umer wants it remembered.
