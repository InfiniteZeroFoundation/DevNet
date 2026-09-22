// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";

interface IDinCoordinator {
    function mintEmission(address to, uint256 amount) external;
}

interface IDINTaskAuditor {
    function depositRewards(uint256 gi, uint256 amount) external;
}

/// @title DIN Emission
/// @notice Per-GI protocol reward subsidy on a geometric decay schedule.
///         Emission decays by (decayBps/10000) per epoch, where one epoch is
///         epochLength completed GIs. After maxEpochs epochs the subsidy is zero —
///         the "final epoch" design: explicit retirement rather than an asymptotic
///         tail, consistent with DinCoordinator.faucetRetired semantics.
///
///         Minting goes through DinCoordinator.mintEmission(), which enforces
///         mintCap, totalMinted, and faucetRetired — emission cannot bypass
///         the supply-cap machinery.
///
///         Deployed behind a Transparent Proxy following the DinTreasury /
///         DinFairLaunchDistributor pattern.
contract DinEmission is Initializable, OwnableUpgradeable, ReentrancyGuardTransient {
    using SafeERC20 for IERC20;

    // ── Errors ────────────────────────────────────────────────────────────
    error InvalidAddress();
    error InvalidParams();
    error GIAlreadyFunded(uint256 gi);
    error EmissionExhausted();

    // ── Events ────────────────────────────────────────────────────────────
    event EmissionParamsUpdated(
        uint256 initialEmissionPerGI,
        uint256 decayBps,
        uint256 epochLength,
        uint256 maxEpochs
    );
    event GIFunded(
        uint256 indexed gi,
        address indexed taskAuditor,
        uint256 amount,
        uint256 epoch
    );

    // ── State ─────────────────────────────────────────────────────────────

    /// @notice DinCoordinator proxy — mint gateway.
    IDinCoordinator public coordinator;

    /// @notice DIN token — used to approve depositRewards.
    IERC20 public dinToken;

    /// @notice DIN emitted per GI at epoch 0.
    uint256 public initialEmissionPerGI;

    /// @notice Fraction of per-GI emission retained after each epoch, in bps.
    ///         e.g. 8000 = 80% retained → 20% reduction per epoch.
    uint256 public decayBps;

    /// @notice Number of GIs that constitute one epoch.
    uint256 public epochLength;

    /// @notice Total epochs before emission stops. After maxEpochs epochs
    ///         fundGI() is a no-op (returns 0) — the final-epoch retirement.
    uint256 public maxEpochs;

    /// @notice Current epoch index (0-based).
    uint256 public currentEpoch;

    /// @notice Number of GIs funded in the current epoch so far.
    uint256 public gisInCurrentEpoch;

    /// @notice Per-GI emission amount for the current epoch.
    ///         Updated at each epoch boundary via the decay formula.
    uint256 public currentEmissionPerGI;

    /// @notice Cumulative DIN minted through this contract.
    uint256 public totalEmitted;

    /// @notice Guards against funding the same GI twice.
    mapping(uint256 => bool) public giEmissionFunded;

    // Reserved for future state variables.
    uint256[38] private __gap;

    // ── Constructor / initializer ─────────────────────────────────────────

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /// @notice Initialises the proxy.
    /// @param coordinator_         DinCoordinator proxy address.
    /// @param dinToken_            DinToken proxy address.
    /// @param initialEmissionPerGI_ DIN emitted per GI at epoch 0 (wei).
    /// @param decayBps_            Retention fraction per epoch in bps (1–10000).
    /// @param epochLength_         GIs per epoch (>= 1).
    /// @param maxEpochs_           Number of epochs before emission stops (>= 1).
    function initialize(
        address coordinator_,
        address dinToken_,
        uint256 initialEmissionPerGI_,
        uint256 decayBps_,
        uint256 epochLength_,
        uint256 maxEpochs_
    ) external initializer {
        if (coordinator_ == address(0) || dinToken_ == address(0)) revert InvalidAddress();
        _validateParams(initialEmissionPerGI_, decayBps_, epochLength_, maxEpochs_);
        __Ownable_init(msg.sender);
        coordinator = IDinCoordinator(coordinator_);
        dinToken = IERC20(dinToken_);
        initialEmissionPerGI = initialEmissionPerGI_;
        decayBps = decayBps_;
        epochLength = epochLength_;
        maxEpochs = maxEpochs_;
        currentEmissionPerGI = initialEmissionPerGI_;
    }

    // ── Core function ─────────────────────────────────────────────────────

    /// @notice Mints the scheduled emission subsidy for a GI and deposits it
    ///         into the GI's reward pool via IDINTaskAuditor.depositRewards().
    ///
    ///         Callable by anyone — the amount is deterministic from the epoch
    ///         schedule so there is no benefit to restricting the caller.
    ///         A GI can only be funded once; subsequent calls revert.
    ///
    ///         If emission is exhausted (currentEpoch >= maxEpochs) the call
    ///         reverts with EmissionExhausted — callers should check
    ///         emissionForCurrentEpoch() == 0 before calling to avoid gas waste.
    ///
    /// @param gi          GI index to subsidise. Must match or exceed the task
    ///                    coordinator's current GI (enforced by depositRewards).
    /// @param taskAuditor Address of the DINTaskAuditor whose depositRewards
    ///                    will receive the minted DIN.
    /// @return amount     DIN amount deposited (0 if already retired, never
    ///                    negative — the return value is informational only;
    ///                    the revert paths cover the error cases).
    function fundGI(uint256 gi, address taskAuditor) external nonReentrant returns (uint256 amount) {
        if (taskAuditor == address(0)) revert InvalidAddress();
        if (giEmissionFunded[gi]) revert GIAlreadyFunded(gi);
        if (currentEpoch >= maxEpochs) revert EmissionExhausted();

        amount = currentEmissionPerGI;

        giEmissionFunded[gi] = true;
        totalEmitted += amount;

        // Advance epoch counter before external calls (CEI).
        _advanceEpoch();

        // Mint → approve → deposit.
        coordinator.mintEmission(address(this), amount);
        dinToken.safeIncreaseAllowance(taskAuditor, amount);
        IDINTaskAuditor(taskAuditor).depositRewards(gi, amount);

        emit GIFunded(gi, taskAuditor, amount, currentEpoch > 0 ? currentEpoch - 1 : 0);
        return amount;
    }

    // ── View helpers ──────────────────────────────────────────────────────

    /// @notice Returns the emission amount for the current epoch.
    ///         Returns 0 when emission is exhausted.
    function emissionForCurrentEpoch() external view returns (uint256) {
        if (currentEpoch >= maxEpochs) return 0;
        return currentEmissionPerGI;
    }

    /// @notice Computes the emission amount at any future epoch index.
    ///         Returns 0 for epochs >= maxEpochs.
    function emissionAtEpoch(uint256 epoch) external view returns (uint256) {
        if (epoch >= maxEpochs) return 0;
        uint256 e = initialEmissionPerGI;
        for (uint256 i = 0; i < epoch; i++) {
            e = (e * decayBps) / 10_000;
        }
        return e;
    }

    // ── Governance ────────────────────────────────────────────────────────

    /// @notice Updates all four emission schedule parameters.
    ///         Takes effect from the NEXT epoch boundary — the current epoch's
    ///         per-GI emission (currentEmissionPerGI) is not retroactively changed.
    ///         Resets currentEmissionPerGI to initialEmissionPerGI_ so the new
    ///         schedule starts fresh.
    /// @dev Intentionally resets the epoch counters so the new schedule is
    ///      predictable. DAO should time this call at an epoch boundary if
    ///      continuity matters.
    function setEmissionParams(
        uint256 initialEmissionPerGI_,
        uint256 decayBps_,
        uint256 epochLength_,
        uint256 maxEpochs_
    ) external onlyOwner {
        _validateParams(initialEmissionPerGI_, decayBps_, epochLength_, maxEpochs_);
        initialEmissionPerGI = initialEmissionPerGI_;
        decayBps = decayBps_;
        epochLength = epochLength_;
        maxEpochs = maxEpochs_;
        currentEpoch = 0;
        gisInCurrentEpoch = 0;
        currentEmissionPerGI = initialEmissionPerGI_;
        emit EmissionParamsUpdated(initialEmissionPerGI_, decayBps_, epochLength_, maxEpochs_);
    }

    // ── Internal ──────────────────────────────────────────────────────────

    function _advanceEpoch() internal {
        gisInCurrentEpoch++;
        if (gisInCurrentEpoch >= epochLength) {
            gisInCurrentEpoch = 0;
            currentEpoch++;
            if (currentEpoch < maxEpochs) {
                currentEmissionPerGI = (currentEmissionPerGI * decayBps) / 10_000;
            } else {
                currentEmissionPerGI = 0;
            }
        }
    }

    function _validateParams(
        uint256 initialEmissionPerGI_,
        uint256 decayBps_,
        uint256 epochLength_,
        uint256 maxEpochs_
    ) internal pure {
        if (
            initialEmissionPerGI_ == 0 ||
            decayBps_ == 0 || decayBps_ > 10_000 ||
            epochLength_ == 0 ||
            maxEpochs_ == 0
        ) revert InvalidParams();
    }
}
