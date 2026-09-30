// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test, console} from "forge-std/Test.sol";
import {Upgrades} from "@openzeppelin/foundry-upgrades/Upgrades.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinFairLaunchDistributor} from "../src/DinFairLaunchDistributor.sol";

// ─── Shared fixture ───────────────────────────────────────────────────────────

/// @dev Sets up a 3-leaf Merkle tree, funds the distributor, and opens claims.
///      All test contracts inherit from this base to reuse the fixture.
abstract contract FLDFixture is Test {
    DinToken            internal dinToken;
    DinFairLaunchDistributor internal fld;

    address internal owner = address(0xABCD);
    address internal alice = address(0x1111);
    address internal bob   = address(0x2222);
    address internal carol = address(0x3333);

    uint256 internal constant ALICE_AMOUNT = 1_000e18;
    uint256 internal constant BOB_AMOUNT   = 2_000e18;
    uint256 internal constant CAROL_AMOUNT = 3_000e18;
    uint256 internal constant TOTAL        = ALICE_AMOUNT + BOB_AMOUNT + CAROL_AMOUNT;

    uint64 internal constant CLIFF   = 90 days;
    uint64 internal constant VESTING = 365 days;

    // Leaf indices
    uint256 internal constant IDX_ALICE = 0;
    uint256 internal constant IDX_BOB   = 1;
    uint256 internal constant IDX_CAROL = 2;

    bytes32 internal merkleRoot;
    bytes32[] internal proofAlice;
    bytes32[] internal proofBob;
    bytes32[] internal proofCarol;

    function setUp() public virtual {
        // 1. DinToken — proxy; coordinator wired to address(this) for direct minting
        address tokenProxy = Upgrades.deployTransparentProxy(
            "DinToken.sol:DinToken",
            address(this),
            abi.encodeCall(DinToken.initialize, ())
        );
        dinToken = DinToken(tokenProxy);
        dinToken.setCoordinator(address(this));
        dinToken.mint(owner, TOTAL);

        // 2. DinFairLaunchDistributor proxy
        address fldProxy = Upgrades.deployTransparentProxy(
            "DinFairLaunchDistributor.sol:DinFairLaunchDistributor",
            address(this),
            abi.encodeCall(
                DinFairLaunchDistributor.initialize,
                (tokenProxy, owner, CLIFF, VESTING)
            )
        );
        fld = DinFairLaunchDistributor(fldProxy);

        // 3. Build 3-leaf Merkle tree
        //    Leaf = keccak256(bytes.concat(keccak256(abi.encode(index, addr, amount))))
        bytes32 leaf0 = _leaf(IDX_ALICE, alice, ALICE_AMOUNT);
        bytes32 leaf1 = _leaf(IDX_BOB,   bob,   BOB_AMOUNT);
        bytes32 leaf2 = _leaf(IDX_CAROL, carol, CAROL_AMOUNT);

        bytes32 node01 = _hashPair(leaf0, leaf1);
        merkleRoot     = _hashPair(node01, leaf2);

        // Proofs: Alice and Bob each need [sibling_leaf, leaf2]; Carol needs [node01]
        proofAlice = new bytes32[](2);
        proofAlice[0] = leaf1;
        proofAlice[1] = leaf2;

        proofBob = new bytes32[](2);
        proofBob[0] = leaf0;
        proofBob[1] = leaf2;

        proofCarol = new bytes32[](1);
        proofCarol[0] = node01;
    }

    function _leaf(uint256 index, address account, uint256 amount)
        internal pure returns (bytes32)
    {
        return keccak256(bytes.concat(keccak256(abi.encode(index, account, amount))));
    }

    function _hashPair(bytes32 a, bytes32 b) internal pure returns (bytes32) {
        return a < b
            ? keccak256(abi.encodePacked(a, b))
            : keccak256(abi.encodePacked(b, a));
    }

    function _openClaims() internal {
        vm.startPrank(owner);
        dinToken.approve(address(fld), TOTAL);
        fld.deposit(TOTAL);
        fld.setRoot(merkleRoot);
        fld.openClaims();
        vm.stopPrank();
    }
}

