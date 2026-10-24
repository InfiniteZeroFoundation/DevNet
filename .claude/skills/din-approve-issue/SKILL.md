---
name: din-approve-issue
description: Use when a maintainer asks to approve, vet, or sign off on a GitHub issue in InfiniteZeroFoundation/DevNet before anyone implements it — "approve issue #N", "run din-approve-issue on 179", "does issue N have merit", "verify the plan in issue N". Any maintainer can run it, as long as they didn't open the issue and aren't its intended implementer (checked first with `.claude/scripts/din_peer_check.py`); mechanism-design issues also need @umeradl's sign-off. Checks every factual claim in the issue (file:line refs, function names, "the contract doesn't have X", "the ABI already has Y", "no command exists for Z") against `origin/develop`, not the local working tree. Then judges whether the proposed plan is sound, complete, and correctly scoped. Posts one verdict comment (Approved / Approved with amendments / Changes requested / Not approved) and, on approval, applies the `Approved` label. Not for PRs (`din-pr-review`) or for closing task discussions (`din-task-close`).
---

# DIN issue approval

Issues in this repo often come with a full plan ("Problem → Proposed change →
Out of scope → Verification"), and many are drafted with Claude's help. Before
anyone implements one, a peer signs off ([`Developer/MAINTAINING.md`](../../../Developer/MAINTAINING.md)
No. 5.1): someone who didn't open the issue and won't implement it.
Approval means someone ran every factual claim against the real code and
thought through what the plan leaves out. Reading the text and agreeing
with it is not approval. This skill does that check and records the verdict on the issue.

## 0. Hard rules

- **Peer check first.** "The operator" is the active `gh` user. Before
  anything else:
  ```bash
  python3 .claude/scripts/din_peer_check.py issue-approve <N>
  ```
  `REFUSE` means the operator opened the issue or is assigned to it. Stop,
  say so, and suggest a maintainer from MAINTAINING No. 3. Never switch `gh`
  accounts to get past it — logins listed together in
  `.claude/scripts/din-maintainers.json` are one person. If the issue names
  its implementer in the body rather than as an assignee, apply the same rule
  by hand.
- **Mechanism-design issues** (slashing, tokenomics, fees, scoring) need
  @umeradl's approval (MAINTAINING No. 5.1, mechanism sign-off). If the
  operator isn't `umeradl`, post the verdict as usual, but for **Approved** /
  **Approved with amendments** end it with "Mechanism sign-off needed from
  @umeradl before implementation" and don't add the label — `umeradl` adds it
  when signing off. If Umer opened the issue himself, the mechanism sign-off
  comes from @abrahamnash (recorded in a comment that cc's him).
- **Verify against `origin/develop`, never the working tree.** Run
  `git fetch origin develop` and read files with `git show origin/develop:<path>`
  / `git grep <pattern> origin/develop -- <paths>`. The `develop` checkout
  usually has uncommitted work in progress (sometimes the issue's own fix,
  half done). That work must not count as evidence for or against a claim.
  Record `git rev-parse --short origin/develop` and cite it in the comment.
- **Foundry is canonical.** Check contract claims against `foundry/src/`;
  `hardhat/contracts/` and `cache_model_0` ABIs lag behind. A hardhat-only
  mismatch is at most a note, not a blocker.
- **Never write `#N`** in the comment. Write "No. N".
- **Never fabricate GitHub IDs or SHAs.** Fetch them.
- **`-F body=@<file>`**, never `-f`, and re-fetch after posting to check the
  body arrived intact.
- **Don't close, reassign, or edit the issue body.** The skill only comments
  and labels. If the verdict is "Not approved", the author or a peer decides
  whether to close it as not planned (MAINTAINING No. 5.2).
- **Show the draft comment to the operator and wait for a go-ahead before
  posting**, unless they have already said to post directly this session.

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
- **Consistency with recorded decisions:** check `Developer/MECHANISM_DESIGN.md`,
  `Developer/design/`, `Developer/ROADMAP.md` and the decision comments on
  related issues and Discussions for standing calls (for example: burning
  applies to DIN only — ETH "burn" shares go to the Treasury; DIN-DAO is
  deferred until after mainnet; foundry is canonical, hardhat lags).
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

## 7. Post and label (after the operator's go-ahead)

```bash
gh api repos/InfiniteZeroFoundation/DevNet/issues/<N>/comments -F body=@<draft> --jq .html_url
gh api repos/InfiniteZeroFoundation/DevNet/issues/<N>/comments --jq '.[-1] | {html_url, user: .user.login, body_start: .body[:80]}'
```

Post through `gh api`, not `gh issue comment`: for `gh issue comment`, `-F`
means `--body-file <path>`, so `-F body=@<draft>` fails and posts nothing.
Confirm `user` is the operator and the body starts with `## Approval review`.
Add the label only after that check passes.

For **Approved** / **Approved with amendments**, add the label (unless it's a
mechanism issue still waiting on @umeradl, see section 0):

```bash
gh issue edit <N> --repo InfiniteZeroFoundation/DevNet --add-label Approved
```

The `Approved` label must already exist. If `gh label list` doesn't show it,
ask the operator before creating it. For the other two verdicts, don't label.

## 8. Report back

Give the operator the verdict, the comment URL (fetched), the label change
(or that it waits on the mechanism sign-off), and the amendments list in one
line each.
