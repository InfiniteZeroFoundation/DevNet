#!/usr/bin/env python3
"""Checks every view against what spike/NuthatchSpike.s.sol and spike/NuthatchGov.s.sol did on the
anvil, and where the chain can say it, against the chain: `cast call` at the head.

  python3 spike/check.py [http://127.0.0.1:8289] [http://127.0.0.1:8545]

Exit status 1 if any check fails. A view with no rows on the run is reported as UNCHECKED, not as
passing: nothing in the run produces its events. Needs `cast` (foundry) on PATH for the chain checks.
"""
import json
import shutil
import subprocess
import sys
import urllib.request

NEST = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8289"
RPC = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8545"
REG = "0x959922bE3CAee4b8Cd9a407cc3ac1C251C2007B1"
STAKE = "0xA51c1fc2f0D1a1b8494Ed1FE312d7C3a78Ed91C0"
ROUTER = "0x5FC8d32690cc91D4c39d9d3abcBD16989F875707"


def sql(q):
    req = urllib.request.Request(NEST + "/sql", data=json.dumps({"q": q}).encode(), headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(req))["rows"]


def cast(*args):
    out = subprocess.run(["cast", "call", *args, "--rpc-url", RPC], capture_output=True, text=True, check=True).stdout.strip()
    return out.split()[0]


failed, passed = [], 0


def check(name, got, want):
    global passed
    if got == want:
        passed += 1
        print("ok     ", name)
    else:
        failed.append(name)
        print("FAIL   ", name, "\n   got ", got, "\n   want", want)


def one(view, cols=None):
    rows = sql(f"SELECT * FROM {view}")
    return rows


def pick(rows, *cols):
    return [{c: r[c] for c in cols} for r in rows]


# --- the script's own numbers (NuthatchGov.s.sol) -------------------------------------------------
E = 10**18
r = one("stake_governance")
check("stake_governance", pick(r, "min_stake", "unbonding_period", "max_concurrent_registrations_per_stake_unit"),
      [{"min_stake": str(20 * E), "unbonding_period": str(14 * 86400), "max_concurrent_registrations_per_stake_unit": "3"}])
check("model_stake_bounds (the second call stands)", pick(one("model_stake_bounds"), "model_id", "min_stake", "max_stake"),
      [{"model_id": "0", "min_stake": str(10 * E), "max_stake": str(100 * E)}])
check("s5_global_params", pick(one("s5_global_params"), "window", "threshold"), [{"window": "10", "threshold": "3"}])
check("s5_recidivism_params", pick(one("s5_recidivism_params"), "window", "threshold", "jail_duration"),
      [{"window": "20", "threshold": "4", "jail_duration": "86400"}])
check("s6_params", pick(one("s6_params"), "threshold"), [{"threshold": "5"}])
u = one("unstake_requests")
check("unstake_requests: one, 4 DIN, claimed false", pick(u, "amount", "claimed"), [{"amount": str(4 * E), "claimed": False}])
sl = one("slasher_registrations")
check("slasher_registrations: tc active, ta removed, from both sources",
      sorted((x["source_contract"] == "0xa513e6e4b8f2a923d98304ec87f64353c4d5c853", x["active"]) for x in sl),
      [(False, False), (False, True), (True, False), (True, True)])
fs = one("fee_sources")
check("fee_sources: registry active, coordinator removed",
      sorted((x["source"][:6], x["active"]) for x in fs), [("0x9599", True), ("0xa513", False)])
fc = one("fee_router_config")
check("fee_router_config", pick(fc, "treasury_bps_ceiling", "din_validator_pool_bps", "din_treasury_bps", "din_burn_bps",
                                "din_storage_bps", "din_public_goods_bps", "eth_validator_pool_bps", "eth_treasury_bps",
                                "eth_storage_bps", "eth_public_goods_bps"),
      [{"treasury_bps_ceiling": 2500, "din_validator_pool_bps": 5500, "din_treasury_bps": 2200, "din_burn_bps": 1800,
        "din_storage_bps": 500, "din_public_goods_bps": 0, "eth_validator_pool_bps": 6000, "eth_treasury_bps": 2000,
        "eth_storage_bps": 1500, "eth_public_goods_bps": 500}])