// ─── §1  Initialisation ───────────────────────────────────────────────────────

contract InitTest is FLDFixture {
    function test_initialize_setsState() public view {
        assertEq(address(fld.dinToken()),    address(dinToken));
        assertEq(fld.owner(),                owner);
        assertEq(fld.cliffDuration(),        CLIFF);
        assertEq(fld.vestingDuration(),      VESTING);
        assertEq(fld.claimsOpen(),           false);
        assertEq(fld.vestingStart(),         0);
        assertEq(fld.totalFunded(),          0);
        assertEq(fld.totalClaimedPrincipal(), 0);
    }

    function test_initialize_reverts_zeroToken() public {
        DinFairLaunchDistributor impl = new DinFairLaunchDistributor();
        vm.expectRevert(DinFairLaunchDistributor.InvalidAddress.selector);
        new _ProxyHelper(address(impl), address(this),
            abi.encodeCall(DinFairLaunchDistributor.initialize,
                (address(0), owner, CLIFF, VESTING)));
    }

    function test_initialize_reverts_zeroAdmin() public {
        DinFairLaunchDistributor impl = new DinFairLaunchDistributor();
        vm.expectRevert(DinFairLaunchDistributor.InvalidAddress.selector);
        new _ProxyHelper(address(impl), address(this),
            abi.encodeCall(DinFairLaunchDistributor.initialize,
                (address(dinToken), address(0), CLIFF, VESTING)));
    }

    function test_initialize_reverts_vestingZero() public {
        DinFairLaunchDistributor impl = new DinFairLaunchDistributor();
        vm.expectRevert(DinFairLaunchDistributor.InvalidDuration.selector);
        new _ProxyHelper(address(impl), address(this),
            abi.encodeCall(DinFairLaunchDistributor.initialize,
                (address(dinToken), owner, 0, 0)));
    }

    function test_initialize_reverts_cliffExceedsVesting() public {
        DinFairLaunchDistributor impl = new DinFairLaunchDistributor();
        vm.expectRevert(DinFairLaunchDistributor.InvalidDuration.selector);
        new _ProxyHelper(address(impl), address(this),
            abi.encodeCall(DinFairLaunchDistributor.initialize,
                (address(dinToken), owner, 365 days, 90 days)));
    }
}

// ─── §2  Deposit & root management ───────────────────────────────────────────

contract DepositAndRootTest is FLDFixture {
    function test_deposit_increasesTotalFunded() public {
        vm.startPrank(owner);
        dinToken.approve(address(fld), TOTAL);
        fld.deposit(TOTAL);
        vm.stopPrank();
        assertEq(fld.totalFunded(), TOTAL);
        assertEq(dinToken.balanceOf(address(fld)), TOTAL);
    }

    function test_setRoot_storesRoot() public {
        vm.prank(owner);
        fld.setRoot(merkleRoot);
        assertEq(fld.merkleRoot(), merkleRoot);
    }

    function test_setRoot_reverts_afterOpenClaims() public {
        _openClaims();
        vm.prank(owner);
        vm.expectRevert(DinFairLaunchDistributor.RootAlreadyFrozen.selector);
        fld.setRoot(bytes32(0));
    }

    function test_openClaims_reverts_noRoot() public {
        vm.prank(owner);
        vm.expectRevert(DinFairLaunchDistributor.NoRootSet.selector);
        fld.openClaims();
    }

    function test_openClaims_reverts_alreadyOpen() public {
        _openClaims();
        vm.prank(owner);
        vm.expectRevert(DinFairLaunchDistributor.ClaimsAlreadyOpen.selector);
        fld.openClaims();
    }

    function test_openClaims_setsState() public {
        uint256 t0 = block.timestamp;
        _openClaims();
        assertTrue(fld.claimsOpen());
        assertEq(fld.vestingStart(), t0);
    }
}

