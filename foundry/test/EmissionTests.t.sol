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
        assertEq(emission.currentEpoch(), 1);
        uint256 expected = (INITIAL_EMISSION * DECAY_BPS) / 10_000; // 80 DIN
        assertEq(emission.currentEmissionPerGI(), expected, "epoch 1 emission should be 80 DIN");
    }

    function test_decaySchedule_multipleEpochs() public {
        // Advance through 3 epochs.
        for (uint256 gi = 1; gi <= EPOCH_LENGTH * 3; gi++) {
            emission.fundGI(gi, address(auditor));
        }
        assertEq(emission.currentEpoch(), 3);
        // 100 * 0.8^3 = 51.2 DIN → integer: 100 * 8000/10000 * 8000/10000 * 8000/10000
        uint256 expected = (((INITIAL_EMISSION * DECAY_BPS) / 10_000) * DECAY_BPS / 10_000) * DECAY_BPS / 10_000;
        assertEq(emission.currentEmissionPerGI(), expected);
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
        assertEq(emission.currentEpoch(), MAX_EPOCHS);
        vm.expectRevert(DinEmission.EmissionExhausted.selector);
        emission.fundGI(EPOCH_LENGTH * MAX_EPOCHS + 1, address(auditor));
    }

    function test_emissionForCurrentEpoch_returnsZeroWhenExhausted() public {
        for (uint256 gi = 1; gi <= EPOCH_LENGTH * MAX_EPOCHS; gi++) {
            emission.fundGI(gi, address(auditor));
        }
        assertEq(emission.emissionForCurrentEpoch(), 0);
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

    function test_setEmissionParams_resetsSchedule() public {
        // Fund a few GIs first.
        emission.fundGI(1, address(auditor));
        emission.fundGI(2, address(auditor));

        vm.prank(admin);
        emission.setEmissionParams(200e18, 9000, 5, 3);

        assertEq(emission.currentEpoch(), 0);
        assertEq(emission.gisInCurrentEpoch(), 0);
        assertEq(emission.currentEmissionPerGI(), 200e18);
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
}
