// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "forge-std/Test.sol";
import "../../src/dao/DinMultisig.sol";
import "../../src/dao/interfaces/IDinMultisig.sol";

/// @dev Minimal call target used to verify proposal dispatch.
contract CallTarget {
    uint256 public value;

    function setValue(uint256 v) external {
        value = v;
    }

    function revertAlways() external pure {
        revert("always");
    }
}

contract DinMultisigTest is Test {
    DinMultisig internal ms;
    CallTarget  internal target;

    address internal alice = makeAddr("alice");
    address internal bob   = makeAddr("bob");
    address internal carol = makeAddr("carol");
    address internal eve   = makeAddr("eve"); // non-signer

    // Thresholds: Parameter=2, Operational=2, Treasury=3, Upgrade=3
    uint256[4] internal thresholds = [uint256(2), 2, 3, 3];

    function setUp() public {
        address[] memory s = new address[](3);
        s[0] = alice;
        s[1] = bob;
        s[2] = carol;
        ms = new DinMultisig(s, thresholds);
        target = new CallTarget();
    }

    // ─── Constructor ──────────────────────────────────────────────────────────

    function test_Constructor_SetsSigners() public view {
        assertTrue(ms.isSigner(alice));
        assertTrue(ms.isSigner(bob));
        assertTrue(ms.isSigner(carol));
        assertFalse(ms.isSigner(eve));
    }

    function test_Constructor_SetsThresholds() public view {
        assertEq(ms.threshold(ProposalCategory.Parameter),   2);
        assertEq(ms.threshold(ProposalCategory.Operational), 2);
        assertEq(ms.threshold(ProposalCategory.Treasury),    3);
        assertEq(ms.threshold(ProposalCategory.Upgrade),     3);
    }

    function test_Constructor_RejectsEmptySigners() public {
        address[] memory empty = new address[](0);
        vm.expectRevert(MS_EmptySignerList.selector);
        new DinMultisig(empty, thresholds);
    }

    function test_Constructor_RejectsZeroAddress() public {
        address[] memory s = new address[](1);
        s[0] = address(0);
        vm.expectRevert(MS_ZeroAddress.selector);
        new DinMultisig(s, thresholds);
    }

    function test_Constructor_RejectsDuplicateSigner() public {
        address[] memory s = new address[](2);
        s[0] = alice;
        s[1] = alice;
        vm.expectRevert(MS_DuplicateSigner.selector);
        new DinMultisig(s, thresholds);
    }

    function test_Constructor_RejectsZeroThreshold() public {
        uint256[4] memory bad = [uint256(0), 1, 1, 1];
        address[] memory s = new address[](2);
        s[0] = alice; s[1] = bob;
        vm.expectRevert(MS_InvalidThreshold.selector);
        new DinMultisig(s, bad);
    }

    function test_Constructor_RejectsThresholdAboveSignerCount() public {
        uint256[4] memory bad = [uint256(4), 1, 1, 1];
        address[] memory s = new address[](3);
        s[0] = alice; s[1] = bob; s[2] = carol;
        vm.expectRevert(MS_InvalidThreshold.selector);
        new DinMultisig(s, bad);
    }

    // ─── propose ──────────────────────────────────────────────────────────────

    function test_Propose_SucceedsForSigner() public {
        bytes memory data = abi.encodeCall(CallTarget.setValue, (42));
        vm.prank(alice);
        uint256 id = ms.propose(address(target), data, 0, ProposalCategory.Parameter);
        assertEq(id, 0);
        assertEq(ms.proposalCount(), 1);

        (, , , ProposalCategory cat, ProposalState state, , ) = ms.getProposal(id);
        assertEq(uint8(cat),   uint8(ProposalCategory.Parameter));
        assertEq(uint8(state), uint8(ProposalState.Open));
    }

    function test_Propose_RevertsForNonSigner() public {
        vm.prank(eve);
        vm.expectRevert(MS_NotSigner.selector);
        ms.propose(address(target), "", 0, ProposalCategory.Parameter);
    }

    function test_Propose_RevertsOnZeroTarget() public {
        vm.prank(alice);
        vm.expectRevert(MS_ZeroAddress.selector);
        ms.propose(address(0), "", 0, ProposalCategory.Parameter);
    }

    // ─── confirm / threshold transition ───────────────────────────────────────

    function test_Confirm_IncreasesCount() public {
        uint256 id = _createProposal(ProposalCategory.Parameter);

        vm.prank(alice);
        ms.confirm(id);
        (, , , , , uint256 count, ) = ms.getProposal(id);
        assertEq(count, 1);
    }

    function test_Confirm_TransitionsToExecutable() public {
        uint256 id = _createProposal(ProposalCategory.Parameter); // threshold=2
        vm.prank(alice); ms.confirm(id);
        vm.prank(bob);   ms.confirm(id);
        (, , , , ProposalState state, , ) = ms.getProposal(id);
        assertEq(uint8(state), uint8(ProposalState.Executable));
    }

    function test_Confirm_RevertsOnNonOpen() public {
        uint256 id = _createProposal(ProposalCategory.Parameter);
        vm.prank(alice); ms.confirm(id);
        vm.prank(bob);   ms.confirm(id); // now Executable
        vm.prank(carol);
        vm.expectRevert(MS_ProposalNotOpen.selector);
        ms.confirm(id);
    }

    function test_Confirm_RevertsOnDuplicate() public {
        uint256 id = _createProposal(ProposalCategory.Parameter);
        vm.prank(alice); ms.confirm(id);
        vm.prank(alice);
        vm.expectRevert(MS_AlreadyConfirmed.selector);
        ms.confirm(id);
    }

    // ─── revoke ───────────────────────────────────────────────────────────────

    function test_Revoke_DecreasesCount() public {
        uint256 id = _createProposal(ProposalCategory.Parameter);
        vm.prank(alice); ms.confirm(id);
        vm.prank(alice); ms.revoke(id);
        (, , , , , uint256 count, ) = ms.getProposal(id);
        assertEq(count, 0);
    }

    function test_Revoke_FromExecutableBackToOpen() public {
        uint256 id = _createProposal(ProposalCategory.Parameter);
        vm.prank(alice); ms.confirm(id);
        vm.prank(bob);   ms.confirm(id); // Executable
        vm.prank(alice); ms.revoke(id);  // drops below threshold → Open
        (, , , , ProposalState state, , ) = ms.getProposal(id);
        assertEq(uint8(state), uint8(ProposalState.Open));
    }

    function test_Revoke_RevertsIfNotConfirmed() public {
        uint256 id = _createProposal(ProposalCategory.Parameter);
        vm.prank(alice);
        vm.expectRevert(MS_NotConfirmed.selector);
        ms.revoke(id);
    }

    // ─── execute ──────────────────────────────────────────────────────────────

    function test_Execute_DispatchesCall() public {
        bytes memory data = abi.encodeCall(CallTarget.setValue, (99));
        vm.prank(alice);
        uint256 id = ms.propose(address(target), data, 0, ProposalCategory.Parameter);
        vm.prank(alice); ms.confirm(id);
        vm.prank(bob);   ms.confirm(id);
        vm.prank(carol); ms.execute(id);
        assertEq(target.value(), 99);

        (, , , , ProposalState state, , ) = ms.getProposal(id);
        assertEq(uint8(state), uint8(ProposalState.Executed));
    }

    function test_Execute_RevertsIfNotExecutable() public {
        uint256 id = _createProposal(ProposalCategory.Parameter);
        vm.prank(alice);
        vm.expectRevert(MS_ProposalNotExecutable.selector);
        ms.execute(id);
    }

    function test_Execute_RevertsOnFailedCall() public {
        bytes memory data = abi.encodeCall(CallTarget.revertAlways, ());
        vm.prank(alice);
        uint256 id = ms.propose(address(target), data, 0, ProposalCategory.Parameter);
        vm.prank(alice); ms.confirm(id);
        vm.prank(bob);   ms.confirm(id);
        vm.prank(carol);
        vm.expectRevert(MS_ExecutionFailed.selector);
        ms.execute(id);
    }

    // ─── cancel ───────────────────────────────────────────────────────────────

    function test_Cancel_TransitionsToCancelled() public {
        uint256 id = _createProposal(ProposalCategory.Parameter);
        vm.prank(alice); ms.cancel(id);
        (, , , , ProposalState state, , ) = ms.getProposal(id);
        assertEq(uint8(state), uint8(ProposalState.Cancelled));
    }

    function test_Cancel_RevertsAfterExecution() public {
        uint256 id = _createProposal(ProposalCategory.Parameter);
        vm.prank(alice); ms.confirm(id);
        vm.prank(bob);   ms.confirm(id);
        vm.prank(alice); ms.execute(id);
        vm.prank(carol);
        vm.expectRevert(MS_ProposalNotCancellable.selector);
        ms.cancel(id);
    }

    // ─── Category threshold enforcement ───────────────────────────────────────

    function test_TreasuryRequiresThreeConfirms() public {
        uint256 id = _createProposal(ProposalCategory.Treasury); // threshold=3
        vm.prank(alice); ms.confirm(id);
        vm.prank(bob);   ms.confirm(id);
        (, , , , ProposalState state, , ) = ms.getProposal(id);
        assertEq(uint8(state), uint8(ProposalState.Open));   // still open after 2
        vm.prank(carol); ms.confirm(id);
        (, , , , state, , ) = ms.getProposal(id);
        assertEq(uint8(state), uint8(ProposalState.Executable));
    }

    // ─── Helpers ──────────────────────────────────────────────────────────────

    function _createProposal(ProposalCategory cat) internal returns (uint256 id) {
        bytes memory data = abi.encodeCall(CallTarget.setValue, (1));
        vm.prank(alice);
        id = ms.propose(address(target), data, 0, cat);
    }
}
