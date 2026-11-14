---
name: din-close-issue
description: Use when deciding whether a GitHub issue in InfiniteZeroFoundation/DevNet can be closed — "close issue N", "can issue N be closed", "is issue N done", "run din-close-issue on 195", or a batch "close issues 159-161". Any maintainer can run it, as long as they didn't implement the issue (checked first with `.claude/scripts/din_peer_check.py`). Gathers the full context (issue body, every comment including the `din-approve-issue` review and its amendments, linked PRs and their review/outcome comments, sub-issues, follow-up commits) and verifies every proposed change, amendment and verification item against `origin/develop`. It never takes a comment that says "done" or "landed" as proof. If nothing remains, it posts a closing comment and closes the issue as completed. If anything remains, it posts a status-update comment listing done vs. remaining and leaves the issue open. Not for task Discussions (`din-task-close`), pre-implementation sign-off (`din-approve-issue`), or PR review (`din-pr-review`).
---

# DIN issue closure

Most issues in this repo are implemented by a PR merged into `develop`. `develop`
became the default branch on 2026-10-29. A PR merged after that with a closing
keyword closes its issue automatically. Issues whose PRs merged before then never
auto-closed and are closed by hand. This skill does the closing, and it also
re-checks auto-closed issues. It proves that everything the
issue asked for is on `develop`, then either closes the issue with one comment
that recaps the evidence, or posts a status update that says exactly what is
done and what is left, and leaves the issue open.

This is the issue counterpart of `din-task-close`. The verification discipline
is the same. The differences: the source of truth is the issue body plus its
approval amendments rather than a task file's Deliverables list, and an issue
that can't be closed gets a posted status-update comment instead of only a
report back to the operator.

The process is [`Developer/MAINTAINING.md`](../../../Developer/MAINTAINING.md)
No. 5.2: closing as completed is a peer's check, not the implementer's.

## 0. Hard rules

- **Peer check first.** "The operator" is the active `gh` user. Before
  anything else:
  ```bash
  python3 .claude/scripts/din_peer_check.py issue-close <N>
  ```
  `REFUSE` means the operator implemented it: they're assigned, or they
  authored a merged PR that references it. They may still post a progress
  note, but the closing check goes to a peer (MAINTAINING No. 5.2). Stop and
  name one. Never switch `gh` accounts to get past it. For a batch, run it per
  issue and hand off only the refused ones.
- **Verify against `origin/develop`, never the working tree.** Run
  `git fetch origin develop` and read files with `git show origin/develop:<path>`
  or `git grep <pattern> origin/develop -- <paths>`. Local uncommitted or
  unpushed work doesn't count: an issue is done only once the work is on the
  remote. Record `git rev-parse --short origin/develop` and cite it in the
  comment.
- **Verify against code and merge state, never against thread claims.**
  "Implemented", "fixed" or "landed" in a comment has meant an open, unmerged
  PR branch before. Each item needs its own real check: a read or grep of the
  file on `origin/develop`, or `gh pr view <P> --json state,mergedAt,baseRefName`
  showing `MERGED` into `develop`.
- **Foundry is canonical.** Check contract claims against `foundry/src/`.
  `hardhat/contracts/` and the `cache_model_0` ABIs lag behind. A hardhat-only
  gap blocks closure only if the issue explicitly scoped hardhat in.
- **Never write `#N`** in anything GitHub renders. Write "No. N". Before
  posting, run `grep -n '#[0-9]' <draft>`. The only hits allowed are inside
  code spans or URLs.
- **Never fabricate GitHub IDs or SHAs.** Fetch commit SHAs (`git rev-parse`),
  comment URLs and CI run ids. Never pattern-match them from nearby real ones.
- **Post with `gh api ... -F body=@<file>`, never `-f`, and never `gh issue
  comment -F body=@<file>`** (there `-F` is `--body-file` and the post fails;
  see step 7). Fetch the comment again after posting
  and check that the body arrived intact.
- **Run `git status --short` and `git diff --stat` repo-wide** before posting,
  so stray local edits from verification can't leak into a "verified on
  develop" claim.
- **Don't edit the issue body, reassign, or change labels.** The skill
  comments, and it closes the issue when the verdict is closable. Nothing else.
- **Invoking the skill is the go-ahead to post.** The exception is a judgment
  call (see step 5). In that case show the operator the draft and wait.

## 1. Fetch the full context

