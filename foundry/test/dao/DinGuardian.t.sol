// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "forge-std/Test.sol";
import "../../src/dao/DinGuardian.sol";
import "../../src/dao/interfaces/IDinGuardian.sol";

/// @dev Minimal target that records guardian calls and supports reversal.
contract GuardianTarget {
    bool public modelDisabled;
    bool public slasherDeauthorized;

    function disableModel() external {
        modelDisabled = true;
    }

    function enableModel() external {
        modelDisabled = false;
    }

    function deauthorizeSlasher() external {
        slasherDeauthorized = true;
    }

    function reauthorizeSlasher() external {
        slasherDeauthorized = false;
    }

    function revertAlways() external pure {
        revert("always fails");
    }
}

contract DinGuardianTest is Test {
    DinGuardian    internal guardian;
    GuardianTarget internal target;

    address internal multisig = makeAddr("multisig"); // guardian role
    address internal governor = makeAddr("governor"); // ratifier role
    address internal anyone   = makeAddr("anyone");

    uint256 internal constant WINDOW = 7 days;

    function setUp() public {
        guardian = new DinGuardian(multisig, governor, WINDOW);
        target   = new GuardianTarget();
    }

    // ─── Constructor ──────────────────────────────────────────────────────────

    function test_GuardianAddress() public view {
        assertEq(guardian.guardian(), multisig);
    }

    function test_GovernorAddress() public view {
        assertEq(guardian.governor(), governor);
    }

    function test_RatificationWindow() public view {
        assertEq(guardian.ratificationWindow(), WINDOW);
    }

    function test_Constructor_RejectsZeroGuardian() public {
        vm.expectRevert(DG_ZeroAddress.selector);
        new DinGuardian(address(0), governor, WINDOW);
    }

    // ─── performAction ────────────────────────────────────────────────────────

    function test_PerformAction_DispatchesCall() public {
        bytes memory data    = abi.encodeCall(GuardianTarget.disableModel, ());
        bytes memory reversal = abi.encodeCall(GuardianTarget.enableModel, ());

        vm.prank(multisig);
        uint256 id = guardian.performAction(address(target), data, reversal, "disable model 1");

        assertEq(id, 0);
        assertTrue(target.modelDisabled());

        ( , , , , ActionState state, uint256 expiry) = guardian.getAction(id);
        assertEq(uint8(state), uint8(ActionState.Active));
        assertEq(expiry, block.timestamp + WINDOW);
    }

    function test_PerformAction_RevertsForNonGuardian() public {
        vm.prank(anyone);
        vm.expectRevert(DG_NotGuardian.selector);
        guardian.performAction(address(target), "", "", "");
    }

    function test_PerformAction_RevertsOnZeroTarget() public {
        vm.prank(multisig);
        vm.expectRevert(DG_ZeroAddress.selector);
        guardian.performAction(address(0), "", "", "");
    }

    function test_PerformAction_RevertsWhenCallFails() public {
        bytes memory data = abi.encodeCall(GuardianTarget.revertAlways, ());
        vm.prank(multisig);
        vm.expectRevert(DG_ActionCallFailed.selector);
        guardian.performAction(address(target), data, "", "bad call");
    }

    // ─── ratifyAction ─────────────────────────────────────────────────────────

    function test_RatifyAction_Succeeds() public {
        uint256 id = _performDisableModel();

        vm.prank(governor);
        guardian.ratifyAction(id);

        ( , , , , ActionState state, ) = guardian.getAction(id);
        assertEq(uint8(state), uint8(ActionState.Ratified));
    }

    function test_RatifyAction_RevertsForNonGovernor() public {
        uint256 id = _performDisableModel();
        vm.prank(anyone);
        vm.expectRevert(DG_NotGovernor.selector);
        guardian.ratifyAction(id);
    }

    function test_RatifyAction_RevertsIfNotActive() public {
        uint256 id = _performDisableModel();
        vm.prank(governor); guardian.ratifyAction(id); // Ratified
        vm.prank(governor);
        vm.expectRevert(DG_ActionNotActive.selector);
        guardian.ratifyAction(id);
    }

    // ─── expireAction ─────────────────────────────────────────────────────────

    function test_ExpireAction_ReversesAfterWindow() public {
        uint256 id = _performDisableModel();
        assertTrue(target.modelDisabled()); // action took effect

        vm.warp(block.timestamp + WINDOW + 1);
        vm.prank(anyone);
        guardian.expireAction(id);

        assertFalse(target.modelDisabled()); // reversal applied

        ( , , , , ActionState state, ) = guardian.getAction(id);
        assertEq(uint8(state), uint8(ActionState.Expired));
    }

    function test_ExpireAction_RevertsBeforeWindow() public {
        uint256 id = _performDisableModel();
        vm.warp(block.timestamp + WINDOW - 1);
        vm.expectRevert(DG_WindowNotElapsed.selector);
        guardian.expireAction(id);
    }

    function test_ExpireAction_RevertsIfRatified() public {
        uint256 id = _performDisableModel();
        vm.prank(governor); guardian.ratifyAction(id);
        vm.warp(block.timestamp + WINDOW + 1);
        vm.expectRevert(DG_ActionNotExpirable.selector);
        guardian.expireAction(id);
    }

    function test_ExpireAction_NoReversalDataIsNoop() public {
        bytes memory data = abi.encodeCall(GuardianTarget.disableModel, ());
        vm.prank(multisig);
        uint256 id = guardian.performAction(address(target), data, "", "no reversal");

        vm.warp(block.timestamp + WINDOW + 1);
        guardian.expireAction(id); // should not revert even with empty reversal

        ( , , , , ActionState state, ) = guardian.getAction(id);
        assertEq(uint8(state), uint8(ActionState.Expired));
    }

    // ─── setGovernor ──────────────────────────────────────────────────────────

    function test_SetGovernor_UpdatesAddress() public {
        address newGov = makeAddr("newGov");
        vm.prank(multisig);
        guardian.setGovernor(newGov);
        assertEq(guardian.governor(), newGov);
    }

    function test_SetGovernor_RevertsForNonGuardian() public {
        vm.prank(anyone);
        vm.expectRevert(DG_NotGuardian.selector);
        guardian.setGovernor(makeAddr("x"));
    }

    function test_SetGovernor_RevertsOnZeroAddress() public {
        vm.prank(multisig);
        vm.expectRevert(DG_ZeroAddress.selector);
        guardian.setGovernor(address(0));
    }

    // ─── Action count ─────────────────────────────────────────────────────────

    function test_ActionCountIncrements() public {
        _performDisableModel();
        _performDeauthorizeSlasher();
        assertEq(guardian.actionCount(), 2);
    }

    // ─── Invalid action ID ────────────────────────────────────────────────────

    function test_GetAction_RevertsOnInvalidId() public {
        vm.expectRevert(DG_InvalidActionId.selector);
        guardian.getAction(999);
    }

    // ─── Helpers ──────────────────────────────────────────────────────────────

    function _performDisableModel() internal returns (uint256 id) {
        bytes memory data     = abi.encodeCall(GuardianTarget.disableModel, ());
        bytes memory reversal = abi.encodeCall(GuardianTarget.enableModel, ());
        vm.prank(multisig);
        id = guardian.performAction(address(target), data, reversal, "disable model");
    }

    function _performDeauthorizeSlasher() internal returns (uint256 id) {
        bytes memory data     = abi.encodeCall(GuardianTarget.deauthorizeSlasher, ());
        bytes memory reversal = abi.encodeCall(GuardianTarget.reauthorizeSlasher, ());
        vm.prank(multisig);
        id = guardian.performAction(address(target), data, reversal, "deauthorize slasher");
    }
}
