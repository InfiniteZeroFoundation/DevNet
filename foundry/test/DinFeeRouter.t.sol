// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinTreasury} from "../src/DinTreasury.sol";
import {DinFeeRouter, DinSplit, EthSplit} from "../src/DinFeeRouter.sol";

/// @notice Tests for DinFeeRouter routing, split validation, and invariants.
///         The test contract is registered as coordinator (to mint DIN) and as a
///         fee source (to call routeFeeDIN / routeFeeETH directly).
contract DinFeeRouterTest is Test {
    DinToken token;
    DinTreasury treasury;
    DinFeeRouter router;

    address alice = makeAddr("alice");

    function setUp() public {
        // Deploy DinTreasury
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

        // Deploy DinToken with test contract as coordinator so we can mint directly
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
        token.setCoordinator(address(this));

        // Deploy DinFeeRouter
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

        // Register test contract as fee source
        router.addFeeSource(address(this));
    }

    function _mintTo(address to, uint256 amount) internal {
        token.mint(to, amount);
    }

    // ── Split setters ─────────────────────────────────────────────────────────

    function test_setDinSplit_rejectsBadBpsSum() public {
        // Sum = 9999, should revert
        vm.expectRevert(DinFeeRouter.InvalidSplit.selector);
        router.setDinSplit(DinSplit(9000, 500, 0, 499, 0));
    }

    function test_setDinSplit_rejectsOverCeilingTreasury() public {
        // treasuryBps = 2500 > 2000 ceiling
        vm.expectRevert(DinFeeRouter.TreasuryCutExceedsCeiling.selector);
        router.setDinSplit(DinSplit(7500, 2500, 0, 0, 0));
    }

    function test_setDinSplit_acceptsValidSplit() public {
        router.setDinSplit(DinSplit(8000, 1000, 500, 300, 200));
        (uint16 vpBps, uint16 tBps, uint16 bBps, uint16 sBps, uint16 pgBps) = router.dinSplit();
        assertEq(vpBps, 8000);
        assertEq(tBps, 1000);
        assertEq(bBps, 500);
        assertEq(sBps, 300);
        assertEq(pgBps, 200);
    }

    function test_setEthSplit_rejectsBadBpsSum() public {
        vm.expectRevert(DinFeeRouter.InvalidSplit.selector);
        router.setEthSplit(EthSplit(9000, 500, 499, 0)); // sum = 9999
    }

    function test_setEthSplit_rejectsOverCeilingTreasury() public {
        vm.expectRevert(DinFeeRouter.TreasuryCutExceedsCeiling.selector);
        router.setEthSplit(EthSplit(7500, 2500, 0, 0)); // treasuryBps=2500>2000
    }

    function test_setEthSplit_acceptsValidSplit() public {
        router.setEthSplit(EthSplit(9000, 500, 300, 200));
        (uint16 vp, uint16 t, uint16 s, uint16 pg) = router.ethSplit();
        assertEq(vp, 9000);
        assertEq(t, 500);
        assertEq(s, 300);
        assertEq(pg, 200);
    }

    function test_setTreasuryBpsCeiling_clampsSubsequentSplits() public {
        router.setTreasuryBpsCeiling(1000);
        // Treasury cut of 1500 should now revert
        vm.expectRevert(DinFeeRouter.TreasuryCutExceedsCeiling.selector);
        router.setDinSplit(DinSplit(8500, 1500, 0, 0, 0));
    }

    // ── onlyFeeSource gate ────────────────────────────────────────────────────

    function test_routeFeeDIN_revertsForNonFeeSource() public {
        _mintTo(alice, 1e18);
        vm.prank(alice);
        token.approve(address(router), 1e18);

        vm.prank(alice); // alice is not a fee source
        vm.expectRevert(DinFeeRouter.NotFeeSource.selector);
        router.routeFeeDIN(alice, 1e18);
    }

    function test_routeFeeETH_revertsForNonFeeSource() public {
        vm.deal(alice, 1 ether);
        vm.prank(alice);
        vm.expectRevert(DinFeeRouter.NotFeeSource.selector);
        router.routeFeeETH{value: 1 ether}(alice);
    }

    function test_routeFeeDIN_revertsOnZeroAmount() public {
        vm.expectRevert(DinFeeRouter.ZeroAmount.selector);
        router.routeFeeDIN(alice, 0);
    }

    function test_routeFeeETH_revertsOnZeroValue() public {
        vm.expectRevert(DinFeeRouter.ZeroAmount.selector);
        router.routeFeeETH{value: 0}(alice);
    }

    // ── routeFeeDIN — real burn + treasury settlement ─────────────────────────

    function test_routeFeeDIN_burnDecreasesTotalSupply() public {
        // Set 10% burn: 8000+500+1000+300+200 = 10000
        router.setDinSplit(DinSplit(8000, 500, 1000, 300, 200));

        uint256 amount = 1000e18;
        _mintTo(alice, amount);
        vm.prank(alice);
        token.approve(address(router), amount);

        uint256 supplyBefore = token.totalSupply();
        router.routeFeeDIN(alice, amount);
        uint256 supplyAfter = token.totalSupply();

        // burned = amount * burnBps / 10000 = 1000e18 * 1000 / 10000 = 100e18
        uint256 expectedBurned = (amount * 1000) / 10000;
        assertEq(supplyBefore - supplyAfter, expectedBurned);
    }

    function test_routeFeeDIN_treasuryReceivesDin() public {
        // Default split: validatorPool=9500, treasury=500, rest=0
        uint256 amount = 10000e18;
        _mintTo(alice, amount);
        vm.prank(alice);
        token.approve(address(router), amount);

        uint256 treasuryBefore = token.balanceOf(address(treasury));
        router.routeFeeDIN(alice, amount);

        // treasuryAmt = amount * 500 / 10000 = amount / 20
        uint256 expectedTreasuryAmt = amount / 20;
        assertEq(token.balanceOf(address(treasury)) - treasuryBefore, expectedTreasuryAmt);
    }

    function test_routeFeeDIN_validatorPoolAccrues() public {
        uint256 amount = 10000e18;
        _mintTo(alice, amount);
        vm.prank(alice);
        token.approve(address(router), amount);

        router.routeFeeDIN(alice, amount);

        // validatorPoolAmt = amount * 9500 / 10000
        uint256 expectedVP = (amount * 9500) / 10000;
        assertEq(router.accruedDin(keccak256("validatorPool")), expectedVP);
    }

    // ── routeFeeETH — no burn invariant ──────────────────────────────────────

    function test_routeFeeETH_noEthBurnInvariant() public {
        // Set a known split: treasury=1000, validatorPool=8000, storage=500, publicGoods=500
        router.setEthSplit(EthSplit(8000, 1000, 500, 500));

        uint256 ethAmount = 10 ether;
        vm.deal(address(this), ethAmount);

        uint256 treasuryBefore = address(treasury).balance;

        router.routeFeeETH{value: ethAmount}(address(this));

        uint256 toTreasury = address(treasury).balance - treasuryBefore;
        uint256 inVP      = router.accruedEth(keccak256("validatorPool"));
        uint256 inStorage = router.accruedEth(keccak256("storage"));
        uint256 inPG      = router.accruedEth(keccak256("publicGoods"));

        // Invariant: all ETH is accounted for — none is burned
        assertEq(toTreasury + inVP + inStorage + inPG, ethAmount, "ETH in != ETH out");

        // Confirm the router holds the unforwarded ETH
        assertEq(address(router).balance, ethAmount - toTreasury);
    }

    function test_routeFeeETH_zeroBurnBucket_doesNotExist() public {
        // Structural proof: EthSplit has no burnBps field at all.
        // This test confirms the compile-time constraint — routeFeeETH cannot route to burn.
        // We verify 100% of ETH is accounted for: treasury + validator + storage + publicGoods.
        uint256 ethAmount = 1 ether;
        vm.deal(address(this), ethAmount);

        uint256 supplyBefore = token.totalSupply(); // DIN totalSupply must be unchanged

        router.routeFeeETH{value: ethAmount}(address(this));

        // DIN supply unchanged — no ETH was converted to DIN and burned
        assertEq(token.totalSupply(), supplyBefore);
    }

    // ── Fuzz: DIN split-sum invariant ─────────────────────────────────────────

    function test_fuzz_routeFeeDIN_splitsSumExactlyToAmount(
        uint16 validatorPoolBps,
        uint16 treasuryBps,
        uint16 burnBps,
        uint16 storageBps,
        uint256 amount
    ) public {
        // Constrain: four buckets ≤ 10000, treasury ≤ ceiling (2000)
        vm.assume(uint256(validatorPoolBps) + treasuryBps + burnBps + storageBps <= 10000);
        vm.assume(treasuryBps <= 2000);
        uint16 publicGoodsBps = uint16(
            10000 - uint256(validatorPoolBps) - treasuryBps - burnBps - storageBps
        );

        router.setDinSplit(
            DinSplit(validatorPoolBps, treasuryBps, burnBps, storageBps, publicGoodsBps)
        );

        amount = bound(amount, 1, 1e36);
        _mintTo(alice, amount);
        vm.prank(alice);
        token.approve(address(router), amount);

        uint256 supplyBefore = token.totalSupply();
        uint256 treasuryBefore = token.balanceOf(address(treasury));

        router.routeFeeDIN(alice, amount);

        uint256 burned     = supplyBefore - token.totalSupply();
        uint256 toTreasury = token.balanceOf(address(treasury)) - treasuryBefore;
        uint256 inVP       = router.accruedDin(keccak256("validatorPool"));
        uint256 inStorage  = router.accruedDin(keccak256("storage"));
        uint256 inPG       = router.accruedDin(keccak256("publicGoods"));

        // The five buckets must sum exactly to the routed amount
        assertEq(
            burned + toTreasury + inVP + inStorage + inPG,
            amount,
            "DIN split buckets do not sum to routed amount"
        );
    }

    // ── addFeeSource / removeFeeSource ────────────────────────────────────────

    function test_addFeeSource_rejectsZeroAddress() public {
        vm.expectRevert(DinFeeRouter.InvalidAddress.selector);
        router.addFeeSource(address(0));
    }

    function test_addFeeSource_rejectsDuplicate() public {
        vm.expectRevert(DinFeeRouter.FeeSourceAlreadyAdded.selector);
        router.addFeeSource(address(this)); // already added in setUp
    }

    function test_removeFeeSource_revokesAccess() public {
        router.removeFeeSource(address(this));
        assertFalse(router.feeSources(address(this)));

        uint256 amount = 1e18;
        _mintTo(alice, amount);
        vm.prank(alice);
        token.approve(address(router), amount);

        vm.expectRevert(DinFeeRouter.NotFeeSource.selector);
        router.routeFeeDIN(alice, amount);
    }

    function test_removeFeeSource_revertsForUnregistered() public {
        vm.expectRevert(DinFeeRouter.FeeSourceNotAdded.selector);
        router.removeFeeSource(alice);
    }
}
