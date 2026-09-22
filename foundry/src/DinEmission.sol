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
///         GI is a per-DINTaskCoordinator counter — every model has its own
///         "GI 1", "GI 2", etc., independent of every other model's. This
///         contract is a single platform-level deployment shared by every
///         model, so the funded-GI guard and the epoch/decay progress are
///         tracked per taskAuditor (i.e. per model) rather than globally;
///         otherwise two models would collide on identically-numbered GIs
///         and a schedule tuned for one model's cadence would burn down N
///         times faster with N models concurrently drawing emission.
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

    /// @notice One taskAuditor's (model's) independent progress through the
    ///         shared decay schedule.
    struct EmissionState {
        /// @notice Current epoch index (0-based) for this taskAuditor.
        uint256 currentEpoch;
        /// @notice Number of GIs funded in the current epoch so far.
        uint256 gisInCurrentEpoch;
        /// @notice Per-GI emission amount for the current epoch.
        ///         Updated at each epoch boundary via the decay formula.
        uint256 currentEmissionPerGI;
        /// @notice Set on this taskAuditor's first fundGI() call. Distinguishes
        ///         "hasn't started yet" (use initialEmissionPerGI) from
        ///         "exhausted" (currentEmissionPerGI legitimately decayed to 0).
        bool started;
    }

    /// @notice Per-taskAuditor (per-model) emission schedule progress.
    mapping(address => EmissionState) public emissionState;

    /// @notice Cumulative DIN minted through this contract, across all models.
    uint256 public totalEmitted;

    /// @notice Guards against funding the same GI twice, scoped per
    ///         taskAuditor so identically-numbered GIs on different models
    ///         don't collide.
    mapping(address => mapping(uint256 => bool)) public giEmissionFunded;

    // Reserved for future state variables.
    uint256[40] private __gap;

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
    }

    // ── Core function ─────────────────────────────────────────────────────

    /// @notice Mints the scheduled emission subsidy for a GI and deposits it
    ///         into the GI's reward pool via IDINTaskAuditor.depositRewards().
    ///
    ///         Callable by anyone — the amount is deterministic from the epoch
    ///         schedule so there is no benefit to restricting the caller.
    ///         A GI can only be funded once; subsequent calls revert.
    ///
    ///         If taskAuditor's schedule is exhausted (currentEpoch >=
    ///         maxEpochs) the call reverts with EmissionExhausted — callers
    ///         should check emissionForCurrentEpoch(taskAuditor) == 0 before
    ///         calling to avoid gas waste.
    ///
    /// @param gi          GI index to subsidise, scoped to taskAuditor's own
    ///                    model. Must match or exceed the task coordinator's
    ///                    current GI (enforced by depositRewards).
    /// @param taskAuditor Address of the DINTaskAuditor whose depositRewards
    ///                    will receive the minted DIN. Also identifies which
    ///                    model's independent epoch/decay schedule and
    ///                    funded-GI guard this call operates on.
    /// @return amount     DIN amount deposited (0 if already retired, never
    ///                    negative — the return value is informational only;
    ///                    the revert paths cover the error cases).
    function fundGI(uint256 gi, address taskAuditor) external nonReentrant returns (uint256 amount) {
        if (taskAuditor == address(0)) revert InvalidAddress();
        if (giEmissionFunded[taskAuditor][gi]) revert GIAlreadyFunded(gi);

        EmissionState storage state = emissionState[taskAuditor];
        if (!state.started) {
            state.currentEmissionPerGI = initialEmissionPerGI;
            state.started = true;
        }
        if (state.currentEpoch >= maxEpochs) revert EmissionExhausted();

        amount = state.currentEmissionPerGI;
        uint256 epochFunded = state.currentEpoch;

        giEmissionFunded[taskAuditor][gi] = true;
        totalEmitted += amount;

        // Advance epoch counter before external calls (CEI).
        _advanceEpoch(state);

        // Mint → approve → deposit.
        coordinator.mintEmission(address(this), amount);
        dinToken.safeIncreaseAllowance(taskAuditor, amount);
        IDINTaskAuditor(taskAuditor).depositRewards(gi, amount);

        emit GIFunded(gi, taskAuditor, amount, epochFunded);
        return amount;
    }

    // ── View helpers ──────────────────────────────────────────────────────

    /// @notice Returns the emission amount for taskAuditor's (model's)
    ///         current epoch. Returns initialEmissionPerGI for a taskAuditor
    ///         that hasn't funded a GI yet, and 0 once its schedule is
    ///         exhausted.
    function emissionForCurrentEpoch(address taskAuditor) external view returns (uint256) {
        EmissionState storage state = emissionState[taskAuditor];
        if (!state.started) return initialEmissionPerGI;
        if (state.currentEpoch >= maxEpochs) return 0;
        return state.currentEmissionPerGI;
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
    ///         Takes effect from each taskAuditor's NEXT fundGI() call — an
    ///         already-started model's in-flight currentEpoch/
    ///         currentEmissionPerGI progress is not retroactively reset here
    ///         (per-model progress lives in a mapping and isn't centrally
    ///         enumerable on-chain); a taskAuditor that hasn't funded a GI
    ///         yet picks up initialEmissionPerGI_ on its first call.
    /// @dev DAO should time this call at an epoch boundary for models
    ///      already in progress if continuity matters.
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
        emit EmissionParamsUpdated(initialEmissionPerGI_, decayBps_, epochLength_, maxEpochs_);
    }

    // ── Internal ──────────────────────────────────────────────────────────

    function _advanceEpoch(EmissionState storage state) internal {
        state.gisInCurrentEpoch++;
        if (state.gisInCurrentEpoch >= epochLength) {
            state.gisInCurrentEpoch = 0;
            state.currentEpoch++;
            if (state.currentEpoch < maxEpochs) {
                state.currentEmissionPerGI = (state.currentEmissionPerGI * decayBps) / 10_000;
            } else {
                state.currentEmissionPerGI = 0;
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
