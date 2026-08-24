// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Test, console} from "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from
    "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken}          from "../src/DinToken.sol";
import {DinCoordinator}    from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DinTreasury}       from "../src/DinTreasury.sol";
import {DINTaskCoordinator} from "../src/DINTaskCoordinator.sol";
import {DINTaskAuditor}     from "../src/DINTaskAuditor.sol";

/// @notice Gas simulation for issue #78 — validator network-fee sizing.
///
/// Measures on-chain gas across three GI lifecycle scenarios:
///   S1. Aggregation submissions (T1 and T2 CID submissions, finalization)
///   S2. Evaluation submissions (setAuditScorenEligibility — cold and quorum-trigger)
///   S3. Worst-case slashing (slashAggregators with 2/3 slashed, slashAuditors full loop)
///
/// Run: forge clean && forge test --match-contract GasSimulationTest -vv
/// Results feed into Developer/design/gas-simulation-network-fee.md.
///
/// Participation tiers:
///   LOW  : 3 T1 batches →  9 models, 12 aggregators (9 T1 + 3 T2),  9 auditors
///   MID  : 5 T1 batches → 15 models, 18 aggregators (15 T1 + 3 T2), 15 auditors
///   HIGH : 10 T1 batches → 30 models, 33 aggregators (30 T1 + 3 T2), 30 auditors
///
/// Note: DINTaskAuditor runs at demo-default params (3 aud/batch, 3 models/batch,
/// quorum=2). Audit batch count therefore equals T1 batch count at each tier.
contract GasSimulationTest is Test {

    // ── Platform contracts ────────────────────────────────────────────────────
    DinToken          token;
    DinCoordinator    coordinator;
    DinValidatorStake stake;
    DinTreasury       treasury;

    // ── Task contracts (fresh per test via setUp) ─────────────────────────────
    DINTaskCoordinator tc;
    DINTaskAuditor     ta;

    // ── Constants mirroring on-chain values ───────────────────────────────────
    uint constant T1_AGG_PER_BATCH = 3; // DINTaskCoordinator.T1_AGGREGATORS_PER_BATCH
    uint constant T1_MOD_PER_BATCH = 3; // DINTaskCoordinator.T1_MODELS_PER_BATCH
    uint constant AUD_PER_BATCH    = 3; // DINTaskAuditor default params.auditorsPerBatch
    uint constant MOD_PER_BATCH    = 3; // DINTaskAuditor default params.modelsPerBatch
    uint constant QUORUM           = 2; // DINTaskAuditor default params.minEligibilityQuorum

    // ── setUp: deploy and wire everything ─────────────────────────────────────

    function setUp() public {
        treasury = DinTreasury(payable(address(new TransparentUpgradeableProxy(
            address(new DinTreasury()), address(this),
            abi.encodeCall(DinTreasury.initialize, ())
        ))));

        token = DinToken(address(new TransparentUpgradeableProxy(
            address(new DinToken()), address(this),
            abi.encodeCall(DinToken.initialize, ())
        )));

        coordinator = DinCoordinator(payable(address(new TransparentUpgradeableProxy(
            address(new DinCoordinator()), address(this),
            abi.encodeCall(DinCoordinator.initialize, (address(token)))
        ))));
        token.setCoordinator(address(coordinator));

        stake = DinValidatorStake(address(new TransparentUpgradeableProxy(
            address(new DinValidatorStake()), address(this),
            abi.encodeCall(DinValidatorStake.initialize, (address(token), address(coordinator)))
        )));
        coordinator.updateValidatorStakeContract(address(stake));
        stake.setSlashTreasury(address(treasury));

        // Task contracts
        tc = new DINTaskCoordinator(address(stake));
        ta = new DINTaskAuditor(address(stake), address(tc));

        // Wire state machine: auditor → coordinator slasher → auditor slasher → genesis
        tc.setDINTaskAuditorContract(address(ta));
        vm.prank(address(coordinator)); stake.addSlasherContract(address(tc));
        tc.setDINTaskCoordinatorAsSlasher();
        vm.prank(address(coordinator)); stake.addSlasherContract(address(ta));
        tc.setDINTaskAuditorAsSlasher();
        tc.setGenesisModelIpfsHash(bytes32("genesis"));
        // GIstate is now GenesisModelCreated — ready for startGI
    }

    // ── Internal helpers ──────────────────────────────────────────────────────

    function _stake(address who) internal {
        vm.deal(who, 1 ether);
        vm.prank(who); coordinator.depositAndMint{value: 0.1 ether}();
        vm.prank(who); token.approve(address(stake), type(uint256).max);
        vm.prank(who); stake.stake(10e18);
    }

    /// @dev Runs GI from GenesisModelCreated to LMSevaluationStarted (no votes cast yet).
    ///      Returns (aggs, auds) address arrays in registration order.
    ///      nT1Batches drives: nAggs = nT1Batches*3 + 3, nAuds = nT1Batches*3, nModels = nT1Batches*3.
    function _setupToEvalStart(
        uint nT1Batches
    ) internal returns (address[] memory aggs, address[] memory auds) {
        uint nAggs   = nT1Batches * T1_AGG_PER_BATCH + T1_AGG_PER_BATCH; // T1 slots + T2 slots
        uint nAuds   = nT1Batches * AUD_PER_BATCH;
        uint nModels = nT1Batches * T1_MOD_PER_BATCH;

        aggs = new address[](nAggs);
        auds = new address[](nAuds);

        for (uint i = 0; i < nAggs; i++) {
            aggs[i] = makeAddr(string.concat("agg", vm.toString(i)));
            _stake(aggs[i]);
        }
        for (uint i = 0; i < nAuds; i++) {
            auds[i] = makeAddr(string.concat("aud", vm.toString(i)));
            _stake(auds[i]);
        }

        uint gi = 1;
        tc.startGI(gi);

        tc.startDINaggregatorsRegistration(gi);
        for (uint i = 0; i < nAggs; i++) { vm.prank(aggs[i]); tc.registerDINaggregator(gi); }
        tc.closeDINaggregatorsRegistration(gi);

        tc.startDINauditorsRegistration(gi);
        for (uint i = 0; i < nAuds; i++) { vm.prank(auds[i]); ta.registerDINAuditor(gi); }
        tc.closeDINauditorsRegistration(gi);

        tc.startLMsubmissions(gi);
        for (uint i = 0; i < nModels; i++) {
            address client = makeAddr(string.concat("cl", vm.toString(i)));
            vm.prank(client); ta.submitLocalModel(bytes32(uint256(0xC1D) | i), gi);
        }
        tc.closeLMsubmissions(gi);

        tc.createAuditorsBatches(gi);
        tc.setTestDataAssignedFlag(gi, true);
        tc.startLMsubmissionsEvaluation(gi);
    }

    /// @dev Continues from LMSevaluationStarted: has all auditors vote on all
    ///      their assigned models (score 75, vote=true), then advances to
    ///      T1AggregationStarted.
    function _completeEvalAndOpenT1(uint gi) internal {
        uint bCnt = ta.AuditorsBatchCount(gi);
        for (uint b = 0; b < bCnt; b++) {
            (, address[] memory bAuds, uint[] memory bMods,) = ta.getAuditorsBatch(gi, b);
            for (uint a = 0; a < bAuds.length; a++) {
                for (uint m = 0; m < bMods.length; m++) {
                    vm.prank(bAuds[a]);
                    ta.setAuditScorenEligibility(gi, b, bMods[m], 75, true);
                }
            }
        }
        tc.closeLMsubmissionsEvaluation(gi);
        tc.autoCreateTier1AndTier2(gi);
        tc.startT1Aggregation(gi);
    }

    /// @dev Full setup: GenesisModelCreated → T1AggregationStarted.
    function _setupToT1Open(
        uint nT1Batches
    ) internal returns (address[] memory aggs, address[] memory auds) {
        (aggs, auds) = _setupToEvalStart(nT1Batches);
        _completeEvalAndOpenT1(1);
    }

    /// @dev From T1AggregationStarted: has 2 aggregators per T1 batch submit (quorum met),
    ///      1 per batch doesn't submit (will be slashed). Runs through to T2AggregationDone.
    ///      Post-H-1 worst case: minimum quorum (2 of 3) required to reach finalization.
    function _runT1T2WorstCase(uint gi) internal {
        bytes32 cid = bytes32("agreed_cid");
        uint t1Cnt = tc.tier1BatchCount(gi);
        for (uint b = 0; b < t1Cnt; b++) {
            (, address[] memory bAggs,,,) = tc.getTier1Batch(gi, b);
            vm.prank(bAggs[0]); tc.submitT1Aggregation(gi, b, cid);
            vm.prank(bAggs[1]); tc.submitT1Aggregation(gi, b, cid); // quorum met (2 of 3)
            // bAggs[2] intentionally does not submit → will be slashed (1 per batch)
        }
        tc.finalizeT1Aggregation(gi);

        tc.startT2Aggregation(gi);
        (, address[] memory t2Aggs,,) = tc.getTier2Batch(gi, 0);
        vm.prank(t2Aggs[0]); tc.submitT2Aggregation(gi, 0, cid);
        vm.prank(t2Aggs[1]); tc.submitT2Aggregation(gi, 0, cid); // quorum met (2 of 3)
        // t2Aggs[2] does not submit → will be slashed
        tc.finalizeT2Aggregation(gi);
        tc.setTier2Score(gi, 85);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // SCENARIO 1 — Aggregation submissions
    // ─────────────────────────────────────────────────────────────────────────

    /// @dev Per-aggregator cost of submitting a T1 CID (cold storage paths).
    function test_gas_s1_submitT1Aggregation_cold() public {
        _setupToT1Open(3);
        (, address[] memory bAggs,,,) = tc.getTier1Batch(1, 0);

        uint before = gasleft();
        vm.prank(bAggs[0]); tc.submitT1Aggregation(1, 0, bytes32("cid_a"));
        console.log("[GAS][S1] submitT1Aggregation (1st call, cold SSTORE):", before - gasleft());
    }

    /// @dev Second aggregator submitting to the same batch — vote counter increment is warm.
    function test_gas_s1_submitT1Aggregation_warm() public {
        _setupToT1Open(3);
        (, address[] memory bAggs,,,) = tc.getTier1Batch(1, 0);
        vm.prank(bAggs[0]); tc.submitT1Aggregation(1, 0, bytes32("cid_a"));

        uint before = gasleft();
        vm.prank(bAggs[1]); tc.submitT1Aggregation(1, 0, bytes32("cid_a")); // same CID → warm counter
        console.log("[GAS][S1] submitT1Aggregation (2nd call, warm vote counter):", before - gasleft());
    }

    function test_gas_s1_finalizeT1_3batches() public {
        _setupToT1Open(3);
        for (uint b = 0; b < 3; b++) {
            (, address[] memory a,,,) = tc.getTier1Batch(1, b);
            vm.prank(a[0]); tc.submitT1Aggregation(1, b, bytes32("cid"));
            vm.prank(a[1]); tc.submitT1Aggregation(1, b, bytes32("cid")); // quorum needs 2
        }
        uint before = gasleft();
        tc.finalizeT1Aggregation(1);
        console.log("[GAS][S1] finalizeT1Aggregation (3 batches, 3 agg/batch):", before - gasleft());
    }

    function test_gas_s1_finalizeT1_5batches() public {
        _setupToT1Open(5);
        for (uint b = 0; b < 5; b++) {
            (, address[] memory a,,,) = tc.getTier1Batch(1, b);
            vm.prank(a[0]); tc.submitT1Aggregation(1, b, bytes32("cid"));
            vm.prank(a[1]); tc.submitT1Aggregation(1, b, bytes32("cid")); // quorum needs 2
        }
        uint before = gasleft();
        tc.finalizeT1Aggregation(1);
        console.log("[GAS][S1] finalizeT1Aggregation (5 batches, 3 agg/batch):", before - gasleft());
    }

    function test_gas_s1_finalizeT1_10batches() public {
        _setupToT1Open(10);
        for (uint b = 0; b < 10; b++) {
            (, address[] memory a,,,) = tc.getTier1Batch(1, b);
            vm.prank(a[0]); tc.submitT1Aggregation(1, b, bytes32("cid"));
            vm.prank(a[1]); tc.submitT1Aggregation(1, b, bytes32("cid")); // quorum needs 2
        }
        uint before = gasleft();
        tc.finalizeT1Aggregation(1);
        console.log("[GAS][S1] finalizeT1Aggregation (10 batches, 3 agg/batch):", before - gasleft());
    }

    /// @dev Per-T2-aggregator cost of submitting a T2 CID.
    function test_gas_s1_submitT2Aggregation() public {
        _setupToT1Open(3);
        // Complete T1 first — quorum requires 2 of 3 per batch
        for (uint b = 0; b < tc.tier1BatchCount(1); b++) {
            (, address[] memory a,,,) = tc.getTier1Batch(1, b);
            vm.prank(a[0]); tc.submitT1Aggregation(1, b, bytes32("cid"));
            vm.prank(a[1]); tc.submitT1Aggregation(1, b, bytes32("cid"));
        }
        tc.finalizeT1Aggregation(1);
        tc.startT2Aggregation(1);

        (, address[] memory t2Aggs,,) = tc.getTier2Batch(1, 0);
        uint before = gasleft();
        vm.prank(t2Aggs[0]); tc.submitT2Aggregation(1, 0, bytes32("cid_t2"));
        console.log("[GAS][S1] submitT2Aggregation (cold SSTORE):", before - gasleft());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // SCENARIO 2 — Evaluation submissions
    // ─────────────────────────────────────────────────────────────────────────

    /// @dev First auditor vote for a model: all storage writes are cold.
    function test_gas_s2_auditScore_cold_noQuorum() public {
        _setupToEvalStart(3);
        (, address[] memory bAuds, uint[] memory bMods,) = ta.getAuditorsBatch(1, 0);

        uint before = gasleft();
        vm.prank(bAuds[0]); ta.setAuditScorenEligibility(1, 0, bMods[0], 75, true);
        console.log("[GAS][S2] setAuditScorenEligibility (cold, quorum not met):", before - gasleft());
    }

    /// @dev Vote that tips the batch to eligibility quorum — triggers _tryFinalizeEligibility write.
    function test_gas_s2_auditScore_quorumTrigger() public {
        _setupToEvalStart(3);
        (, address[] memory bAuds, uint[] memory bMods,) = ta.getAuditorsBatch(1, 0);
        // First vote (cold, below quorum)
        vm.prank(bAuds[0]); ta.setAuditScorenEligibility(1, 0, bMods[0], 70, true);
        // Second vote — hits quorum (QUORUM=2), _tryFinalizeEligibility fires and writes eligible=true
        uint before = gasleft();
        vm.prank(bAuds[1]); ta.setAuditScorenEligibility(1, 0, bMods[0], 80, true);
        console.log("[GAS][S2] setAuditScorenEligibility (quorum trigger, eligibility write):", before - gasleft());
    }

    // ─────────────────────────────────────────────────────────────────────────
    // SCENARIO 3 — Slashing (worst-case proxy for dispute resolution cost)
    //
    // slashAuditors  : iterates all audit batches × auditors × models. All auditors
    //                  voted in setUp, so 0 are slashed here — pure loop overhead.
    //                  Worst-case cost = loop overhead + N_missed × marginal slash cost.
    //                  marginal slash cost is visible from slashAggregators measurements.
    //
    // slashAggregators: 1 of 3 aggregators per T1 batch + 1 of 3 T2 aggregators
    //                  did not submit → all are slashed. Shows real slash() call cost at scale.
    // ─────────────────────────────────────────────────────────────────────────

    function test_gas_s3_slashAuditors_3batches() public {
        _setupToT1Open(3);
        _runT1T2WorstCase(1);

        uint before = gasleft();
        tc.slashAuditors(1);
        // 3 audit batches × 3 auditors × 3 models checked; 0 slashed (all voted)
        console.log("[GAS][S3] slashAuditors (3 batches, 0 slashed - loop overhead only):", before - gasleft());
    }

    function test_gas_s3_slashAuditors_5batches() public {
        _setupToT1Open(5);
        _runT1T2WorstCase(1);

        uint before = gasleft();
        tc.slashAuditors(1);
        console.log("[GAS][S3] slashAuditors (5 batches, 0 slashed - loop overhead only):", before - gasleft());
    }

    function test_gas_s3_slashAuditors_10batches() public {
        _setupToT1Open(10);
        _runT1T2WorstCase(1);

        uint before = gasleft();
        tc.slashAuditors(1);
        console.log("[GAS][S3] slashAuditors (10 batches, 0 slashed - loop overhead only):", before - gasleft());
    }

    function test_gas_s3_slashAggregators_3batches() public {
        _setupToT1Open(3);
        _runT1T2WorstCase(1);
        tc.slashAuditors(1);

        // 3 T1 batches × 1 slashed per batch + 1 T2 slashed = 4 slash() calls
        uint before = gasleft();
        tc.slashAggregators(1);
        console.log("[GAS][S3] slashAggregators (3 T1 batches, 1/3 agg slashed per batch):", before - gasleft());
    }

    function test_gas_s3_slashAggregators_5batches() public {
        _setupToT1Open(5);
        _runT1T2WorstCase(1);
        tc.slashAuditors(1);

        // 5 T1 batches × 1 slashed + 1 T2 slashed = 6 slash() calls
        uint before = gasleft();
        tc.slashAggregators(1);
        console.log("[GAS][S3] slashAggregators (5 T1 batches, 1/3 agg slashed per batch):", before - gasleft());
    }

    function test_gas_s3_slashAggregators_10batches() public {
        _setupToT1Open(10);
        _runT1T2WorstCase(1);
        tc.slashAuditors(1);

        // 10 T1 batches × 1 slashed + 1 T2 slashed = 11 slash() calls
        uint before = gasleft();
        tc.slashAggregators(1);
        console.log("[GAS][S3] slashAggregators (10 T1 batches, 1/3 agg slashed per batch):", before - gasleft());
    }
}
