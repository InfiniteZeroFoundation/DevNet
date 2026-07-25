// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";

contract DinValidatorStakeTest is Test {
    DinToken token;
    DinCoordinator coordinator;
    DinValidatorStake stake;

    address alice = makeAddr("alice");
    address bob   = makeAddr("bob");

    // Registered as a slasher so tests can call jailValidator/slash
    address slasher = makeAddr("slasher");

    uint256 constant FLOOR = 10e18; // initial MIN_STAKE

    function setUp() public {
        // ── DinToken ────────────────────────────────────────────────────────
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

        // ── DinCoordinator ──────────────────────────────────────────────────
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

        // ── DinValidatorStake ───────────────────────────────────────────────
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

        // Register slasher via coordinator
        coordinator.addSlasherContract(slasher);

        // Fund alice and bob with DIN for staking
        vm.deal(alice, 10 ether);
        vm.deal(bob, 10 ether);
        vm.prank(alice);
        coordinator.depositAndMint{value: 1 ether}();
        vm.prank(bob);
        coordinator.depositAndMint{value: 1 ether}();
        vm.prank(alice);
        token.approve(address(stake), type(uint256).max);
        vm.prank(bob);
        token.approve(address(stake), type(uint256).max);
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
        assertEq(stake.minStake(), 20e18);
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
        // Alice stakes and requests unstake — records withdrawAvailableAt = now + 7d
        vm.prank(alice);
        stake.stake(FLOOR);
        vm.prank(alice);
        stake.unstake(FLOOR);

        (, , uint64 withdrawAvailableAt, , ) = stake.validators(alice);
        uint64 expectedAt = uint64(block.timestamp + 7 days);
        assertEq(withdrawAvailableAt, expectedAt);

        // Owner changes period to 30 days — existing withdrawal unaffected
        stake.setUnbondingPeriod(30 days);
        (, , uint64 stillSame, , ) = stake.validators(alice);
        assertEq(stillSame, expectedAt);
    }

    // ── setModelStakeBounds ───────────────────────────────────────────────────

    function test_setModelStakeBounds_onlyOwner() public {
        vm.prank(alice);
        vm.expectRevert();
        stake.setModelStakeBounds(1, 10e18, 100e18);
    }

    function test_setModelStakeBounds_revertsWhenMinGtMax() public {
        vm.expectRevert(DinValidatorStake.InvalidStakeBounds.selector);
        stake.setModelStakeBounds(1, 100e18, 10e18);
    }

    function test_setModelStakeBounds_roundTrip() public {
        stake.setModelStakeBounds(42, 5e18, 50e18);
        (uint256 min, uint256 max) = stake.modelMinStakeBounds(42);
        assertEq(min, 5e18);
        assertEq(max, 50e18);
    }

    function test_setModelStakeBounds_doesNotAffectStaking() public {
        // Setting bounds must not change whether a validator can stake/register
        stake.setModelStakeBounds(1, 999e18, 9999e18);
        // Alice can still stake at the network floor with no issue
        vm.prank(alice);
        stake.stake(FLOOR);
        assertTrue(stake.isValidatorActive(alice));
    }

    // ── setMaxConcurrentRegistrationsPerStakeUnit ─────────────────────────────

    function test_setMaxConcurrent_onlyOwner() public {
        vm.prank(alice);
        vm.expectRevert();
        stake.setMaxConcurrentRegistrationsPerStakeUnit(3);
    }

    function test_setMaxConcurrent_roundTrip() public {
        stake.setMaxConcurrentRegistrationsPerStakeUnit(5);
        assertEq(stake.maxConcurrentRegistrationsPerStakeUnit(), 5);
    }

    function test_setMaxConcurrent_doesNotAffectStaking() public {
        stake.setMaxConcurrentRegistrationsPerStakeUnit(1);
        vm.prank(alice);
        stake.stake(FLOOR);
        assertTrue(stake.isValidatorActive(alice));
    }

    // ── jailValidator ─────────────────────────────────────────────────────────

    function test_jailValidator_onlySlasher() public {
        vm.prank(alice);
        stake.stake(FLOOR);
        vm.prank(alice); // alice is not a slasher
        vm.expectRevert(DinValidatorStake.NotSlasherContract.selector);
        stake.jailValidator(alice, 1 days, bytes32("bad"));
    }

    function test_jailValidator_revertsOnZeroAddress() public {
        vm.prank(slasher);
        vm.expectRevert(DinValidatorStake.InvalidAddress.selector);
        stake.jailValidator(address(0), 1 days, bytes32("bad"));
    }

    function test_jailValidator_revertsOnZeroDuration() public {
        vm.prank(alice);
        stake.stake(FLOOR);
        vm.prank(slasher);
        vm.expectRevert(DinValidatorStake.InvalidJailDuration.selector);
        stake.jailValidator(alice, 0, bytes32("bad"));
    }

    function test_jailValidator_revertsForBlacklisted() public {
        vm.prank(alice);
        stake.stake(FLOOR);
        stake.blacklistValidator(alice);
        vm.prank(slasher);
        vm.expectRevert(DinValidatorStake.ValidatorIsBlacklisted.selector);
        stake.jailValidator(alice, 1 days, bytes32("bad"));
    }

    function test_jailValidator_setsJailedStatus() public {
        vm.prank(alice);
        stake.stake(FLOOR);
        assertTrue(stake.isValidatorActive(alice));

        vm.prank(slasher);
        stake.jailValidator(alice, 1 days, bytes32("offline"));

        (, , , , DinValidatorStake.ValidatorStatus status) = stake.validators(alice);
        assertEq(uint8(status), uint8(DinValidatorStake.ValidatorStatus.Jailed));
        assertFalse(stake.isValidatorActive(alice));
    }

    function test_jailValidator_extendsExistingJail() public {
        vm.prank(alice);
        stake.stake(FLOOR);

        // First jail: 1 day
        vm.prank(slasher);
        stake.jailValidator(alice, 1 days, bytes32("first"));
        (, , , uint64 jailedUntilFirst, ) = stake.validators(alice);

        // Second jail: 3 days — should extend (set further out)
        vm.prank(slasher);
        stake.jailValidator(alice, 3 days, bytes32("second"));
        (, , , uint64 jailedUntilSecond, ) = stake.validators(alice);
        assertGt(jailedUntilSecond, jailedUntilFirst);
    }

    function test_jailValidator_neverShortensExistingJail() public {
        vm.prank(alice);
        stake.stake(FLOOR);

        // Long jail first: 7 days
        vm.prank(slasher);
        stake.jailValidator(alice, 7 days, bytes32("long"));
        (, , , uint64 longJail, ) = stake.validators(alice);

        // Short jail attempt: 1 day — should NOT shorten
        vm.prank(slasher);
        stake.jailValidator(alice, 1 days, bytes32("short"));
        (, , , uint64 stillLong, ) = stake.validators(alice);
        assertEq(stillLong, longJail);
    }

    // ── reactivate ────────────────────────────────────────────────────────────

    function test_reactivate_revertsIfNotJailed() public {
        vm.prank(alice);
        stake.stake(FLOOR);
        vm.prank(alice);
        vm.expectRevert(DinValidatorStake.NotJailed.selector);
        stake.reactivate();
    }

    function test_reactivate_revertsIfJailPeriodNotExpired() public {
        vm.prank(alice);
        stake.stake(FLOOR);
        vm.prank(slasher);
        stake.jailValidator(alice, 1 days, bytes32("bad"));

        vm.prank(alice);
        vm.expectRevert(DinValidatorStake.JailPeriodNotExpired.selector);
        stake.reactivate();
    }

    function test_reactivate_revertsIfStakeBelowFloor() public {
        vm.prank(alice);
        stake.stake(FLOOR);

        // Slash alice below floor then jail her
        vm.prank(slasher);
        stake.slash(alice, FLOOR, bytes32("penalised"));
        vm.prank(slasher);
        stake.jailValidator(alice, 1 days, bytes32("offline"));

        vm.warp(block.timestamp + 1 days + 1);
        vm.prank(alice);
        vm.expectRevert(DinValidatorStake.StakeBelowFloor.selector);
        stake.reactivate();
    }

    function test_reactivate_fullLifecycle() public {
        // 1. Stake
        vm.prank(alice);
        stake.stake(FLOOR);
        assertTrue(stake.isValidatorActive(alice));

        // 2. Jail for 2 days
        vm.prank(slasher);
        stake.jailValidator(alice, 2 days, bytes32("liveness"));
        assertFalse(stake.isValidatorActive(alice));

        // 3. Early reactivate fails
        vm.warp(block.timestamp + 1 days);
        vm.prank(alice);
        vm.expectRevert(DinValidatorStake.JailPeriodNotExpired.selector);
        stake.reactivate();

        // 4. After jail expires, reactivate succeeds
        vm.warp(block.timestamp + 1 days + 1);
        vm.prank(alice);
        stake.reactivate();
        assertTrue(stake.isValidatorActive(alice));

        // 5. jailedUntil cleared
        (, , , uint64 jailedUntil, ) = stake.validators(alice);
        assertEq(jailedUntil, 0);
    }

    function test_reactivate_requiresTopUpIfSlashedBelowFloor() public {
        vm.prank(alice);
        stake.stake(FLOOR);

        // Slash half, then jail
        vm.prank(slasher);
        stake.slash(alice, FLOOR / 2, bytes32("penalised"));
        vm.prank(slasher);
        stake.jailValidator(alice, 1 days, bytes32("offline"));

        vm.warp(block.timestamp + 1 days + 1);

        // Still below floor — fails
        vm.prank(alice);
        vm.expectRevert(DinValidatorStake.StakeBelowFloor.selector);
        stake.reactivate();

        // Top up — each stake() call requires >= MIN_STAKE, so stake the full floor amount
        vm.prank(alice);
        stake.stake(FLOOR);
        vm.prank(alice);
        stake.reactivate();
        assertTrue(stake.isValidatorActive(alice));
    }
}
