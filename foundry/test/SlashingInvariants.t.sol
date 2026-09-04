// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

// ─────────────────────────────────────────────────────────────────────────────
// Invariant and fuzz coverage for DinValidatorStake.slash() as it exists
// today (task_210726_6 Part 4b, issue #38). Confirms the three properties
// specified in Developer/design/MECHANISM_DESIGN.md §4 against real execution
// rather than reading the source once: staked supply never increases from a
// slash, slashed tokens split between burn and slashTreasury per the #60/#65
// resolution rather than reaching a third party, and no validator can be
// pushed into a negative-stake state.
//
// Those three specified properties are carried by four invariant_ functions
// plus nine fuzz/unit tests -- the first property needs two of them, since the
// per-actor bound alone is too loose (see invariant_totalAccountedStakeMatchesLedger).
// Run: forge test --match-contract SlashingInvariantsTest -vv
// ─────────────────────────────────────────────────────────────────────────────

import {Test} from "forge-std/Test.sol";
import {StdInvariant} from "forge-std/StdInvariant.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";

/// @dev Drives stake()/slash()/unstake()/claimUnstaked() against a fixed pool
///      of actors in random order and amounts, tracking ghost totals so the
///      invariant test can check the stake contract's real DIN balance
///      against what accounting says it should hold.
contract SlashingHandler is Test {
    DinToken public token;
    DinCoordinator public coordinator;
    DinValidatorStake public stake;

    address[] public actors;
    uint256 public ghost_totalStaked;
    uint256 public ghost_totalWithdrawn;
    uint256 public ghost_totalSlashed;
    uint256 public ghost_slashCallCount;
    uint256 public ghost_totalMinted;
    uint256 public ghost_totalBurned;
    uint256 public ghost_totalToTreasury;

    constructor(DinToken _token, DinCoordinator _coordinator, DinValidatorStake _stake) {
        token = _token;
        coordinator = _coordinator;
        stake = _stake;

        for (uint256 i = 0; i < 5; i++) {
            actors.push(makeAddr(string(abi.encodePacked("slashActor", i))));
        }
    }

    function _actor(uint256 seed) internal view returns (address) {
        return actors[seed % actors.length];
    }

    function _fund(address who, uint256 dinAmount) internal {
        if (dinAmount == 0) return;
        // dinPerEth defaults to 1_000_000 * 1e18 on DinCoordinator.
        uint256 ethNeeded = (dinAmount * 1e18) / (1_000_000 * 1e18) + 1;
        vm.deal(who, ethNeeded);
        uint256 supplyBefore = token.totalSupply();
        vm.prank(who);
        coordinator.depositAndMint{value: ethNeeded}();
        ghost_totalMinted += token.totalSupply() - supplyBefore;
    }

    function stakeAction(uint256 actorSeed, uint256 amount) external {
        address who = _actor(actorSeed);
        amount = bound(amount, stake.MIN_STAKE(), 1_000_000 ether);

        _fund(who, amount);

        vm.startPrank(who);
        token.approve(address(stake), amount);
        stake.stake(amount);
        vm.stopPrank();

        ghost_totalStaked += amount;
    }

    function slashAction(uint256 actorSeed, uint256 amount) external {
        address who = _actor(actorSeed);
        (uint256 activeStake, uint256 pendingWithdrawals, , , ) = stake.validators(who);
        uint256 slashable = activeStake + pendingWithdrawals;
        if (slashable == 0) return;
        amount = bound(amount, 1, slashable * 2); // sometimes over-slash on purpose

        uint256 actual = stake.slash(who, amount, "FUZZ_SLASH");

        ghost_totalSlashed += actual;
        // Recomputed here rather than read back from the contract, so the
        // invariants check the split instead of restating it.
        ghost_totalBurned += actual / 2;
        ghost_totalToTreasury += actual - actual / 2;
        ghost_slashCallCount++;
    }

    function unstakeAction(uint256 actorSeed, uint256 amount) external {
        address who = _actor(actorSeed);
        (uint256 activeStake, uint256 pendingWithdrawals, , , ) = stake.validators(who);
        if (activeStake == 0 || pendingWithdrawals > 0) return; // one pending withdrawal at a time
        amount = bound(amount, 1, activeStake);

        vm.prank(who);
        stake.unstake(amount);
    }

    function claimAction(uint256 actorSeed, uint256 warpSeed) external {
        address who = _actor(actorSeed);
        (, uint256 pendingWithdrawals, uint64 withdrawAvailableAt, , ) = stake.validators(who);
        if (pendingWithdrawals == 0) return;

        // Sometimes claim early (expected to revert and be a no-op), sometimes
        // warp forward far enough to succeed -- both are valid handler paths.
        if (warpSeed % 2 == 0) {
            vm.warp(withdrawAvailableAt);
        }
        if (block.timestamp < withdrawAvailableAt) return;

        vm.prank(who);
        try stake.claimUnstaked() {
            ghost_totalWithdrawn += pendingWithdrawals;
        } catch {}
    }

    function actorsLength() external view returns (uint256) {
        return actors.length;
    }
}

