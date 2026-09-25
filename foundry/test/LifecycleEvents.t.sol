// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

// ─────────────────────────────────────────────────────────────────────────────
// Tests for issue #153: lifecycle events
//   - GIStateChanged emitted by _setGIstate with correct GI and ordinal
//   - GI ordering fix: GIstarted fires for GI N, not GI N-1
//   - LocalModelSubmitted emitted by DINTaskAuditor.submitLocalModel
//   - T1AggregationSubmitted emitted by submitT1Aggregation
//   - T2AggregationSubmitted emitted by submitT2Aggregation
//   - T1BatchFinalized emitted per batch in finalizeT1Aggregation
//   - T2Finalized emitted in finalizeT2Aggregation
// Run: forge test --match-contract LifecycleEventsTest -vv
// ─────────────────────────────────────────────────────────────────────────────

import {Test} from "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DINTaskCoordinator} from "../src/DINTaskCoordinator.sol";
import {DINTaskAuditor} from "../src/DINTaskAuditor.sol";
import {GIstates} from "../src/DINShared.sol";

contract LifecycleEventsTest is Test {
    DinToken token;
    DinCoordinator coordinator;
    DinValidatorStake stake;

    DINTaskCoordinator tc;
    DINTaskAuditor ta;

    address admin      = makeAddr("admin");
    address modelOwner = makeAddr("modelOwner");
    address auditor1   = makeAddr("auditor1");
    address auditor2   = makeAddr("auditor2");
    address auditor3   = makeAddr("auditor3");
    address agg1       = makeAddr("agg1");
    address agg2       = makeAddr("agg2");
    address agg3       = makeAddr("agg3");
    address agg4       = makeAddr("agg4");
    address agg5       = makeAddr("agg5");
    address agg6       = makeAddr("agg6");
    address client1    = makeAddr("client1");
    address client2    = makeAddr("client2");
    address client3    = makeAddr("client3");

    bytes32 constant TEST_SALT = bytes32(uint256(0xC0FFEE));
    bytes32 constant CID_A     = bytes32(uint256(0xA1));
    bytes32 constant CID_B     = bytes32(uint256(0xB2));

    // GIstates ordinals
    uint8 constant GI_STARTED                      = 5;
    uint8 constant GI_AGG_REG_STARTED              = 6;
    uint8 constant GI_AGG_REG_CLOSED               = 7;
    uint8 constant GI_AUD_REG_STARTED              = 8;
    uint8 constant GI_AUD_REG_CLOSED               = 9;
    uint8 constant GI_LMS_STARTED                  = 10;
    uint8 constant GI_LMS_CLOSED                   = 11;
    uint8 constant GI_AUDITOR_BATCHES_CREATED       = 12;
    uint8 constant GI_LMS_EVAL_STARTED             = 13;
    uint8 constant GI_LMS_EVAL_REVEAL_STARTED      = 14;
    uint8 constant GI_LMS_EVAL_CLOSED              = 15;
    uint8 constant GI_T1T2_CREATED                 = 16;
    uint8 constant GI_T1_AGG_STARTED               = 17;
    uint8 constant GI_T1_AGG_DONE                  = 18;
    uint8 constant GI_T2_AGG_STARTED               = 19;
    uint8 constant GI_T2_AGG_DONE                  = 20;
    uint8 constant GI_AUDITORS_SLASHED             = 21;
    uint8 constant GI_AGGREGATORS_SLASHED          = 22;
    uint8 constant GI_ENDED                        = 23;

    function setUp() public {
        vm.startPrank(admin);

        DinToken tokenImpl = new DinToken();
        TransparentUpgradeableProxy tokenProxy = new TransparentUpgradeableProxy(
            address(tokenImpl), admin, abi.encodeCall(DinToken.initialize, ())
        );
        token = DinToken(address(tokenProxy));

        DinCoordinator coordinatorImpl = new DinCoordinator();
        TransparentUpgradeableProxy coordinatorProxy = new TransparentUpgradeableProxy(
            address(coordinatorImpl), admin,
            abi.encodeCall(DinCoordinator.initialize, (address(token)))
        );
        coordinator = DinCoordinator(address(coordinatorProxy));
        token.setCoordinator(address(coordinator));

        DinValidatorStake stakeImpl = new DinValidatorStake();
        TransparentUpgradeableProxy stakeProxy = new TransparentUpgradeableProxy(
            address(stakeImpl), admin,
            abi.encodeCall(DinValidatorStake.initialize, (address(token), address(coordinator)))
        );
        stake = DinValidatorStake(address(stakeProxy));
        coordinator.updateValidatorStakeContract(address(stake));

        vm.stopPrank();

        vm.startPrank(modelOwner);
        tc = new DINTaskCoordinator(address(stake), 1);
        ta = new DINTaskAuditor(address(stake), address(tc), 1);
        tc.setDINTaskAuditorContract(address(ta));
        tc.setDinToken(address(token));
        ta.setDinToken(address(token));
        vm.stopPrank();

        vm.startPrank(admin);
        coordinator.addSlasherContract(address(tc));
        coordinator.addSlasherContract(address(ta));
        vm.stopPrank();

        vm.startPrank(modelOwner);
        tc.setDINTaskCoordinatorAsSlasher();
        tc.setDINTaskAuditorAsSlasher();
        tc.setGenesisModelIpfsHash(bytes32(uint256(1)));
        vm.stopPrank();
    }

    // ── helpers ──────────────────────────────────────────────────────────────

    function _fundAndStake(address who) internal {
        vm.deal(who, 1 ether);
        vm.prank(who);
        coordinator.depositAndMint{value: 0.001 ether}();
        vm.startPrank(who);
        token.approve(address(stake), type(uint256).max);
        stake.stake(10 ether);
        vm.stopPrank();
    }

    function _fundDin(address who, uint256 dinAmount) internal {
        uint256 ethNeeded = (dinAmount * 1e18) / (1_000_000 * 1e18) + 1;
        vm.deal(who, ethNeeded + 1 ether);
        vm.prank(who);
        coordinator.depositAndMint{value: ethNeeded}();
        vm.startPrank(who);
        token.approve(address(tc), type(uint256).max);
        token.approve(address(ta), type(uint256).max);
        vm.stopPrank();
    }

    /// @dev Advances to LMSstarted with 6 aggs and 3 auditors registered.
    function _setupToLMS(uint256 giIndex, uint256 pool) internal {
        for (uint i = 0; i < 6; i++) {
            address agg = [agg1, agg2, agg3, agg4, agg5, agg6][i];
            _fundAndStake(agg);
        }
        _fundAndStake(auditor1);
        _fundAndStake(auditor2);
        _fundAndStake(auditor3);

        _fundDin(modelOwner, pool);
        vm.prank(modelOwner);
        ta.depositRewards(giIndex, pool);

        vm.startPrank(modelOwner);
        tc.startGI(giIndex);
        tc.startDINaggregatorsRegistration(giIndex);
        vm.stopPrank();

        vm.prank(agg1); tc.registerDINaggregator(giIndex);
        vm.prank(agg2); tc.registerDINaggregator(giIndex);
        vm.prank(agg3); tc.registerDINaggregator(giIndex);
        vm.prank(agg4); tc.registerDINaggregator(giIndex);
        vm.prank(agg5); tc.registerDINaggregator(giIndex);
        vm.prank(agg6); tc.registerDINaggregator(giIndex);

        vm.startPrank(modelOwner);
        tc.closeDINaggregatorsRegistration(giIndex);
        tc.startDINauditorsRegistration(giIndex);
        vm.stopPrank();

        vm.prank(auditor1); ta.registerDINAuditor(giIndex);
        vm.prank(auditor2); ta.registerDINAuditor(giIndex);
        vm.prank(auditor3); ta.registerDINAuditor(giIndex);

        vm.startPrank(modelOwner);
        tc.closeDINauditorsRegistration(giIndex);
        tc.startLMsubmissions(giIndex);
        vm.stopPrank();
    }

    /// @dev Submits 3 local models and advances through eval to T1AggregationStarted.
    function _advanceToT1(uint256 giIndex) internal {
        vm.prank(client1); ta.submitLocalModel(bytes32(uint256(100)), giIndex);
        vm.prank(client2); ta.submitLocalModel(bytes32(uint256(200)), giIndex);
        vm.prank(client3); ta.submitLocalModel(bytes32(uint256(300)), giIndex);

        vm.startPrank(modelOwner);
        tc.closeLMsubmissions(giIndex);
        tc.createAuditorsBatches(giIndex);
        tc.setTestDataAssignedFlag(giIndex, true);
        tc.startLMsubmissionsEvaluation(giIndex);
        vm.stopPrank();

        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(giIndex, 0);
        for (uint ai = 0; ai < batchAuditors.length; ai++) {
            for (uint mi = 0; mi < modelIdxs.length; mi++) {
                bytes32 ch = keccak256(abi.encodePacked(uint256(80), true, TEST_SALT));
                vm.prank(batchAuditors[ai]);
                ta.commitAuditScore(giIndex, 0, modelIdxs[mi], ch);
            }
        }

        vm.prank(modelOwner);
        tc.startLMsubmissionsEvaluationReveal(giIndex);

        for (uint ai = 0; ai < batchAuditors.length; ai++) {
            for (uint mi = 0; mi < modelIdxs.length; mi++) {
                vm.prank(batchAuditors[ai]);
                ta.revealAuditScore(giIndex, 0, modelIdxs[mi], 80, true, TEST_SALT);
            }
        }

        vm.startPrank(modelOwner);
        tc.closeLMsubmissionsEvaluation(giIndex);
        tc.autoCreateTier1AndTier2(giIndex);
        tc.startT1Aggregation(giIndex);
        vm.stopPrank();
    }

    // ── GIStateChanged ordering fix ───────────────────────────────────────────

    /// @dev Verifies that GIstarted fires with the new GI index (N), not N-1.
    function test_GIStateChanged_GIstarted_usesIncrementedGI() public {
        // GI starts at 0; after startGI(1) the counter is incremented to 1
        // before the event fires, so the event must carry GI=1.
        _fundDin(modelOwner, 1_000 ether);
        vm.prank(modelOwner);
        ta.depositRewards(1, 1_000 ether);

        vm.expectEmit(true, true, false, false, address(tc));
        emit DINTaskCoordinator.GIStateChanged(1, GI_STARTED);
        vm.prank(modelOwner);
        tc.startGI(1);
    }

    /// @dev Sanity: a second startGI (GI=2) fires with GI=2, not 1.
    function test_GIStateChanged_secondGI_usesCorrectIndex() public {
        _setupToLMS(1, 10_000 ether);
        _advanceToT1(1);

        uint256 t1Count = tc.tier1BatchCount(1);
        for (uint b = 0; b < t1Count; b++) {
            (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, b);
            for (uint i = 0; i < t1aggs.length; i++) {
                vm.prank(t1aggs[i]);
                tc.submitT1Aggregation(1, b, CID_A);
            }
        }
        vm.prank(modelOwner); tc.finalizeT1Aggregation(1);
        vm.prank(modelOwner); tc.startT2Aggregation(1);

        try tc.getTier2Batch(1, 0) returns (uint, address[] memory t2aggs, bool, bytes32) {
            for (uint i = 0; i < t2aggs.length; i++) {
                vm.prank(t2aggs[i]);
                tc.submitT2Aggregation(1, 0, CID_B);
            }
        } catch {}

        vm.prank(modelOwner); tc.finalizeT2Aggregation(1);
        vm.prank(modelOwner); tc.slashAuditors(1);
        vm.prank(modelOwner); tc.slashAggregators(1);
        vm.prank(modelOwner); tc.endGI(1);

        _fundDin(modelOwner, 10_000 ether);
        vm.prank(modelOwner);
        ta.depositRewards(2, 10_000 ether);

        vm.expectEmit(true, true, false, false, address(tc));
        emit DINTaskCoordinator.GIStateChanged(2, GI_STARTED);
        vm.prank(modelOwner);
        tc.startGI(2);
    }

    // ── LocalModelSubmitted ───────────────────────────────────────────────────

    function test_localModelSubmitted_emitted() public {
        _setupToLMS(1, 10_000 ether);

        vm.expectEmit(true, true, true, true, address(ta));
        emit DINTaskAuditor.LocalModelSubmitted(1, 0, client1, bytes32(uint256(100)));
        vm.prank(client1);
        ta.submitLocalModel(bytes32(uint256(100)), 1);
    }

    function test_localModelSubmitted_indexIncrements() public {
        _setupToLMS(1, 10_000 ether);

        vm.prank(client1);
        ta.submitLocalModel(bytes32(uint256(100)), 1);

        // Second submission gets modelIndex = 1
        vm.expectEmit(true, true, true, true, address(ta));
        emit DINTaskAuditor.LocalModelSubmitted(1, 1, client2, bytes32(uint256(200)));
        vm.prank(client2);
        ta.submitLocalModel(bytes32(uint256(200)), 1);
    }

    // ── T1AggregationSubmitted ────────────────────────────────────────────────

    function test_t1AggregationSubmitted_emitted() public {
        _setupToLMS(1, 10_000 ether);
        _advanceToT1(1);

        (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, 0);
        address firstAgg = t1aggs[0];

        vm.expectEmit(true, true, true, true, address(tc));
        emit DINTaskCoordinator.T1AggregationSubmitted(1, 0, firstAgg, CID_A);
        vm.prank(firstAgg);
        tc.submitT1Aggregation(1, 0, CID_A);
    }

    // ── T2AggregationSubmitted ────────────────────────────────────────────────

    function test_t2AggregationSubmitted_emitted() public {
        _setupToLMS(1, 10_000 ether);
        _advanceToT1(1);

        uint256 t1Count = tc.tier1BatchCount(1);
        for (uint b = 0; b < t1Count; b++) {
            (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, b);
            for (uint i = 0; i < t1aggs.length; i++) {
                vm.prank(t1aggs[i]);
                tc.submitT1Aggregation(1, b, CID_A);
            }
        }
        vm.prank(modelOwner); tc.finalizeT1Aggregation(1);
        vm.prank(modelOwner); tc.startT2Aggregation(1);

        (uint bId, address[] memory t2aggs, , ) = tc.getTier2Batch(1, 0);

        vm.expectEmit(true, true, true, true, address(tc));
        emit DINTaskCoordinator.T2AggregationSubmitted(1, bId, t2aggs[0], CID_B);
        vm.prank(t2aggs[0]);
        tc.submitT2Aggregation(1, bId, CID_B);
    }

    // ── T1BatchFinalized ──────────────────────────────────────────────────────

    function test_t1BatchFinalized_emittedPerBatch() public {
        _setupToLMS(1, 10_000 ether);
        _advanceToT1(1);

        uint256 t1Count = tc.tier1BatchCount(1);
        for (uint b = 0; b < t1Count; b++) {
            (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, b);
            for (uint i = 0; i < t1aggs.length; i++) {
                vm.prank(t1aggs[i]);
                tc.submitT1Aggregation(1, b, CID_A);
            }
        }

        // Expect one T1BatchFinalized per batch
        for (uint b = 0; b < t1Count; b++) {
            vm.expectEmit(true, true, false, true, address(tc));
            emit DINTaskCoordinator.T1BatchFinalized(1, b, CID_A);
        }
        vm.prank(modelOwner);
        tc.finalizeT1Aggregation(1);
    }

    // ── T2Finalized ──────────────────────────────────────────────────────────

    function test_t2Finalized_emitted() public {
        _setupToLMS(1, 10_000 ether);
        _advanceToT1(1);

        uint256 t1Count = tc.tier1BatchCount(1);
        for (uint b = 0; b < t1Count; b++) {
            (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, b);
            for (uint i = 0; i < t1aggs.length; i++) {
                vm.prank(t1aggs[i]);
                tc.submitT1Aggregation(1, b, CID_A);
            }
        }
        vm.prank(modelOwner); tc.finalizeT1Aggregation(1);
        vm.prank(modelOwner); tc.startT2Aggregation(1);

        (, address[] memory t2aggs, , ) = tc.getTier2Batch(1, 0);
        for (uint i = 0; i < t2aggs.length; i++) {
            vm.prank(t2aggs[i]);
            tc.submitT2Aggregation(1, 0, CID_B);
        }

        vm.expectEmit(true, false, false, true, address(tc));
        emit DINTaskCoordinator.T2Finalized(1, CID_B);
        vm.prank(modelOwner);
        tc.finalizeT2Aggregation(1);
    }

    // ── Full-GI ordered GIStateChanged sequence ───────────────────────────────

    /// @dev Runs a full honest GI and asserts every state transition fires in
    ///      order with the correct GI index and state ordinal.
    function test_fullGI_GIStateChanged_sequence() public {
        _setupToLMS(1, 10_000 ether);

        // startGI already fired inside _setupToLMS — re-verify via recorded
        // state rather than expectEmit (call already happened).
        assertEq(tc.GI(), 1);
        assertEq(uint8(tc.GIstate()), GI_LMS_STARTED);

        // LMSclosed
        vm.prank(client1); ta.submitLocalModel(bytes32(uint256(100)), 1);
        vm.prank(client2); ta.submitLocalModel(bytes32(uint256(200)), 1);
        vm.prank(client3); ta.submitLocalModel(bytes32(uint256(300)), 1);

        vm.expectEmit(true, true, false, false, address(tc));
        emit DINTaskCoordinator.GIStateChanged(1, GI_LMS_CLOSED);
        vm.prank(modelOwner); tc.closeLMsubmissions(1);

        // AuditorsBatchesCreated
        vm.expectEmit(true, true, false, false, address(tc));
        emit DINTaskCoordinator.GIStateChanged(1, GI_AUDITOR_BATCHES_CREATED);
        vm.prank(modelOwner); tc.createAuditorsBatches(1);

        vm.prank(modelOwner); tc.setTestDataAssignedFlag(1, true);

        // LMSevaluationStarted
        vm.expectEmit(true, true, false, false, address(tc));
        emit DINTaskCoordinator.GIStateChanged(1, GI_LMS_EVAL_STARTED);
        vm.prank(modelOwner); tc.startLMsubmissionsEvaluation(1);

        // commit
        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);
        for (uint ai = 0; ai < batchAuditors.length; ai++) {
            for (uint mi = 0; mi < modelIdxs.length; mi++) {
                bytes32 ch = keccak256(abi.encodePacked(uint256(80), true, TEST_SALT));
                vm.prank(batchAuditors[ai]);
                ta.commitAuditScore(1, 0, modelIdxs[mi], ch);
            }
        }

        // LMSevaluationRevealStarted
        vm.expectEmit(true, true, false, false, address(tc));
        emit DINTaskCoordinator.GIStateChanged(1, GI_LMS_EVAL_REVEAL_STARTED);
        vm.prank(modelOwner); tc.startLMsubmissionsEvaluationReveal(1);

        // reveal
        for (uint ai = 0; ai < batchAuditors.length; ai++) {
            for (uint mi = 0; mi < modelIdxs.length; mi++) {
                vm.prank(batchAuditors[ai]);
                ta.revealAuditScore(1, 0, modelIdxs[mi], 80, true, TEST_SALT);
            }
        }

        // LMSevaluationClosed
        vm.expectEmit(true, true, false, false, address(tc));
        emit DINTaskCoordinator.GIStateChanged(1, GI_LMS_EVAL_CLOSED);
        vm.prank(modelOwner); tc.closeLMsubmissionsEvaluation(1);

        // T1nT2Bcreated
        vm.expectEmit(true, true, false, false, address(tc));
        emit DINTaskCoordinator.GIStateChanged(1, GI_T1T2_CREATED);
        vm.prank(modelOwner); tc.autoCreateTier1AndTier2(1);

        // T1AggregationStarted
        vm.expectEmit(true, true, false, false, address(tc));
        emit DINTaskCoordinator.GIStateChanged(1, GI_T1_AGG_STARTED);
        vm.prank(modelOwner); tc.startT1Aggregation(1);

        uint256 t1Count = tc.tier1BatchCount(1);
        for (uint b = 0; b < t1Count; b++) {
            (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, b);
            for (uint i = 0; i < t1aggs.length; i++) {
                vm.prank(t1aggs[i]);
                tc.submitT1Aggregation(1, b, CID_A);
            }
        }

        // T1AggregationDone
        vm.expectEmit(true, true, false, false, address(tc));
        emit DINTaskCoordinator.GIStateChanged(1, GI_T1_AGG_DONE);
        vm.prank(modelOwner); tc.finalizeT1Aggregation(1);

        // T2AggregationStarted
        vm.expectEmit(true, true, false, false, address(tc));
        emit DINTaskCoordinator.GIStateChanged(1, GI_T2_AGG_STARTED);
        vm.prank(modelOwner); tc.startT2Aggregation(1);

        (, address[] memory t2aggs, , ) = tc.getTier2Batch(1, 0);
        for (uint i = 0; i < t2aggs.length; i++) {
            vm.prank(t2aggs[i]);
            tc.submitT2Aggregation(1, 0, CID_B);
        }

        // T2AggregationDone
        vm.expectEmit(true, true, false, false, address(tc));
        emit DINTaskCoordinator.GIStateChanged(1, GI_T2_AGG_DONE);
        vm.prank(modelOwner); tc.finalizeT2Aggregation(1);

        // AuditorsSlashed
        vm.expectEmit(true, true, false, false, address(tc));
        emit DINTaskCoordinator.GIStateChanged(1, GI_AUDITORS_SLASHED);
        vm.prank(modelOwner); tc.slashAuditors(1);

        // AggregatorsSlashed
        vm.expectEmit(true, true, false, false, address(tc));
        emit DINTaskCoordinator.GIStateChanged(1, GI_AGGREGATORS_SLASHED);
        vm.prank(modelOwner); tc.slashAggregators(1);

        // GIended
        vm.expectEmit(true, true, false, false, address(tc));
        emit DINTaskCoordinator.GIStateChanged(1, GI_ENDED);
        vm.prank(modelOwner); tc.endGI(1);
    }
}
