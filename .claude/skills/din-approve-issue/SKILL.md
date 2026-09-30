---
name: din-approve-issue
description: Use when Umer asks to approve, vet, or sign off on a GitHub issue in InfiniteZeroFoundation/DevNet before anyone implements it — "approve issue #N", "run din-approve-issue on 179", "does issue N have merit", "verify the plan in issue N". Must run as the `umeradl` GitHub account. Checks every factual claim in the issue (file:line refs, function names, "the contract doesn't have X", "the ABI already has Y", "no command exists for Z") against `origin/develop`, not the local working tree. Then judges whether the proposed plan is sound, complete, and correctly scoped. Posts one verdict comment (Approved / Approved with amendments / Changes requested / Not approved) and, on approval, applies the `Approved` label. Not for PRs (`din-pr-review`) or for closing task discussions (`din-task-close`).
---

# DIN issue approval

Issues in this repo often come with a full plan ("Problem → Proposed change →
Out of scope → Verification"), and many are drafted with Claude's help from
the `umermjd11` account. Before anyone implements one, `umeradl` signs off.
Approval means someone ran every factual claim against the real code and
thought through what the plan leaves out. Reading the text and agreeing
with it is not approval. This skill does that check and records the verdict on the issue.

## 0. Hard rules

- **Run as `umeradl`.** Before anything else:
  ```bash
  gh api user --jq .login
  ```
  If it is not `umeradl`, run `gh auth switch --user umeradl` and re-check.
  If the switch fails (account not logged in), stop and tell Umer. Don't fall
  back to another account. If you switched, say so in the final report. The
  `umermjd11` fork workflow switches back at the end of its own step, so leave
  `umeradl` active.
- **Verify against `origin/develop`, never the working tree.** Run
  `git fetch origin develop` and read files with `git show origin/develop:<path>`
  / `git grep <pattern> origin/develop -- <paths>`. The `develop` checkout
  usually has uncommitted work in progress (sometimes the issue's own fix,
  half done). That work must not count as evidence for or against a claim.
  Record `git rev-parse --short origin/develop` and cite it in the comment.
- **Foundry is canonical.** Check contract claims against `foundry/src/`;
  `hardhat/contracts/` and `cache_model_0` ABIs lag behind
  (`foundry-canonical-hardhat-stale`). A hardhat-only mismatch is at most a
  note, not a blocker.
- **Never write `#N`** in the comment. Write "No. N".
- **Never fabricate GitHub IDs or SHAs.** Fetch them.
- **`-F body=@<file>`**, never `-f`, and re-fetch after posting to check the
  body arrived intact.
- **Don't close, reassign, or edit the issue body.** The skill only comments
  and labels. If the verdict is "Not approved", Umer decides whether to close.
- **Show the draft comment to Umer and wait for a go-ahead before posting**,
  unless he has already said to post directly this session.

## 1. Fetch the issue

```bash
gh issue view <N> --repo InfiniteZeroFoundation/DevNet \
  --json number,title,author,body,labels,state,comments,createdAt
```

Read existing comments too. A prior review or later amendment by the author
changes what needs checking. If the issue is closed or already carries
`Approved`, stop and ask.

## 2. Extract the claims

Go through the body and list every **checkable** statement as a separate line:

- file:line references ("`dincli/cli/dinrep.py:401` calls `withdrawFees`")
- existence/absence ("the contract has no `setDAOAdmin`", "dincli has no
  command for X", "no test covers Y")
- behaviour ("`sweepFeesToRouter` sends the whole balance", "deploy wires X")
- artifact state ("the bundled ABI already has `feeRouter`")
- cross-refs ("PR No. 175's follow-up already removed these from the doc")
- conflict claims ("PR No. 29 / No. 72 touch this file")

Opinions and the plan itself go to step 4, not here.

## 3. Verify each claim

Use the cheapest real check that settles it, for example:

```bash
R=origin/develop
git show $R:<path> | sed -n '<a>,<b>p'                     # line refs
git show $R:<path> | sed -n '/function foo/,/^    }/p'       # function bodies
git grep -n "<symbol>" $R -- foundry/src dincli tests Documentation/public
python3 -c "import json,sys;d=json.load(open(sys.argv[1]));d=d.get('abi',d);print(sorted(x.get('name','') for x in d))" <(git show $R:dincli/abis/<C>.json)
gh api --paginate repos/InfiniteZeroFoundation/DevNet/pulls/<P>/files --jq '.[].filename'   # PR file lists
```

`gh pr view --json files` caps at 100 files, and `gh pr diff` fails over
20k lines. Use the paginated `pulls/<P>/files` endpoint for any conflict
claim.

Mark each claim ✅ verified, ⚠️ partly right / imprecise (say what's off), or
❌ wrong. An off-by-a-few line ref is ⚠️. A wrong function name or a false
"doesn't exist" is ❌.

## 4. Judge the plan's merit

Follow what the proposed change would actually do on-chain or at runtime,
one level further than the issue did. Questions that have caught real gaps:

- **Where does the value/state end up?** E.g. for a fee sweep, follow the
  ETH into the router. Does any function let it out again, or does it
  accrue in a bucket with no consumer yet?
- **Does it remove something load-bearing?** For each removal, grep for
  callers in `dincli/`, `tests/`, `foundry/script/`, docs, and skills.
- **Does the contract already guard what the CLI plans to pre-check?** If
  so, the CLI check is only worth it for a clearer error. With
  `build_and_send_tx`, a revert surfaces as an opaque gas-estimation
  failure, so a pre-check with a clear message usually is worth it.
- **Access control:** who can call the target function (`onlyOwner`, etc.)?
  Is that the role whose CLI the command lives under?
- **Consistency with recorded decisions:** check memory and `Developer/` for
  standing calls (e.g. `eth-burn-din-only`, `p3-issues-defer-fee-changes`,
  `din-dao-deferred-post-mainnet`, `foundry-canonical-hardhat-stale`).
- **Tests and verification:** does the test plan cover the failure paths?
  Does it follow an existing test file's style? Is the new test file named
  for what it covers?
- **Scope:** is anything in "Out of scope" actually required for the change
  to be correct? Is anything in scope better split out?

## 5. Verdict

| Verdict | When |
|---|---|
| **Approved** | All claims ✅, plan sound as written. |
| **Approved with amendments** | Claims hold. Plan is right but needs specific, small additions (listed as numbered items the implementer must fold in). |
| **Changes requested** | A ❌ claim the plan depends on, or a design gap that needs the author to rethink part of the plan. |
| **Not approved** | Premise is false or the change conflicts with a recorded decision. |

## 6. Draft the comment

Write it to the scratchpad. Structure:

```markdown
## Approval review: <Verdict>

Verified against `origin/develop` @ `<short sha>`.

### Claims
| Claim | Result | Evidence |
|---|---|---|
| ... | ✅ | `foundry/src/X.sol:511`: ... |

### Merit
<2-5 sentences: why the change is worth doing, and what tracing it one step further showed.>

### Amendments   <!-- only for "with amendments" / "changes requested" -->
1. ...
2. ...

### Conflicts
<open PRs touching the same files, from the paginated file list, or "None found">
```

Keep evidence to file:line plus a short quote. Don't paste whole function
bodies. Use "No. N" for every issue/PR number. Run
`grep -n '#[0-9]' <draft>` before posting; the only hits allowed are inside
code spans or URLs.

## 7. Post and label (after Umer's go-ahead)

```bash
gh issue comment <N> --repo InfiniteZeroFoundation/DevNet -F body=@<draft>   # or: gh api repos/.../issues/<N>/comments -F body=@<draft>
gh api repos/InfiniteZeroFoundation/DevNet/issues/<N>/comments --jq '.[-1] | {html_url, user: .user.login, body_start: .body[:80]}'
```

Confirm `user` is `umeradl` and the body starts with `## Approval review`.

For **Approved** / **Approved with amendments**, add the label:

```bash
gh issue edit <N> --repo InfiniteZeroFoundation/DevNet --add-label Approved
```

The `Approved` label must already exist. If `gh label list` doesn't show it,
ask Umer before creating it. For the other two verdicts, don't label.

## 8. Report back

Give Umer the verdict, the comment URL (fetched), the label change, the
amendments list in one line each, and whether `gh auth` was switched.
