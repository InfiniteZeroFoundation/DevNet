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

/// @dev Has no receive()/fallback(), so any plain ETH transfer to it fails --
///      used to prove a failed overpayment refund reverts the whole
///      requestModelRegistration call instead of silently swallowing it (L-3).
contract RevertingReceiver {
    DINModelRegistry private immutable registry;

    constructor(DINModelRegistry registry_) {
        registry = registry_;
    }

    function register(
        bytes32 manifestCID,
        address taskCoordinator,
        address taskAuditor,
        bool isOpenSource
    ) external payable returns (uint256) {
        return
            registry.requestModelRegistration{value: msg.value}(
                manifestCID,
                taskCoordinator,
                taskAuditor,
                isOpenSource
            );
    }
}

/// @notice Registry stays ETH-only (see PR #51 comment thread) — no DIN fee
///         tiers or DIN-paying entry points. Fees accumulate in the registry
///         per request, then sweepFeesToRouter() batches the whole balance
///         through DinFeeRouter in one call instead of paying the router's
///         external-call cost on every registration/update.
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

        // ── wire DinCoordinator → DinFeeRouter (sweepFeesToRouter) ──────────
        coordinator.setFeeRouter(address(router));
        router.addFeeSource(address(coordinator));

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

        // ── wire fee router (used only by sweepFeesToRouter, not per-request) ──
        registry.setFeeRouter(address(router));
        router.addFeeSource(address(registry));

        // ── deploy task contract stubs owned by alice ───────────────────────
        taskCoordinator = address(new MockTaskContractRegistry(alice));
        taskAuditor     = address(new MockTaskContractRegistry(alice));
        // Register them as slashers
        coordinator.addSlasherContract(taskCoordinator);
        coordinator.addSlasherContract(taskAuditor);

        vm.deal(alice, 10 ether);
    }

    // ── ETH registration: fees accumulate in registry, not forwarded per-request ──

    function test_requestModelRegistration_ethAccumulatesInRegistry() public {
        uint256 fee = registry.openSourceFee();
        vm.prank(alice);
        registry.requestModelRegistration{value: fee}(
            keccak256("manifest"),
            taskCoordinator,
            taskAuditor,
            true
        );

        // Accumulate-then-sweep design: ETH stays in the registry per request,
        // regardless of whether feeRouter is wired — sweepFeesToRouter() batches
        // it later instead of paying the router's external-call cost every time.
        assertEq(address(registry).balance, fee, "ETH should accumulate in registry");
        assertEq(address(router).balance, 0, "Router should not receive per-request ETH");
    }

    function test_requestModelRegistration_multipleFeesAccumulate() public {
        uint256 osFee = registry.openSourceFee();
        uint256 propFee = registry.proprietaryFee();

        vm.startPrank(alice);
        registry.requestModelRegistration{value: osFee}(
            keccak256("manifest1"), taskCoordinator, taskAuditor, true
        );
        registry.requestModelRegistration{value: propFee}(
            keccak256("manifest2"), taskCoordinator, taskAuditor, false
        );
        vm.stopPrank();

        assertEq(address(registry).balance, osFee + propFee);
    }

    function test_requestModelRegistration_accumulatesRegardlessOfFeeRouterWiring() public {
        // Fresh registry with no feeRouter set at all.
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
        vm.prank(alice);
        bareRegistry.requestModelRegistration{value: fee}(
            keccak256("manifest"),
            taskCoordinator,
            taskAuditor,
            true
        );

        // Request succeeds either way — feeRouter wiring only matters at sweep time.
        assertEq(address(bareRegistry).balance, fee);
    }

    // ── requestModelRegistration: overpayment refund (L-3) ──────────────────────

    function test_requestModelRegistration_refundsOverpayment() public {
        uint256 fee = registry.openSourceFee();
        uint256 overpay = 0.01 ether;
        uint256 balanceBefore = alice.balance;

        vm.prank(alice);
        uint256 requestId = registry.requestModelRegistration{value: fee + overpay}(
            keccak256("manifest"),
            taskCoordinator,
            taskAuditor,
            true
        );

        assertEq(alice.balance, balanceBefore - fee, "overpayment should be refunded");
        assertEq(address(registry).balance, fee, "registry should only keep the required fee");

        (, , , , , uint256 feePaid, , , ) = registry.modelRequests(requestId);
        assertEq(feePaid, fee, "feePaid must record requiredFee, not msg.value");
    }

    function test_requestModelRegistration_exactPaymentUnchanged() public {
        uint256 fee = registry.openSourceFee();
        uint256 balanceBefore = alice.balance;

        vm.prank(alice);
        uint256 requestId = registry.requestModelRegistration{value: fee}(
            keccak256("manifest"),
            taskCoordinator,
            taskAuditor,
            true
        );

        assertEq(alice.balance, balanceBefore - fee, "no refund attempted on an exact payment");
        assertEq(address(registry).balance, fee);

        (, , , , , uint256 feePaid, , , ) = registry.modelRequests(requestId);
        assertEq(feePaid, fee);
    }

    function test_requestModelRegistration_revertsWholeCallIfRefundFails() public {
        RevertingReceiver bad = new RevertingReceiver(registry);
        address badTaskCoordinator = address(new MockTaskContractRegistry(address(bad)));
        address badTaskAuditor = address(new MockTaskContractRegistry(address(bad)));
        coordinator.addSlasherContract(badTaskCoordinator);
        coordinator.addSlasherContract(badTaskAuditor);

        uint256 fee = registry.openSourceFee();
        vm.deal(address(bad), fee + 0.01 ether);

        vm.expectRevert(DINModelRegistry.RefundFailed.selector);
        bad.register{value: fee + 0.01 ether}(
            keccak256("manifest"),
            badTaskCoordinator,
            badTaskAuditor,
            true
        );

        // Whole call reverted -- no request was recorded, no fee retained.
        assertEq(registry.totalModelRequests(), 0);
        assertEq(address(registry).balance, 0);
    }

    // ── sweepFeesToRouter ──────────────────────────────────────────────────────

    function test_sweepFeesToRouter_revertsWhenFeeRouterNotSet() public {
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

        vm.expectRevert(DINModelRegistry.FeeRouterNotSet.selector);
        bareRegistry.sweepFeesToRouter();
    }

    function test_sweepFeesToRouter_onlyOwner() public {
        uint256 fee = registry.openSourceFee();
        vm.prank(alice);
        registry.requestModelRegistration{value: fee}(
            keccak256("manifest"), taskCoordinator, taskAuditor, true
        );

        vm.prank(alice);
        vm.expectRevert();
        registry.sweepFeesToRouter();
    }

    function test_sweepFeesToRouter_noopOnZeroBalance() public {
        registry.sweepFeesToRouter(); // must not revert
    }

    function test_sweepFeesToRouter_forwardsFullBalanceToRouter() public {
        uint256 fee = registry.openSourceFee();
        vm.prank(alice);
        registry.requestModelRegistration{value: fee}(
            keccak256("manifest"), taskCoordinator, taskAuditor, true
        );

        registry.sweepFeesToRouter();

        assertEq(address(registry).balance, 0, "Registry balance should be swept to zero");
        // Fee is now fully accounted for between the router (accrued buckets,
        // held as router's own balance) and treasury (paid out directly).
        assertEq(address(router).balance + address(treasury).balance, fee);
    }

    function test_sweepFeesToRouter_emitsFeesSweptToRouterEvent() public {
        uint256 fee = registry.openSourceFee();
        vm.prank(alice);
        registry.requestModelRegistration{value: fee}(
            keccak256("manifest"), taskCoordinator, taskAuditor, true
        );

        vm.expectEmit(false, false, false, true, address(registry));
        emit DINModelRegistry.FeesSweptToRouter(fee);
        registry.sweepFeesToRouter();
    }

    function test_sweepFeesToRouter_batchesMultipleRequestsInOneCall() public {
        uint256 osFee = registry.openSourceFee();
        uint256 propFee = registry.proprietaryFee();

        vm.startPrank(alice);
        registry.requestModelRegistration{value: osFee}(
            keccak256("manifest1"), taskCoordinator, taskAuditor, true
        );
        registry.requestModelRegistration{value: propFee}(
            keccak256("manifest2"), taskCoordinator, taskAuditor, false
        );
        vm.stopPrank();

        uint256 totalFees = osFee + propFee;
        vm.expectEmit(false, false, false, true, address(registry));
        emit DINModelRegistry.FeesSweptToRouter(totalFees);
        registry.sweepFeesToRouter();

        assertEq(address(registry).balance, 0);
    }

    // ── setFeeRouter ─────────────────────────────────────────────────────────

    function test_setFeeRouter_onlyOwner() public {
        vm.prank(alice);
        vm.expectRevert();
        registry.setFeeRouter(address(router));
    }

    function test_setFeeRouter_revertsOnZeroAddress() public {
        vm.expectRevert(DINModelRegistry.ZeroAddress.selector);
        registry.setFeeRouter(address(0));
    }
}