contract SlashingInvariantsTest is StdInvariant, Test {
    DinToken tokenImpl;
    DinCoordinator coordinatorImpl;
    DinValidatorStake stakeImpl;

    DinToken token;
    DinCoordinator coordinator;
    DinValidatorStake stake;

    address admin = makeAddr("admin");
    address slasher = makeAddr("slasher");
    address validator1 = makeAddr("validator1");
    address slashTreasury = makeAddr("slashTreasury");
    uint256 initialSupply;

    SlashingHandler handler;

    function _deployPlatform() internal {
        vm.startPrank(admin);

        tokenImpl = new DinToken();
        TransparentUpgradeableProxy tokenProxy = new TransparentUpgradeableProxy(
            address(tokenImpl),
            admin,
            abi.encodeCall(DinToken.initialize, ())
        );
        token = DinToken(address(tokenProxy));

        coordinatorImpl = new DinCoordinator();
        TransparentUpgradeableProxy coordinatorProxy = new TransparentUpgradeableProxy(
            address(coordinatorImpl),
            admin,
            abi.encodeCall(DinCoordinator.initialize, (address(token)))
        );
        coordinator = DinCoordinator(address(coordinatorProxy));

        token.setCoordinator(address(coordinator));

        stakeImpl = new DinValidatorStake();
        TransparentUpgradeableProxy stakeProxy = new TransparentUpgradeableProxy(
            address(stakeImpl),
            admin,
            abi.encodeCall(
                DinValidatorStake.initialize,
                (address(token), address(coordinator))
            )
        );
        stake = DinValidatorStake(address(stakeProxy));

        coordinator.updateValidatorStakeContract(address(stake));

        vm.stopPrank();
    }

    function _fund(address who, uint256 dinAmount) internal {
        uint256 ethNeeded = (dinAmount * 1e18) / (1_000_000 * 1e18) + 1;
        vm.deal(who, ethNeeded);
        vm.prank(who);
        coordinator.depositAndMint{value: ethNeeded}();
    }

    // ─────────────────────────────────────────────────────────────────────
    // Invariant test: random sequences of stake/slash/unstake/claim
    // ─────────────────────────────────────────────────────────────────────

    function setUp() public {
        _deployPlatform();

        handler = new SlashingHandler(token, coordinator, stake);

        vm.prank(admin);
        coordinator.addSlasherContract(address(handler));

        vm.prank(admin);
        stake.setSlashTreasury(slashTreasury);

        // Captured rather than assumed zero: DinToken.initialize() mints
        // nothing today, but the supply identity below should not silently
        // depend on that staying true.
        initialSupply = token.totalSupply();

        targetContract(address(handler));
    }

    /// @dev The stake contract's real DIN balance must always equal
    ///      (total staked - total withdrawn - total slashed): slash() moves
    ///      the slashed amount out via burn and/or transfer to slashTreasury,
    ///      so what remains in the contract's balance is only what is still
    ///      accounted for, plus nothing beyond what claimUnstaked() has paid
    ///      out.
    function invariant_contractBalanceMatchesStakedMinusWithdrawn() public view {
        uint256 expected = handler.ghost_totalStaked()
            - handler.ghost_totalWithdrawn()
            - handler.ghost_totalSlashed();
        assertEq(token.balanceOf(address(stake)), expected);
    }

    /// @dev The contract's internal accounting must equal the same ledger its
    ///      token balance does. Paired with the balance invariant above this is
    ///      solvency: every unit of stake the contract believes it owes is a
    ///      unit it actually holds. This is what carries MECHANISM_DESIGN.md
    ///      §4's "total staked supply never increases after a slash" -- an
    ///      exact equality, not the loose per-actor bound below, which a slash
    ///      that wrongly *raised* an actor's stake could still satisfy.
    function invariant_totalAccountedStakeMatchesLedger() public view {
        uint256 total;
        for (uint256 i = 0; i < handler.actorsLength(); i++) {
            (uint256 activeStake, uint256 pendingWithdrawals, , , ) = stake.validators(handler.actors(i));
            total += activeStake + pendingWithdrawals;
        }
        assertEq(
            total,
            handler.ghost_totalStaked() - handler.ghost_totalWithdrawn() - handler.ghost_totalSlashed()
        );
    }

    /// @dev Slashed tokens leave the stake contract in the 50/50 split resolved
    ///      in MECHANISM_DESIGN.md §4: half burned, half to slashTreasury (an
    ///      odd wei goes to the treasury). Nothing reaches a third party -- that
    ///      follows jointly from these two assertions and the balance invariant
    ///      above, which together account for every unit that left.
    ///      The unset-treasury fallback (both halves burned) is covered by
    ///      DinValidatorStake.t.sol:test_slash_burns100PercentWhenNoTreasurySet.
    function invariant_slashedAmountSplitsBetweenBurnAndTreasury() public view {
        if (handler.ghost_slashCallCount() == 0) return;
        assertEq(token.balanceOf(slashTreasury), handler.ghost_totalToTreasury());
        assertEq(
            token.totalSupply(),
            initialSupply + handler.ghost_totalMinted() - handler.ghost_totalBurned()
        );
    }

    /// @dev No sequence of stake/slash/unstake/claim calls can leave any
    ///      tracked actor with an activeStake+pendingWithdrawals sum that
    ///      exceeds what they ever staked (uint256 underflow would revert
    ///      the whole run before this assertion could even be reached, but
    ///      this additionally proves the accounting never "creates" stake).
    ///      This is a loose per-actor bound, not the exact property --
    ///      invariant_totalAccountedStakeMatchesLedger above carries that.
    function invariant_noActorStakeExceedsWhatWasEverStaked() public view {
        for (uint256 i = 0; i < handler.actorsLength(); i++) {
            address actor = handler.actors(i);
            (uint256 activeStake, uint256 pendingWithdrawals, , , ) = stake.validators(actor);
            assertLe(activeStake + pendingWithdrawals, handler.ghost_totalStaked());
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    // Direct fuzz tests: sharper, single-call assertions the invariant
    // runner's random walk won't reliably hit on its own.
    // ─────────────────────────────────────────────────────────────────────

    function _setUpSingleValidator(uint256 stakeAmount) internal returns (uint256) {
        stakeAmount = bound(stakeAmount, stake.MIN_STAKE(), 1_000_000 ether);
        _fund(validator1, stakeAmount);

        vm.startPrank(validator1);
        token.approve(address(stake), stakeAmount);
        stake.stake(stakeAmount);
        vm.stopPrank();

        vm.prank(admin);
        coordinator.addSlasherContract(slasher);

        return stakeAmount;
    }

    function testFuzz_slash_actualAmountNeverExceedsRequestedOrSlashable(
        uint256 stakeAmount,
        uint256 slashAmount
    ) public {
        stakeAmount = _setUpSingleValidator(stakeAmount);
        slashAmount = bound(slashAmount, 1, stakeAmount * 3);

        vm.prank(slasher);
        uint256 actual = stake.slash(validator1, slashAmount, "TEST");

        assertLe(actual, slashAmount);
        assertLe(actual, stakeAmount);
    }

    function testFuzz_slash_overSlashCapsInsteadOfReverting(
        uint256 stakeAmount,
        uint256 excessBps
    ) public {
        stakeAmount = _setUpSingleValidator(stakeAmount);
        // Request between 1x and 10x the staked amount.
        excessBps = bound(excessBps, 10_000, 100_000);
        uint256 requested = (stakeAmount * excessBps) / 10_000;

        vm.prank(slasher);
        uint256 actual = stake.slash(validator1, requested, "TEST");

        assertEq(actual, stakeAmount);
        assertEq(stake.getStake(validator1), 0);
    }

    function testFuzz_slash_neverLeavesNegativeAccounting(
        uint256 stakeAmount,
        uint256 slashAmount
    ) public {
        stakeAmount = _setUpSingleValidator(stakeAmount);
        slashAmount = bound(slashAmount, 1, stakeAmount);

        vm.prank(slasher);
        stake.slash(validator1, slashAmount, "TEST");

        // uint256 storage can't go negative -- if the arithmetic in slash()
        // were wrong this call would have reverted with an underflow before
        // reaching here. Assert the resulting stake is exactly what's left.
        assertEq(stake.getStake(validator1), stakeAmount - slashAmount);
    }

    function testFuzz_slash_splitsBetweenBurnAndTreasury(
        uint256 stakeAmount,
        uint256 slashAmount
    ) public {
        stakeAmount = _setUpSingleValidator(stakeAmount);
        vm.prank(admin);
        stake.setSlashTreasury(slashTreasury);
        slashAmount = bound(slashAmount, 1, stakeAmount);

        uint256 supplyBefore = token.totalSupply();
        uint256 contractBalanceBefore = token.balanceOf(address(stake));
        uint256 treasuryBefore = token.balanceOf(slashTreasury);

        vm.prank(slasher);
        uint256 actual = stake.slash(validator1, slashAmount, "TEST");

        assertGt(actual, 0);
        // These three together are the no-leak property: exactly `actual` left
        // the contract, and burn + treasury account for all of it.
        assertEq(contractBalanceBefore - token.balanceOf(address(stake)), actual);
        assertEq(supplyBefore - token.totalSupply(), actual / 2);
        assertEq(token.balanceOf(slashTreasury) - treasuryBefore, actual - actual / 2);
    }

    function test_slash_unauthorizedCallerReverts() public {
        _setUpSingleValidator(1_000 ether);

        vm.prank(validator1);
        vm.expectRevert(); // NotSlasherContract
        stake.slash(validator1, 1, "TEST");
    }

    function test_slash_zeroAmountReverts() public {
        _setUpSingleValidator(1_000 ether); // already registers `slasher`

        vm.prank(slasher);
        vm.expectRevert(); // InvalidSlashAmount
        stake.slash(validator1, 0, "TEST");
    }

    function test_slash_zeroAddressReverts() public {
        vm.prank(admin);
        coordinator.addSlasherContract(slasher);

        vm.prank(slasher);
        vm.expectRevert(); // InvalidAddress
        stake.slash(address(0), 1, "TEST");
    }

    function testFuzz_sequentialSlashes_stakeMonotonicallyDecreasing(
        uint256 stakeAmount,
        uint256 firstSlash,
        uint256 secondSlash
    ) public {
        stakeAmount = _setUpSingleValidator(stakeAmount);
        firstSlash = bound(firstSlash, 1, stakeAmount / 2);
        secondSlash = bound(secondSlash, 1, stakeAmount / 2);

        uint256 before = stake.getStake(validator1);

        vm.prank(slasher);
        stake.slash(validator1, firstSlash, "TEST_1");
        uint256 afterFirst = stake.getStake(validator1);
        assertLt(afterFirst, before);

        vm.prank(slasher);
        stake.slash(validator1, secondSlash, "TEST_2");
        uint256 afterSecond = stake.getStake(validator1);
        assertLe(afterSecond, afterFirst);
    }

    /// @dev A slash that eats into pendingWithdrawals (because activeStake
    ///      alone is insufficient) must also clear withdrawAvailableAt once
    ///      pendingWithdrawals hits zero, otherwise claimUnstaked() would be
    ///      claimable-in-principle for a balance of zero.
    function test_slash_clearsWithdrawTimestampWhenPendingFullyConsumed() public {
        uint256 stakeAmount = _setUpSingleValidator(1_000 ether);

        vm.prank(validator1);
        stake.unstake(stakeAmount); // moves everything into pendingWithdrawals

        vm.prank(slasher);
        stake.slash(validator1, stakeAmount, "TEST");

        (, uint256 pendingWithdrawals, uint64 withdrawAvailableAt, , ) = stake.validators(validator1);
        assertEq(pendingWithdrawals, 0);
        assertEq(withdrawAvailableAt, 0);
    }
}
