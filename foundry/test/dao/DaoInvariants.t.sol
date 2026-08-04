// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "forge-std/Test.sol";
import "../../src/dao/DinGovernanceStaking.sol";
import "../../src/dao/DinMultisig.sol";
import "../../src/dao/DinTimelock.sol";
import "../../src/dao/DinGuardian.sol";
import "../../src/dao/interfaces/IDinMultisig.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

// ─────────────────────────────────────────────────────────────────────────────
// Shared mock DIN token
// ─────────────────────────────────────────────────────────────────────────────

contract InvMockDIN is ERC20 {
    constructor() ERC20("DIN Token", "DIN") {}
    function mint(address to, uint256 amount) external { _mint(to, amount); }
}

// ─────────────────────────────────────────────────────────────────────────────
// I. Staking invariants
//    Invariant A: totalSupply of stDIN always equals DIN held by the contract
//    Invariant B: total delegated voting power never exceeds stDIN totalSupply
// ─────────────────────────────────────────────────────────────────────────────

/// @dev Handler called by the Foundry fuzzer for staking invariant tests.
///      Maintains a list of up to 4 actors and ghost variables tracking the
///      expected locked amount so invariant assertions have a ground truth.
contract StakingHandler is Test {
    InvMockDIN           internal din;
    DinGovernanceStaking internal stDIN;

    address[4] internal actors;
    uint256 public  ghostTotalLocked;

    constructor(InvMockDIN din_, DinGovernanceStaking stDIN_) {
        din   = din_;
        stDIN = stDIN_;

        actors[0] = makeAddr("inv_alice");
        actors[1] = makeAddr("inv_bob");
        actors[2] = makeAddr("inv_carol");
        actors[3] = makeAddr("inv_dave");

        // Pre-fund every actor with 10 000 DIN
        for (uint256 i; i < 4; ++i) {
            din_.mint(actors[i], 10_000e18);
            vm.prank(actors[i]);
            din_.approve(address(stDIN_), type(uint256).max);
        }
    }

    // ─── Actions ──────────────────────────────────────────────────────────────

    /// @dev Lock a bounded amount of DIN for a random actor.
    function lock(uint256 actorSeed, uint256 amount) external {
        address actor = actors[actorSeed % 4];
        uint256 cap   = din.balanceOf(actor);
        if (cap == 0) return;
        amount = bound(amount, 1, cap);

        vm.prank(actor);
        stDIN.lock(amount);
        ghostTotalLocked += amount;
    }

    /// @dev Unlock a bounded amount of stDIN for a random actor.
    function unlock(uint256 actorSeed, uint256 amount) external {
        address actor = actors[actorSeed % 4];
        uint256 cap   = stDIN.balanceOf(actor);
        if (cap == 0) return;
        amount = bound(amount, 1, cap);

        vm.prank(actor);
        stDIN.unlock(amount);
        ghostTotalLocked -= amount;
    }

    /// @dev Delegate voting power between random actors to exercise checkpoints.
    function delegate(uint256 actorSeed, uint256 delegateeSeed) external {
        address actor     = actors[actorSeed   % 4];
        address delegatee = actors[delegateeSeed % 4];
        vm.prank(actor);
        stDIN.delegate(delegatee);
    }
}

