// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinEmission} from "../src/DinEmission.sol";

// ─── Minimal task-auditor stub ───────────────────────────────────────────────

contract MockTaskAuditor {
    mapping(uint256 => uint256) public giRewardPool;

    function depositRewards(uint256 gi, uint256 amount) external {
        DinToken(msg.sender); // silence unused-import warning
        // pull DIN from caller
        require(
            DinToken(address(0)).balanceOf(address(this)) >= 0, // dummy — real transfer below
            "stub"
        );
        giRewardPool[gi] += amount;
    }
}

// We need a real ERC20 transfer in depositRewards so let's wire it properly.
contract MockTaskAuditorReal {
    DinToken public immutable din;
    mapping(uint256 => uint256) public giRewardPool;

    constructor(DinToken din_) { din = din_; }

    function depositRewards(uint256 gi, uint256 amount) external {
        din.transferFrom(msg.sender, address(this), amount);
        giRewardPool[gi] += amount;
    }
}

// ─── Test contract ───────────────────────────────────────────────────────────

contract EmissionTests is Test {
    address internal admin = address(0xABCD);

    DinToken internal token;
    DinCoordinator internal coordinator;
    DinEmission internal emission;
    MockTaskAuditorReal internal auditor;

    // Default schedule: 100 DIN/GI, 80% decay per epoch, 10 GIs/epoch, 5 epochs.
    uint256 internal constant INITIAL_EMISSION = 100e18;
    uint256 internal constant DECAY_BPS        = 8000; // 80% retained
    uint256 internal constant EPOCH_LENGTH     = 10;
    uint256 internal constant MAX_EPOCHS       = 5;

    function setUp() public {
        vm.startPrank(admin);

        // DinToken proxy
        DinToken tokenImpl = new DinToken();
        TransparentUpgradeableProxy tokenProxy = new TransparentUpgradeableProxy(
            address(tokenImpl),
            admin,
            abi.encodeCall(DinToken.initialize, ())
        );
        token = DinToken(address(tokenProxy));

        // DinCoordinator proxy
        DinCoordinator coordImpl = new DinCoordinator();
        TransparentUpgradeableProxy coordProxy = new TransparentUpgradeableProxy(
            address(coordImpl),
            admin,
            abi.encodeCall(DinCoordinator.initialize, (address(token)))
        );
        coordinator = DinCoordinator(address(coordProxy));
        token.setCoordinator(address(coordinator));

        // DinEmission proxy
        DinEmission emissionImpl = new DinEmission();
        TransparentUpgradeableProxy emissionProxy = new TransparentUpgradeableProxy(
            address(emissionImpl),
            admin,
            abi.encodeCall(
                DinEmission.initialize,
                (
                    address(coordinator),
                    address(token),
                    INITIAL_EMISSION,
                    DECAY_BPS,
                    EPOCH_LENGTH,
                    MAX_EPOCHS
                )
            )
        );
        emission = DinEmission(address(emissionProxy));

        // Wire emission contract into coordinator
        coordinator.setEmissionContract(address(emission));

        // Mock task auditor
        auditor = new MockTaskAuditorReal(token);

        vm.stopPrank();
    }

    // ── mintEmission access control ──────────────────────────────────────

    function test_mintEmission_rejectsUnauthorizedCaller() public {
        vm.expectRevert(DinCoordinator.UnauthorizedEmissionCaller.selector);
        vm.prank(address(0xDEAD));
        coordinator.mintEmission(address(0xDEAD), 1e18);
    }

    // ── fundGI basic ─────────────────────────────────────────────────────

    function test_fundGI_mintsAndDeposits() public {
        uint256 balBefore = token.balanceOf(address(auditor));
        emission.fundGI(1, address(auditor));
        assertEq(
            token.balanceOf(address(auditor)) - balBefore,
            INITIAL_EMISSION,
            "auditor should receive INITIAL_EMISSION DIN"
        );
        assertEq(auditor.giRewardPool(1), INITIAL_EMISSION);
    }

    function test_fundGI_updatesTotalEmitted() public {
        emission.fundGI(1, address(auditor));
        assertEq(emission.totalEmitted(), INITIAL_EMISSION);
    }

    function test_fundGI_updatesTotalMintedOnCoordinator() public {
        emission.fundGI(1, address(auditor));
        assertEq(coordinator.totalMinted(), INITIAL_EMISSION);
    }

    function test_fundGI_revertsOnDoubleFund() public {
        emission.fundGI(1, address(auditor));
        vm.expectRevert(abi.encodeWithSelector(DinEmission.GIAlreadyFunded.selector, 1));
        emission.fundGI(1, address(auditor));
    }

    // ── Decay schedule ───────────────────────────────────────────────────

    function test_decaySchedule_epochBoundaryReducesEmission() public {
        // Fund EPOCH_LENGTH GIs to advance to epoch 1.
        for (uint256 gi = 1; gi <= EPOCH_LENGTH; gi++) {
            emission.fundGI(gi, address(auditor));
        }
        (uint256 currentEpoch,, uint256 currentEmissionPerGI,) = emission.emissionState(address(auditor));
        assertEq(currentEpoch, 1);
        uint256 expected = (INITIAL_EMISSION * DECAY_BPS) / 10_000; // 80 DIN
        assertEq(currentEmissionPerGI, expected, "epoch 1 emission should be 80 DIN");
    }

    function test_decaySchedule_multipleEpochs() public {
        // Advance through 3 epochs.
        for (uint256 gi = 1; gi <= EPOCH_LENGTH * 3; gi++) {
            emission.fundGI(gi, address(auditor));
        }
        (uint256 currentEpoch,, uint256 currentEmissionPerGI,) = emission.emissionState(address(auditor));
        assertEq(currentEpoch, 3);
        // 100 * 0.8^3 = 51.2 DIN → integer: 100 * 8000/10000 * 8000/10000 * 8000/10000
        uint256 expected = (((INITIAL_EMISSION * DECAY_BPS) / 10_000) * DECAY_BPS / 10_000) * DECAY_BPS / 10_000;
        assertEq(currentEmissionPerGI, expected);
    }

    function test_emissionAtEpoch_matchesFormula() public view {
        // emissionAtEpoch should match on-chain currentEmissionPerGI at each boundary.
        uint256 e = INITIAL_EMISSION;
        for (uint256 epoch = 0; epoch < MAX_EPOCHS; epoch++) {
            assertEq(emission.emissionAtEpoch(epoch), e, "emissionAtEpoch mismatch");
            e = (e * DECAY_BPS) / 10_000;
        }
        assertEq(emission.emissionAtEpoch(MAX_EPOCHS), 0, "past maxEpochs should return 0");
    }

    // ── Final epoch (exhaustion) ─────────────────────────────────────────

    function test_finalEpoch_revertsAfterMaxEpochs() public {
        // Exhaust all MAX_EPOCHS epochs.
        for (uint256 gi = 1; gi <= EPOCH_LENGTH * MAX_EPOCHS; gi++) {
            emission.fundGI(gi, address(auditor));
        }
        (uint256 currentEpoch,,,) = emission.emissionState(address(auditor));
        assertEq(currentEpoch, MAX_EPOCHS);
        vm.expectRevert(DinEmission.EmissionExhausted.selector);
        emission.fundGI(EPOCH_LENGTH * MAX_EPOCHS + 1, address(auditor));
    }

    function test_emissionForCurrentEpoch_returnsZeroWhenExhausted() public {
        for (uint256 gi = 1; gi <= EPOCH_LENGTH * MAX_EPOCHS; gi++) {
            emission.fundGI(gi, address(auditor));
        }
        assertEq(emission.emissionForCurrentEpoch(address(auditor)), 0);
    }

    // ── mintCap respected ────────────────────────────────────────────────

    function test_mintCap_blocksEmissionOverCap() public {
        vm.prank(admin);
        // Cap at exactly 1 GI's worth — second fund should fail.
        coordinator.setMintCap(INITIAL_EMISSION);

        emission.fundGI(1, address(auditor));

        vm.expectRevert(DinCoordinator.MintCapExceeded.selector);
        emission.fundGI(2, address(auditor));
    }

    // ── faucetRetired blocks emission ────────────────────────────────────

    function test_faucetRetired_blocksEmission() public {
        vm.prank(admin);
        coordinator.retireFaucet();

        vm.expectRevert(DinCoordinator.FaucetRetired.selector);
        emission.fundGI(1, address(auditor));
    }

    // ── setEmissionParams ────────────────────────────────────────────────

    // NOTE: setEmissionParams updates only the four global schedule constants.
    // It deliberately does NOT reset any taskAuditor's in-flight progress —
    // that progress now lives in a per-taskAuditor mapping and isn't
    // centrally enumerable on-chain (see DinEmission.setEmissionParams's
    // natspec). Split into two tests covering both halves of that contract.

    function test_setEmissionParams_doesNotResetInProgressAuditor() public {
        // Fund a few GIs first — auditor has already "started".
        emission.fundGI(1, address(auditor));
        emission.fundGI(2, address(auditor));

        vm.prank(admin);
        emission.setEmissionParams(200e18, 9000, 5, 3);

        // Already-started auditor's own progress is untouched by the new
        // params — no retroactive reset.
        (uint256 currentEpoch, uint256 gisInCurrentEpoch, uint256 currentEmissionPerGI,) =
            emission.emissionState(address(auditor));
        assertEq(currentEpoch, 0);
        assertEq(gisInCurrentEpoch, 2);
        assertEq(currentEmissionPerGI, INITIAL_EMISSION);
    }

    function test_setEmissionParams_appliesToFreshAuditorOnFirstFundGI() public {
        vm.prank(admin);
        emission.setEmissionParams(200e18, 9000, 5, 3);

        // A taskAuditor that hasn't funded a GI yet picks up the new
        // schedule on its first call.
        MockTaskAuditorReal freshAuditor = new MockTaskAuditorReal(token);
        emission.fundGI(1, address(freshAuditor));

        (uint256 currentEpoch, uint256 gisInCurrentEpoch, uint256 currentEmissionPerGI,) =
            emission.emissionState(address(freshAuditor));
        assertEq(currentEpoch, 0);
        assertEq(gisInCurrentEpoch, 1);
        assertEq(currentEmissionPerGI, 200e18);
    }

    function test_setEmissionParams_invalidRevertsZeroInitial() public {
        vm.prank(admin);
        vm.expectRevert(DinEmission.InvalidParams.selector);
        emission.setEmissionParams(0, DECAY_BPS, EPOCH_LENGTH, MAX_EPOCHS);
    }

    function test_setEmissionParams_invalidRevertsZeroEpochLength() public {
        vm.prank(admin);
        vm.expectRevert(DinEmission.InvalidParams.selector);
        emission.setEmissionParams(INITIAL_EMISSION, DECAY_BPS, 0, MAX_EPOCHS);
    }

    function test_setEmissionParams_invalidRevertsZeroMaxEpochs() public {
        vm.prank(admin);
        vm.expectRevert(DinEmission.InvalidParams.selector);
        emission.setEmissionParams(INITIAL_EMISSION, DECAY_BPS, EPOCH_LENGTH, 0);
    }

    function test_setEmissionParams_invalidRevertsDecayBpsOverMax() public {
        vm.prank(admin);
        vm.expectRevert(DinEmission.InvalidParams.selector);
        emission.setEmissionParams(INITIAL_EMISSION, 10_001, EPOCH_LENGTH, MAX_EPOCHS);
    }

    // ── Integration: partial emission + external depositRewards ──────────

    function test_integration_emissionPlusExternalDeposit() public {
        // Model owner also deposits 50 DIN externally for the same GI.
        address modelOwner = address(0xBEEF);
        // Mint some DIN for the model owner via coordinator.depositAndMint.
        vm.deal(modelOwner, 1 ether);
        vm.prank(modelOwner);
        coordinator.depositAndMint{value: 1 ether}();
        uint256 externalDeposit = 50e18;

        // Emission funds the GI first.
        emission.fundGI(1, address(auditor));

        // Model owner adds on top — no double-counting.
        vm.startPrank(modelOwner);
        token.approve(address(auditor), externalDeposit);
        auditor.depositRewards(1, externalDeposit);
        vm.stopPrank();

        assertEq(
            auditor.giRewardPool(1),
            INITIAL_EMISSION + externalDeposit,
            "pool should be emission + external without double-counting"
        );
    }

    // ── Cross-model isolation (regression) ────────────────────────────────
    //
    // giEmissionFunded and the epoch/decay counters used to be single global
    // values, so two unrelated models' identically-numbered GIs collided —
    // only the first model to call fundGI for a given number could ever
    // succeed, and one model's cadence silently sped up every other model's
    // decay schedule. These regression-test the per-taskAuditor fix.

    function test_crossModel_identicalGiNumbersDoNotCollide() public {
        // Model A funds its own "GI 1".
        emission.fundGI(1, address(auditor));

        // Model B is a different taskAuditor with its own, unrelated "GI 1"
        // — must succeed, not revert with GIAlreadyFunded.
        MockTaskAuditorReal auditorB = new MockTaskAuditorReal(token);
        emission.fundGI(1, address(auditorB));

        assertEq(auditor.giRewardPool(1), INITIAL_EMISSION, "model A's GI 1 funded");
        assertEq(auditorB.giRewardPool(1), INITIAL_EMISSION, "model B's GI 1 funded independently");
    }

    function test_crossModel_independentDecaySchedules() public {
        // Model A advances through a full epoch (EPOCH_LENGTH GIs) alone.
        for (uint256 gi = 1; gi <= EPOCH_LENGTH; gi++) {
            emission.fundGI(gi, address(auditor));
        }
        (uint256 epochA,,,) = emission.emissionState(address(auditor));
        assertEq(epochA, 1, "model A should be in epoch 1 after EPOCH_LENGTH GIs");

        // Model B has funded nothing yet — its schedule must be untouched by
        // model A's progress (no shared global counter).
        MockTaskAuditorReal auditorB = new MockTaskAuditorReal(token);
        (uint256 epochB,,, bool startedB) = emission.emissionState(address(auditorB));
        assertEq(epochB, 0, "model B's schedule is unaffected by model A's progress");
        assertFalse(startedB, "model B hasn't started yet");

        // Model B's first GI still gets the full epoch-0 rate, not model
        // A's already-decayed rate.
        emission.fundGI(1, address(auditorB));
        assertEq(auditorB.giRewardPool(1), INITIAL_EMISSION, "model B starts at epoch-0 rate independently");
    }
}