// ─── §3  Claim ────────────────────────────────────────────────────────────────

contract ClaimTest is FLDFixture {
    function setUp() public override {
        super.setUp();
        _openClaims();
    }

    function test_claim_preCliff_zeroRelease() public {
        vm.prank(alice);
        fld.claim(IDX_ALICE, ALICE_AMOUNT, proofAlice);

        (uint256 total, uint256 claimed) = fld.positions(alice);
        assertEq(total,   ALICE_AMOUNT);
        assertEq(claimed, 0);
        assertEq(dinToken.balanceOf(alice), 0);
    }

    function test_claim_postCliff_nonzeroRelease() public {
        vm.warp(block.timestamp + CLIFF + 1);

        vm.prank(alice);
        fld.claim(IDX_ALICE, ALICE_AMOUNT, proofAlice);

        uint256 bal = dinToken.balanceOf(alice);
        assertTrue(bal > 0, "expected nonzero initial release post-cliff");

        (, uint256 claimed) = fld.positions(alice);
        assertEq(claimed, bal);
    }

    function test_claim_registersPosition() public {
        vm.prank(alice);
        fld.claim(IDX_ALICE, ALICE_AMOUNT, proofAlice);

        (uint256 total,) = fld.positions(alice);
        assertEq(total, ALICE_AMOUNT);
        assertTrue(fld.hasClaimed(alice));
        assertEq(fld.totalClaimedPrincipal(), ALICE_AMOUNT);
    }

    function test_claim_reverts_alreadyClaimed() public {
        vm.prank(alice);
        fld.claim(IDX_ALICE, ALICE_AMOUNT, proofAlice);

        vm.prank(alice);
        vm.expectRevert(DinFairLaunchDistributor.AlreadyClaimed.selector);
        fld.claim(IDX_ALICE, ALICE_AMOUNT, proofAlice);
    }

    function test_claim_reverts_invalidProof() public {
        vm.prank(alice);
        vm.expectRevert(DinFairLaunchDistributor.InvalidProof.selector);
        fld.claim(IDX_ALICE, BOB_AMOUNT, proofAlice); // wrong amount
    }

    function test_claim_reverts_wrongAddress() public {
        vm.prank(bob); // uses alice's proof but from bob's address
        vm.expectRevert(DinFairLaunchDistributor.InvalidProof.selector);
        fld.claim(IDX_ALICE, ALICE_AMOUNT, proofAlice);
    }

    function test_claim_reverts_claimsNotOpen() public {
        // Deploy a fresh distributor without calling openClaims
        address newFldProxy = Upgrades.deployTransparentProxy(
            "DinFairLaunchDistributor.sol:DinFairLaunchDistributor",
            address(this),
            abi.encodeCall(
                DinFairLaunchDistributor.initialize,
                (address(dinToken), owner, CLIFF, VESTING)
            )
        );
        DinFairLaunchDistributor newFld = DinFairLaunchDistributor(newFldProxy);

        vm.prank(alice);
        vm.expectRevert(DinFairLaunchDistributor.ClaimsNotOpen.selector);
        newFld.claim(IDX_ALICE, ALICE_AMOUNT, proofAlice);
    }

    function test_allThreeClaimants_validProofs() public {
        vm.prank(alice);
        fld.claim(IDX_ALICE, ALICE_AMOUNT, proofAlice);

        vm.prank(bob);
        fld.claim(IDX_BOB, BOB_AMOUNT, proofBob);

        vm.prank(carol);
        fld.claim(IDX_CAROL, CAROL_AMOUNT, proofCarol);

        assertEq(fld.totalClaimedPrincipal(), TOTAL);
    }
}

// ─── §4  Release ─────────────────────────────────────────────────────────────

