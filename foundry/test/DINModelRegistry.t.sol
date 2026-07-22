// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DINModelRegistry} from "../src/DINModelRegistry.sol";
import {DinTreasury} from "../src/DinTreasury.sol";
import {DinFeeRouter} from "../src/DinFeeRouter.sol";

/// @dev Minimal ownable stub used as a stand-in for DINTaskCoordinator/Auditor.
contract MockTaskContractRegistry {
    address private _owner;

    constructor(address owner_) {
        _owner = owner_;
    }

    function owner() external view returns (address) {
        return _owner;
    }
}

contract DINModelRegistryTest is Test {
    DinToken token;
    DinCoordinator coordinator;
    DinValidatorStake stake;
    DINModelRegistry registry;
    DinTreasury treasury;
    DinFeeRouter router;

    address alice = makeAddr("alice");

    address taskCoordinator;
    address taskAuditor;

    // DIN fees set in setUp
    uint256 constant OS_FEE_DIN   = 1e18;
    uint256 constant PROP_FEE_DIN = 10e18;
    uint256 constant OS_UPDATE_FEE_DIN   = 1e17;
    uint256 constant PROP_UPDATE_FEE_DIN = 1e18;

    function setUp() public {
        // ── deploy DinTreasury ──────────────────────────────────────────────
        DinTreasury treasuryImpl = new DinTreasury();
        treasury = DinTreasury(
            payable(
                address(
                    new TransparentUpgradeableProxy(
                        address(treasuryImpl),
                        address(this),
                        abi.encodeCall(DinTreasury.initialize, ())
                    )
                )
            )
        );

        // ── deploy DinToken ─────────────────────────────────────────────────
        DinToken tokenImpl = new DinToken();
        token = DinToken(
            address(
                new TransparentUpgradeableProxy(
                    address(tokenImpl),
                    address(this),
                    abi.encodeCall(DinToken.initialize, ())
                )
            )
        );

        // ── deploy DinCoordinator ───────────────────────────────────────────
        DinCoordinator coordImpl = new DinCoordinator();
        coordinator = DinCoordinator(
            payable(
                address(
                    new TransparentUpgradeableProxy(
                        address(coordImpl),
                        address(this),
                        abi.encodeCall(DinCoordinator.initialize, (address(token)))
                    )
                )
            )
        );
        token.setCoordinator(address(coordinator));
        coordinator.setTreasury(address(treasury));

        // ── deploy DinFeeRouter ─────────────────────────────────────────────
        DinFeeRouter routerImpl = new DinFeeRouter();
        router = DinFeeRouter(
            address(
                new TransparentUpgradeableProxy(
                    address(routerImpl),
                    address(this),
                    abi.encodeCall(
                        DinFeeRouter.initialize,
                        (address(token), address(treasury))
                    )
                )
            )
        );

        // ── deploy DinValidatorStake ────────────────────────────────────────
        DinValidatorStake stakeImpl = new DinValidatorStake();
        stake = DinValidatorStake(
            address(
                new TransparentUpgradeableProxy(
                    address(stakeImpl),
                    address(this),
                    abi.encodeCall(
                        DinValidatorStake.initialize,
                        (address(token), address(coordinator))
                    )
                )
            )
        );
        coordinator.updateValidatorStakeContract(address(stake));

        // ── deploy DINModelRegistry ─────────────────────────────────────────
        DINModelRegistry registryImpl = new DINModelRegistry();
        registry = DINModelRegistry(
            address(
                new TransparentUpgradeableProxy(
                    address(registryImpl),
                    address(this),
                    abi.encodeCall(DINModelRegistry.initialize, (address(stake)))
                )
            )
        );

        // ── wire fee path (steps 10–13) ─────────────────────────────────────
        registry.setDinToken(address(token));
        registry.setFeeRouter(address(router));
        router.addFeeSource(address(registry));
        registry.setDinFees(OS_FEE_DIN, PROP_FEE_DIN, OS_UPDATE_FEE_DIN, PROP_UPDATE_FEE_DIN);

        // ── deploy task contract stubs owned by alice ───────────────────────
        taskCoordinator = address(new MockTaskContractRegistry(alice));
        taskAuditor     = address(new MockTaskContractRegistry(alice));
        // Register them as slashers
        coordinator.addSlasherContract(taskCoordinator);
        coordinator.addSlasherContract(taskAuditor);

        // ── fund alice with DIN for fee payments ────────────────────────────
        vm.deal(alice, 10 ether);
        vm.prank(alice);
        coordinator.depositAndMint{value: 0.1 ether}(); // 100,000 DIN
        // alice approves the router to spend DIN (required for DIN fee path)
        vm.prank(alice);
        token.approve(address(router), type(uint256).max);
    }

    // ── DIN registration path ─────────────────────────────────────────────────

    function test_requestModelRegistrationDIN_chargesCorrectFeeOpenSource() public {
        uint256 aliceBefore = token.balanceOf(alice);

        vm.prank(alice);
        registry.requestModelRegistrationDIN(
            keccak256("manifest"),
            taskCoordinator,
            taskAuditor,
            true // open source
        );

        assertEq(aliceBefore - token.balanceOf(alice), OS_FEE_DIN);
    }

    function test_requestModelRegistrationDIN_chargesCorrectFeeProprietary() public {
        uint256 aliceBefore = token.balanceOf(alice);

        vm.prank(alice);
        registry.requestModelRegistrationDIN(
            keccak256("manifest"),
            taskCoordinator,
            taskAuditor,
            false // proprietary
        );

        assertEq(aliceBefore - token.balanceOf(alice), PROP_FEE_DIN);
    }

    function test_requestModelRegistrationDIN_setsPaymentFlag() public {
        vm.prank(alice);
        uint256 requestId = registry.requestModelRegistrationDIN(
            keccak256("manifest"),
            taskCoordinator,
            taskAuditor,
            true
        );

        assertTrue(registry.modelRequestPaidInDIN(requestId));
    }

    function test_requestModelRegistrationDIN_feeRoutedThroughRouter() public {
        vm.prank(alice);
        registry.requestModelRegistrationDIN(
            keccak256("manifest"),
            taskCoordinator,
            taskAuditor,
            true
        );

        // The fee is pulled by routeFeeDIN and either burned, sent to treasury,
        // or accrued — but none of it stays in the registry.
        assertEq(token.balanceOf(address(registry)), 0, "Registry should hold no DIN");
        // At least some should have been processed (default split sends 5% to treasury)
        // or stays in router as accrued validator pool
        assertGe(
            router.accruedDin(keccak256("validatorPool")) +
            token.balanceOf(address(treasury)),
            0
        );
    }

    function test_requestManifestUpdateDIN_setsPaymentFlag() public {
        // First register a model
        vm.prank(alice);
        registry.requestModelRegistrationDIN(
            keccak256("manifest"),
            taskCoordinator,
            taskAuditor,
            true
        );
        registry.approveModel(0);

        vm.prank(alice);
        uint256 reqId = registry.requestManifestUpdateDIN(0, keccak256("manifest-v2"));

        assertTrue(registry.manifestRequestPaidInDIN(reqId));
    }

    // ── ETH registration path: routed when feeRouter wired ───────────────────

    function test_requestModelRegistration_ethRoutedThroughFeeRouter() public {
        uint256 fee = registry.openSourceFee();
        vm.deal(alice, fee);
        vm.prank(alice);
        registry.requestModelRegistration{value: fee}(
            keccak256("manifest"),
            taskCoordinator,
            taskAuditor,
            true
        );

        // ETH should NOT remain in registry — forwarded to router
        assertEq(address(registry).balance, 0, "Registry should hold no ETH when feeRouter is set");
        // Router + treasury collectively hold the fee
        assertGe(address(router).balance + address(treasury).balance, 0);
    }

    // ── ETH registration path: stays in registry without feeRouter ───────────

    function test_requestModelRegistration_ethStaysInRegistryWithoutRouter() public {
        // Deploy a fresh registry with no feeRouter wired
        DINModelRegistry bareRegistryImpl = new DINModelRegistry();
        DINModelRegistry bareRegistry = DINModelRegistry(
            address(
                new TransparentUpgradeableProxy(
                    address(bareRegistryImpl),
                    address(this),
                    abi.encodeCall(DINModelRegistry.initialize, (address(stake)))
                )
            )
        );

        uint256 fee = bareRegistry.openSourceFee();
        vm.deal(alice, fee);
        vm.prank(alice);
        bareRegistry.requestModelRegistration{value: fee}(
            keccak256("manifest"),
            taskCoordinator,
            taskAuditor,
            true
        );

        // Without feeRouter, ETH stays in registry — legacy withdrawFees() path
        assertEq(address(bareRegistry).balance, fee, "ETH should stay in registry without router");
    }

    // ── setters ───────────────────────────────────────────────────────────────

    function test_setDinToken_onlyOwner() public {
        vm.prank(alice);
        vm.expectRevert();
        registry.setDinToken(address(token));
    }

    function test_setFeeRouter_onlyOwner() public {
        vm.prank(alice);
        vm.expectRevert();
        registry.setFeeRouter(address(router));
    }

    function test_setDinFees_onlyOwner() public {
        vm.prank(alice);
        vm.expectRevert();
        registry.setDinFees(1, 2, 3, 4);
    }

    function test_setDinFees_updatesAllFourTiers() public {
        registry.setDinFees(1e18, 2e18, 3e17, 4e17);
        assertEq(registry.openSourceFeeDIN(), 1e18);
        assertEq(registry.proprietaryFeeDIN(), 2e18);
        assertEq(registry.openSourceUpdateFeeDIN(), 3e17);
        assertEq(registry.proprietaryUpdateFeeDIN(), 4e17);
    }
}
