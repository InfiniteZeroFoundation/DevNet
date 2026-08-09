// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DinTreasury} from "../src/DinTreasury.sol";

contract DinValidatorStakeTest is Test {
    DinToken token;
    DinCoordinator coordinator;
    DinValidatorStake stake;
    DinTreasury treasury;

    address alice = makeAddr("alice");
    address bob   = makeAddr("bob");
    address slasher = makeAddr("slasher");

    uint256 constant MIN = 10e18;

    function setUp() public {
        // DinTreasury
        DinTreasury treasuryImpl = new DinTreasury();
        treasury = DinTreasury(payable(address(new TransparentUpgradeableProxy(
            address(treasuryImpl), address(this), abi.encodeCall(DinTreasury.initialize, ())
        ))));

        // DinToken
        DinToken tokenImpl = new DinToken();
        token = DinToken(address(new TransparentUpgradeableProxy(
            address(tokenImpl), address(this), abi.encodeCall(DinToken.initialize, ())
        )));

        // DinCoordinator
        DinCoordinator coordImpl = new DinCoordinator();
        coordinator = DinCoordinator(payable(address(new TransparentUpgradeableProxy(
            address(coordImpl), address(this),
            abi.encodeCall(DinCoordinator.initialize, (address(token)))
        ))));
        token.setCoordinator(address(coordinator));

        // DinValidatorStake
        DinValidatorStake stakeImpl = new DinValidatorStake();
        stake = DinValidatorStake(address(new TransparentUpgradeableProxy(
            address(stakeImpl), address(this),
            abi.encodeCall(DinValidatorStake.initialize, (address(token), address(coordinator)))
        )));
        coordinator.updateValidatorStakeContract(address(stake));

        // Register test contract as a slasher so tests can call slash/jailValidator
        vm.prank(address(coordinator));
        stake.addSlasherContract(slasher);

        stake.setSlashTreasury(address(treasury));
    }

    function _mintAndStake(address who, uint256 amount) internal {
        vm.deal(who, 1 ether);
        vm.prank(who);
        coordinator.depositAndMint{value: 0.1 ether}(); // 100,000 DIN
        vm.prank(who);
        token.approve(address(stake), type(uint256).max);
        vm.prank(who);
        stake.stake(amount);
    }

    // ── Initialization ────────────────────────────────────────────────────────

    function test_minStake_initializedTo10DIN() public view {
        assertEq(stake.MIN_STAKE(), 10e18);
    }

    function test_unbondingPeriod_initializedTo7Days() public view {
        assertEq(stake.UNBONDING_PERIOD(), 7 days);
    }

    // ── setMinStake ───────────────────────────────────────────────────────────

    function test_setMinStake_onlyOwner() public {
        vm.prank(alice);
        vm.expectRevert();
        stake.setMinStake(5e18);
    }

    function test_setMinStake_revertsOnZero() public {
        vm.expectRevert(DinValidatorStake.InvalidMinStake.selector);
        stake.setMinStake(0);
    }

    function test_setMinStake_updatesStorage() public {
        stake.setMinStake(20e18);
        assertEq(stake.MIN_STAKE(), 20e18);
    }

    // ── setUnbondingPeriod ────────────────────────────────────────────────────

    function test_setUnbondingPeriod_onlyOwner() public {
        vm.prank(alice);
        vm.expectRevert();
        stake.setUnbondingPeriod(1 days);
    }

    function test_setUnbondingPeriod_revertsOnZero() public {
        vm.expectRevert(DinValidatorStake.InvalidUnbondingPeriod.selector);
        stake.setUnbondingPeriod(0);
    }

    function test_setUnbondingPeriod_updatesStorage() public {
        stake.setUnbondingPeriod(14 days);
        assertEq(stake.UNBONDING_PERIOD(), 14 days);
    }

    function test_setUnbondingPeriod_doesNotAffectExistingWithdrawal() public {
        _mintAndStake(alice, MIN);
        vm.prank(alice);
        stake.unstake(MIN);

        (, uint256 pending, uint64 availableAt,,) = stake.validators(alice);
        assertEq(pending, MIN);

        // Change the period after the withdrawal is queued
        stake.setUnbondingPeriod(30 days);

        // withdrawAvailableAt should not have changed
        (, , uint64 availableAtAfter,,) = stake.validators(alice);
        assertEq(availableAtAfter, availableAt);
    }

    // ── modelMinStakeBounds ───────────────────────────────────────────────────

    function test_setModelStakeBounds_roundTrip() public {
        stake.setModelStakeBounds(1, 5e18, 50e18);
        (uint256 min, uint256 max) = stake.modelMinStakeBounds(1);
        assertEq(min, 5e18);
        assertEq(max, 50e18);
    }

    function test_setModelStakeBounds_revertsWhenMinExceedsMax() public {
        vm.expectRevert(DinValidatorStake.InvalidStakeBounds.selector);
        stake.setModelStakeBounds(1, 50e18, 5e18);
    }

    // ── maxConcurrentRegistrationsPerStakeUnit ────────────────────────────────

    function test_setMaxConcurrentRegistrationsPerStakeUnit_roundTrip() public {
        stake.setMaxConcurrentRegistrationsPerStakeUnit(3);
        assertEq(stake.maxConcurrentRegistrationsPerStakeUnit(), 3);
    }

    // ── setSlashTreasury ──────────────────────────────────────────────────────

    function test_setSlashTreasury_onlyOwner() public {
        vm.prank(alice);
        vm.expectRevert();
        stake.setSlashTreasury(address(treasury));
    }

    function test_setSlashTreasury_revertsOnZeroAddress() public {
        vm.expectRevert(DinValidatorStake.InvalidAddress.selector);
        stake.setSlashTreasury(address(0));
    }

    function test_setSlashTreasury_stored() public view {
        assertEq(stake.slashTreasury(), address(treasury));
    }

    // ── slash burn distribution ───────────────────────────────────────────────

    function test_slash_burns50Percent() public {
        _mintAndStake(alice, MIN);
        uint256 supplyBefore = token.totalSupply();

        vm.prank(slasher);
        uint256 slashed = stake.slash(alice, MIN, bytes32("test"));

        uint256 expectedBurn = slashed / 2;
        assertEq(supplyBefore - token.totalSupply(), expectedBurn);
    }

    function test_slash_sends50PercentToTreasury() public {
        _mintAndStake(alice, MIN);
        uint256 treasuryBefore = token.balanceOf(address(treasury));

        vm.prank(slasher);
        uint256 slashed = stake.slash(alice, MIN, bytes32("test"));

        uint256 expectedTreasury = slashed - slashed / 2;
        assertEq(token.balanceOf(address(treasury)) - treasuryBefore, expectedTreasury);
    }

    function test_slash_burns100PercentWhenNoTreasurySet() public {
        // Deploy a fresh stake without slashTreasury wired
        DinValidatorStake stakeImpl = new DinValidatorStake();
        DinValidatorStake bareStake = DinValidatorStake(address(new TransparentUpgradeableProxy(
            address(stakeImpl), address(this),
            abi.encodeCall(DinValidatorStake.initialize, (address(token), address(coordinator)))
        )));
        vm.prank(address(coordinator));
        bareStake.addSlasherContract(slasher);
        // slashTreasury intentionally NOT set

        vm.deal(bob, 1 ether);
        vm.prank(bob);
        coordinator.depositAndMint{value: 0.1 ether}();
        vm.prank(bob);
        token.approve(address(bareStake), type(uint256).max);
        vm.prank(bob);
        bareStake.stake(MIN);

        uint256 supplyBefore = token.totalSupply();
        uint256 treasuryBefore = token.balanceOf(address(treasury));

        vm.prank(slasher);
        uint256 slashed = bareStake.slash(bob, MIN, bytes32("test"));

        // 100% burned
        assertEq(supplyBefore - token.totalSupply(), slashed);
        // treasury unchanged
        assertEq(token.balanceOf(address(treasury)), treasuryBefore);
    }

    // ── jailValidator ─────────────────────────────────────────────────────────

    function test_jailValidator_onlySlasher() public {
        _mintAndStake(alice, MIN);
        vm.expectRevert(DinValidatorStake.NotSlasherContract.selector);
        stake.jailValidator(alice, 1 days, bytes32("bad"));
    }

    function test_jailValidator_revertsOnZeroAddress() public {
        vm.prank(slasher);
        vm.expectRevert(DinValidatorStake.InvalidAddress.selector);
        stake.jailValidator(address(0), 1 days, bytes32("bad"));
    }

    function test_jailValidator_revertsOnZeroDuration() public {
        _mintAndStake(alice, MIN);
        vm.prank(slasher);
        vm.expectRevert(DinValidatorStake.InvalidJailDuration.selector);
        stake.jailValidator(alice, 0, bytes32("bad"));
    }

    function test_jailValidator_revertsForBlacklisted() public {
        _mintAndStake(alice, MIN);
        stake.blacklistValidator(alice);

        vm.prank(slasher);
        vm.expectRevert(DinValidatorStake.ValidatorIsBlacklisted.selector);
        stake.jailValidator(alice, 1 days, bytes32("bad"));
    }

    function test_jailValidator_setsJailedStatus() public {
        _mintAndStake(alice, MIN);
        vm.prank(slasher);
        stake.jailValidator(alice, 1 days, bytes32("bad"));

        (,,, , DinValidatorStake.ValidatorStatus status) = stake.validators(alice);
        assertEq(uint256(status), uint256(DinValidatorStake.ValidatorStatus.Jailed));
    }

    function test_jailValidator_extendsNeverShortens() public {
        _mintAndStake(alice, MIN);
        vm.prank(slasher);
        stake.jailValidator(alice, 7 days, bytes32("first"));

        (,,, uint64 jailedUntilAfterFirst,) = stake.validators(alice);

        // Second jail with shorter duration — must NOT shorten
        vm.prank(slasher);
        stake.jailValidator(alice, 1 days, bytes32("second"));

        (,,, uint64 jailedUntilAfterSecond,) = stake.validators(alice);
        assertEq(jailedUntilAfterSecond, jailedUntilAfterFirst);
    }

    // ── reactivate ────────────────────────────────────────────────────────────

    function test_reactivate_revertsIfNotJailed() public {
        _mintAndStake(alice, MIN);
        vm.prank(alice);
        vm.expectRevert(DinValidatorStake.NotJailed.selector);
        stake.reactivate();
    }

    function test_reactivate_revertsIfJailPeriodActive() public {
        _mintAndStake(alice, MIN);
        vm.prank(slasher);
        stake.jailValidator(alice, 7 days, bytes32("bad"));

        vm.prank(alice);
        vm.expectRevert(DinValidatorStake.JailPeriodNotExpired.selector);
        stake.reactivate();
    }

    function test_reactivate_revertsIfStakeBelowFloor() public {
        _mintAndStake(alice, MIN);
        vm.prank(slasher);
        stake.jailValidator(alice, 1 days, bytes32("bad"));
        // Slash most of the stake so it falls below MIN_STAKE
        vm.prank(slasher);
        stake.slash(alice, MIN - 1, bytes32("slash"));

        vm.warp(block.timestamp + 2 days);

        vm.prank(alice);
        vm.expectRevert(DinValidatorStake.StakeBelowFloor.selector);
        stake.reactivate();
    }

    function test_reactivate_fullLifecycle() public {
        _mintAndStake(alice, MIN);
        vm.prank(slasher);
        stake.jailValidator(alice, 1 days, bytes32("bad"));

        vm.warp(block.timestamp + 2 days);

        vm.prank(alice);
        stake.reactivate();

        (,,,, DinValidatorStake.ValidatorStatus status) = stake.validators(alice);
        assertEq(uint256(status), uint256(DinValidatorStake.ValidatorStatus.Active));
    }

    function test_reactivate_allowsRestaking() public {
        _mintAndStake(alice, MIN);
        vm.prank(slasher);
        stake.jailValidator(alice, 1 days, bytes32("bad"));

        vm.warp(block.timestamp + 2 days);
        vm.prank(alice);
        stake.reactivate();

        // Should be able to unstake normally
        vm.prank(alice);
        stake.unstake(MIN);

        (, uint256 pending,,,) = stake.validators(alice);
        assertEq(pending, MIN);
    }
}