contract ReleaseTest is FLDFixture {
    function setUp() public override {
        super.setUp();
        _openClaims();
        vm.prank(alice);
        fld.claim(IDX_ALICE, ALICE_AMOUNT, proofAlice);
    }

    function test_release_reverts_preCliff() public {
        vm.prank(alice);
        vm.expectRevert(DinFairLaunchDistributor.NothingToRelease.selector);
        fld.release();
    }

    function test_release_postCliff() public {
        vm.warp(block.timestamp + CLIFF + 1);

        uint256 vested = fld.vestedAmount(alice);
        assertTrue(vested > 0);

        vm.prank(alice);
        fld.release();

        assertEq(dinToken.balanceOf(alice), vested);
        (, uint256 claimed) = fld.positions(alice);
        assertEq(claimed, vested);
    }

    function test_release_reverts_nothingNewVested() public {
        vm.warp(block.timestamp + CLIFF + 1);
        vm.prank(alice);
        fld.release(); // first release

        // Warp only 1 second more — tiny amount may vest but let's test the
        // edge case by warping exactly to the same second (nothing new)
        vm.prank(alice);
        vm.expectRevert(DinFairLaunchDistributor.NothingToRelease.selector);
        fld.release();
    }

    function test_release_fullVestingAtEnd() public {
        vm.warp(block.timestamp + VESTING);

        vm.prank(alice);
        fld.release();

        assertEq(dinToken.balanceOf(alice), ALICE_AMOUNT);
        (, uint256 claimed) = fld.positions(alice);
        assertEq(claimed, ALICE_AMOUNT);
    }

    function test_release_afterEnd_clampedToTotal() public {
        vm.warp(block.timestamp + VESTING + 100 days);
        assertEq(fld.vestedAmount(alice), ALICE_AMOUNT);

        vm.prank(alice);
        fld.release();
        assertEq(dinToken.balanceOf(alice), ALICE_AMOUNT);
    }
}

// ─── §5  Sweep ───────────────────────────────────────────────────────────────

contract SweepTest is FLDFixture {
    function setUp() public override {
        super.setUp();
        _openClaims();
    }

    function test_sweepUnclaimed_reverts_tooEarly() public {
        vm.prank(owner);
        vm.expectRevert(DinFairLaunchDistributor.SweepTooEarly.selector);
        fld.sweepUnclaimed(owner);
    }

    function test_sweepUnclaimed_afterGrace_allUnclaimed() public {
        // Nobody claimed — entire TOTAL is sweepable
        vm.warp(block.timestamp + VESTING + fld.SWEEP_GRACE_PERIOD() + 1);

        uint256 ownerBefore = dinToken.balanceOf(owner);
        vm.prank(owner);
        fld.sweepUnclaimed(owner);

        assertEq(dinToken.balanceOf(owner), ownerBefore + TOTAL);
        assertEq(fld.totalFunded(), 0);
    }

    function test_sweepUnclaimed_partialClaims() public {
        // Only Alice claims; Bob and Carol allocations are sweepable
        vm.prank(alice);
        fld.claim(IDX_ALICE, ALICE_AMOUNT, proofAlice);

        vm.warp(block.timestamp + VESTING + fld.SWEEP_GRACE_PERIOD() + 1);

        uint256 expectedSweep = BOB_AMOUNT + CAROL_AMOUNT;
        uint256 ownerBefore = dinToken.balanceOf(owner);

        vm.prank(owner);
        fld.sweepUnclaimed(owner);

        assertEq(dinToken.balanceOf(owner), ownerBefore + expectedSweep);
        // Alice's remaining unvested tokens (claimed principal - released so far) stay in the contract
        uint256 aliceReleased = dinToken.balanceOf(alice);
        assertEq(dinToken.balanceOf(address(fld)), ALICE_AMOUNT - aliceReleased);
    }

    function test_sweepUnclaimed_reverts_claimsNotOpen() public {
        // Deploy fresh distributor with no openClaims
        address newFldProxy = Upgrades.deployTransparentProxy(
            "DinFairLaunchDistributor.sol:DinFairLaunchDistributor",
            address(this),
            abi.encodeCall(
                DinFairLaunchDistributor.initialize,
                (address(dinToken), owner, CLIFF, VESTING)
            )
        );
        DinFairLaunchDistributor newFld = DinFairLaunchDistributor(newFldProxy);

        vm.warp(block.timestamp + VESTING + newFld.SWEEP_GRACE_PERIOD() + 1);
        vm.prank(owner);
        vm.expectRevert(DinFairLaunchDistributor.ClaimsNotOpen.selector);
        newFld.sweepUnclaimed(owner);
    }
}

