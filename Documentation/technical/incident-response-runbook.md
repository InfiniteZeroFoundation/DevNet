# InfiniteZero Testnet Incident-Response Runbook

Status: agreed in [#167](https://github.com/InfiniteZeroFoundation/DevNet/issues/167) and [#352](https://github.com/InfiniteZeroFoundation/DevNet/issues/352), checked against `develop` at `f041c8d` (27 November 2026). Review it after every SEV1 or SEV2, and before the public testnet opens.

## Purpose and scope

This runbook tells the InfiniteZero team what to do, in what order, when something goes wrong on the testnet. It covers the invite-only cohort (about 10 validators for about 10 rounds) and is revisited before the public testnet, where we expect 100+ validators.

An incident is anything that puts participants' funds, data, trust or ability to take part at risk, for example:

- a smart-contract bug or exploit;
- a leaked or misused admin key;
- honest validators being slashed or jailed wrongly;
- training rounds stalling, or the network being unusable;
- a broken dincli release, or an infrastructure outage (RPC, IPFS);
- scams or impersonation targeting our community.

Testnet tokens have no real-money value, but treat every incident as rehearsal for mainnet: the same contracts, keys and habits carry over.

## Roles and contacts

Every incident has one named incident lead who makes the calls; everyone else supports them. Contact details live in the private incident channel, not in this repository.

| Role | Responsibility | Primary | Backup |
| :--- | :--- | :--- | :--- |
| Incident lead | Declares the incident, sets severity, decides actions, closes it | @umeradl | @Santiagocetran |
| Engineering lead, contracts | Diagnoses contract-side incidents (slashing, stuck GI, exploit), prepares the lever or upgrade | @robertocarlous | @Abidoyesimze |
| Engineering lead, off-chain | dincli and dind releases, the IPFS and RPC providers, the monitoring itself | @Santiagocetran | @umeradl |
| Key holder(s) | Signs admin transactions | Named in the private custody plan | |
| Comms lead | Posts the investigating, mitigated and resolved updates, and answers the cohort channel | @robertocarlous | @Santiagocetran |
| Public statement on a SEV1 | Approves any statement that describes the cause of an exploit or a key compromise | @abrahamnash | @umeradl |
| Infra and monitoring owner | Runs the monitors, checks provider limits and owns the fallbacks | @Santiagocetran | @robertocarlous |

Rules:

- The incident lead and the key holder should be different people, so nobody acts alone on an admin key.
- One person can hold more than one role.
- The comms lead posts the standard investigating, mitigated and resolved updates without waiting for approval. Only statements that describe the cause of an exploit or a key compromise need the SEV1 public-statement approver. If the approver hasn't replied within 30 minutes, the backup approves.
- A 15-minute weekly check-in during the cohort hands over anything open and swaps primaries if someone is away.

## Coverage and severity

Covered hours are 05:00 to 24:00 UTC, every day of the cohort period, weekends included. Nobody is on call from 00:00 to 05:00 UTC; response targets there start at 05:00, except for an automated SEV1 alert.

Set the severity in the first 15 minutes, and raise or lower it as you learn more. When unsure, pick the higher level.

| Level | Meaning | Examples | Acknowledge (covered hours) | Acknowledge (uncovered hours) | First community update | Then |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| SEV1 Critical | Active loss or misuse of funds or control; the network can't be trusted | Admin key leaked; an exploit in use; honest validators slashed at scale | 1 hour | 4 hours | Within 2 hours of acknowledging | Every 4 hours until mitigated |
| SEV2 Major | Serious harm likely, or a core function broken, but contained | A training round stuck; a bad dincli release; an RPC or IPFS outage blocking participation; a vulnerability reported privately | 4 hours | Next covered hours | Within 4 hours of acknowledging | Daily |
| SEV3 Minor | Limited impact, workaround exists | A single validator wrongly jailed; a docs error; a scam post in our channels | 1 working day | 1 working day | When resolved | |
| Cohort support question | | | 1 working day | 1 working day | | |

"Acknowledge" means someone in the roles table has said "I've got it" in the private incident channel and set a severity, not that it's fixed.

Escalation: if the primary hasn't acknowledged by half the target (30 minutes for a SEV1, 2 hours for a SEV2), the backup takes it. A SEV1 still unacknowledged after 1 hour pings everyone in the roles table.

## Monitoring

- `dincli/dind/gi_monitor.py` (PR #377) reports when a GI stays in an active phase past its threshold, and when it recovers.
- `dincli/dind/cohort_monitor.py` (PR #386) watches `TokensMinted` and `ValidatorSlashed` events and routes them, with the stalled-GI alerts, to one webhook.
- The webhook must post to the private incident channel, so alerts reach a phone. PagerDuty's free tier can be added later if the channel isn't enough.

## The first 30 minutes

Whoever spots a problem starts here, even if they are not the incident lead.

1. **Raise the alarm.** Post in the private incident channel: what you saw, where (transaction link, contract, model) and when. Don't discuss suspected exploits in public channels yet.
2. **Name an incident lead.** The primary from the roles table, or the first available person until they take over.
3. **Set a severity** using the table above.
4. **Start an incident log.** A shared note with timestamps: what happened, what was decided, what was done, by whom. It becomes the post-mortem.
5. **Contain before you fix.** Use the levers in Emergency levers to stop further harm first. Two people check every admin transaction before it's signed.
6. **Preserve evidence.** Record transaction hashes, block numbers, addresses and screenshots before anything changes.
7. **Tell the community** (SEV1 and SEV2) using the first template in Communication, even if all you can say is that you're investigating.
8. **Pick the playbook** below that fits, and follow it.

## Playbooks

Each playbook follows the same order: contain, fix, communicate.

### 1. Admin key leaked or misused (SEV1)

The deployer key owns every platform contract and all seven ProxyAdmins, so it can change settings and upgrade contract code.

- **Contain:** if you still control the key, immediately transfer ownership of every platform contract and every ProxyAdmin to a fresh, secure address (hardware wallet or Safe). Two people verify each transaction.
- **If the attacker is faster:** on testnet, redeploy a fresh platform from `develop`, publish the new addresses, and update `dincli/config/din_info.json` and the docs. Announce the old addresses as compromised.
- **Never call `retireFaucet` in a panic.** It is one-way, permanently stops all new DIN (the ETH faucet and emission), and locks the mint cap.
- **Communicate:** SEV1 template; tell participants which addresses to stop using.

### 2. Smart-contract bug being exploited (SEV1)

No contract has a global pause, so containment means switching off the specific path being abused.

- **Freeze new minting** if tokens are being created: set the mint cap to the current total minted. A cap of 0 means unlimited, so never set it to 0 to stop minting.
- **Stop a misbehaving task contract from slashing:** remove it as a slasher via `DinCoordinator.removeSlasherContract`. This is a full brake on that model: it can no longer slash, jail or register validators, or release their slots. Expect its current round to stall if anyone in it is due to be slashed, and release the slots of already-ended GIs first if there's time. Re-adding the pair restores everything.
- **Stop a model from starting new rounds:** `disableModel`. Since PR #305, a disabled model can't start new GIs; the round in progress finishes.
- **Fix:** platform contracts can be upgraded through their ProxyAdmin after the fix is reviewed and tested; task contracts are not upgradeable, so the model owner redeploys them.
- **Communicate:** SEV1 template; publish a post-mortem once fixed.

### 3. Honest validators slashed or jailed (SEV1 at scale, SEV3 for one)

- **Contain:** remove the responsible task contract as a slasher so no further slashing happens (see the effects in Playbook 2).
- **Note:** there is no admin "unjail". A wrongly jailed validator must wait out the jail period (7 days by default, `s5JailDuration`) and then call `reactivate`.
- **Make good:** agree any compensation (test tokens) case by case and record it in the incident log.
- **Fix the root cause** before re-adding the slasher.

### 4. Training round stuck (SEV2)

A stuck round can't yet be recovered on-chain, and its pool and validators' registration slots stay locked. The recovery design is in draft PR #337 (#222), and its implementation waits on the contract-size work in #201.

- Ask the model owner to stop starting new rounds on that model.
- Tell affected validators what is locked and what happens next.
- Once #222 ships, abort the round under the agreed policy.

### 5. Broken dincli release (SEV2)

- Tell participants which version to stay on or roll back to.
- Fix on `develop`, test, publish a new release, then announce it.

### 6. Infrastructure outage: RPC, IPFS, OP Sepolia (SEV2)

- Check whether the problem is ours or the provider's (OP Sepolia status, RPC provider, IPFS gateway).
- Point participants to the named fallback RPC endpoint or IPFS provider (dincli supports several IPFS providers and an opt-in gateway fallback).
- No on-chain action is usually needed; post status updates until resolved.

### 7. A participant's key is leaked (SEV3, SEV2 if many)

- Advise them to move remaining funds and unstake (the unbonding period applies).
- Consider freezing the address with `blacklistValidator`: nobody can then stake, unstake or claim unstaked tokens with it, so an attacker can't withdraw the stake. It's reversible with `unblacklistValidator` once the owner has a safe new key.
- Remind everyone to use encrypted keystores, never plaintext keys.

### 8. Scams and impersonation (SEV3, SEV2 if spreading)

Another project already uses the name and ticker "DIN" (our token is being renamed INZ, #281), so expect confusion and fake airdrops.

- Remove scam posts and ban the accounts in our channels.
- Post the scam-warning template: we sell no tokens, run no airdrop, and never ask for keys.
- Pin the official links (GitHub organisation, Telegram, Signal).

### 9. Malicious or broken service code in a model (SEV2, SEV1 if it spreads)

Validators run each model's own service code (training, auditing, aggregation) on their machines, so a bad manifest can harm validator nodes.

- **Contain:** `disableModel` so the model can't start new rounds, and tell validators to stop running that model's services.
- Advise validators to run models inside the `din-node` container rather than directly on their host.
- **Fix:** the model owner publishes corrected services through a manifest update, reviewed before the model is re-enabled.

### 10. Poisoned model updates getting through aggregation (SEV2)

Auditors score each local model before aggregation, and the reference manifest's anomaly gate (`eligibility_anomaly_gate`) screens outliers, but a poisoned update can still slip through.

- **Contain:** the model owner doesn't publish or use the affected aggregated model, and `disableModel` stops new rounds while you investigate.
- Check the round's audit scores and anomaly results to find the update and the auditors who passed it; open a dispute where the scores were wrong.
- **Fix:** tighten the model's scoring or anomaly settings before re-enabling it.

### 11. Faucet, emission or test-token drain (SEV1)

For example, the open issue #238: `DinEmission.fundGI` can be called by anyone, so a model's emission schedule can be used up on far-future rounds.

- **Contain:** freeze new minting with `setMintCap` (set it to the current total minted), and `disableModel` to stop emission funding for an affected model.
- **Fix:** adjust the schedule with `setEmissionParams` after the cause is fixed.
- Never use `retireFaucet` as a quick stop: it is permanent.

## Emergency levers

These are the on-chain actions the team can take today on `develop`'s contracts. There is no global pause, so every response uses one of these targeted levers. All except `reactivate` need the platform owner key (the deployer, today); task-contract settings need the model owner's key.

| Lever | Contract and function | Effect | Reversible? |
| :--- | :--- | :--- | :--- |
| Freeze new minting | `DinCoordinator.setMintCap` (set to current total minted) | Stops both the ETH faucet and emission minting. A cap of 0 means unlimited. | Yes, raise the cap |
| Retire the faucet | `DinCoordinator.retireFaucet` | Permanently stops all new DIN: the ETH faucet and emission. Also locks the mint cap. | No, one-way |
| Stop a contract slashing | `DinCoordinator.removeSlasherContract` | That task pair can no longer slash, jail or register validators, or release their slots; its current round may stall until it's re-added | Yes, re-add it |
| Disable a model | `DINModelRegistry.disableModel` | Blocks manifest updates, emission funding and new rounds; the round in progress finishes | Yes, `enableModel` |
| Freeze an address | `DinValidatorStake.blacklistValidator` | The address can't stake, unstake or claim unstaked tokens | Yes, `unblacklistValidator` |
| Change penalty settings | `DinValidatorStake.setS5GlobalParams`, `setS5RecidivismParams`, `setMinStake`, `setUnbondingPeriod` | Adjusts penalties and stake rules; `setS5GlobalParams(0, 0)` switches the cross-model escalation off | Yes |
| Change emission | `DinEmission.setEmissionParams` | Adjusts the per-round emission schedule | Yes |
| Change the pool split | `DINTaskAuditor.setRewardSplit` (model owner) | Changes who receives each round's pool. #340 moves the split to the protocol before the public testnet. | Yes |
| Upgrade a platform contract | The contract's ProxyAdmin | Replaces the contract's code after a reviewed fix | Yes, by another upgrade |
| Move control to a safe key | `transferOwnership` on each contract and ProxyAdmin | Hands control to a new owner address | Only by the new owner |
| Leave jail | `DinValidatorStake.reactivate` (the validator) | Ends a jail once its period has expired | Not applicable |

Practise each lever on the DevNet 2.0 rehearsal (#284) before launch, so nobody uses one for the first time during an incident.

## Communication

The comms lead posts in the Telegram community (main channel) and a pinned GitHub Discussion, with Signal as a mirror. Say what you know, what you don't, and when the next update comes. Never post exploit details until the issue is fixed. Statements that describe the cause of an exploit or a key compromise need the SEV1 public-statement approver (see Roles and contacts).

**1. Initial notice (SEV1/SEV2)**

> ⚠️ We're investigating an issue affecting [what: e.g. staking / training rounds / dincli] on the InfiniteZero testnet, first seen at [time, UTC].
>
> What to do for now: [e.g. don't start new rounds / don't stake / no action needed].
>
> Testnet tokens have no real-money value. Next update by [time, UTC].

**2. Update**

> Update on [issue], [time, UTC]: [what we've learned and done]. [What participants should do]. Next update by [time, UTC].

**3. Resolved**

> ✅ Resolved: [issue]. Cause: [one line]. What we changed: [one line]. What you need to do: [nothing / action]. A full write-up will follow at [link]. Thank you for your patience.

**4. Scam warning**

> 🚫 Scam warning: InfiniteZero has no token for sale and no airdrop running, and we will never ask for your private key or seed phrase. Official links only: github.com/InfiniteZeroFoundation and this Telegram group. Please report suspicious messages to the admins.

## After an incident

Within 5 working days of a SEV1 or SEV2, the incident lead publishes a short, blameless post-mortem as a GitHub Discussion, and opens an issue for every follow-up action. Blameless means it describes what happened and why the system allowed it, not who to blame.

~~~markdown
# Post-mortem: [title], [date]

Severity: SEV[n] · Duration: [start] to [end] (UTC) · Incident lead: [name]

## Summary
[Two or three sentences: what happened and the impact.]

## Impact
[Who was affected, and how: participants, funds, rounds, downtime.]

## Timeline (UTC)
- [time]: [event]

## Root cause
[Why it happened, and why existing checks didn't catch it.]

## What went well / what didn't
- ...

## Follow-up actions
- [ ] [action] (#issue, owner)
~~~

Review this runbook after every SEV1 or SEV2, and update it with anything the incident taught you.

## Before launch

Tick these off before the invite-only cohort starts.

- [x] Names and backups filled in under Roles and contacts (#352)
- [x] Response times agreed and the severity table updated to match (#352)
- [ ] Admin keys moved off a single hot wallet (hardware wallet or Safe), with at least two people able to sign
- [ ] A private incident channel, with everyone in the roles table in it and contact details pinned there
- [ ] Monitoring webhook posting to the private incident channel, running against the DevNet 2.0 deployment
- [ ] RPC and IPFS provider limits checked for the cohort size, with a fallback named for each
- [ ] The cohort support channel named and linked from the onboarding docs
- [ ] A pinned list of official contract addresses, explorer links and RPC endpoints
- [ ] Every lever in Emergency levers practised once on the DevNet 2.0 rehearsal
- [ ] Communication templates saved where the comms lead can post them quickly
- [ ] The scam-warning message and official links pinned in Telegram
- [ ] One tabletop rehearsal done, with findings recorded

## Known gaps

Writing this runbook against `develop` surfaced limits in what the team can do during an incident. Each is a decision for the team.

| Gap | Why it matters in an incident | Tracked |
| :--- | :--- | :--- |
| No global pause on any contract | An exploit can only be stopped path by path, which is slower and easier to get wrong | Decision to record under #167: add a pause or guardian, or accept not having one |
| `DinEmission.fundGI` can be called by anyone for far-future rounds | A model's emission schedule can be drained | #238 |
| No admin way to release a wrongly jailed validator | Honest validators stay jailed for the full period (7 days by default) even after the team confirms a mistake | Not yet |
| Stuck rounds can't be recovered | Pools and validators' registration slots stay locked | #222 (design in draft PR #337, waits on #201) |
| Removing a slasher holds validators' registration slots on every model | The registration count is global per validator, so containing one model cuts into their slots everywhere | Not yet |
| A mint cap of 0 means unlimited; retiring the faucet also ends emission and locks the cap | Easy to make a mistake under pressure | Behaviour, noted in the levers table |
| One deployer key controls every contract and all seven ProxyAdmins | A single leaked key gives full control | funding#2 (key custody) |
| Task contracts aren't upgradeable | A bug in them is fixed only by each model owner redeploying | By design |
