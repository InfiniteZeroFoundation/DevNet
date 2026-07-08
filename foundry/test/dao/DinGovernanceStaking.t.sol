// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "forge-std/Test.sol";
import "../../src/dao/DinGovernanceStaking.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @dev Minimal ERC-20 used as the DIN stand-in in tests.
contract MockDIN is ERC20 {
    constructor() ERC20("DIN Token", "DIN") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

contract DinGovernanceStakingTest is Test {
    MockDIN              internal din;
    DinGovernanceStaking internal stDIN;

    address internal alice = makeAddr("alice");
    address internal bob   = makeAddr("bob");

    uint256 internal constant INITIAL = 1_000e18;

    function setUp() public {
        din   = new MockDIN();
        stDIN = new DinGovernanceStaking(address(din));

        din.mint(alice, INITIAL);
        din.mint(bob,   INITIAL);
    }

    // ─── Constructor ──────────────────────────────────────────────────────────

    function test_DinTokenAddress() public view {
        assertEq(stDIN.dinToken(), address(din));
    }

    function test_NameAndSymbol() public view {
        assertEq(stDIN.name(),   "Staked DIN");
        assertEq(stDIN.symbol(), "stDIN");
    }

    // ─── lock ─────────────────────────────────────────────────────────────────

    function test_Lock_MintsStDIN() public {
        vm.startPrank(alice);
        din.approve(address(stDIN), 100e18);
        stDIN.lock(100e18);
        vm.stopPrank();

        assertEq(stDIN.balanceOf(alice), 100e18);
        assertEq(din.balanceOf(address(stDIN)), 100e18);
        assertEq(stDIN.totalLocked(), 100e18);
    }

    function test_Lock_RevertsOnZero() public {
        vm.prank(alice);
        vm.expectRevert(GS_ZeroAmount.selector);
        stDIN.lock(0);
    }

    // ─── unlock ───────────────────────────────────────────────────────────────

    function test_Unlock_BurnsStDINAndReturnsDIN() public {
        _lock(alice, 100e18);

        vm.prank(alice);
        stDIN.unlock(60e18);

        assertEq(stDIN.balanceOf(alice), 40e18);
        assertEq(din.balanceOf(alice),   INITIAL - 100e18 + 60e18);
    }

    function test_Unlock_RevertsOnInsufficientBalance() public {
        _lock(alice, 50e18);
        vm.prank(alice);
        vm.expectRevert(GS_InsufficientBalance.selector);
        stDIN.unlock(51e18);
    }

    function test_Unlock_RevertsOnZero() public {
        _lock(alice, 50e18);
        vm.prank(alice);
        vm.expectRevert(GS_ZeroAmount.selector);
        stDIN.unlock(0);
    }

    // ─── Non-transferability ──────────────────────────────────────────────────

    function test_Transfer_AlwaysReverts() public {
        _lock(alice, 100e18);
        vm.prank(alice);
        vm.expectRevert(GS_NonTransferable.selector);
        stDIN.transfer(bob, 10e18);
    }

    function test_TransferFrom_AlwaysReverts() public {
        _lock(alice, 100e18);
        vm.prank(alice);
        stDIN.approve(bob, 50e18);
        vm.prank(bob);
        vm.expectRevert(GS_NonTransferable.selector);
        stDIN.transferFrom(alice, bob, 50e18);
    }

    // ─── Delegation + voting power checkpoints ────────────────────────────────

    function test_VotingPowerZeroWithoutDelegation() public {
        _lock(alice, 100e18);
        // No self-delegation → getVotes returns 0
        assertEq(stDIN.getVotes(alice), 0);
    }

    function test_VotingPowerAfterSelfDelegate() public {
        _lock(alice, 100e18);
        vm.prank(alice);
        stDIN.delegate(alice);
        assertEq(stDIN.getVotes(alice), 100e18);
    }

    function test_DelegationTransfersVotingPower() public {
        _lock(alice, 100e18);
        vm.prank(alice);
        stDIN.delegate(bob);
        assertEq(stDIN.getVotes(alice), 0);
        assertEq(stDIN.getVotes(bob),   100e18);
    }

    function test_PastVotesCheckpointed() public {
        _lock(alice, 200e18);
        vm.prank(alice);
        stDIN.delegate(alice);

        uint256 snap = vm.getBlockNumber();
        vm.roll(snap + 1);

        // Unlock half — past votes at `snap` should still reflect 200e18
        vm.prank(alice);
        stDIN.unlock(100e18);

        assertEq(stDIN.getPastVotes(alice, snap), 200e18);
        assertEq(stDIN.getVotes(alice),            100e18);
    }

    // ─── Invariant: totalLocked == DIN held by contract ───────────────────────

    function test_TotalLockedMatchesDINBalance() public {
        _lock(alice, 300e18);
        _lock(bob,   150e18);
        vm.prank(alice); stDIN.unlock(100e18);

        assertEq(stDIN.totalLocked(), din.balanceOf(address(stDIN)));
        assertEq(stDIN.totalLocked(), 350e18);
    }

    // ─── Helpers ──────────────────────────────────────────────────────────────

    function _lock(address account, uint256 amount) internal {
        vm.startPrank(account);
        din.approve(address(stDIN), amount);
        stDIN.lock(amount);
        vm.stopPrank();
    }
}