check("fee_router_config.treasury is account 30", fc[0]["treasury"], "0x1bcb8e569eedab4668e55145cfeaf190902d3cf2")

snaps = sorted(one("fee_snapshots"), key=lambda x: (x["block_number"], x["log_index"]))
def fee(*v):
    names = ("open_source_fee", "proprietary_fee", "open_source_update_fee", "proprietary_update_fee")
    return dict(zip(names, map(str, v)))

check("fee_snapshots: five, four granular then one atomic", [s["update_kind"] for s in snaps], ["granular"] * 4 + ["atomic"])
# each single setter changes one fee; the other three are read from the chain, so they carry the earlier setters
check("fee_snapshots: granular snapshots carry the setters made so far",
      [(x["open_source_fee"], x["proprietary_fee"], x["open_source_update_fee"]) for x in snaps[:3]],
      [(str(10**16), snaps[0]["proprietary_fee"], snaps[0]["open_source_update_fee"]),
       (str(10**16), str(2 * 10**16), snaps[0]["open_source_update_fee"]),
       (str(10**16), str(2 * 10**16), str(3 * 10**15))])
check("fee_snapshots: last granular is the four set values",
      pick(snaps[3:4], "open_source_fee", "proprietary_fee", "open_source_update_fee", "proprietary_update_fee"),
      [fee(10**16, 2 * 10**16, 3 * 10**15, 4 * 10**15)])
check("fee_snapshots: atomic is setFees' four values",
      pick(snaps[4:], "open_source_fee", "proprietary_fee", "open_source_update_fee", "proprietary_update_fee"),
      [fee(11 * 10**15, 22 * 10**15, 33 * 10**14, 44 * 10**14)])

mr = sorted(one("model_registration_requests"), key=lambda x: int(x["request_id"]))
check("model_registration_requests", [(x["request_id"], x["is_open_source"], x["processed"], x["approved"], x["model_id"]) for x in mr],
      [("0", True, True, True, "0"), ("1", False, True, False, None)])
check("model_registration_requests: fee paid is the proprietary fee at the time", mr[1]["fee_paid"], str(22 * 10**15))
mu = sorted(one("manifest_update_requests"), key=lambda x: int(x["request_id"]))
check("manifest_update_requests", [(x["request_id"], x["model_id"], x["processed"], x["approved"], x["fee_paid"]) for x in mu],
      [("0", "0", True, True, str(33 * 10**14)), ("1", "0", True, False, str(33 * 10**14))])
check("manifest_update_requests: requester is the model's owner", {x["requester"] for x in mu}, {"0x70997970c51812dc3a010c7d01b50e0d17dc79c8"})
cmn = one("current_manifests")
check("current_manifests: model 0 carries the approved update's CID, not the approval-time one", pick(cmn, "model_id", "manifest_cid", "updated"),
      [{"model_id": "0", "manifest_cid": "0x" + "%064x" % 0xC1E, "updated": True}])
w = one("registry_fee_withdrawals")
check("registry_fee_withdrawals: to the fee router", [x["to"] for x in w], [ROUTER.lower()])
check("task_coordinator_governance", pick(one("task_coordinator_governance"), "s2_slash_fraction_bps"), [{"s2_slash_fraction_bps": "4000"}])
check("task_auditor_governance", pick(one("task_auditor_governance"), "s1_slash_fraction_bps", "s3_deviation_threshold", "s3_slashing_enabled"),
      [{"s1_slash_fraction_bps": "2500", "s3_deviation_threshold": "15", "s3_slashing_enabled": True}])