```bash
R=InfiniteZeroFoundation/DevNet
gh api repos/$R/issues/<N> --jq '{number,title,state,state_reason,user:.user.login,labels:[.labels[].name],body}'
gh api --paginate repos/$R/issues/<N>/comments --jq '.[] | {id, user: .user.login, created_at, html_url, body}'
# PRs and issues that reference this one (cross-references, "Closes"/"Fixes" mentions)
gh api --paginate repos/$R/issues/<N>/timeline \
  --jq '.[] | select(.event=="cross-referenced") | .source.issue | {number, title, state, pr: (.pull_request != null), merged_at: .pull_request.merged_at}'
# sub-issues (Umbrella issues)
gh api repos/$R/issues/<N>/sub_issues --jq '.[] | {number, title, state}' 2>/dev/null
```

If the issue is already closed: when a closing keyword closed it automatically
(the timeline shows `closed` by a merged PR or commit), run the full check anyway.
If it's not done, reopen it (`gh issue reopen <N>`) with the status-update comment
from step 6. If someone closed it by hand, stop and ask.

Read every comment. Pay particular attention to:

- **The `## Approval review` comment** from `din-approve-issue`. Its numbered
  **Amendments** are part of the scope, as binding as the body.
- **Later scope changes by a maintainer or the author** ("drop Part C", "moving X to
  issue No. M"). An item that was explicitly moved out doesn't block closure,
  but the comment should say where it went.
- **Linked PRs.** For each PR, also read its `din-pr-review` verification,
  merge-proposal and outcome comments. The outcome comment often lists what
  was deliberately left out or deferred.

## 2. Build the checklist

From the issue body and the context above, list every item that "done" has to
cover, one line each:

- each **Proposed change** / **Part** / fix item in the body
- each **approval amendment**
- each **Verification** item the body lists (tests to add, commands that must
  pass, doc updates)
- for **Umbrella** issues: each sub-issue or task-list entry (`- [ ]`)
- anything added in scope by a later comment

Out-of-scope items aren't checklist items. Collect them separately for step 6
so the comment can say whether each one is tracked anywhere.

## 3. Verify the PRs

For each PR that claims to implement part of the issue:

```bash
gh pr view <P> --repo $R --json state,mergedAt,baseRefName,mergeCommit,isDraft
git log --oneline origin/develop --grep="<P>" -i        # merge commit and follow-ups
```

The PR must be `MERGED` into `develop`. Older PRs and path-B merges were
merged by hand (`din-pr-merge` path B), so the GitHub state can say `CLOSED`
while the work is on `develop` in a `merge: PR No. <P> ...` commit. In that case find the commit
with `git log origin/develop --grep` and cite it. A PR that is open, a draft,
or closed with no merge commit on `develop` carries nothing.

If the PR review flagged blocking items, check that each fix is actually on
`origin/develop` by reading the fix commit. A "fixed" reply is not evidence.

## 4. Verify every checklist item on `origin/develop`

Use the cheapest real check that settles it:

```bash
D=origin/develop
git show $D:<path> | sed -n '<a>,<b>p'
git show $D:<path> | sed -n '/function foo/,/^    }/p'
git grep -n "<symbol>" $D -- foundry/src foundry/test foundry/script dincli tests Documentation
git log --oneline $D -- <path>                          # later commits that touched it
```

For items that name tests or require a build to pass, the green `develop`
push CI run for the merge commit (or a later one) counts as evidence:

```bash
gh run list --repo $R --branch develop --event push --limit 10 --json databaseId,headSha,conclusion,url
```

If no green run covers the commit, run the relevant suite yourself in a clean
worktree of `origin/develop`: real via_ir `forge build` (the plain build no
longer compiles `develop`), `forge test --match-contract <Suite>`, and
`"$DIN_PY" -m pytest -m "not integration"` (`source .claude/scripts/din-env.sh`).
Never run them in the `develop` checkout. The `tests/dincli/` integration
suite counts only from a green manual **Full GI** workflow run on the commit,
or a local run (MAINTAINING No. 4.9).

Mark each item ✅ done (with evidence), ❌ missing, or ↪️ moved out of scope
(with where it went).

**Watch for deliberate deviations.** If an item was implemented in the merged
PR but is missing or different on `develop` now, check `git log` on the path
for a later commit that explains why before calling it a gap. A deliberate
change backed by a commit (or by a recorded decision such as
a decision comment on the issue or in `Developer/MECHANISM_DESIGN.md`) counts
as ✅ with the deviation named. An unexplained one is ❌.

## 5. Verdict

| Verdict | When | Action |
|---|---|---|
| **Closable** | Every item is ✅ or ↪️ with a destination. | Closing comment, then close as `completed`. |
| **Not closable** | Any ❌. | Status-update comment. Leave open. |
| **Judgment call** | For example: the only gap is small and could become a follow-up issue instead; an item was dropped silently with no comment or commit; an amendment reads ambiguously. | Show the operator the draft and the question. Don't post until they answer. |

A partial issue doesn't get closed with caveats. It gets a status update. If
the operator wants the remainder split out, they say so, and the close happens after
the follow-up issue exists so the comment can link it.

## 6. Draft the comment

Write it to the scratchpad. Match the closing comments on issues No. 187,
No. 195 and No. 203: a lead sentence that names the PR and merge SHA, the
by-hand note, then bullets grouped by Part/amendment. Link commits as
`` [`<short>`](https://github.com/InfiniteZeroFoundation/DevNet/commit/<full sha>) ``.

**Closing comment:**

```markdown
Done by PR No. <P>, merged into `develop` as [`<short>`](<commit url>)<, with review fixes in [`<short>`](<url>)>. <Outcome/CI link if there is one.> <Only if the PR merged before 2026-10-29, when `develop` became the default branch: "Closing by hand, because closing keywords didn't fire on `develop` merges before then.">

Checked on `origin/develop` @ `<short sha>`:
- **Proposed change 1–N / Part A:** <what exists, file refs, short>
- **Amendments 1–K:** <how each is met; group them where that's natural>
- **Verification:** <test counts / CI run link / doc-link check>
<- **Deviation:** <item> changed in [`<short>`](<url>) because <reason>.>

<Out-of-scope items and follow-ups: "tracked in issue No. M", or "not tracked in an issue yet".>
```

**Status-update comment:**

```markdown
## Status update: not closable yet

Checked on `origin/develop` @ `<short sha>`. <One sentence on what landed so far, e.g. PR No. P merged as `<short>`.>

| Item | Status | Evidence |
|---|---|---|
| Part A: <short> | ✅ | `foundry/src/X.sol:120` ... |
| Amendment 2: <short> | ❌ | no `<symbol>` on develop; PR No. Q still draft |
| Part C: <short> | ↪️ | moved to issue No. M |

### Remaining
1. <each ❌ item, concretely: what is missing and where it would go>

<Blocking PRs and their state, if any.>
```

Keep evidence to file:line plus a short quote. Use "No. N" for every
issue/PR number and run the `#[0-9]` grep.

## 7. Post, and close if closable

```bash
gh api repos/$R/issues/<N>/comments -F body=@<draft> --jq .html_url
gh api repos/$R/issues/<N>/comments --jq '.[-1] | {html_url, user: .user.login}'
gh api repos/$R/issues/<N>/comments --jq '.[-1].body' > <scratchpad>/posted.md
diff <(sed -e '$a\' <draft>) <(sed -e :a -e '/^\n*$/{$d;N;ba' -e '}' <scratchpad>/posted.md) && echo BODY-OK
```

Post through `gh api`, not `gh issue comment`: for `gh issue comment`, `-F`
means `--body-file <path>`, so `-F body=@<draft>` fails with "open
body=@...: no such file or directory" and posts nothing. Confirm that `user`
is the operator and the diff prints `BODY-OK` (GitHub can add a trailing blank
line, which the `sed` strips).

Only for **Closable**, and only after `BODY-OK`. Run the close as a separate
step, or chain it with `&&`, never `;`. On issue No. 206 a failed comment
followed by `; gh issue close` closed the issue with no comment.

```bash
gh issue close <N> --repo $R --reason completed
gh api repos/$R/issues/<N> --jq '{state, state_reason, closed_by: .closed_by.login}'
```

For a batch, handle each issue on its own. Close the ones that qualify, post
status updates on the rest, and don't skip any silently.

## 8. Report back

Tell the operator, per issue: the verdict, the comment URL (fetched), whether
the issue was closed, any deviations named, remaining items in one line each
for status updates, out-of-scope items not tracked anywhere yet, and any issue
handed to a peer because the peer check refused it. Don't update project memory unless asked.
