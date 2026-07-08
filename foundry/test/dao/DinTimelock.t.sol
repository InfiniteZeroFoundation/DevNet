// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "forge-std/Test.sol";
import "../../src/dao/DinTimelock.sol";

/// @dev Minimal target whose state changes verify that scheduled calls execute.
contract TimelockTarget {
    uint256 public value;

    function setValue(uint256 v) external {
        value = v;
    }
}

contract DinTimelockTest is Test {
    DinTimelock    internal tlShort; // 24 h
    DinTimelock    internal tlLong;  // 48 h
    TimelockTarget internal target;

    address internal proposer = makeAddr("proposer");
    address internal executor = makeAddr("executor");

    uint256 internal constant SHORT_DELAY = 1 days;
    uint256 internal constant LONG_DELAY  = 2 days;

    bytes32 internal constant PROPOSER_ROLE  = keccak256("PROPOSER_ROLE");
    bytes32 internal constant EXECUTOR_ROLE  = keccak256("EXECUTOR_ROLE");
    bytes32 internal constant CANCELLER_ROLE = keccak256("CANCELLER_ROLE");
    bytes32 internal constant ADMIN_ROLE     = 0x00;

    function setUp() public {
        address[] memory proposers_ = new address[](1);
        proposers_[0] = proposer;

        address[] memory executors_ = new address[](1);
        executors_[0] = address(0); // open execution

        tlShort = new DinTimelock(SHORT_DELAY, proposers_, executors_, address(0));
        tlLong  = new DinTimelock(LONG_DELAY,  proposers_, executors_, address(0));

        target = new TimelockTarget();
    }

    // ─── Role assignments ─────────────────────────────────────────────────────

    function test_ShortDelay_ProposerHasRole() public view {
        assertTrue(tlShort.hasRole(PROPOSER_ROLE, proposer));
    }

    function test_LongDelay_ProposerHasRole() public view {
        assertTrue(tlLong.hasRole(PROPOSER_ROLE, proposer));
    }

    function test_OpenExecutorGranted() public view {
        // address(0) as executor grants EXECUTOR_ROLE to everyone
        assertTrue(tlShort.hasRole(EXECUTOR_ROLE, address(0)));
    }

    function test_AdminRoleRenounced() public view {
        // Passing address(0) as admin_ causes TimelockController to skip
        // granting DEFAULT_ADMIN_ROLE to any external address.
        assertFalse(tlShort.hasRole(ADMIN_ROLE, address(this)));
    }

    function test_MinDelayShort() public view {
        assertEq(tlShort.getMinDelay(), SHORT_DELAY);
    }

    function test_MinDelayLong() public view {
        assertEq(tlLong.getMinDelay(), LONG_DELAY);
    }

    // ─── Propose → wait → execute (short timelock) ───────────────────────────

    function test_ShortTimelock_ScheduleAndExecute() public {
        bytes memory data = abi.encodeCall(TimelockTarget.setValue, (7));
        bytes32 salt      = bytes32(0);
        bytes32 id        = tlShort.hashOperation(address(target), 0, data, bytes32(0), salt);

        vm.prank(proposer);
        tlShort.schedule(address(target), 0, data, bytes32(0), salt, SHORT_DELAY);

        assertTrue(tlShort.isOperationPending(id));

        vm.warp(block.timestamp + SHORT_DELAY);

        // Anyone can execute once the delay has elapsed (open EXECUTOR_ROLE)
        tlShort.execute(address(target), 0, data, bytes32(0), salt);

        assertTrue(tlShort.isOperationDone(id));
        assertEq(target.value(), 7);
    }

    function test_ShortTimelock_CannotExecuteBeforeDelay() public {
        bytes memory data = abi.encodeCall(TimelockTarget.setValue, (1));
        bytes32 salt      = bytes32(0);

        vm.prank(proposer);
        tlShort.schedule(address(target), 0, data, bytes32(0), salt, SHORT_DELAY);

        vm.warp(block.timestamp + SHORT_DELAY - 1);
        vm.expectRevert();
        tlShort.execute(address(target), 0, data, bytes32(0), salt);
    }

    // ─── Cancel (canceller role) ──────────────────────────────────────────────

    function test_ProposerCanCancel() public {
        bytes memory data = abi.encodeCall(TimelockTarget.setValue, (1));
        bytes32 salt      = bytes32(0);
        bytes32 id        = tlShort.hashOperation(address(target), 0, data, bytes32(0), salt);

        vm.prank(proposer);
        tlShort.schedule(address(target), 0, data, bytes32(0), salt, SHORT_DELAY);

        // Proposer also holds CANCELLER_ROLE by OZ default
        vm.prank(proposer);
        tlShort.cancel(id);

        assertFalse(tlShort.isOperationPending(id));
    }

    // ─── Long timelock delay enforcement ─────────────────────────────────────

    function test_LongTimelock_DelayEnforced() public {
        bytes memory data = abi.encodeCall(TimelockTarget.setValue, (99));
        bytes32 salt      = bytes32(0);

        vm.prank(proposer);
        tlLong.schedule(address(target), 0, data, bytes32(0), salt, LONG_DELAY);

        // Warp only to short delay — should still be too early for the long lock
        vm.warp(block.timestamp + SHORT_DELAY);
        vm.expectRevert();
        tlLong.execute(address(target), 0, data, bytes32(0), salt);
    }

    function test_LongTimelock_ExecutesAfterFullDelay() public {
        bytes memory data = abi.encodeCall(TimelockTarget.setValue, (42));
        bytes32 salt      = bytes32(0);

        vm.prank(proposer);
        tlLong.schedule(address(target), 0, data, bytes32(0), salt, LONG_DELAY);

        vm.warp(block.timestamp + LONG_DELAY);
        tlLong.execute(address(target), 0, data, bytes32(0), salt);
        assertEq(target.value(), 42);
    }
}
