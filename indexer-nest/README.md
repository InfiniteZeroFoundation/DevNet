# din-nest

A [nuthatch](https://github.com/nuthatch-org/nuthatch) nest for the DIN protocol contracts, built as a
comparison spike for [InfiniteZeroFoundation/DevNet discussion 150](https://github.com/InfiniteZeroFoundation/DevNet/discussions/150).
It runs against a local anvil deploy of `develop` (409bf2c, which contains b714f17), not the dropped DevNet 1.0 contracts on OP
Sepolia, and it is measured against PR 29's subgraph (613f5b2).

One binary, no Docker or Postgres. Events land in local SQL; `views/*.sql` hold the derived entities.

## Run it

```sh
# in foundry/: the local chain
./anvil.sh --host 127.0.0.1

# in another shell: the platform, one model taken through GI 1 to GIended, then the owner-side
# governance calls (three forge scripts in spike/; it runs forge clean first)
spike/run.sh

# here (indexer-nest/)
nuthatch dev --dir . --listen 127.0.0.1:8289 --state-rpc http://127.0.0.1:8545
nuthatch sql --url http://127.0.0.1:8289 "SELECT * FROM global_iterations"
python3 spike/check.py        # every view against what the scripts did, and the chain where it answers
```

The first script, `NuthatchSpike.s.sol`, is the original run: it stops at GI 1's local-model
submissions. `NuthatchGI.s.sol` takes GI 1 on to GIended in three stages with blocks mined between
(the seed locks wait `disputeSeedDelay` blocks), and `NuthatchGov.s.sol` makes the owner calls the
first two leave out: fee, stake and S5/S6 settings, model stake bounds, the fee router's sources and
splits, a manifest update, a rejected request, an unstake, a slasher removal. Without them most of
the views below have no rows to be checked against.

`abis/` is generated from `forge build`, not hand-edited: `spike/sync-abis.py` rewrites it and
`spike/sync-abis.py --check` exits 1 if it has drifted (see "The ABIs").

The addresses in `nuthatch.toml` are the ones a fresh anvil gives that deploy. A different deploy
means editing them, as with the subgraph's `update-subgraph-addresses.sh`. The `[[calls]]` read
state at the event's block, so `--state-rpc` has to point at a node that keeps it (anvil does).

## What it covers, against PR 29

I read every handler in PR 29 and sorted its 75 entities by what SQL needs to reproduce them:

| | entities | how |
|---|---|---|
| a raw event row | 36 | the event table, columns renamed |
| a view over events | 32 written, 2 dropped | latest per key, running sums, first-seen, joins |
| a contract read at the event's block | 5 | a row-driven `eth_call`, then a view |
| logic SQL cannot express | 0 | |

The 34 are the entities a handler loads, changes and saves again, or keys by a natural id so that a
later event replaces an earlier one. The first count came without a list; the list is below, so it
can be argued with. Two of the 34 (AggregationDispute and TestDataDispute) are not in the nest: see
"Dropped: the dispute views".

### The 32 view-shaped entities

**All 32 are written and match the run.** `python3 spike/check.py` is the check: 55 assertions, all
pass, on `develop` at 409bf2c (run 2026-11-20).

| entity | view | checked on the run | note |
|---|---|---|---|
| Validator | `validators` | yes, with gaps | no `pending_withdrawal`, `withdraw_available_at` or `status` (below) |
| StakeGovernance | `stake_governance` | yes | |
| ModelStakeBounds | `model_stake_bounds` | yes | two calls for model 0, the second stands |
| SlasherRegistration | `slasher_registrations` | yes | one row per (slasher, source contract); removal shown |
| S5GlobalParams | `s5_global_params` | yes | |
| S5RecidivismParams | `s5_recidivism_params` | yes | |
| S6Params | `s6_params` | yes | |
| UnstakeRequest | `unstake_requests` | yes | `claimed` is always false, as PR 29 writes it |
| FeeSource | `fee_sources` | yes | one added, one removed |
| FeeRouterConfig | `fee_router_config` | yes | both splits are JSON tuples, sliced with `json_extract_string` |
| GlobalIteration | `global_iterations` | yes, with differences | below |
| AggregatorRegistration, AuditorRegistration | `registrations` | yes | |
| GIStateTransition | `gi_state_transitions` | yes | GI 1 enters states 5 to 28 once each, in order |
| Tier1Batch | `tier1_batches` | yes | |
| Tier2Batch | `tier2_batches` | yes | |
| T1AggregationSubmission, T2AggregationSubmission | `t1_`, `t2_aggregation_submissions` | yes | |
| T1AggregationCommitment, T2AggregationCommitment | `t1_`, `t2_aggregation_commitments` | yes | |
| SeedLock | `seed_locks` | audit and aggregation kinds only | the dispute kind and every reanchor have no rows |
| TaskCoordinatorGovernance | `task_coordinator_governance` | yes | |
| LocalModelSubmission | `local_model_submissions` | yes | `eligible` filled by EligibilityFinalized |
| AuditBatch | `audit_batches` | yes | `pending_reassignment` is never true on the run |
| AuditScoreSubmission | `audit_score_submissions` | yes | |
| AuditScoreCommitment | `audit_score_commitments` | yes | revealed, score 80, for all nine |
| EligibilityVote | `eligibility_votes` | yes | |
| EligibilityResult | `eligibility_results` | yes | |
| TestDataCommitment | `test_data_commitments` | yes | |
| EncryptedTestDataKeys | `encrypted_test_data_keys` | yes | |
| RewardSplit | `reward_splits` | yes | JSON tuple |
| TaskAuditorGovernance | `task_auditor_governance` | yes | three settings, each from its own event |

"Checked" means the view's rows equal what the scripts did (counts, ids, values, order) and, for the
state the contracts expose, what `cast call` returns at the head. It does not mean compared with a
running subgraph: I did not run graph-node, so no row here was diffed against PR 29's own output.

**Where the written views differ from the subgraph, found while checking:**

- `global_iterations.started_at` is the first `GIStateChanged` of the GI. The subgraph creates the row
  on the first event of any kind for it, which here is `RewardDeposited`, one block earlier (93, not
  94). The view also leaves GI 0 (the setup states) out, where the subgraph has a row for it, and
  carries no `global_model_cid`; `tier2_batches.global_model_cid` has it.
- `validators` has the totals, `active_stake`, `blacklisted`, `jailed`, `jailed_until`,
  `total_withdrawn`, `active_registrations` and `encryption_key`. It has no `pending_withdrawal`,
  `withdraw_available_at` or `status`. The subgraph works `status` out from the minimum stake as it
  stood at that validator's last event, which needs an as-of join I did not write. `active_stake` is
  the closed form described below and ignores how a slash eats a pending withdrawal once active
  stake is gone; no slash happens on the run, so that is untested.
- Rows that need a `LocalModelSubmission` (commitments, submissions, votes, results) are kept only
  when one exists, as the subgraph skips them; the view does not check that it came first.
- The dispute seed locks (`seed_locks` rows of kind `Dispute`) are written from the handlers and no
  row on the run reaches them, so they are unverified. The two dispute entities themselves are not
  in the nest at all (below).

`Validator` was the nearest thing to handler logic. Its active stake floors slashes at zero step by
step, which has a closed form: the final running sum less its lowest negative point. The
`validators` view uses that, and the same form for `active_registrations`.

### Dropped: the dispute views

`AggregationDispute` and `TestDataDispute` were written from the subgraph handlers and never had a row
to be checked against: the full-GI run opens no dispute. They are removed until something exercises
them. The raw event tables they read (`task__dispute_opened`, `task__test_data_dispute_opened` and the
rest) are still in the nest, so no data is lost, only the derived view. Putting them back needs its own
anvil scenario; `foundry/test/DisputeResolution.t.sol` has the call sequence for opening and resolving a
test-data dispute.

### The 5 contract reads

The subgraph's handlers read the registry with `modelRequests`, `getModel`, `manifestRequests`, the
four fee getters and `feeRouter`. Each is a row-driven `[[calls]]` in `nuthatch.toml`, pinned to the
block of the event that triggers it, and a view slices the returned words.

| entity | read | view | checked |
|---|---|---|---|
| Model | `getModel` | `model_record`, `model_contracts`, `models`, `current_manifests` | yes |
| ModelRegistrationRequest | `modelRequests(requestId)` | `model_registration_requests` | yes: one approved, one rejected |
| ManifestUpdateRequest | `manifestRequests(requestId)` | `manifest_update_requests` | yes: one approved, one rejected |
| FeeSnapshot | `openSourceFee()`, `proprietaryFee()`, `openSourceUpdateFee()`, `proprietaryUpdateFee()` | `fee_snapshots` | yes: four granular, one atomic |
| RegistryFeeWithdrawal | `feeRouter()` | `registry_fee_withdrawals` | yes |

Two things about how they are wired. `on_any` needs a `graph` build of nuthatch, so the four fee
getters are declared once per setter event, 16 small `fee_*_on_*` tables, rather than once across the
four. And the SQL surface has no hex-to-number function, so a `uint256` word in a call result is
turned into a `DECIMAL(38,0)` by an expression over its 32 low hex digits, written out in
`views/40-din-reads.sql`; `spike/gen-reads.py` writes that file. It is right for any value under
10^38 and wrong above, which no fee here comes near.

`ManifestUpdateRequest.requester` is the model's owner, as the subgraph derives it. The subgraph falls
back to the transaction's sender when the model is unknown; the nest does not keep senders, so that
case would be NULL. The contract only accepts a request from the owner of a model, so it should not
arise.

## What cannot be reproduced

Nothing in PR 29's schema needed logic SQL cannot express. These are the places where the nest does
not give what the subgraph gives, or where I could not check that it does:

- **Events a task contract emits before it is announced.** 5 on the run, at blocks 39 to 43, before
  `SlasherContractAdded` at 44 and 45. The nest finds task contracts from that event, so it starts
  there. The subgraph starts its templates at `ModelApproved`, which is later still, so it misses
  them too: a loss against the chain, not against the subgraph.
- **One template for two contracts.** A nuthatch child takes one template, so the coordinator and
  auditor ABIs are merged (`abis/DINTask.json`) and their tables share the `task__` prefix; the
  `address` column says which contract a row came from. Views that need the pair read
  `model_contracts`.
- **The gaps listed above:** `validators.pending_withdrawal`, `withdraw_available_at` and `status`;
  GI 0; `global_iterations.started_at`; the two dispute entities (dropped) and the dispute seed locks
  (written, no row).
- **A diff against a running subgraph.** Not done. I did not stand up graph-node and Postgres.

## Answers to umeradl's constraints

[The comment](https://github.com/InfiniteZeroFoundation/DevNet/discussions/150#discussioncomment-19637768),
point by point.

1. **Not the current OP Sepolia contracts.** The nest targets a local anvil (`chain_id = 1337`) with
   the contracts from `forge script` on `develop` at 409bf2c; nothing in it names OP Sepolia or the
   DevNet 1.0 addresses. For DevNet 2.0 when issue 284 lands, the edit is `rpc_urls`, `chain`,
   `chain_id`, and the addresses and `start_block`s in `nuthatch.toml`, from
   `foundry/deployments/<network>.json`.
2. **Task contracts are per model.** Found from `DinCoordinator`'s `SlasherContractAdded`, which every
   task contract triggers before its model can be registered. No contract change. See "Finding the
   task contracts".
3. **Coverage yardstick: PR 29's `schema.graphql`.** The two tables above: 32 view-shaped entities
   written and matching the run (2 more dropped, untested); 5 reads, all 5 matching. The other 36
   of the 75 are raw event tables and are not reviewed here.
4. **Consumer side.** See "dincli's read path" and "Running it in the din-node container".
5. **Reorgs and finality.** See "Reorgs and finality on OP Sepolia". Not exercised on this run:
   nothing here forks the chain.

## Finding the task contracts

Every task contract is authorised as a slasher before a model can be registered, and `DinCoordinator`
emits `SlasherContractAdded(address)` when it is. The nest's factory reads that event, so no contract
change is needed. Both task contracts were found at blocks 44 and 45 of the run. Which model a pair
belongs to comes from `getModel` (`model_contracts`).

## Measured on the run

On `develop` at 409bf2c the chain held 269 logs (head at block 240). The nest caught up at block 214
with 244 events, in under a second; at this size that measures nothing. The difference from 269 is the
logs it does not index, as before: `Upgraded` and `AdminChanged` on the platform proxies, the
implementations' and proxy admins' own events, and task-contract events emitted before
`SlasherContractAdded`. I did not re-count that split on this run.

## The ABIs

`abis/` is a third copy after `dincli/abis/` and `subgraph/abis/`, and I could not avoid it. I tried
the two places it could have read from:

- **`subgraph/abis/` or `foundry/out/` by path.** Nuthatch refuses a path with `..` or an absolute path
  in `abi = ...` ("path-traversal guard"), so `../subgraph/abis/DinToken.json` does not load. A symlink
  inside the nest gets past that guard, but then:
- **The file format.** Both `subgraph/abis/*.json` and the forge artifacts wrap the ABI as
  `{"abi": [...]}`. Nuthatch wants a bare JSON array and fails with "expected a valid JSON ABI
  sequence".

Two more reasons a straight pointer would not have worked: `subgraph/abis/` has no `DinEmission.json`,
and the nest reads both task contracts through one template, so it needs `DINTaskCoordinator` and
`DINTaskAuditor` merged into one array (`abis/DINTask.json`, without their constructors).

So `abis/` stays, and `spike/sync-abis.py` is the only thing that writes it, from `foundry/out/`:

```sh
cd foundry && forge build && cd ..
indexer-nest/spike/sync-abis.py            # rewrite indexer-nest/abis/
indexer-nest/spike/sync-abis.py --check    # exit 1 if abis/ differs from forge build; for CI
```

`--check` compares entries as JSON, so key order and formatting do not matter. It also prints a note if
`subgraph/abis/` disagrees with the build. On `develop` at 409bf2c, after `forge build`, `--check`
passes: all eight files already equal the build, and the six that `subgraph/abis/` also has equal
those too. I have not added it to `.github/workflows/`: that is the maintainers' call, and it needs
`forge build` to have run first, which `ci.yml` may or may not already do.

## dincli's read path

Today dincli reads the subgraph in one place: `_query_subgraph` in `dincli/cli/dinrep.py`, a POST to
`DIN_SUBGRAPH_URL` (default `http://localhost:8000/subgraphs/name/din-protocol/graphql`). It returns
`None` on any error and the caller falls back to RPC. It makes two queries: unprocessed
`modelRegistrationRequests` (`requestId requester isOpenSource feePaid`) and unprocessed
`manifestUpdateRequests` (`requestId model { modelId } requester feePaid`). The nest has both as views,
`model_registration_requests` and `manifest_update_requests`, with `processed`, `request_id`,
`requester`, `fee_paid` and `is_open_source` / `model_id` as columns, so the data is there.

What nuthatch serves today, in the default binary, is SQL over HTTP (`GET /sql?q=...` or
`POST /sql`, JSON or Arrow), the `views/*.sql` files as named queries at `/q/{name}`, and an MCP
server. It does not serve GraphQL in the default binary. There is a Graph-shaped read surface in
nuthatch behind a cargo feature that is off by default; I have not tried it against this nest, it is a
partial read surface rather than a second graph-node, and I am not relying on it here.

So there are two options, and the PR does not build either:

1. **A SQL client in dincli.** Replace `_query_subgraph(graphql)` with a function that calls
   `/sql?q=SELECT request_id, requester, is_open_source, fee_paid FROM model_registration_requests
   WHERE NOT processed`, using `requests`, which dincli already imports. It is about the same size as
   the function it replaces, and it keeps the None-then-RPC fallback. The cost is a second config
   (`DIN_NEST_URL` beside `DIN_SUBGRAPH_URL`), and dincli would have to choose or try both.
2. **A small local shim that accepts the two GraphQL queries and answers from the views.** dincli does
   not change. The cost is that someone writes and owns a GraphQL parser or a fixed pair of query
   patterns, and it then has to follow the subgraph schema as dincli's queries grow. With two fixed
   queries that is small; as a general GraphQL surface it is not.

Option 1 is less code to own. Option 2 only pays if dincli's GraphQL reads are meant to stay as they
are. Either way, the nest is a read path that dincli can fall back from, as it does with the subgraph.

## Running it in the din-node container

I have not run it in the container. What I can say from reading `dincli/docker/node/`:

- The image is `python:3.12-slim` with `dincli` and the Docker client. Its main process is
  `sleep infinity`; the `dind` daemon is not there yet and will become the entrypoint. The container
  uses `network_mode: host` and runs as a non-root user.
- Nuthatch is a static binary and needs nothing the image lacks, so it could be copied in. But
  `nuthatch dev` is a long-running process, and the container has one slot for it, which `dind` will
  want.
- So the plausible shapes are a second compose service next to `din-node` on the host network (the
  nest on `127.0.0.1:8289`, dincli reaching it as it reaches anvil and IPFS today), or a process
  supervised inside the container beside `dind`. The compose service keeps one process per container
  and does not touch the din-node image; I would start there.
- The nest keeps its state in a `data/` directory (the hot store and the sealed segments), so a
  compose service needs a volume for it, or it re-indexes from `start_block` on each start.

Footprint: nuthatch budgets 2 GB of RAM per chain it follows. I have not measured this nest's RSS on
this run, and a nest this small is nowhere near it, but I have no number to quote.

## Reorgs and finality on OP Sepolia

How nuthatch behaves, from its operator docs and chain registry, not from a run here:

- Rows land in a mutable hot store. A reorg is detected by a reorg check (on a poll that sees the tip
  move, and at most every 12 seconds while idle for a fork at the same height) and rolls back the
  rows of the replaced blocks. Views read hot plus sealed, so the next query no longer sees them.
  Until the check runs, the nest answers from what it last indexed, discarded blocks included.
- Only rows past finality are sealed into immutable Parquet segments. A reorg deeper than the sealed
  watermark is a terminal fault: nuthatch stops rather than rewrite sealed history.
- Finality comes from the chain's policy in nuthatch's registry. Base (an OP-stack chain) and
  Arbitrum One use the node's `finalized` tag; OP mainnet is built in too, and I did not check which
  rule it takes. **OP Sepolia is not in the registry.** A chain it does not know gets the
  default: seal 64 blocks behind the tip, with a small `eth_getLogs` window. At OP Sepolia's 2 second
  block time that is about two minutes. Nuthatch's docs call this default a guess for a chain that
  finalises differently, and say that the safe direction is deeper.
- The depth can be set only in a runtime's `mounts.toml`, in a `[[chains]]` entry with
  `finality_depth` and `log_window`, for a chain outside the registry. It is not a key of this nest's
  `nuthatch.toml`, so for OP Sepolia the nest would run under `mounts.toml`, or take the 64.
  Registering OP Sepolia with the `finalized` tag is a change to nuthatch, not to this nest.
- There is a `--finality-only` flag that keeps the cursor at the finality boundary: nothing it indexes
  can reorg, at the price of reads that lag the tip.

For DIN this means that views over OP Sepolia would show recent task state (a GI state, a batch)
that a reorg could replace within about the last 64 blocks, and would not show it again until the
chain's new branch has been indexed. Whether 64 blocks is deep enough for OP Sepolia is a question
about that chain I have not answered, and this run, on a local anvil that never forks, does not
test it.

## Where it loses to the subgraph

- No handlers. The 32 view-shaped entities are SQL; none needs more, but it is work.
- Not GraphQL. dincli's reads would change.
- The merged task template, and the 5 pre-announcement events, as above.
- The gaps in `validators` and `global_iterations`, as above.
