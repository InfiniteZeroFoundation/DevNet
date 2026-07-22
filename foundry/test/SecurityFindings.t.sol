// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

// ─────────────────────────────────────────────────────────────────────────────
// PoC tests for the 2026-07 security review (Developer/audits/2026-07_foundry-src-security-review.md).
// Pinned to commit d136ff3. These are additive, read/observe only — no
// contract source under test is modified.
// Run: forge test --match-contract SecurityFindingsTest -vv
// ─────────────────────────────────────────────────────────────────────────────

import {Test} from "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DINModelRegistry} from "../src/DINModelRegistry.sol";
import {DinTreasury} from "../src/DinTreasury.sol";
import {DinFeeRouter} from "../src/DinFeeRouter.sol";
import {DINTaskCoordinator} from "../src/DINTaskCoordinator.sol";
import {DINTaskAuditor} from "../src/DINTaskAuditor.sol";
import {GIstates} from "../src/DINShared.sol";

contract SecurityFindingsTest is Test {
    // ─────────────────────────────────────────────────────────────────────
    // Shared platform fixture (6-step deployment order from
    // Documentation/technical/upgradable-contracts/hardhat/README.md §5)
    // ─────────────────────────────────────────────────────────────────────

    DinToken tokenImpl;
    DinCoordinator coordinatorImpl;
    DinValidatorStake stakeImpl;
    DINModelRegistry registryImpl;

    DinToken token;
    DinCoordinator coordinator;
    DinValidatorStake stake;
    DINModelRegistry registry;
    DinTreasury treasury;
    DinFeeRouter feeRouter;

    address admin = makeAddr("admin");

    function _deployPlatform() internal {
        vm.startPrank(admin);
        _deployTreasury();
        _deployTokenAndCoordinator();
        _deployFeeRouter();
        _deployStakeAndRegistry();
        vm.stopPrank();
    }

    function _deployTreasury() private {
        treasury = DinTreasury(payable(address(new TransparentUpgradeableProxy(
            address(new DinTreasury()), admin, abi.encodeCall(DinTreasury.initialize, ())
        ))));
    }

    function _deployTokenAndCoordinator() private {
        tokenImpl = new DinToken();
        token = DinToken(address(new TransparentUpgradeableProxy(
            address(tokenImpl), admin, abi.encodeCall(DinToken.initialize, ())
        )));

        coordinatorImpl = new DinCoordinator();
        coordinator = DinCoordinator(address(new TransparentUpgradeableProxy(
            address(coordinatorImpl), admin, abi.encodeCall(DinCoordinator.initialize, (address(token)))
        )));

        token.setCoordinator(address(coordinator));
        coordinator.setTreasury(address(treasury));
    }

    function _deployFeeRouter() private {
        feeRouter = DinFeeRouter(address(new TransparentUpgradeableProxy(
            address(new DinFeeRouter()), admin,
            abi.encodeCall(DinFeeRouter.initialize, (address(token), address(treasury)))
        )));
    }

    function _deployStakeAndRegistry() private {
        stakeImpl = new DinValidatorStake();
        stake = DinValidatorStake(address(new TransparentUpgradeableProxy(
            address(stakeImpl), admin,
            abi.encodeCall(DinValidatorStake.initialize, (address(token), address(coordinator)))
        )));
        coordinator.updateValidatorStakeContract(address(stake));

        registryImpl = new DINModelRegistry();
        registry = DINModelRegistry(address(new TransparentUpgradeableProxy(
            address(registryImpl), admin,
            abi.encodeCall(DINModelRegistry.initialize, (address(stake)))
        )));

        registry.setDinToken(address(token));
        registry.setFeeRouter(address(feeRouter));
        feeRouter.addFeeSource(address(registry));
        registry.setDinFees(1e18, 10e18, 1e17, 1e18);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Proxy-specific: initializer protection
    //
    // Confirms _disableInitializers() is effective at RUNTIME, not just
    // present in source — i.e. an attacker cannot call initialize() directly
    // on the deployed implementation address and claim ownership of it.
    // (Not exploitable against the real protocol today, since the
    // implementation holds no funds/routing of its own — but see the
    // finding writeup for why this still matters operationally.)
    // ─────────────────────────────────────────────────────────────────────

    function test_implementation_rejectsDirectInitialize_DinToken() public {
        DinToken impl = new DinToken();
        vm.expectRevert();
        impl.initialize();
    }

    function test_implementation_rejectsDirectInitialize_DinCoordinator() public {
        DinCoordinator impl = new DinCoordinator();
        vm.expectRevert();
        impl.initialize(makeAddr("fakeToken"));
    }

    function test_implementation_rejectsDirectInitialize_DinValidatorStake() public {
        DinValidatorStake impl = new DinValidatorStake();
        vm.expectRevert();
        impl.initialize(makeAddr("fakeToken"), makeAddr("fakeCoordinator"));
    }

    function test_implementation_rejectsDirectInitialize_DINModelRegistry() public {
        DINModelRegistry impl = new DINModelRegistry();
        vm.expectRevert();
        impl.initialize(makeAddr("fakeStake"));
    }

    function test_proxy_rejectsDoubleInitialize_DinToken() public {
        _deployPlatform();
        vm.expectRevert();
        token.initialize();
    }

    function test_proxy_rejectsDoubleInitialize_DinCoordinator() public {
        _deployPlatform();
        vm.expectRevert();
        coordinator.initialize(makeAddr("someToken"));
    }

    function test_proxy_rejectsDoubleInitialize_DinValidatorStake() public {
        _deployPlatform();
        vm.expectRevert();
        stake.initialize(makeAddr("t"), makeAddr("c"));
    }

    function test_proxy_rejectsDoubleInitialize_DINModelRegistry() public {
        _deployPlatform();
        vm.expectRevert();
        registry.initialize(makeAddr("s"));
    }

    // ─────────────────────────────────────────────────────────────────────
    // Finding: zero-CID sentinel collision permanently DoSes
    // finalizeT1Aggregation / finalizeT2Aggregation for the whole GI.
    //
    // T1/T2 finalization uses `winningCID == bytes32(0)` to detect "no
    // submissions for this batch" and revert. Any assigned aggregator can
    // submit `bytes32(0)` as their own aggregation CID; if that CID ends up
    // as the batch's plurality vote (e.g. the only submission in that
    // batch), finalization reverts for the ENTIRE GI, indistinguishable
    // from "nobody submitted" — even though a submission genuinely exists.
    // Task contracts are not upgradeable, so this has no on-chain recovery
    // path: the GI is bricked and the model owner must abandon the round.
    // ─────────────────────────────────────────────────────────────────────

    DINTaskCoordinator tc;
    DINTaskAuditor ta;

    address modelOwner = makeAddr("modelOwner");
    address auditor1 = makeAddr("auditor1");
    address auditor2 = makeAddr("auditor2");
    address client1 = makeAddr("client1");
    address client2 = makeAddr("client2");
    address client3 = makeAddr("client3");
    address agg1 = makeAddr("agg1");
    address agg2 = makeAddr("agg2");
    address agg3 = makeAddr("agg3");

    function _fundAndStake(address who) internal {
        vm.deal(who, 1 ether);
        vm.prank(who);
        coordinator.depositAndMint{value: 0.001 ether}();
        vm.startPrank(who);
        token.approve(address(stake), type(uint256).max);
        stake.stake(10 ether); // MIN_STAKE
        vm.stopPrank();
    }

    function _deployTaskPair() internal {
        vm.startPrank(modelOwner);
        tc = new DINTaskCoordinator(address(stake));
        ta = new DINTaskAuditor(address(stake), address(tc));
        tc.setDINTaskAuditorContract(address(ta));
        vm.stopPrank();

        // DIN-Representative authorises both as slashers
        vm.startPrank(admin);
        coordinator.addSlasherContract(address(tc));
        coordinator.addSlasherContract(address(ta));
        vm.stopPrank();

        vm.startPrank(modelOwner);
        tc.setDINTaskCoordinatorAsSlasher();
        tc.setDINTaskAuditorAsSlasher();
        tc.setGenesisModelIpfsHash(bytes32(uint256(1)));
        tc.startGI(1);
        vm.stopPrank();
    }

    function _runToT1AggregationStarted() internal {
        _deployPlatform();
        _deployTaskPair();

        _fundAndStake(auditor1);
        _fundAndStake(auditor2);
        _fundAndStake(agg1);
        _fundAndStake(agg2);
        _fundAndStake(agg3);

        vm.startPrank(modelOwner);
        tc.startDINaggregatorsRegistration(1);
        vm.stopPrank();

        vm.prank(agg1);
        tc.registerDINaggregator(1);
        vm.prank(agg2);
        tc.registerDINaggregator(1);
        vm.prank(agg3);
        tc.registerDINaggregator(1);

        vm.startPrank(modelOwner);
        tc.closeDINaggregatorsRegistration(1);
        tc.startDINauditorsRegistration(1);
        vm.stopPrank();

        // auditorsPerBatch defaults to 3 (demo Params in the DINTaskAuditor
        // constructor) so all 3 auditors must register before the window closes.
        address auditor3 = makeAddr("auditor3");
        _fundAndStake(auditor3);

        vm.prank(auditor1);
        ta.registerDINAuditor(1);
        vm.prank(auditor2);
        ta.registerDINAuditor(1);
        vm.prank(auditor3);
        ta.registerDINAuditor(1);

        vm.startPrank(modelOwner);
        tc.closeDINauditorsRegistration(1);
        tc.startLMsubmissions(1);
        vm.stopPrank();

        vm.prank(client1);
        ta.submitLocalModel(bytes32(uint256(100)), 1);
        vm.prank(client2);
        ta.submitLocalModel(bytes32(uint256(200)), 1);
        vm.prank(client3);
        ta.submitLocalModel(bytes32(uint256(300)), 1);

        vm.startPrank(modelOwner);
        tc.closeLMsubmissions(1);
        tc.createAuditorsBatches(1);
        tc.setTestDataAssignedFlag(1, true);
        tc.startLMsubmissionsEvaluation(1);
        vm.stopPrank();

        // Both models pass: all 3 auditors vote eligible + score 100 on both models.
        (, address[] memory batchAuditors, uint[] memory modelIdxs,) = ta.getAuditorsBatch(1, 0);
        for (uint i = 0; i < batchAuditors.length; i++) {
            for (uint m = 0; m < modelIdxs.length; m++) {
                vm.prank(batchAuditors[i]);
                ta.setAuditScorenEligibility(1, 0, modelIdxs[m], 100, true);
            }
        }

        vm.startPrank(modelOwner);
        tc.closeLMsubmissionsEvaluation(1);
        tc.autoCreateTier1AndTier2(1);
        tc.startT1Aggregation(1);
        vm.stopPrank();
    }

    function test_finalizeT1Aggregation_zeroCID_bricksEntireGI() public {
        _runToT1AggregationStarted();

        (, address[] memory t1aggs,,,) = tc.getTier1Batch(1, 0);
        assertEq(t1aggs.length, 3, "sanity: T1 batch should have 3 aggregators");

        // Only ONE of the three assigned aggregators submits, and submits
        // the zero CID. The other two never submit before the model owner
        // closes the window (a routine "not everyone responded in time"
        // scenario, not an edge case).
        vm.prank(t1aggs[0]);
        tc.submitT1Aggregation(1, 0, bytes32(0));

        // This is the ONLY submission in the batch, so it is unambiguously
        // the plurality winner (1 vote > 0). Finalization should therefore
        // either succeed with finalCID == bytes32(0), or explicitly reject
        // zero-CID submissions at submit time. Instead:
        vm.expectRevert(); // TC_NoSubmissions — wrongly conflates "no one voted" with "the winning vote was 0x0"
        tc.finalizeT1Aggregation(1);

        // The GI is now stuck: GIstate is still T1AggregationStarted, the
        // task contracts are not upgradeable, and there is no admin
        // function to skip/override a single batch. Every subsequent call
        // to finalizeT1Aggregation reverts the same way, forever.
        assertEq(uint256(tc.GIstate()), uint256(GIstates.T1AggregationStarted));
    }
}