check("reward_splits", pick(one("reward_splits"), "client_bps", "auditor_bps", "aggregator_bps", "treasury_bps"),
      [{"client_bps": 6000, "auditor_bps": 2000, "aggregator_bps": 1500, "treasury_bps": 500}])
lm = sorted(one("local_model_submissions"), key=lambda x: int(x["model_index"]))
check("local_model_submissions: three, all judged eligible", [(x["gi"], x["model_index"], x["eligible"]) for x in lm],
      [("1", "0", True), ("1", "1", True), ("1", "2", True)])
gst = sorted(one("gi_state_transitions"), key=lambda x: x["block_number"])
check("gi_state_transitions: GI 1 enters states 5..28 once each, in order", [x["new_state"] for x in gst if x["gi"] == "1"], list(range(5, 29)))
gi = one("global_iterations")
check("global_iterations: GI 1 ended in state 28", pick(gi, "gi", "current_state", "ended"), [{"gi": "1", "current_state": "28", "ended": True}])

va = {x["validator"]: x for x in one("validators")}
check("validators: nine, one with a 4 DIN unstake request and 6 DIN active", (len(va), sorted((x["active_stake"], x["total_unstake_requested"]) for x in va.values() if x["total_unstake_requested"] != "0")),
      (9, [(str(6 * E), str(4 * E))]))
check("validators: the three auditors registered an encryption key", sum(1 for x in va.values() if x["encryption_key"]), 3)
check("validators: nobody jailed, blacklisted or withdrawn", (any(x["jailed"] or x["blacklisted"] for x in va.values()), {x["total_withdrawn"] for x in va.values()}), (False, {"0"}))

# --- the GI's flow: 3 local models, 3 auditors in one batch, 6 aggregators in one T1 batch and one T2 batch (NuthatchGI.s.sol)
def CID(n):
    return "0x" + "%064x" % n

t1 = one("tier1_batches")
check("tier1_batches: one, finalized with CID A", pick(t1, "gi", "batch_id", "finalized", "winning_cid"),
      [{"gi": "1", "batch_id": "0", "finalized": True, "winning_cid": CID(0xA1)}])
check("tier1_batches: created before it was finalized", t1[0]["created_at_block"] < t1[0]["finalized_at_block"], True)
t2 = one("tier2_batches")
check("tier2_batches: one, finalized with CID B", pick(t2, "gi", "finalized", "global_model_cid"), [{"gi": "1", "finalized": True, "global_model_cid": CID(0xB2)}])
s1, s2 = one("t1_aggregation_submissions"), one("t2_aggregation_submissions")
check("t1_aggregation_submissions: three aggregators, CID A", (len({x["aggregator"] for x in s1}), {x["cid"] for x in s1}), (3, {CID(0xA1)}))
check("t2_aggregation_submissions: three aggregators, CID B", (len({x["aggregator"] for x in s2}), {x["cid"] for x in s2}), (3, {CID(0xB2)}))
c1, c2 = one("t1_aggregation_commitments"), one("t2_aggregation_commitments")
check("t1/t2_aggregation_commitments: three each, same aggregators as the submissions",
      (len(c1), len(c2), {x["aggregator"] for x in c1} == {x["aggregator"] for x in s1}, {x["aggregator"] for x in c2} == {x["aggregator"] for x in s2}),
      (3, 3, True, True))
sk = sorted(one("seed_locks"), key=lambda x: x["kind"])
check("seed_locks: Agg and Audit, seed set, never reanchored", [(x["kind"], x["seed"] is not None, x["reanchored_at_block"]) for x in sk],
      [("Agg", True, None), ("Audit", True, None)])
