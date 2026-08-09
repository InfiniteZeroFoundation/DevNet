// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinTreasury} from "../src/DinTreasury.sol";
import {DinFeeRouter} from "../src/DinFeeRouter.sol";

contract DinCoordinatorTest is Test {
    DinToken token;
    DinCoordinator coordinator;
    DinTreasury treasury;
    DinFeeRouter router;

    address alice = makeAddr("alice");

    function setUp() public {
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
    }

    // ── depositAndMint: faucet retirement ─────────────────────────────────────

    function test_depositAndMint_succeedsWhenFaucetActive() public {
        vm.deal(alice, 1 ether);
        vm.prank(alice);
        coordinator.depositAndMint{value: 0.001 ether}();
        assertGt(token.balanceOf(alice), 0);
    }

    function test_depositAndMint_revertsWhenFaucetRetired() public {
        coordinator.retireFaucet();

        vm.deal(alice, 1 ether);
        vm.prank(alice);
        vm.expectRevert(DinCoordinator.FaucetRetired.selector);
        coordinator.depositAndMint{value: 0.001 ether}();
    }

    // ── depositAndMint: mint cap ───────────────────────────────────────────────

    function test_depositAndMint_uncappedByDefault() public {
        assertEq(coordinator.mintCap(), 0);

        vm.deal(alice, 100 ether);
        vm.prank(alice);
        coordinator.depositAndMint{value: 100 ether}();
        assertGt(token.balanceOf(alice), 0);
    }

    function test_depositAndMint_revertsWhenCapExceeded() public {
        coordinator.setMintCap(500e18); // 0.001 ETH → 1000 DIN > 500

        vm.deal(alice, 1 ether);
        vm.prank(alice);
        vm.expectRevert(DinCoordinator.MintCapExceeded.selector);
        coordinator.depositAndMint{value: 0.001 ether}();
    }

    function test_depositAndMint_succeedsAtExactlyTheCap() public {
        uint256 capAmount = (0.001 ether * coordinator.dinPerEth()) / 1e18;
        coordinator.setMintCap(capAmount);

        vm.deal(alice, 1 ether);
        vm.prank(alice);
        coordinator.depositAndMint{value: 0.001 ether}();

        assertEq(token.balanceOf(alice), capAmount);
        assertEq(coordinator.totalMinted(), capAmount);
    }

    function test_depositAndMint_tracksTotalMinted() public {
        vm.deal(alice, 1 ether);
        vm.prank(alice);
        coordinator.depositAndMint{value: 0.001 ether}();

        uint256 expected = (0.001 ether * coordinator.dinPerEth()) / 1e18;
        assertEq(coordinator.totalMinted(), expected);
    }

    // ── retireFaucet ──────────────────────────────────────────────────────────

    function test_retireFaucet_isOneWay() public {
        coordinator.retireFaucet();
        assertTrue(coordinator.faucetRetired());

        vm.expectRevert(DinCoordinator.FaucetRetired.selector);
        coordinator.retireFaucet();
    }

    function test_retireFaucet_onlyOwner() public {
        vm.prank(alice);
        vm.expectRevert();
        coordinator.retireFaucet();
    }

    function test_setMintCap_rejectsAfterRetirement() public {
        coordinator.retireFaucet();

        vm.expectRevert(DinCoordinator.FaucetRetired.selector);
        coordinator.setMintCap(1e18);
    }

    // ── sweepFeesToRouter ───────────────────────────────────────────────────────

    function test_sweepFeesToRouter_revertsWhenFeeRouterNotSet() public {
        vm.deal(address(coordinator), 1 ether);

        vm.expectRevert(DinCoordinator.FeeRouterNotSet.selector);
        coordinator.sweepFeesToRouter();
    }

    function test_sweepFeesToRouter_forwardsFullBalanceToRouter() public {
        coordinator.setFeeRouter(address(router));
        router.addFeeSource(address(coordinator));

        // Deposit ETH by minting (ETH accumulates in coordinator)
        vm.deal(alice, 1 ether);
        vm.prank(alice);
        coordinator.depositAndMint{value: 1 ether}();

        uint256 treasuryBefore = address(treasury).balance;
        uint256 coordBalance = address(coordinator).balance;

        coordinator.sweepFeesToRouter();

        assertEq(address(coordinator).balance, 0);
        // Default ETH split: 95% validatorPool (accrues in router), 5% treasury.
        assertEq(address(treasury).balance, treasuryBefore + (coordBalance * 500) / 10000);
        assertEq(address(router).balance, coordBalance - (coordBalance * 500) / 10000);
    }

    function test_sweepFeesToRouter_emitsFeesSweptToRouterEvent() public {
        coordinator.setFeeRouter(address(router));
        router.addFeeSource(address(coordinator));

        vm.deal(address(coordinator), 1 ether);

        vm.expectEmit(true, true, true, true);
        emit DinCoordinator.FeesSweptToRouter(1 ether);
        coordinator.sweepFeesToRouter();
    }

    function test_sweepFeesToRouter_noopOnZeroBalance() public {
        coordinator.setFeeRouter(address(router));
        router.addFeeSource(address(coordinator));

        coordinator.sweepFeesToRouter(); // must not revert
    }

    function test_sweepFeesToRouter_onlyOwner() public {
        coordinator.setFeeRouter(address(router));
        router.addFeeSource(address(coordinator));

        vm.prank(alice);
        vm.expectRevert();
        coordinator.sweepFeesToRouter();
    }

    // ── setFeeRouter ─────────────────────────────────────────────────────────────

    function test_setFeeRouter_revertsOnZeroAddress() public {
        vm.expectRevert(DinCoordinator.InvalidAddress.selector);
        coordinator.setFeeRouter(address(0));
    }

    function test_setFeeRouter_onlyOwner() public {
        vm.prank(alice);
        vm.expectRevert();
        coordinator.setFeeRouter(address(router));
    }
}