// ─── §6  vestedAmount ────────────────────────────────────────────────────────

contract VestedAmountTest is FLDFixture {
    function setUp() public override {
        super.setUp();
        _openClaims();
        vm.prank(alice);
        fld.claim(IDX_ALICE, ALICE_AMOUNT, proofAlice);
    }

    function test_vestedAmount_preCliff_isZero() public view {
        assertEq(fld.vestedAmount(alice), 0);
    }

    function test_vestedAmount_atCliff() public {
        vm.warp(block.timestamp + CLIFF);
        uint256 expected = ALICE_AMOUNT * CLIFF / VESTING;
        assertEq(fld.vestedAmount(alice), expected);
    }

    function test_vestedAmount_atFullVesting() public {
        vm.warp(block.timestamp + VESTING);
        assertEq(fld.vestedAmount(alice), ALICE_AMOUNT);
    }

    function test_vestedAmount_pastVestingEnd() public {
        vm.warp(block.timestamp + VESTING + 999 days);
        assertEq(fld.vestedAmount(alice), ALICE_AMOUNT);
    }

    function test_vestedAmount_noPosition_isZero() public view {
        assertEq(fld.vestedAmount(address(0xDEAD)), 0);
    }

    /// @dev Fuzz: vestedAmount never exceeds the position's total allocation.
    function testFuzz_vestedAmount_neverExceedsTotal(uint32 warpSeconds) public {
        vm.warp(block.timestamp + warpSeconds);
        uint256 vested = fld.vestedAmount(alice);
        assertLe(vested, ALICE_AMOUNT);
    }
}

// ─── §7  ExceedsFunding guard ─────────────────────────────────────────────────

contract FundingGuardTest is FLDFixture {
    function test_claim_reverts_exceedsFunding() public {
        // Deposit only half the total
        vm.startPrank(owner);
        dinToken.approve(address(fld), ALICE_AMOUNT);
        fld.deposit(ALICE_AMOUNT);
        fld.setRoot(merkleRoot);
        fld.openClaims();
        vm.stopPrank();

        // Alice claims fine (ALICE_AMOUNT == totalFunded)
        vm.prank(alice);
        fld.claim(IDX_ALICE, ALICE_AMOUNT, proofAlice);

        // Bob's claim would push totalClaimedPrincipal over totalFunded
        vm.prank(bob);
        vm.expectRevert(DinFairLaunchDistributor.ExceedsFunding.selector);
        fld.claim(IDX_BOB, BOB_AMOUNT, proofBob);
    }
}

// ─── Helper ───────────────────────────────────────────────────────────────────

/// @dev Thin wrapper so we can use new() with expectRevert for proxy init failures.
contract _ProxyHelper {
    constructor(address impl, address admin, bytes memory data) {
        new _TinyProxy(impl, admin, data);
    }
}

import {TransparentUpgradeableProxy} from
    "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

contract _TinyProxy is TransparentUpgradeableProxy {
    constructor(address impl, address admin, bytes memory data)
        TransparentUpgradeableProxy(impl, admin, data)
    {}
}