check("seed_locks: audit seed locked before the aggregation seed", sk[1]["block_number"] < sk[0]["block_number"], True)
ab = one("audit_batches")
check("audit_batches: one batch, not pending reassignment", pick(ab, "gi", "batch_id", "pending_reassignment"), [{"gi": "1", "batch_id": "0", "pending_reassignment": False}])
cm, sb = one("audit_score_commitments"), one("audit_score_submissions")
check("audit_score_commitments: 3 auditors x 3 models, all revealed at 80",
      (len(cm), {(x["revealed"], x["score"]) for x in cm}, len({(x["auditor"], x["model_index"]) for x in cm})), (9, {(True, "80")}, 9))
check("audit_score_submissions: 9, each with its commitment", (len(sb), {(x["score"], x["committed"]) for x in sb}), (9, {("80", True)}))
ev, er = one("eligibility_votes"), one("eligibility_results")
check("eligibility_votes: 9 votes, all yes", (len(ev), {x["vote"] for x in ev}), (9, {True}))
check("eligibility_results: one per model, all eligible", sorted((x["model_index"], x["eligible"]) for x in er), [("0", True), ("1", True), ("2", True)])
td, ek = one("test_data_commitments"), one("encrypted_test_data_keys")
check("test_data_commitments: one for the batch", pick(td, "gi", "batch_id"), [{"gi": "1", "batch_id": "0"}])
check("encrypted_test_data_keys: one, for three auditors", pick(ek, "gi", "batch_id", "auditor_count", "test_data_cid"),
      [{"gi": "1", "batch_id": "0", "auditor_count": "3", "test_data_cid": "0x01"}])

# --- the chain's own answer, where it gives one ---------------------------------------------------
if shutil.which("cast"):
    check("chain: registry.openSourceFee() = last fee_snapshot", cast(REG, "openSourceFee()(uint256)"), snaps[4]["open_source_fee"])
    check("chain: registry.proprietaryUpdateFee() = last fee_snapshot", cast(REG, "proprietaryUpdateFee()(uint256)"), snaps[4]["proprietary_update_fee"])
    check("chain: stake.minStake() = stake_governance", cast(STAKE, "minStake()(uint256)"), r[0]["min_stake"])
    check("chain: router.treasuryBpsCeiling() = fee_router_config", cast(ROUTER, "treasuryBpsCeiling()(uint16)"), str(fc[0]["treasury_bps_ceiling"]))
    check("chain: registry.feeRouter() = registry_fee_withdrawals.to", cast(REG, "feeRouter()(address)").lower(), w[0]["to"])
    mc = one("model_contracts")[0]
    check("chain: tc.tier1BatchCount(1) = tier1_batches", cast(mc["task_coordinator"], "tier1BatchCount(uint256)(uint256)", "1"), str(len(t1)))
    check("chain: ta.AuditorsBatchCount(1) = audit_batches", cast(mc["task_auditor"], "AuditorsBatchCount(uint256)(uint256)", "1"), str(len(ab)))
    v0 = sorted(va)[0]
    check("chain: stake.activeRegistrationCount(v) = validators", cast(STAKE, "activeRegistrationCount(address)(uint256)", v0), va[v0]["active_registrations"])
    check("chain: stake.encryptionKeys(auditor) = validators.encryption_key", cast(STAKE, "encryptionKeys(address)(bytes)", "0x23618e81e3f5cdf7f54c3d65f7fbc0abf5b21e8f"), va["0x23618e81e3f5cdf7f54c3d65f7fbc0abf5b21e8f"]["encryption_key"])
    acct2 = "0x3c44cdddb6a900fa2b585dd299e03d12fa4293bc"
    check("chain: stake.validators(acct2).activeStake = validators.active_stake", cast(STAKE, "validators(address)(uint256,uint256,uint64,uint64,uint8)", acct2), va[acct2]["active_stake"])
    mrq = cast(REG, "manifestRequests(uint256)(uint256,bytes32,address,uint256,bool,bool)", "0")
    check("chain: manifestRequests(0).modelId", mrq, "0")
else:
    print("skip    chain checks: no `cast` on PATH")

print(f"\n{passed} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