contract StakingInvariantTest is Test {
    InvMockDIN           internal din;
    DinGovernanceStaking internal stDIN;
    StakingHandler       internal handler;

    function setUp() public {
        din    = new InvMockDIN();
        stDIN  = new DinGovernanceStaking(address(din));
        handler = new StakingHandler(din, stDIN);

        targetContract(address(handler));
    }

    /// @dev Invariant A: stDIN total supply equals DIN locked in the contract.
    ///      Any discrepancy indicates a mint or burn without a matching transfer,
    ///      which would violate 1:1 conservation.
    function invariant_TotalSupplyEqualsLockedDIN() public view {
        assertEq(
            stDIN.totalSupply(),
            din.balanceOf(address(stDIN)),
            "stDIN supply != DIN balance"
        );
    }

    /// @dev Invariant B: ghost variable tracks every lock/unlock; it must
    ///      match both the contract's totalLocked view and the stDIN supply.
    function invariant_GhostLockedMatchesContract() public view {
        assertEq(
            handler.ghostTotalLocked(),
            stDIN.totalLocked(),
            "ghost != totalLocked"
        );
        assertEq(
            stDIN.totalLocked(),
            stDIN.totalSupply(),
            "totalLocked != totalSupply"
        );
    }

    /// @dev Invariant C: total votes delegated to all actors never exceeds
    ///      the stDIN total supply. Voting power cannot be conjured.
    function invariant_TotalVotesNeverExceedSupply() public view {
        address[4] memory actors_ = [
            makeAddr("inv_alice"),
            makeAddr("inv_bob"),
            makeAddr("inv_carol"),
            makeAddr("inv_dave")
        ];
        uint256 totalVotes;
        for (uint256 i; i < 4; ++i) {
            totalVotes += stDIN.getVotes(actors_[i]);
        }
        assertLe(totalVotes, stDIN.totalSupply(), "total votes > supply");
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// II. Timelock invariant / fuzz
//     Nothing can execute before minDelay has elapsed from scheduling.
// ─────────────────────────────────────────────────────────────────────────────

/// @dev Minimal call target used by timelock tests.
contract InvTimelockTarget {
    uint256 public value;
    function setValue(uint256 v) external { value = v; }
}

contract TimelockFuzzTest is Test {
    DinTimelock         internal tl;
    InvTimelockTarget   internal target;

    address internal proposer_ = makeAddr("tl_proposer");

    uint256 internal constant MIN_DELAY = 1 days;

    function setUp() public {
        address[] memory proposers = new address[](1);
        proposers[0] = proposer_;
        address[] memory executors = new address[](1);
        executors[0] = address(0);

        tl     = new DinTimelock(MIN_DELAY, proposers, executors, address(0));
        target = new InvTimelockTarget();
    }

    /// @dev Fuzz: for any elapsed time strictly less than MIN_DELAY, execution
    ///      must revert. The fuzzer explores the entire [0, MIN_DELAY) range.
    function testFuzz_CannotExecuteBeforeMinDelay(uint256 elapsed) public {
        elapsed = bound(elapsed, 0, MIN_DELAY - 1);

        bytes memory data = abi.encodeCall(InvTimelockTarget.setValue, (1));
        bytes32 salt      = bytes32(uint256(elapsed)); // unique salt per run

        vm.prank(proposer_);
        tl.schedule(address(target), 0, data, bytes32(0), salt, MIN_DELAY);

        vm.warp(block.timestamp + elapsed);

        vm.expectRevert();
        tl.execute(address(target), 0, data, bytes32(0), salt);
    }

    /// @dev Fuzz: for any elapsed time >= MIN_DELAY, execution must succeed.
    function testFuzz_AlwaysExecutesAfterDelay(uint256 extra) public {
        extra = bound(extra, 0, 365 days);

        bytes memory data = abi.encodeCall(InvTimelockTarget.setValue, (42));
        bytes32 salt      = bytes32(extra);

        vm.prank(proposer_);
        tl.schedule(address(target), 0, data, bytes32(0), salt, MIN_DELAY);

        vm.warp(block.timestamp + MIN_DELAY + extra);
        tl.execute(address(target), 0, data, bytes32(0), salt);

        assertEq(target.value(), 42);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// III. Multisig fuzz
//      Confirm/revoke sequences never produce a count outside [0, signerCount].
//      A proposal cannot reach Executable with fewer confirms than its threshold.
// ─────────────────────────────────────────────────────────────────────────────

/// @dev Minimal call target for multisig fuzz tests.
contract InvMultisigTarget {
    uint256 public value;
    function setValue(uint256 v) external { value = v; }
}

contract MultisigFuzzTest is Test {
    DinMultisig        internal ms;
    InvMultisigTarget  internal msTarget;

    address internal s0 = makeAddr("ms_s0");
    address internal s1 = makeAddr("ms_s1");
    address internal s2 = makeAddr("ms_s2");

    // Thresholds: Parameter=2, Operational=2, Treasury=3, Upgrade=3
    uint256[4] internal thresholds = [uint256(2), 2, 3, 3];

    function setUp() public {
        address[] memory signers_ = new address[](3);
        signers_[0] = s0; signers_[1] = s1; signers_[2] = s2;
        ms       = new DinMultisig(signers_, thresholds);
        msTarget = new InvMultisigTarget();
    }

    /// @dev Fuzz: confirm count after a random sequence of confirms and revokes
    ///      from distinct signers must always be in [0, 3].
    function testFuzz_ConfirmCountBounded(
        bool confirmS0,
        bool confirmS1,
        bool confirmS2,
        bool revokeS0,
        bool revokeS1
    ) public {
        bytes memory data = abi.encodeCall(InvMultisigTarget.setValue, (1));
        vm.prank(s0);
        uint256 id = ms.propose(address(msTarget), data, 0, ProposalCategory.Parameter);

        if (confirmS0) { vm.prank(s0); ms.confirm(id); }
        if (confirmS1) { vm.prank(s1); ms.confirm(id); }
        if (confirmS2) { vm.prank(s2); ms.confirm(id); }

        // Revoke only if previously confirmed to avoid revert on NotConfirmed
        if (revokeS0 && confirmS0) {
            (, , , , ProposalState st, , ) = ms.getProposal(id);
            if (st == ProposalState.Open || st == ProposalState.Executable) {
                vm.prank(s0); ms.revoke(id);
            }
        }
        if (revokeS1 && confirmS1) {
            (, , , , ProposalState st, , ) = ms.getProposal(id);
            if (st == ProposalState.Open || st == ProposalState.Executable) {
                vm.prank(s1); ms.revoke(id);
            }
        }

        (, , , , , uint256 count, ) = ms.getProposal(id);
        assertLe(count, 3, "confirm count exceeds signer count");
    }

    /// @dev Fuzz: a Parameter proposal (threshold=2) can only become Executable
    ///      once at least 2 signers have confirmed without revoking.
    function testFuzz_ExecutableRequiresThreshold(bool s1Confirms, bool s0Revokes) public {
        bytes memory data = abi.encodeCall(InvMultisigTarget.setValue, (7));
        vm.prank(s0);
        uint256 id = ms.propose(address(msTarget), data, 0, ProposalCategory.Parameter);

        vm.prank(s0); ms.confirm(id);

        if (s0Revokes) {
            vm.prank(s0); ms.revoke(id);
        }

        if (s1Confirms) {
            vm.prank(s1); ms.confirm(id);
        }

        (, , , , ProposalState state, uint256 count, ) = ms.getProposal(id);

        if (state == ProposalState.Executable) {
            assertGe(count, 2, "Executable with fewer than threshold confirms");
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// IV. Guardian fuzz
//     expireAction always reverts before the ratification window elapses.
//     ratifyAction always reverts after the action has already been ratified.
// ─────────────────────────────────────────────────────────────────────────────

contract GuardianFuzz_Target {
    bool public flag;
    function setFlag()   external { flag = true;  }
    function clearFlag() external { flag = false; }
}

contract GuardianFuzzTest is Test {
    DinGuardian       internal grd;
    GuardianFuzz_Target internal gTarget;

    address internal multisig_ = makeAddr("grd_multisig");
    address internal governor_ = makeAddr("grd_governor");

    uint256 internal constant WINDOW = 7 days;

    function setUp() public {
        grd     = new DinGuardian(multisig_, governor_, WINDOW);
        gTarget = new GuardianFuzz_Target();
    }

    /// @dev Fuzz: expireAction always reverts for any elapsed time before the
    ///      ratification window closes, regardless of how close to the boundary.
    function testFuzz_CannotExpireBeforeWindow(uint256 elapsed) public {
        elapsed = bound(elapsed, 0, WINDOW - 1);

        bytes memory data     = abi.encodeCall(GuardianFuzz_Target.setFlag,   ());
        bytes memory reversal = abi.encodeCall(GuardianFuzz_Target.clearFlag, ());

        vm.prank(multisig_);
        uint256 id = grd.performAction(address(gTarget), data, reversal, "fuzz");

        vm.warp(block.timestamp + elapsed);
        vm.expectRevert(DG_WindowNotElapsed.selector);
        grd.expireAction(id);
    }

    /// @dev Fuzz: for any elapsed time >= WINDOW, expireAction dispatches the
    ///      reversal and the target state is restored.
    function testFuzz_AlwaysExpiresAfterWindow(uint256 extra) public {
        extra = bound(extra, 0, 365 days);

        bytes memory data     = abi.encodeCall(GuardianFuzz_Target.setFlag,   ());
        bytes memory reversal = abi.encodeCall(GuardianFuzz_Target.clearFlag, ());

        vm.prank(multisig_);
        uint256 id = grd.performAction(address(gTarget), data, reversal, "fuzz");

        assertTrue(gTarget.flag()); // action applied

        vm.warp(block.timestamp + WINDOW + extra);
        grd.expireAction(id);

        assertFalse(gTarget.flag()); // reversal applied
    }

    /// @dev Fuzz: double-ratify always reverts — an action cannot be ratified twice.
    function testFuzz_CannotRatifyTwice(uint256 elapsed) public {
        elapsed = bound(elapsed, 0, WINDOW - 1);

        bytes memory data = abi.encodeCall(GuardianFuzz_Target.setFlag, ());

        vm.prank(multisig_);
        uint256 id = grd.performAction(address(gTarget), data, "", "fuzz");

        vm.warp(block.timestamp + elapsed);
        vm.prank(governor_); grd.ratifyAction(id);

        vm.prank(governor_);
        vm.expectRevert(DG_ActionNotActive.selector);
        grd.ratifyAction(id);
    }
}
