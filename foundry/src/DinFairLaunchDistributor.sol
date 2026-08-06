// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";
import "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";

/// @title DIN Fair-Launch Distributor
/// @notice Merkle-drop distributor with cliff + linear vesting for the DIN fair-launch
///         airdrop (issue #75). One contract holds all recipient positions — no per-user
///         VestingWallet deployments. Deployed behind a Transparent Proxy matching the
///         existing platform-contract pattern.
///
/// @dev    Lifecycle:
///           1. Owner calls deposit() to fund the contract from treasury.
///           2. Owner calls setRoot() with the Merkle root of the eligibility snapshot.
///              (Can be called multiple times to correct the snapshot pre-launch.)
///           3. Owner calls openClaims() — one-shot, freezes the root and starts the
///              vesting clock (vestingStart = block.timestamp).
///           4. Recipients call claim() with their Merkle proof to register their position
///              and receive any already-vested amount (0 if still in the cliff).
///           5. Recipients call release() at any time to collect newly vested tokens.
///           6. After vestingStart + vestingDuration + SWEEP_GRACE_PERIOD, owner can
///              sweep any allocations that were never claimed at all back to treasury.
///
///         Admin note: `treasuryAdmin_` is the owner (Ownable). For the testnet dry-run
///         an EOA is acceptable. Once a Gnosis Safe scoped to treasury management exists
///         (per DD-3 / DESIGN_DECISIONS.md), re-deploy or transfer ownership to it before
///         calling openClaims() on any non-test environment.
///
///         Cliff/vesting durations are set at initialisation as seconds. Actual testnet
///         values (e.g. "3-month cliff, 12-month total") must be confirmed by
///         Umer/Abraham before openClaims() is called for real.
///
///         Sweep grace period is a 30-day constant after full vesting elapses — see
///         SWEEP_GRACE_PERIOD. Treat this as a placeholder; adjust before mainnet.
contract DinFairLaunchDistributor is
    Initializable,
    OwnableUpgradeable,
    ReentrancyGuardTransient
{
    using SafeERC20 for IERC20;

    // ─── Errors ───────────────────────────────────────────────────────────────

    error InvalidAddress();
    error InvalidDuration();
    error ClaimsAlreadyOpen();
    error ClaimsNotOpen();
    error RootAlreadyFrozen();
    error NoRootSet();
    error AlreadyClaimed();
    error InvalidProof();
    error NothingToRelease();
    error SweepTooEarly();
    error ExceedsFunding();

    // ─── Constants ────────────────────────────────────────────────────────────

    /// @notice Grace period after full vesting elapses before unclaimed allocations
    ///         can be swept. Placeholder — confirm before mainnet.
    uint256 public constant SWEEP_GRACE_PERIOD = 30 days;

    // ─── State ────────────────────────────────────────────────────────────────

    IERC20 public dinToken;
    bytes32 public merkleRoot;

    // Packed slot: 1 + 8 + 8 + 8 = 25 bytes
    bool    public claimsOpen;
    uint64  public cliffDuration;   // seconds
    uint64  public vestingDuration; // seconds (total, including cliff)
    uint64  public vestingStart;    // set by openClaims(); vesting clock starts here

    uint256 public totalFunded;
    uint256 public totalClaimedPrincipal; // sum of totalAmount for each address that claimed

    struct VestingPosition {
        uint256 total;   // full allocation
        uint256 claimed; // tokens released so far
    }

    mapping(address => VestingPosition) public positions;
    mapping(address => bool)            public hasClaimed;

    // Reserved for future state variables (50 - 7 current slots).
    uint256[43] private __gap;

    // ─── Events ───────────────────────────────────────────────────────────────

    event Deposited(uint256 amount);
    event RootSet(bytes32 root);
    event ClaimsOpened(uint64 vestingStart);
    event Claimed(address indexed account, uint256 totalAllocation, uint256 initialRelease);
    event Released(address indexed account, uint256 amount);
    event UnclaimedSwept(address indexed to, uint256 amount);

    // ─── Constructor ──────────────────────────────────────────────────────────

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    // ─── Initialiser ──────────────────────────────────────────────────────────

    /// @notice Initialises the proxy.
    /// @param dinToken_        Address of the DinToken proxy.
    /// @param treasuryAdmin_   Initial owner (treasury admin). Use an EOA for testnet;
    ///                         point at a Gnosis Safe once one exists (see contract NatSpec).
    /// @param cliffDuration_   Seconds after vestingStart before any tokens are released.
    ///                         Can be 0 for no cliff. Must be ≤ vestingDuration_.
    /// @param vestingDuration_ Total vesting window in seconds from vestingStart.
    ///                         Must be > 0. Linear release runs from cliffDuration_ to
    ///                         vestingDuration_. Confirm actual values with Umer/Abraham
    ///                         before openClaims() is called on any non-test environment.
    function initialize(
        address dinToken_,
        address treasuryAdmin_,
        uint64  cliffDuration_,
        uint64  vestingDuration_
    ) external initializer {
        if (dinToken_ == address(0))      revert InvalidAddress();
        if (treasuryAdmin_ == address(0)) revert InvalidAddress();
        if (vestingDuration_ == 0)        revert InvalidDuration();
        if (cliffDuration_ > vestingDuration_) revert InvalidDuration();

        __Ownable_init(treasuryAdmin_);
        dinToken       = IERC20(dinToken_);
        cliffDuration  = cliffDuration_;
        vestingDuration = vestingDuration_;
    }

    // ─── Owner actions ────────────────────────────────────────────────────────

    /// @notice Transfers `amount` DIN from the treasury into this contract.
    /// @dev    Caller (owner) must pre-approve this contract for `amount`. Can be
    ///         called multiple times; each call adds to totalFunded. Permitted after
    ///         openClaims() so top-ups are possible, but the sweep invariant
    ///         (totalFunded - totalClaimedPrincipal) covers only the unfunded gap.
    /// @param amount DIN amount to pull in.
    function deposit(uint256 amount) external onlyOwner {
        totalFunded += amount;
        dinToken.safeTransferFrom(msg.sender, address(this), amount);
        emit Deposited(amount);
    }

    /// @notice Sets the Merkle root of the eligibility snapshot.
    /// @dev    Can be called multiple times before openClaims() to correct the snapshot.
    ///         Reverts once claims are open — the root is frozen from that point.
    /// @param root_ The Merkle root.
    function setRoot(bytes32 root_) external onlyOwner {
        if (claimsOpen) revert RootAlreadyFrozen();
        merkleRoot = root_;
        emit RootSet(root_);
    }

    /// @notice Freezes the Merkle root and starts the vesting clock.
    /// @dev    One-shot. After this call, setRoot() reverts and vestingStart is fixed.
    ///         Requires a root to have been set already.
    function openClaims() external onlyOwner {
        if (claimsOpen)        revert ClaimsAlreadyOpen();
        if (merkleRoot == 0)   revert NoRootSet();
        claimsOpen  = true;
        vestingStart = uint64(block.timestamp);
        emit ClaimsOpened(vestingStart);
    }

    /// @notice Sweeps never-claimed allocations back to `to` after the grace period.
    /// @dev    Only sweeps totalFunded - totalClaimedPrincipal — i.e., allocations
    ///         nobody ever called claim() for. Unvested-but-claimed positions are NOT
    ///         swept; those tokens remain in the contract for their rightful owners.
    ///         Callable only after vestingStart + vestingDuration + SWEEP_GRACE_PERIOD.
    /// @param to Destination for the swept tokens (e.g. treasury address).
    function sweepUnclaimed(address to) external onlyOwner {
        if (!claimsOpen) revert ClaimsNotOpen();
        if (to == address(0)) revert InvalidAddress();

        uint256 deadline = uint256(vestingStart) + vestingDuration + SWEEP_GRACE_PERIOD;
        if (block.timestamp < deadline) revert SweepTooEarly();

        uint256 sweepAmount = totalFunded - totalClaimedPrincipal;
        if (sweepAmount == 0) return;

        totalFunded -= sweepAmount;
        dinToken.safeTransfer(to, sweepAmount);
        emit UnclaimedSwept(to, sweepAmount);
    }

    // ─── Recipient actions ────────────────────────────────────────────────────

    /// @notice Registers the caller's allocation via a Merkle proof and immediately
    ///         releases any already-vested tokens (0 if still in the cliff period).
    /// @dev    Leaf encoding: keccak256(bytes.concat(keccak256(abi.encode(index, msg.sender, totalAmount))))
    ///         Standard double-hash avoids second-preimage attacks.
    ///         One call per address — calling twice reverts with AlreadyClaimed.
    /// @param index       The leaf index in the Merkle tree.
    /// @param totalAmount The caller's full allocation.
    /// @param proof       Merkle proof for this leaf.
    function claim(
        uint256          index,
        uint256          totalAmount,
        bytes32[] calldata proof
    ) external nonReentrant {
        if (!claimsOpen)         revert ClaimsNotOpen();
        if (hasClaimed[msg.sender]) revert AlreadyClaimed();

        bytes32 leaf = keccak256(
            bytes.concat(keccak256(abi.encode(index, msg.sender, totalAmount)))
        );
        if (!MerkleProof.verify(proof, merkleRoot, leaf)) revert InvalidProof();

        if (totalClaimedPrincipal + totalAmount > totalFunded) revert ExceedsFunding();

        hasClaimed[msg.sender]     = true;
        totalClaimedPrincipal     += totalAmount;
        positions[msg.sender]      = VestingPosition({total: totalAmount, claimed: 0});

        uint256 initialRelease = vestedAmount(msg.sender);
        if (initialRelease > 0) {
            positions[msg.sender].claimed = initialRelease;
            dinToken.safeTransfer(msg.sender, initialRelease);
        }

        emit Claimed(msg.sender, totalAmount, initialRelease);
    }

    /// @notice Releases all tokens vested since the last release (or claim).
    /// @dev    Callable any number of times. Reverts if nothing new has vested.
    function release() external nonReentrant {
        uint256 releasable = vestedAmount(msg.sender) - positions[msg.sender].claimed;
        if (releasable == 0) revert NothingToRelease();
        positions[msg.sender].claimed += releasable;
        dinToken.safeTransfer(msg.sender, releasable);
        emit Released(msg.sender, releasable);
    }

    // ─── Views ────────────────────────────────────────────────────────────────

    /// @notice Returns the total tokens vested for `account` as of now.
    /// @dev    Mirrors OZ VestingWallet cliff+linear math: 0 before the cliff,
    ///         total * elapsed / vestingDuration between cliff and vestingDuration,
    ///         full total at/after vestingDuration. Elapsed is measured from vestingStart.
    /// @param account Address to query.
    /// @return Cumulative vested amount (some may already have been released).
    function vestedAmount(address account) public view returns (uint256) {
        VestingPosition storage pos = positions[account];
        if (pos.total == 0 || vestingStart == 0) return 0;

        uint64 elapsed = uint64(block.timestamp) - vestingStart;
        if (elapsed < cliffDuration)  return 0;
        if (elapsed >= vestingDuration) return pos.total;

        return pos.total * elapsed / vestingDuration;
    }
}
