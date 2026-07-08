// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "forge-std/Test.sol";
import "../../src/dao/DinGovernor.sol";
import "../../src/dao/DinGovernanceStaking.sol";
import "../../src/dao/DinTimelock.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @dev Minimal ERC-20 used as the DIN stand-in in tests.
contract GovMockDIN is ERC20 {
    constructor() ERC20("DIN Token", "DIN") {}
    function mint(address to, uint256 amount) external { _mint(to, amount); }
}

/// @dev Minimal call target whose state changes verify proposal execution.
contract GovTarget {
    uint256 public value;
    function setValue(uint256 v) external { value = v; }
}

contract DinGovernorTest is Test {
    GovMockDIN           internal din;
    DinGovernanceStaking internal stDIN;
    DinTimelock          internal timelock;
    DinGovernor          internal gov;
    GovTarget            internal target;

    address internal alice   = makeAddr("alice");
    address internal bob     = makeAddr("bob");
    address internal carol   = makeAddr("carol");
    address internal deployer = makeAddr("deployer");

    // Governor settings (block-based)
    uint48  internal constant VOTING_DELAY     = 1;    // 1 block
    uint32  internal constant VOTING_PERIOD    = 50;   // 50 blocks
    uint256 internal constant PROPOSAL_THRESH  = 1e18; // 1 stDIN
    uint256 internal constant QUORUM_FRACTION  = 4;    // 4%
    uint256 internal constant TIMELOCK_DELAY   = 2 days;

    function setUp() public {
        vm.startPrank(deployer);

        din   = new GovMockDIN();
        stDIN = new DinGovernanceStaking(address(din));

        // Build timelock with governor as proposer (wired below after deploy)
        address[] memory noProposers = new address[](0);
        address[] memory openExec    = new address[](1);
        openExec[0] = address(0);

        timelock = new DinTimelock(TIMELOCK_DELAY, noProposers, openExec, deployer);

        gov = new DinGovernor(
            IVotes(address(stDIN)),
            TimelockController(payable(address(timelock))),
            VOTING_DELAY,
            VOTING_PERIOD,
            PROPOSAL_THRESH,
            QUORUM_FRACTION
        );

        // Grant governor PROPOSER_ROLE and CANCELLER_ROLE on the timelock
        timelock.grantRole(timelock.PROPOSER_ROLE(),  address(gov));
        timelock.grantRole(timelock.CANCELLER_ROLE(), address(gov));
        // Renounce deployer's admin
        timelock.renounceRole(timelock.DEFAULT_ADMIN_ROLE(), deployer);

        target = new GovTarget();

        vm.stopPrank();

        // Mint DIN and lock stDIN so voters have voting power
        din.mint(alice, 1_000e18);
        din.mint(bob,   1_000e18);
        _lockAndDelegate(alice, 600e18, alice);
        _lockAndDelegate(bob,   400e18, bob);
    }

    // ─── Governor settings ────────────────────────────────────────────────────

    function test_VotingDelay() public view {
        assertEq(gov.votingDelay(), VOTING_DELAY);
    }

    function test_VotingPeriod() public view {
        assertEq(gov.votingPeriod(), VOTING_PERIOD);
    }

    function test_ProposalThreshold() public view {
        assertEq(gov.proposalThreshold(), PROPOSAL_THRESH);
    }

    // ─── Full proposal lifecycle ───────────────────────────────────────────────

    function test_ProposalLifecycle_ProposeVoteQueueExecute() public {
        // Build a proposal to call target.setValue(77) through the timelock
        bytes memory data = abi.encodeCall(GovTarget.setValue, (77));

        address[] memory targets   = new address[](1);
        uint256[] memory values    = new uint256[](1);
        bytes[]   memory calldatas = new bytes[](1);
        targets[0]   = address(target);
        values[0]    = 0;
        calldatas[0] = data;

        string memory desc = "Set target value to 77";

        // 1. Propose
        vm.prank(alice);
        uint256 proposalId = gov.propose(targets, values, calldatas, desc);
        assertEq(uint8(gov.state(proposalId)), uint8(IGovernor.ProposalState.Pending));

        // 2. Advance past voting delay
        vm.roll(block.number + VOTING_DELAY + 1);
        assertEq(uint8(gov.state(proposalId)), uint8(IGovernor.ProposalState.Active));

        // 3. Vote
        vm.prank(alice); gov.castVote(proposalId, 1); // For
        vm.prank(bob);   gov.castVote(proposalId, 1); // For

        // 4. Advance past voting period
        vm.roll(block.number + VOTING_PERIOD + 1);
        assertEq(uint8(gov.state(proposalId)), uint8(IGovernor.ProposalState.Succeeded));

        // 5. Queue into timelock
        gov.queue(targets, values, calldatas, keccak256(bytes(desc)));
        assertEq(uint8(gov.state(proposalId)), uint8(IGovernor.ProposalState.Queued));

        // 6. Advance past timelock delay
        vm.warp(block.timestamp + TIMELOCK_DELAY + 1);

        // 7. Execute
        gov.execute(targets, values, calldatas, keccak256(bytes(desc)));
        assertEq(uint8(gov.state(proposalId)), uint8(IGovernor.ProposalState.Executed));
        assertEq(target.value(), 77);
    }

    // ─── Quorum ───────────────────────────────────────────────────────────────

    function test_ProposalDefeatedWhenQuorumNotMet() public {
        // Deploy fresh stDIN with tiny supply so quorum fraction fails
        GovMockDIN  smallDin   = new GovMockDIN();
        DinGovernanceStaking smallStDIN = new DinGovernanceStaking(address(smallDin));
        smallDin.mint(alice, 10e18);

        vm.startPrank(alice);
        smallDin.approve(address(smallStDIN), 10e18);
        smallStDIN.lock(10e18);
        smallStDIN.delegate(alice);
        vm.stopPrank();

        address[] memory noProposers = new address[](0);
        address[] memory openExec    = new address[](1);
        openExec[0] = address(0);
        DinTimelock tl2 = new DinTimelock(0, noProposers, openExec, address(this));

        DinGovernor gov2 = new DinGovernor(
            IVotes(address(smallStDIN)),
            TimelockController(payable(address(tl2))),
            1,
            50,
            0,
            50 // 50% quorum — impossible to reach with 10e18 / 10e18 if alice votes only 1 For
        );

        tl2.grantRole(tl2.PROPOSER_ROLE(), address(gov2));

        bytes memory data = abi.encodeCall(GovTarget.setValue, (1));
        address[] memory targets   = new address[](1); targets[0]   = address(target);
        uint256[] memory vals      = new uint256[](1); vals[0]      = 0;
        bytes[]   memory cds       = new bytes[](1);   cds[0]       = data;

        vm.prank(alice);
        uint256 pid = gov2.propose(targets, vals, cds, "test");
        vm.roll(block.number + 2);

        // Alice votes Against — should remain below quorum for For side
        vm.prank(alice);
        gov2.castVote(pid, 0); // Against

        vm.roll(block.number + 51);
        assertEq(uint8(gov2.state(pid)), uint8(IGovernor.ProposalState.Defeated));
    }

    // ─── Proposal below threshold ──────────────────────────────────────────────

    function test_ProposeRevertsWhenBelowThreshold() public {
        address poorAccount = makeAddr("poor");
        vm.prank(poorAccount);
        vm.expectRevert();
        gov.propose(new address[](1), new uint256[](1), new bytes[](1), "no power");
    }

    // ─── Helpers ──────────────────────────────────────────────────────────────

    function _lockAndDelegate(address account, uint256 amount, address delegatee) internal {
        vm.startPrank(account);
        din.approve(address(stDIN), amount);
        stDIN.lock(amount);
        stDIN.delegate(delegatee);
        vm.stopPrank();
    }
}
