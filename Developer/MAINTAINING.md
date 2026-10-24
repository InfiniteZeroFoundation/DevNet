# Maintaining DevNet

How maintainers review, merge, approve and close work on this repo. This file is the agreed outcome of [Discussion 208](https://github.com/InfiniteZeroFoundation/DevNet/discussions/208). If you want to change the process, propose it there (or in a new Discussion) and update this file through a PR.

**Maintainers:** [@umeradl](https://github.com/umeradl) (admin), [@Santiagocetran](https://github.com/Santiagocetran), [@robertocarlous](https://github.com/robertocarlous) and [@Abidoyesimze](https://github.com/Abidoyesimze) (Similoluwa), all with Write access. [@abrahamnash](https://github.com/abrahamnash) decides mechanism and product questions with Umer, often off GitHub ([mechanism sign-off](#mechanism-sign-off)).

## 1. The rule

> **Nobody approves, merges or closes their own work. A peer does it.**

| Activity | Author / assignee may do it? | Who does it |
|---|---|---|
| Review a PR (verification and merge-proposal comments) | ❌ | A peer who didn't write it |
| Approve a PR (GitHub "Approve") | ❌ (GitHub blocks this) | A peer |
| Merge a PR into `develop` | ❌ | The peer who reviewed it, or Umer |
| Approve an issue's plan (`Approved` label) | ❌ if you opened it or will implement it | A peer |
| Post a status update on an issue or task | ✅ progress notes are fine | Anyone. The *authoritative* done-vs-remaining check is the peer's |
| Close an issue as completed | ❌ if you implemented it | A peer |
| Close a task Discussion as Resolved | ❌ if it's assigned to you | A peer |
| Write a new task file | ✅ | Anyone, but **assigning** and **closing** it are done by someone else |
| Wiki edits | ✅ for small fixes | A peer reviews anything substantive ([No. 5.5](#55-wiki)) |

Umer's own PRs (opened from the `umermjd11` fork) follow the same rule: one of the other maintainers approves and merges them.

## 2. What GitHub enforces

**`develop` ruleset:**

- Changes land through a pull request.
- 1 approving review from someone other than the author.
- **The most recent push must be approved by someone other than the person who pushed it.** If a reviewer pushes fixes onto your PR, they can't approve it themselves any more. Someone else has to.
- Stale approvals are dismissed when new commits are pushed.
- The `CI OK` check must pass, and the branch must be **up to date with `develop`** before merging.
- Merge commits only. Squash and rebase merges are turned off, so authorship and history survive.
- No force-pushes, no deleting the branch.
- Only the repository admin role can bypass these rules ([No. 4.4](#44-merge-paths)).

**`main` ruleset:** changes go through a PR; no force-pushes, no deleting the branch. `CI OK` isn't required on `main` yet, because [`ci.yml`](../.github/workflows/ci.yml) only runs on `develop`. It becomes required once CI runs on `main`.

**[`.github/CODEOWNERS`](../.github/CODEOWNERS)** requests reviewers automatically by area. It only *requests*: code-owner review is not required, because that would deadlock (two contract owners couldn't merge each other's work if each was the other's only owner). The real gate is the 1-approval rule plus the peer rule.

Everything else in this file is convention, not enforcement.

## 3. Reviewer pool

Tag reviewers by skillset:

| Area | First choice | Also |
|---|---|---|
| `foundry/src/**`, `foundry/script/**`, contract tests | @robertocarlous and @Abidoyesimze review each other | Second sign-off: @umeradl or @abrahamnash ([No. 4.2](#42-review-depth)) |
| `dincli/**`, `tests/**`, docker/IPFS ops, CI (`.github/`) | @Santiagocetran | @umeradl |
| `Documentation/**`, `Developer/**` | @Santiagocetran, @robertocarlous | anyone in the pool |

**Recusal is a valid outcome.** If you're tagged on something outside your depth, reply "out of my depth — @X" and don't approve. Nobody approves just to unblock a PR. A recusal or an escalation is better than a rubber stamp.

## 4. PR review and merge

### 4.1 Picking the reviewer

CODEOWNERS requests reviewers when you open the PR. Check that at least one requested reviewer isn't you or a co-author, and add one by hand if not. The reviewer either takes the PR or replies within **2 working days** with "can't take this — @umeradl". Silence past 2 working days escalates to Umer. There's no fixed rotation. We'll revisit that if third-party PRs stall.

### 4.2 Review depth

- **Any PR touching `foundry/src/**`** (contract logic, storage layout, upgrade paths) needs the peer's review **plus a second sign-off** from @umeradl or @abrahamnash, or from a security reviewer they route it to. Mechanism changes also need the [mechanism sign-off](#mechanism-sign-off) below.
- Docs-only, test-only, Python and tooling PRs need one peer.

**What counts as evidence.** Required checks that are green against an up-to-date `develop` count as evidence for anything CI covers. The reviewer cites the CI run and doesn't re-run it. **Local reproduction is required only for what CI doesn't cover:**

- storage layout and upgrade safety in `foundry/src/**`
- deploy and upgrade scripts in `foundry/script/**`
- `dincli` flows against a live chain or IPFS, until the integration job is a required check ([No. 4.9](#49-ci-as-the-backbone))
- any claimed behaviour that no test exercises

The author's part: a clear description of what changed and why, and tests for the change. The reviewer's part: implementation, design, edge cases and coverage, with a concise write-up of findings and any requested fixes.

#### Mechanism sign-off

Mechanism-design work (slashing, tokenomics, fees, scoring) needs **@umeradl's approval on GitHub**. That applies to the issue's plan ([No. 5.1](#51-issues-approval-before-implementation)) and to every PR that changes a mechanism. @abrahamnash may not reply on GitHub directly, so his sign-off isn't something a PR waits for there. Mechanisms are often discussed with Abraham off GitHub. If you (author or contributor) had such a conversation, summarise its outcome in a comment on the issue or PR and cc @abrahamnash and @umeradl.

**Umer's own mechanism PRs** (from `umermjd11`): `umeradl` can't approve them, because that would be approving his own work ([No. 1](#1-the-rule)). For these PRs, the mechanism sign-off comes from @abrahamnash instead, whether he gives it on GitHub or off it. If he gives it off GitHub, it's recorded in a comment on the PR that cc's @abrahamnash. The PR still needs a peer's approval as usual.

### 4.3 The review record

The reviewer writes three comments on the PR:

1. **Verification comment.** "Claimed / Verified" pairs for every checkable claim in the PR. A claim is verified by linking the CI job that covers it, or by running it locally where [No. 4.2](#42-review-depth) requires that. Never accept "done" or "landed" in a comment as proof.
2. **Merge-proposal table.** Per file: change, lines, diff, functionality (how and why), diff vs current `develop`, recommended merge proposal, actual merge proposal, pending proposal, local/GitHub conflict. "Actual merge proposal" is filled in by whoever performs the merge, not at review time.
3. **Outcome comment.** Posted after the merge lands, with the real merge SHA(s), the files that deviated from the PR, and final build/test numbers.

Templates: [`.claude/skills/din-pr-review/templates/`](../.claude/skills/din-pr-review/templates/). Use them with or without Claude.

**Trivial changes** (typo, dead link, comment fix) still need a PR and 1 approval, but a quick approval noting "trivial" replaces the three comments.

### 4.4 Merge paths

- **(A) GitHub-side merge commit — the default.** The reviewer approves, CI is green, the branch is up to date, and the reviewer merges with a merge commit. If the reviewer wants something changed first, they push the fix onto the PR branch (or open a small follow-up PR). The last-push rule then sends the final approval to someone else.
- **(B) Local merge plus follow-up fix commit — exceptional, Umer only.** For PRs that need adapting against a `develop` that has moved (renames, ABI regeneration, docs drift). It needs the admin bypass.

**The admin bypass** is for emergencies and path B only. Each use gets a one-line reason in [Discussion 170](https://github.com/InfiniteZeroFoundation/DevNet/discussions/170), followed by a normal reviewed PR where possible.

### 4.5 Attribution

Merges keep the PR author as the commit author. Any deviation commit the merger writes credits the PR author with a `Co-Authored-By:` trailer. Never squash away someone's authorship.

### 4.6 A red `develop` after a merge

Whoever merged owns that push's CI run and makes sure it's fixed **the same working day**. The author is pinged first and fixes it if available. If they aren't, the merger fixes it on top or reverts it. [Discussion 170](https://github.com/InfiniteZeroFoundation/DevNet/discussions/170) stays the incident log, and its "~6h red plus commits on top" escalation rule applies to everyone.

### 4.7 Reverts

Any maintainer may revert a merge that breaks `develop` without waiting for the author. The revert goes through a PR and peer approval like anything else, unless Umer uses the emergency bypass. The author re-lands the change in a new PR.

### 4.8 Labels

`Reviewed` once comments 1–2 are posted. `Merged Locally`, `merged` or `Partially Merged` after the merge. `Hurry to Merge` / `No Hurry To Merge` for priority. `Draft`, `Deferred`.

### 4.9 CI as the backbone

The aim is for CI to carry repeatable verification so reviewers can focus on judgment. The isolated integration harness has landed ([PR 213](https://github.com/InfiniteZeroFoundation/DevNet/pull/213)); a non-blocking full-GI job is in review ([PR 242](https://github.com/InfiniteZeroFoundation/DevNet/pull/242)). The integration job becomes a required check once it has run a full GI green on `develop` for a week. Further CI stages (post-merge checks, a shared develop/testnet environment, validation on `develop` → `main` PRs) are tracked in their own issue.

## 5. Other administrative work

### 5.1 Issues: approval before implementation

A new non-trivial issue gets a verdict comment (*Approved / Approved with amendments / Changes requested / Not approved*) before anyone writes code. The verdict checks every factual claim (`file:line` references, "function X doesn't exist", "the ABI already has Y") against `origin/develop`. On approval, add the `Approved` label. **The approver can't be the issue's author or its intended implementer.** Mechanism-design issues (slashing, tokenomics, fees, scoring) also need @umeradl's approval, because they're product decisions ([mechanism sign-off](#mechanism-sign-off)).

### 5.2 Issues: status updates and closing

Anyone may post progress. Closing as **completed** needs a peer to check every proposed change, every approval amendment, every verification item and every linked PR against `origin/develop`, then post a closing comment listing what landed and where (SHAs). If anything remains, post a "done vs. remaining" status comment and leave the issue open. Closing as **not planned** or **duplicate**: anyone may do it, with a one-line reason and a link to the duplicate.

### 5.3 Tasks

Tasks are `Developer/tasks/task_DDMMYY_N.md` files, each with a Tasks-category Discussion.

- **Writing:** anyone may draft one, following the existing header format (ID / Assigned to / Created / Status / Roadmap ref / Dates). Task files land on `develop` through a PR, so they get peer review too.
- **Assigning:** nobody assigns themselves without Umer or the peer agreeing in the Discussion. Anything involving compensation or a new contributor stays with Umer and Abraham.
- **Status updates:** the assignee posts progress in the task Discussion. The peer posts the authoritative "verified done vs. remaining" check.
- **Closing:** a peer verifies every deliverable in the task file's checklist and every PR it names against `develop`, closes the Discussion as Resolved with a closing comment, and updates the task file's `Status:` line in a follow-up PR. A task can't close while a PR it depends on is still open or in draft.

### 5.4 Docs syncing on merge

Whoever merges a PR checks that:

- `Documentation/` still describes `develop`;
- bundled ABIs in `dincli/abis/` were regenerated if a contract interface changed (see [CONTRIBUTING.md](CONTRIBUTING.md#submitting-prs));
- `Developer/BACK_LOG.md` and `Developer/ROADMAP.md` entries the PR resolves are updated, or a follow-up issue is filed.

### 5.5 Wiki

The wiki has no PR mechanism, so:

- Typos, broken links, and syncing a page to something already merged on `develop`: just edit it.
- New pages, restructuring `_Sidebar.md`, or anything describing a mechanism: post the draft (or a diff) as a comment in a Discussion and get a peer 👍 before publishing.
- Conventions: links into the repo use `blob/develop/...`; planned components carry the 📋 Planned banner; no assignee names or week-level dates on public pages; pages end with "Further reading" links into `Documentation/`.

### 5.6 Discussions

Anyone may answer, label, or lock stale threads. Closing a design or Ideas Discussion as decided needs a comment that records the decision and where it was implemented. Mechanism decisions are recorded by Umer or Abraham.

## 6. What stays with Umer

- Pushing to or releasing on `main`.
- Anything on Sepolia or other live networks: platform deploys, upgrades, DIN-Representative keys and actions, slasher authorisations.
- Repo settings, rulesets, secrets and access changes.
- Contributor onboarding, compensation, and HR-side task approval (with Abraham).
- Roadmap priority calls and final mechanism-design decisions (with Abraham).
- The emergency bypass on `develop` ([No. 4.4](#44-merge-paths)).

## 7. Edge cases

- **Co-authored PRs** (two maintainers both committed to it): neither of them may approve it. It goes to a third maintainer or Umer.
- **The reviewer pushes substantial fixes onto a PR:** they've become a co-author. The final approval comes from an eligible reviewer who is neither the PR author nor anyone who contributed to those fixes: another maintainer, or Umer. The reviewer doesn't merge their own fixes unreviewed.
- **Disagreement between reviewer and author:** discuss it on the PR. If you're not converging after a round or two, tag Umer, who decides. Nobody merges over an unresolved "Changes requested".
- **Urgent fix while the peer is offline** (for example a red `develop` blocking everyone): open the PR and tag both the peer and Umer. Whoever answers first approves it. Never merge unreviewed.
- **PRs from other contributors** (external forks, new contributors): any maintainer who didn't co-author them may review and merge them. The `foundry/src/**` second sign-off still applies.

## 8. Tooling

The `din-*` Claude Code skills under [`.claude/skills/`](../.claude/skills/) implement this workflow, and any maintainer can run them as themselves. Setup and the shared scripts: [`.claude/scripts/README.md`](../.claude/scripts/README.md). Every skill that approves, merges or closes first runs [`din_peer_check.py`](../.claude/scripts/din_peer_check.py), which refuses when the active `gh` user is the author, assignee, implementer or a co-author ([No. 1](#1-the-rule)). Logins that belong to one person, such as `umeradl` and `umermjd11`, count as one.

| Step | Skill |
|---|---|
| Review a PR: the three comments ([No. 4.3](#43-the-review-record)), then approve, request changes or recuse | `din-pr-review` |
| Apply review fixes, per file | `merge-fix-comment-update` |
| Build and test the fixed tree the way CI does, then update the merge-proposal comment | `din-merge-build-test` |
| Merge: path A (GitHub-side merge commit) or path B (admin local merge) ([No. 4.4](#44-merge-paths)), own the `develop` CI run, post the outcome comment | `din-pr-merge` |
| Admin direct push to `develop` (path B, emergencies), with a local CI mirror and a logged bypass reason | `din-push-develop` |
| Approve an issue's plan ([No. 5.1](#51-issues-approval-before-implementation)) | `din-approve-issue` |
| Close an issue as completed, or post done vs. remaining ([No. 5.2](#52-issues-status-updates-and-closing)) | `din-close-issue` |
| Close a task Discussion ([No. 5.3](#53-tasks)) | `din-task-close` |

**When a local build is needed before merging.** A PR that merges as-is needs no local build: its required `CI OK` runs the full pipeline on GitHub's merge of the PR into `develop`, and the branch has to be up to date, so that run tests exactly what lands. When a reviewer applies fixes, they run `din-merge-build-test` on the fixed branch before pushing it, so the PR doesn't go red in public. CI then re-runs on the pushed fixes and is the gate again. In path B there's no PR CI for the deviation commit, so the local run and `din-push-develop`'s precheck are the gate.

The skills are a convenience, not a requirement. Following this file and the [templates](../.claude/skills/din-pr-review/templates/) by hand is equally valid.
