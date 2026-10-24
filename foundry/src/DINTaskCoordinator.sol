// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuardTransient} from "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";
import "./DINShared.sol";

interface IBurnableDinToken {
    function burn(uint256 amount) external;
}

/// @title DIN Task Coordinator
/// @notice Orchestrates the full Global Iteration (GI) lifecycle for a single
///         federated-learning model: slasher setup, validator registration,
///         local model submissions, auditing, Tier-1/Tier-2 aggregation, and
///         validator slashing. Deployed once per model by the model owner.
contract DINTaskCoordinator is Ownable, ReentrancyGuardTransient {
    using SafeERC20 for IERC20;

    IDinValidatorStake public dinvalidatorStakeContract;
    IDINTaskAuditor public dinTaskAuditorContract;

    uint public GI = 0; // GlobalIteration

    GIstates public GIstate;

    bytes32 public genesisModelIpfsHash; // genesis model ipfs hash

    mapping(uint => address[]) public dinAggregators;

    // Track if an address is registered for a given _GI as an aggregator
    mapping(uint => mapping(address => bool)) public isDINAggregator;

    /// @notice Guard: prevents releaseGIRegistrationSlots from being called
    ///         twice for the same GI (which would double-decrement counters).
    mapping(uint256 => bool) public registrationSlotsReleased;

    uint256 public constant T1_AGGREGATORS_PER_BATCH = 3;
    uint256 public constant T1_MODELS_PER_BATCH = 3;
    uint256 public constant MIN_T1_MODELS_PER_BATCH = 2;
    uint256 public constant MAX_REGISTERED_AGGREGATORS = 300;

    struct Tier1Batch {
        uint batchId; // Unique inside round
        address[] aggregators; // Aggregators assigned
        uint[] modelIndexes; // Indexes into approvedModels[GI]
        bool finalized; // True after majority
        bytes32 finalCID; // Majority‐agreed CID
    }

    // tier1Batches/tier2Batches and the t1*/t2* per-aggregator maps below are
    // internal to keep this contract under EIP-170 (issue #201 Part A): read
    // batches via getTier1Batch/getTier2Batch and per-aggregator commit/reveal
    // state via getAggregatorSubmission.
    mapping(uint => Tier1Batch[]) internal tier1Batches;
    mapping(uint => mapping(uint => mapping(address => bool))) isTier1Aggregator;

    // Audit & voting maps            GI  ➜  batchId ➜ validator  ➜  …
    // t1SubmissionCID/t1Submitted are written at REVEAL time only (issue #156
    // M-1, task_240926_18 Part C commit-then-reveal) -- a committed-but-
    // never-revealed aggregator leaves t1Submitted false, which is exactly
    // what slashAggregators()'s existing "no submission" (S2) check already
    // reads, so that loop needed no changes for the commit-reveal split.
    mapping(uint => mapping(uint => mapping(address => bytes32)))
        internal t1SubmissionCID;
    mapping(uint => mapping(uint => mapping(address => bool)))
        internal t1Submitted;
    mapping(uint => mapping(uint => mapping(bytes32 => uint))) internal t1Votes; // CID ➜ votes
    mapping(uint => mapping(uint => mapping(address => bytes32))) internal t1CommitHash;
    mapping(uint => mapping(uint => mapping(address => bool))) internal t1Committed;

    struct Tier2Batch {
        uint batchId;
        address[] aggregators; // Tier‑2 aggregators
        bool finalized;
        bytes32 finalCID;
    }

    mapping(uint => Tier2Batch[]) internal tier2Batches;
    mapping(uint => mapping(uint => mapping(address => bool))) isTier2Aggregator;
    mapping(uint => uint) public tier2Score;

    mapping(uint => mapping(uint => mapping(address => bytes32)))
        internal t2SubmissionCID;
    mapping(uint => mapping(uint => mapping(address => bool)))
        internal t2Submitted;
    mapping(uint => mapping(uint => mapping(bytes32 => uint))) internal t2Votes;
    mapping(uint => mapping(uint => mapping(address => bytes32))) internal t2CommitHash;
    mapping(uint => mapping(uint => mapping(address => bool))) internal t2Committed;

    /// @notice Per-aggregator count of finalized T1/T2 batches they were
    ///         assigned to in a GI, one increment per (aggregator,
    ///         finalized-batch) pair. Preserves the reward weighting
    ///         _collectFinalizedBatchAggregators used to express by emitting
    ///         a duplicate array entry per pair (task_210726_6 §3): an
    ///         aggregator assigned to a finalized batch is rewardable for it
    ///         regardless of whether they personally matched consensus,
    ///         since a mismatch already cost them stake via slashAggregators.
    ///         Accumulated incrementally in finalizeT1Aggregation /
    ///         finalizeT2Aggregation's existing per-batch loop (BL-10, #125)
    ///         and read at claim time by DINTaskAuditor.claimReward.
    mapping(uint256 => mapping(address => uint256)) public aggregatorWeight;

    /// @notice Sum of aggregatorWeight across all aggregators for a GI --
    ///         the settlement denominator for aggregator reward shares.
    ///         Snapshotted into DINTaskAuditor at settleRewards time (#125).
    mapping(uint256 => uint256) public totalAggregatorWeight;

    // ─────────────────────────────────────────────────────────────────────
    // Dispute resolution scaffold (task_210726_6 §4c, issue #38, S4)
    //
    // Bond custody, window enforcement, and fresh-subgroup reassignment are
    // real on-chain mechanics. Adjudication (was the disputed CID actually
    // wrong?) is NOT on-chain here -- verifying a T1/T2 aggregation CID
    // requires re-running aggregation over model weights, which isn't
    // something a contract can or should do. resolveDispute is onlyOwner
    // for now; see Developer/design/slashing-taxonomy.md's S4 section for
    // why, and what a future on-chain adjudication mechanism would need.
    //
    // Bounty/bond-forfeiture payouts are stubbed the same way Part 3's
    // reward engine stubs its treasury share: accrued locally, not
    // forwarded anywhere, because DinTreasury doesn't exist on develop yet.
    // ─────────────────────────────────────────────────────────────────────

    enum TierKind {
        Tier1,
        Tier2
    }

    struct Dispute {
        address challenger;
        uint256 bond;
        uint64 openedAt;
        uint64 resolutionDeadline; // set when fresh subgroup assigned; 0 until then
        uint64 seedBlock;          // block number after which anyone may lock the seed
        bool resolved;    // true after resolveDispute() first decision
        bool upheld;      // true if fresh subgroup was assigned
        bool finalized;   // true after settleRecomputation() or expireDispute()
        bytes32 seed;     // locked via lockDisputeSeed(); zero means not yet locked
    }

    IERC20 public dinToken;
    // Dispute bonds are DIN-denominated as a slashing-pattern security deposit — the
    // challenger's own skin-in-the-game, forfeited via the same 50/50 burn/treasury
    // split as DinValidatorStake.slash() (MECHANISM_DESIGN.md §4 item 1, §9 item 7).
    // This is not a network-fee payment: item 4's ETH resolution governs per-GI
    // validator service fees paid between economic actors, not a challenger's own
    // stake returned or burned based on correctness. When DinTreasury lands
    // (task_210726_5), the resolveDispute forfeiture TODO already cites item 1's
    // burn/treasury destination — no ETH-burn path is needed.
    uint256 public disputeBond = 100 * 1e18; // placeholder default, DAO-settable
    uint64 public disputeWindow = 1 days;    // placeholder default, DAO-settable
    uint64 public resolutionWindow = 2 days; // how long fresh subgroup has to recompute; DAO-settable
    /// @notice Blocks to wait after openDispute before the seed can be locked.
    ///         On OP Stack, blocks are ~2 s, so the default (7) is ~14 s —
    ///         enough for honest validators to observe the seedBlock, yet short
    ///         enough not to delay dispute resolution meaningfully.
    ///         Trust caveat: blockhash is sequencer-produced on OP Stack, so this
    ///         design trusts the sequencer not to grind. Acceptable for DevNet/
    ///         testnet; VRF or multi-party commit-reveal with a slashable
    ///         non-reveal penalty is the mainnet-grade follow-up.
    uint64 public disputeSeedDelay = 7; // DAO-settable; 1–256 enforced by setDisputeParams

    // ── Ungrindable batch-assignment seed (issue #156 H-2, both tiers) ──────
    // Same future-block-seed + permissionless-lock pattern as the dispute
    // seed above, reusing disputeSeedDelay rather than adding a second delay
    // knob -- one randomness pattern, one sequencer-trust caveat, across the
    // whole protocol. aggSeed* covers autoCreateTier1AndTier2 (T1+T2);
    // auditSeed* covers DINTaskAuditor.createAuditorsBatches, anchored here
    // (at the closeLMsubmissions state transition this contract owns) and
    // passed across the interface once locked -- the same cross-contract
    // shape DINTaskAuditor.claimReward already uses for aggregatorWeight.
    mapping(uint256 => uint64) public aggSeedBlock;
    mapping(uint256 => bytes32) public aggSeed;
    mapping(uint256 => uint64) public auditSeedBlock;
    mapping(uint256 => bytes32) public auditSeed;

    uint256 public treasuryAccrued; // cumulative observability counter
    /// @dev Gas units required per validator per GI to cover on-chain submission costs.
    ///      Set by the DAO via setNetworkFeeFloor; not yet enforced at depositRewards
    ///      (enforcement point to be confirmed with Umer — see task_100926_12 #78).
    uint256 public networkFeeFloor;

    /// @notice S2 liveness-fault slash fraction in basis points (1–10000).
    ///         Applied to missed-submission slashes (AGG_T*_NO_SUBMISSION) only.
    ///         Bad-consensus faults (AGG_T*_BAD_CONSENSUS) keep a full minStake()
    ///         amount — they imply an active incorrect submission, not a liveness
    ///         failure, so they are treated as full-severity faults.
    ///         30% default matches S1. DAO-settable via setS2SlashFractionBps.
    uint256 public s2SlashFractionBps = 3000;

    mapping(uint => mapping(uint => uint64)) public tier1FinalizedAt;
    mapping(uint => mapping(uint => uint64)) public tier2FinalizedAt;
    mapping(uint => mapping(TierKind => mapping(uint => Dispute)))
        public disputes;
    mapping(uint => mapping(TierKind => mapping(uint => address[])))
        public reEvaluationAssignees;
    mapping(address => uint256) public disputeBondClaimable;

    event DisputeOpened(
        uint indexed GI,
        TierKind tierKind,
        uint indexed batchId,
        address indexed challenger,
        uint256 bond
    );
    event DisputeResolved(
        uint indexed GI,
        TierKind tierKind,
        uint indexed batchId,
        bool upheld
    );
    event ReEvaluationAssigned(
        uint indexed GI,
        TierKind tierKind,
        uint indexed batchId,
        address[] freshAggregators
    );
    event DisputeBondClaimed(address indexed challenger, uint256 amount);
    event RecomputationSettled(
        uint indexed GI,
        TierKind tierKind,
        uint indexed batchId,
        bool confirmed
    );
    event DisputeExpired(
        uint indexed GI,
        TierKind tierKind,
        uint indexed batchId
    );
    event DisputeSeedLocked(
        uint indexed GI,
        TierKind tierKind,
        uint indexed batchId,
        bytes32 seed
    );
    event DisputeSeedReanchored(
        uint indexed GI,
        TierKind tierKind,
        uint indexed batchId,
        uint64 newSeedBlock
    );
    event AggSeedLocked(uint indexed GI, bytes32 seed);
    event AggSeedReanchored(uint indexed GI, uint64 newSeedBlock);
    event AuditSeedLocked(uint indexed GI, bytes32 seed);
    event AuditSeedReanchored(uint indexed GI, uint64 newSeedBlock);

    modifier onlyCurrentGI(uint _GI) {
        if (_GI != GI) revert TC_WrongGI();
        _;
    }

    event DINValidatorRegistered(uint indexed GI, address indexed validator);
    event Tier1BatchAuto(uint indexed GI, uint indexed batchId);
    event Tier2BatchAuto(uint indexed GI, uint indexed batchId);
    event AggregatorSlashed(
        uint indexed GI,
        uint indexed batchId,
        address indexed aggregator,
        bytes32 reason,
        uint256 requested,
        uint256 actual
    );
    event S2SlashFractionBpsUpdated(uint256 oldBps, uint256 newBps);

    // ── Indexer lifecycle events (task_240926_16 Part C / issue #153) ──────────
    /// @notice Emitted on every GI state transition.
    /// @dev GI is 0 during constructor/setup transitions (ordinals 0–4); expected.
    event GIStateChanged(uint indexed GI, uint8 indexed newState);
    event T1AggregationCommitted(uint indexed GI, uint indexed batchId, address indexed aggregator, bytes32 commitHash);
    event T1AggregationSubmitted(uint indexed GI, uint indexed batchId, address indexed aggregator, bytes32 cid);
    event T2AggregationCommitted(uint indexed GI, uint indexed batchId, address indexed aggregator, bytes32 commitHash);
    event T2AggregationSubmitted(uint indexed GI, uint indexed batchId, address indexed aggregator, bytes32 cid);
    event T1BatchFinalized(uint indexed GI, uint indexed batchId, bytes32 winningCID);
    event T2Finalized(uint indexed GI, bytes32 globalModelCID);

    /// @notice Model registry ID this coordinator manages.
    /// @dev Used to look up modelMinStakeBounds and enforce per-model stake floors.
    uint256 public immutable modelId;

    /// @notice Deploys the coordinator and sets the validator stake contract.
    /// @dev GI state is initialised to AwaitingDINTaskAuditorToBeSet; the model
    ///      owner must call setDINTaskAuditorContract before any other setup step.
    ///      Rejects a zero address (L-6): task contracts are non-upgradeable,
    ///      so a bad deploy here means a full redeploy, not a fix.
    /// @param dinvalidatorStakeContract_address Address of the DinValidatorStake proxy.
    /// @param modelId_ Model registry ID for this deployment, used for per-model stake enforcement.
    constructor(address dinvalidatorStakeContract_address, uint256 modelId_) Ownable(msg.sender) {
        if (dinvalidatorStakeContract_address == address(0))
            revert TC_InvalidAddress();
        dinvalidatorStakeContract = IDinValidatorStake(
            dinvalidatorStakeContract_address
        );
        modelId = modelId_;
        _setGIstate(GIstates.AwaitingDINTaskAuditorToBeSet);
    }

    /// @notice Sets the paired DINTaskAuditor contract for this model.
    /// @dev One-shot: reverts if called after the initial setup step. Rejects
    ///      a zero address (L-6) -- this is a one-shot setter that immediately
    ///      advances GIstate, so a zero address here bricks the contract the
    ///      same way an unchecked constructor argument would.
    /// @param _dintaskauditor_contract_address Address of the DINTaskAuditor contract.
    function setDINTaskAuditorContract(
        address _dintaskauditor_contract_address
    ) public onlyOwner {
        if (GIstate != GIstates.AwaitingDINTaskAuditorToBeSet)
            revert TC_TaskAuditorContractCannotBeSet();
        if (_dintaskauditor_contract_address == address(0))
            revert TC_InvalidAddress();
        dinTaskAuditorContract = IDINTaskAuditor(
            _dintaskauditor_contract_address
        );
        _setGIstate(GIstates.AwaitingDINTaskCoordinatorAsSlasher);
    }

    /// @notice Confirms that this coordinator is registered as a slasher on the
    ///         validator stake contract, advancing the GI state.
    /// @dev The DIN-Representative must have called DinCoordinator.addSlasherContract
    ///      for this address before this function is called.
    function setDINTaskCoordinatorAsSlasher() public onlyOwner {
        if (GIstate != GIstates.AwaitingDINTaskCoordinatorAsSlasher)
            revert TC_CoordinatorCannotBeSetAsSlasher();
        if (!dinvalidatorStakeContract.isSlasherContract(address(this)))
            revert TC_CoordinatorIsNotSlasher();
        _setGIstate(GIstates.AwaitingDINTaskAuditorAsSlasher);
    }

    /// @notice Confirms that the paired DINTaskAuditor is registered as a slasher,
    ///         completing the setup sequence and enabling model registration.
    /// @dev The DIN-Representative must have called DinCoordinator.addSlasherContract
    ///      for the auditor address before this function is called.
    function setDINTaskAuditorAsSlasher() public onlyOwner {
        if (GIstate != GIstates.AwaitingDINTaskAuditorAsSlasher)
            revert TC_AuditorCannotBeSetAsSlasher();
        if (
            !dinvalidatorStakeContract.isSlasherContract(
                address(dinTaskAuditorContract)
            )
        ) revert TC_AuditorIsNotSlasher();
        _setGIstate(GIstates.AwaitingGenesisModel);
    }

    /// @notice Records the genesis model IPFS hash, enabling GI 1 to be started.
    /// @param _genesisModelIpfsHash CID of the genesis model weights, encoded as bytes32.
    function setGenesisModelIpfsHash(
        bytes32 _genesisModelIpfsHash
    ) public onlyOwner {
        if (GIstate != GIstates.AwaitingGenesisModel)
            revert TC_GenesisModelHashCannotBeSet();
        genesisModelIpfsHash = _genesisModelIpfsHash;
        _setGIstate(GIstates.GenesisModelCreated);
    }

    /// @notice Starts the next Global Iteration and updates the auditor pass score.
    /// @param _GI Expected next GI index (must equal current GI + 1).
    /// @param score New pass score to set on the paired DINTaskAuditor.
    function startGI(uint _GI, uint score) public onlyOwner {
        _startGI(_GI, score, true);
    }

    /// @notice Starts the next Global Iteration, retaining the existing pass score.
    /// @param _GI Expected next GI index (must equal current GI + 1).
    function startGI(uint _GI) public onlyOwner {
        _startGI(_GI, 0, false);
    }

    function _startGI(uint _GI, uint score, bool updatePassScore) internal {
        if (
            GIstate != GIstates.GenesisModelCreated &&
            GIstate != GIstates.GIended
        ) revert TC_GICannotBeStarted();
        if (_GI != GI + 1) revert TC_WrongGI();
        // task_210726_6 §3: a GI cannot start unless its reward pool has
        // been funded via DINTaskAuditor.depositRewards(_GI, ...) first.
        // Prevents a GI running to completion with nothing to settle/claim.
        if (dinTaskAuditorContract.giRewardPool(_GI) == 0)
            revert TC_GIRewardPoolNotFunded();
        if (updatePassScore) {
            dinTaskAuditorContract.updatePassScore(score);
        }
        GI++;
        _setGIstate(GIstates.GIstarted);
    }

    /// @notice Opens the aggregator registration window for the current GI.
    /// @param _GI Current GI index, used to guard against stale calls.
    function startDINaggregatorsRegistration(
        uint _GI
    ) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.GIstarted)
            revert TC_AggregatorsRegistrationCannotBeStarted();
        _setGIstate(GIstates.DINaggregatorsRegistrationStarted);
    }

    /// @notice Registers the caller as an aggregator for the current GI.
    /// @dev Caller must be an active validator; duplicate registrations revert.
    /// @param _GI Current GI index.
    function registerDINaggregator(uint _GI) public onlyCurrentGI(_GI) {
        if (GIstate != GIstates.DINaggregatorsRegistrationStarted)
            revert TC_AggregatorsRegistrationNotOpen();

        if (!dinvalidatorStakeContract.isValidatorActive(msg.sender)) {
            revert TC_AggregatorNotActive();
        }
        if (isDINAggregator[_GI][msg.sender])
            revert TC_AggregatorAlreadyRegistered();
        if (dinAggregators[_GI].length >= MAX_REGISTERED_AGGREGATORS)
            revert TC_RegistrationCapReached();

        // Per-model stake floor: enforced when the model owner has set a non-zero bound.
        uint256 floorMin = dinvalidatorStakeContract.getModelStakeMin(modelId);
        if (floorMin > 0 && dinvalidatorStakeContract.getStake(msg.sender) < floorMin)
            revert TC_StakeBelowModelFloor();

        // Concurrent-registration cap: enforced when the DAO has set a non-zero value.
        // Formula: each MIN_STAKE unit of stake allows capPerUnit concurrent registrations.
        uint256 capPerUnit = dinvalidatorStakeContract.maxConcurrentRegistrationsPerStakeUnit();
        if (capPerUnit > 0) {
            uint256 maxAllowed = (dinvalidatorStakeContract.getStake(msg.sender) /
                dinvalidatorStakeContract.minStake()) * capPerUnit;
            if (dinvalidatorStakeContract.activeRegistrationCount(msg.sender) >= maxAllowed)
                revert TC_ConcurrentRegistrationCapReached();
        }

        // Add to list and mark as registered
        dinAggregators[_GI].push(msg.sender);
        isDINAggregator[_GI][msg.sender] = true;
        dinvalidatorStakeContract.incrementActiveRegistration(msg.sender);

        emit DINValidatorRegistered(_GI, msg.sender);
    }

    /// @notice Closes the aggregator registration window.
    /// @param _GI Current GI index.
    function closeDINaggregatorsRegistration(
        uint _GI
    ) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.DINaggregatorsRegistrationStarted)
            revert TC_AggregatorsRegistrationCannotBeFinished();
        _setGIstate(GIstates.DINaggregatorsRegistrationClosed);
    }

    /// @notice Returns the list of aggregators registered for the given GI.
    /// @param _GI GI index to query.
    /// @return Ordered array of aggregator addresses in registration order.
    function getDINtaskAggregators(
        uint _GI
    ) public view returns (address[] memory) {
        return dinAggregators[_GI];
    }

    /// @notice Opens the auditor registration window on the paired DINTaskAuditor.
    /// @param _GI Current GI index.
    function startDINauditorsRegistration(
        uint _GI
    ) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.DINaggregatorsRegistrationClosed)
            revert TC_AuditorsRegistrationCannotBeStarted();
        _setGIstate(GIstates.DINauditorsRegistrationStarted);
    }

    /// @notice Closes the auditor registration window.
    /// @param _GI Current GI index.
    function closeDINauditorsRegistration(
        uint _GI
    ) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.DINauditorsRegistrationStarted)
            revert TC_AuditorsRegistrationCannotBeFinished();
        _setGIstate(GIstates.DINauditorsRegistrationClosed);
    }

    /// @notice Opens the local model submission window for the current GI.
    /// @param _GI Current GI index.
    function startLMsubmissions(uint _GI) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.DINauditorsRegistrationClosed)
            revert TC_LMSubmissionsCannotBeStarted();
        _setGIstate(GIstates.LMSstarted);
    }

    /// @notice Closes the local model submission window.
    /// @param _GI Current GI index.
    function closeLMsubmissions(uint _GI) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.LMSstarted) revert TC_LMSubmissionsNotStarted();
        // Anchor the auditor-batch seed here, at the transition that gates
        // createAuditorsBatches -- by the time this function could possibly
        // be called next, the seed block is already fixed but not yet mined,
        // so the caller (model owner) cannot aim for a favourable outcome.
        auditSeedBlock[_GI] = uint64(block.number) + disputeSeedDelay;
        _setGIstate(GIstates.LMSclosed);
    }

    /// @notice Delegates auditor batch creation to DINTaskAuditor and advances GI state.
    /// @dev Reverts if the auditor contract returns false (e.g. insufficient auditors).
    ///      Requires auditSeed[_GI] to already be locked via lockAuditSeed
    ///      (issue #156 H-2) -- the locked seed is passed across the interface
    ///      so DINTaskAuditor's shuffles are ungrindable without duplicating
    ///      the seed-anchoring logic in that contract.
    /// @param _GI Current GI index.
    function createAuditorsBatches(
        uint _GI
    ) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.LMSclosed) revert TC_LMEvalCannotBeStarted();
        bytes32 seed = auditSeed[_GI];
        if (seed == bytes32(0)) revert TC_AuditSeedNotLocked();

        bool success = dinTaskAuditorContract.createAuditorsBatches(_GI, seed);
        if (!success) revert TC_FailedToCreateAuditorsBatches();

        _setGIstate(GIstates.AuditorsBatchesCreated);
    }

    /// @notice Propagates the test data assignment flag to DINTaskAuditor.
    /// @dev Must be called while GI state is AuditorsBatchesCreated.
    /// @param _GI Current GI index.
    /// @param flag True once test datasets have been distributed to auditors.
    function setTestDataAssignedFlag(
        uint _GI,
        bool flag
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.AuditorsBatchesCreated)
            revert TC_CannotSetTestDataAssignedFlag();

        dinTaskAuditorContract.setTestDataAssignedFlag(_GI, flag);
    }

    /// @notice Opens the LMS evaluation COMMIT phase so auditors can begin
    ///         committing (hidden) scores via DINTaskAuditor.commitAuditScore.
    /// @param _GI Current GI index.
    function startLMsubmissionsEvaluation(
        uint _GI
    ) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.AuditorsBatchesCreated)
            revert TC_LMEvalCannotBeStarted();
        _setGIstate(GIstates.LMSevaluationStarted);
    }

    /// @notice Closes the commit phase and opens the REVEAL phase (task_210726_6
    ///         §2a) so auditors can call DINTaskAuditor.revealAuditScore.
    /// @dev Must run strictly after commits close and before any reveal is
    ///      accepted -- see DINTaskAuditor.revealAuditScore's GIstate gate.
    /// @param _GI Current GI index.
    function startLMsubmissionsEvaluationReveal(
        uint _GI
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.LMSevaluationStarted)
            revert TC_RevealCannotBeStarted();
        _setGIstate(GIstates.LMSevaluationRevealStarted);
    }

    /// @notice Closes the LMS evaluation reveal phase and finalises audit
    ///         results on the paired DINTaskAuditor.
    /// @dev Calls DINTaskAuditor.finalizeEvaluation; reverts if it returns false.
    /// @param _GI Current GI index.
    function closeLMsubmissionsEvaluation(
        uint _GI
    ) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.LMSevaluationRevealStarted)
            revert TC_LMEvalCannotBeFinished();
        bool success = dinTaskAuditorContract.finalizeEvaluation(_GI);
        if (!success) revert TC_FailedToFinalizeEvaluation();
        // Anchor the T1/T2 batch-assignment seed here, at the transition
        // that gates autoCreateTier1AndTier2 -- same reasoning as
        // closeLMsubmissions's auditSeedBlock anchor above.
        aggSeedBlock[_GI] = uint64(block.number) + disputeSeedDelay;
        _setGIstate(GIstates.LMSevaluationClosed);
    }

    /// @notice Partitions active aggregators and approved models into Tier-1 batches
    ///         and creates a single Tier-2 batch from the remaining validators.
    /// @dev Aggregators are filtered to those still Active at call time and shuffled
    ///      using the locked aggSeed (issue #156 H-2) -- fixed at
    ///      closeLMsubmissionsEvaluation, before this function could possibly be
    ///      called, so the caller (model owner) cannot steer batch assignment by
    ///      choosing when to call this. Reverts if fewer than
    ///      T1_AGGREGATORS_PER_BATCH active validators remain, or if fewer than
    ///      T1_MODELS_PER_BATCH models passed, or if the seed isn't locked yet
    ///      (call lockAggSeed first).
    /// @param _GI Current GI index.
    function autoCreateTier1AndTier2(
        uint _GI
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.LMSevaluationClosed)
            revert TC_EvalPhaseNotClosed();
        bytes32 seed = aggSeed[_GI];
        if (seed == bytes32(0)) revert TC_AggSeedNotLocked();

        // Filter the historical registration list down to currently active validators.
        address[] memory valPool = _activeAggregatorPool(_GI);
        uint vLen = valPool.length;
        if (vLen < T1_AGGREGATORS_PER_BATCH) revert TC_NotEnoughValidators();
        // Domain-separated derived seeds so the address and index shuffles
        // don't correlate with each other or with DINTaskAuditor's shuffles
        // (which derive from the independently-locked auditSeed).
        _shuffleAddressArray(valPool, keccak256(abi.encodePacked(seed, "AGG_ADDR")));

        // ▸ 2. Build list of approved model indexes
        uint[] memory modelIdx = _collectApprovedModelIndexes(_GI);
        _shuffleUintArray(modelIdx, keccak256(abi.encodePacked(seed, "AGG_IDX")));

        // ▸ 3. Greedily fill Tier-1 batches
        uint vPtr;
        uint mPtr;
        uint t1cnt;
        while (
            vPtr + T1_AGGREGATORS_PER_BATCH <= valPool.length &&
            (mPtr + T1_MODELS_PER_BATCH <= modelIdx.length ||
                (mPtr + MIN_T1_MODELS_PER_BATCH <= modelIdx.length &&
                    mPtr + T1_MODELS_PER_BATCH > modelIdx.length))
        ) {
            Tier1Batch storage b = tier1Batches[_GI].push();
            b.batchId = t1cnt++;

            for (uint256 k = 0; k < T1_AGGREGATORS_PER_BATCH; k++) {
                b.aggregators.push(valPool[vPtr + k]);
                isTier1Aggregator[_GI][b.batchId][valPool[vPtr + k]] = true;
            }

            uint modelsToAssign = T1_MODELS_PER_BATCH;
            if (modelIdx.length - mPtr < T1_MODELS_PER_BATCH) {
                modelsToAssign = modelIdx.length - mPtr;
            }

            for (uint256 k = 0; k < modelsToAssign; k++) {
                b.modelIndexes.push(modelIdx[mPtr + k]);
            }

            emit Tier1BatchAuto(_GI, b.batchId);

            vPtr += T1_AGGREGATORS_PER_BATCH;
            mPtr += modelsToAssign;
        }

        // ▸ 4. Create Tier-2 batch with EXACTLY T1_AGGREGATORS_PER_BATCH validators if enough remain
        if (valPool.length - vPtr >= T1_AGGREGATORS_PER_BATCH) {
            Tier2Batch storage t2 = tier2Batches[_GI].push();
            t2.batchId = 0;
            for (uint256 k = 0; k < T1_AGGREGATORS_PER_BATCH; k++) {
                t2.aggregators.push(valPool[vPtr + k]);
                isTier2Aggregator[_GI][t2.batchId][valPool[vPtr + k]] = true;
            }

            emit Tier2BatchAuto(_GI, t2.batchId);
        }

        _setGIstate(GIstates.T1nT2Bcreated);
    }

    // ──────────── internal helpers ────────────

    /// @dev Assigns the new GI state and emits GIStateChanged.
    ///      GI is 0 during constructor/setup transitions (ordinals 0–4); expected.
    function _setGIstate(GIstates newState) internal {
        GIstate = newState;
        emit GIStateChanged(GI, uint8(newState));
    }

    // ──────────── internal shuffle helpers ────────────
    function _shuffleAddressArray(address[] memory arr, bytes32 seed) internal pure {
        if (arr.length < 2) return;
        for (uint i = arr.length - 1; i > 0; i--) {
            uint j = uint(
                keccak256(
                    abi.encodePacked(seed, i, arr.length)
                )
            ) % (i + 1);
            (arr[i], arr[j]) = (arr[j], arr[i]);
        }
    }

    function _shuffleUintArray(uint[] memory arr, bytes32 seed) internal pure {
        for (uint i = arr.length - 1; i > 0; i--) {
            uint j = uint(
                keccak256(
                    abi.encodePacked(seed, i, arr.length)
                )
            ) % (i + 1);
            (arr[i], arr[j]) = (arr[j], arr[i]);
        }
    }

    function _collectApprovedModelIndexes(
        uint _GI
    ) internal view returns (uint[] memory out) {
        out = dinTaskAuditorContract.approvedModelIndexes(_GI);
        if (out.length < T1_MODELS_PER_BATCH)
            revert TC_NotEnoughApprovedModels();
    }

    function _activeAggregatorPool(
        uint _GI
    ) internal view returns (address[] memory activePool) {
        address[] storage registeredPool = dinAggregators[_GI];
        uint activeCount;

        for (uint i = 0; i < registeredPool.length; i++) {
            if (
                dinvalidatorStakeContract.isValidatorActive(registeredPool[i])
            ) {
                activeCount++;
            }
        }

        activePool = new address[](activeCount);
        uint ptr;
        for (uint i = 0; i < registeredPool.length; i++) {
            address validator = registeredPool[i];
            if (dinvalidatorStakeContract.isValidatorActive(validator)) {
                activePool[ptr++] = validator;
            }
        }
    }

    // ──────────── read helpers ────────────
    /// @notice Returns the number of Tier-1 batches created for the given GI.
    /// @param _GI GI index to query.
    /// @return Number of Tier-1 batches.
    function tier1BatchCount(uint _GI) external view returns (uint) {
        return tier1Batches[_GI].length;
    }

    /// @notice Returns the full details of a Tier-1 batch.
    /// @param _GI GI index.
    /// @param _id Batch index within that GI.
    /// @return batchId Canonical batch identifier.
    /// @return validators Aggregators assigned to this batch.
    /// @return modelIndexes Indexes into the approved model list assigned to this batch.
    /// @return finalized True once a majority CID has been determined.
    /// @return finalCID The consensus aggregation CID.
    function getTier1Batch(
        uint _GI,
        uint _id
    )
        external
        view
        returns (
            uint batchId,
            address[] memory validators,
            uint[] memory modelIndexes,
            bool finalized,
            bytes32 finalCID
        )
    {
        if (_GI > GI) revert TC_WrongGI();
        if (_id >= tier1Batches[_GI].length) revert TC_BatchNotFound();
        Tier1Batch storage b = tier1Batches[_GI][_id];
        return (
            b.batchId,
            b.aggregators,
            b.modelIndexes,
            b.finalized,
            b.finalCID
        );
    }

    /// @notice Returns the details of the single Tier-2 batch for the given GI.
    /// @dev _id must be 0; there is always exactly one Tier-2 batch per GI.
    /// @param _GI GI index.
    /// @param _id Must be 0.
    /// @return batchId Canonical batch identifier (always 0).
    /// @return validators Aggregators assigned to the Tier-2 batch.
    /// @return finalized True once a majority CID has been determined.
    /// @return finalCID The consensus aggregation CID.
    function getTier2Batch(
        uint _GI,
        uint _id
    )
        external
        view
        returns (
            uint batchId,
            address[] memory validators,
            bool finalized,
            bytes32 finalCID
        )
    {
        if (_id != 0) revert TC_OnlyOneTier2Batch();
        if (_GI > GI) revert TC_WrongGI();
        Tier2Batch storage b = tier2Batches[_GI][_id];
        return (b.batchId, b.aggregators, b.finalized, b.finalCID);
    }

    /// @notice One aggregator's commit-then-reveal state for a T1 or T2 batch.
    /// @dev Replaces the former public t1*/t2* getters (issue #201 Part A).
    ///      `votes` is the vote count of this aggregator's own revealed CID
    ///      (t1Votes/t2Votes are keyed by CID, not by aggregator). Before a
    ///      reveal `cid` is zero, and the zero CID never has votes (reveal
    ///      rejects it with TC_ZeroCID), so `votes` is 0 until the reveal.
    /// @param _GI GI index.
    /// @param tier Tier1 or Tier2.
    /// @param _batchId Batch index (always 0 for Tier2).
    /// @param aggregator Aggregator address.
    /// @return committed True once the aggregator has committed.
    /// @return commitHash The stored commit hash.
    /// @return submitted True once the aggregator has revealed.
    /// @return cid The revealed CID (zero before reveal).
    /// @return votes Votes for `cid` in this batch (zero before reveal).
    function getAggregatorSubmission(
        uint _GI,
        TierKind tier,
        uint _batchId,
        address aggregator
    )
        external
        view
        returns (bool committed, bytes32 commitHash, bool submitted, bytes32 cid, uint votes)
    {
        if (tier == TierKind.Tier1) {
            committed = t1Committed[_GI][_batchId][aggregator];
            commitHash = t1CommitHash[_GI][_batchId][aggregator];
            submitted = t1Submitted[_GI][_batchId][aggregator];
            cid = t1SubmissionCID[_GI][_batchId][aggregator];
            votes = t1Votes[_GI][_batchId][cid];
        } else {
            committed = t2Committed[_GI][_batchId][aggregator];
            commitHash = t2CommitHash[_GI][_batchId][aggregator];
            submitted = t2Submitted[_GI][_batchId][aggregator];
            cid = t2SubmissionCID[_GI][_batchId][aggregator];
            votes = t2Votes[_GI][_batchId][cid];
        }
    }

    /// @notice Transitions GI state to T1AggregationStarted, opening the
    ///         Tier-1 commit window for assigned aggregators
    ///         (commitT1Aggregation).
    /// @param _GI Current GI index.
    function startT1Aggregation(
        uint _GI
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T1nT2Bcreated)
            revert TC_NotReadyForT1Aggregation();
        _setGIstate(GIstates.T1AggregationStarted);
    }

    /// @notice Phase 1 of commit-then-reveal Tier-1 aggregation: lock in a
    ///         hidden aggregation CID.
    /// @dev Caller must be an assigned, active aggregator who has not already
    ///      committed. `commitHash` must equal keccak256(abi.encode(cid,
    ///      salt, msg.sender, GI, TierKind.Tier1, batchId)) for the values
    ///      revealed later -- binding the committer's own address (and GI/
    ///      tier/batchId) into the hash, unlike PR #63's auditor-side
    ///      commitHash, closes the "replay a peer's commit hash and reveal
    ///      their own (cid, salt) under it after they reveal" free-riding
    ///      path (issue #156 M-1). The contract cannot and does not validate
    ///      this at commit time -- that's the point.
    /// @param _GI Current GI index.
    /// @param _batchId Tier-1 batch index.
    /// @param commitHash keccak256(abi.encode(cid, salt, msg.sender, GI, TierKind.Tier1, batchId)).
    function commitT1Aggregation(
        uint _GI,
        uint _batchId,
        bytes32 commitHash
    ) external onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T1AggregationStarted)
            revert TC_T1AggregationNotStarted();
        if (_batchId >= tier1Batches[_GI].length) revert TC_InvalidBatch();
        if (!isTier1Aggregator[_GI][_batchId][msg.sender])
            revert TC_NotBatchAggregator();
        if (!dinvalidatorStakeContract.isValidatorActive(msg.sender)) {
            revert TC_AggregatorNotActive();
        }
        if (commitHash == bytes32(0)) revert TC_T1EmptyCommitHash();
        if (t1Committed[_GI][_batchId][msg.sender])
            revert TC_T1AlreadyCommitted();

        t1CommitHash[_GI][_batchId][msg.sender] = commitHash;
        t1Committed[_GI][_batchId][msg.sender] = true;

        emit T1AggregationCommitted(_GI, _batchId, msg.sender, commitHash);
    }

    /// @notice Closes the T1 commit window and opens the reveal window so
    ///         assigned aggregators can call revealT1Aggregation.
    /// @dev Must run strictly after commits close and before any reveal is
    ///      accepted -- see revealT1Aggregation's GIstate gate.
    /// @param _GI Current GI index.
    function startT1AggregationReveal(
        uint _GI
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T1AggregationStarted)
            revert TC_T1RevealCannotBeStarted();
        _setGIstate(GIstates.T1AggregationRevealStarted);
    }

    /// @notice Phase 2 of commit-then-reveal: reveal the (cid, salt) behind a
    ///         prior commitment and have it counted.
    /// @dev Reverts unless the caller committed for this (GI, batchId) and the
    ///      revealed values hash to that commitment. Open only while
    ///      GIstate == T1AggregationRevealStarted, strictly after the commit
    ///      window has been closed by the model owner. An aggregator who
    ///      committed but never reveals simply never sets t1Submitted, so
    ///      they're excluded from finalization and remain slashable via the
    ///      existing slashAggregators() "no submission" (S2) check -- no
    ///      special-casing needed for the non-reveal case.
    /// @param _GI Current GI index.
    /// @param _batchId Tier-1 batch index.
    /// @param _aggregationCID IPFS CID of the aggregated model weights, encoded as bytes32.
    /// @param salt Arbitrary value chosen at commit time to prevent hash pre-image search.
    function revealT1Aggregation(
        uint _GI,
        uint _batchId,
        bytes32 _aggregationCID,
        bytes32 salt
    ) external onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T1AggregationRevealStarted)
            revert TC_T1RevealPhaseNotOpen();
        if (_batchId >= tier1Batches[_GI].length) revert TC_InvalidBatch();

        // Verify sender is an assigned aggregator
        if (!isTier1Aggregator[_GI][_batchId][msg.sender])
            revert TC_NotBatchAggregator();
        if (!dinvalidatorStakeContract.isValidatorActive(msg.sender)) {
            revert TC_AggregatorNotActive();
        }
        if (!t1Committed[_GI][_batchId][msg.sender]) revert TC_T1NoCommitFound();
        if (t1Submitted[_GI][_batchId][msg.sender])
            revert TC_AlreadySubmitted();
        if (_aggregationCID == bytes32(0)) revert TC_ZeroCID();

        bytes32 expectedHash = keccak256(
            abi.encode(_aggregationCID, salt, msg.sender, _GI, TierKind.Tier1, _batchId)
        );
        if (expectedHash != t1CommitHash[_GI][_batchId][msg.sender])
            revert TC_T1RevealHashMismatch();

        t1Submitted[_GI][_batchId][msg.sender] = true;
        t1SubmissionCID[_GI][_batchId][msg.sender] = _aggregationCID;
        emit T1AggregationSubmitted(_GI, _batchId, msg.sender, _aggregationCID);

        // Increment vote count
        t1Votes[_GI][_batchId][_aggregationCID]++;
    }

    /// @notice Closes the Tier-1 reveal window and selects the majority CID
    ///         for every batch.
    /// @dev Iterates all T1 batches; reverts on the first batch that has no submissions.
    /// @param _GI Current GI index.
    function finalizeT1Aggregation(
        uint _GI
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T1AggregationRevealStarted)
            revert TC_NotReadyToFinalizeT1();

        Tier1Batch[] storage batches = tier1Batches[_GI];

        for (uint i = 0; i < batches.length; i++) {
            Tier1Batch storage b = batches[i];

            // Determine the CID with the most votes
            bytes32 winningCID = "";
            uint maxVotes = 0;
            uint submissionCount = 0;

            for (uint j = 0; j < b.aggregators.length; j++) {
                address aggregator = b.aggregators[j];
                if (t1Submitted[_GI][b.batchId][aggregator]) {
                    submissionCount++;
                    bytes32 cid = t1SubmissionCID[_GI][b.batchId][aggregator];
                    uint votes = t1Votes[_GI][b.batchId][cid];
                    if (votes > maxVotes) {
                        maxVotes = votes;
                        winningCID = cid;
                    }
                }

                // BL-10 (#125): one settlement-weight unit per assigned
                // aggregator in this batch, unconditional on consensus
                // match -- same basis _collectFinalizedBatchAggregators
                // used. Safe to write unconditionally here because the
                // whole call reverts atomically (TC_NoSubmissions /
                // TC_InsufficientSubmissions below) if any batch fails to
                // finalize, so no weight persists for a non-finalized batch.
                aggregatorWeight[_GI][aggregator]++;
                totalAggregatorWeight[_GI]++;
            }

            if (winningCID == bytes32(0)) revert TC_NoSubmissions();
            if (submissionCount < T1_AGGREGATORS_PER_BATCH / 2 + 1)
                revert TC_InsufficientSubmissions();
            b.finalized = true;
            b.finalCID = winningCID;
            tier1FinalizedAt[_GI][b.batchId] = uint64(block.timestamp);
            emit T1BatchFinalized(_GI, b.batchId, winningCID);
        }

        _setGIstate(GIstates.T1AggregationDone);
    }

    /// @notice Opens the Tier-2 aggregation commit window
    ///         (commitT2Aggregation).
    /// @param _GI Current GI index.
    function startT2Aggregation(
        uint _GI
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T1AggregationDone)
            revert TC_NotReadyForT2Aggregation();
        _setGIstate(GIstates.T2AggregationStarted);
    }

    /// @notice Phase 1 of commit-then-reveal Tier-2 aggregation: lock in a
    ///         hidden aggregation CID.
    /// @dev Same sender-bound commit-hash hardening as commitT1Aggregation
    ///      (issue #156 M-1); see that function's NatSpec.
    /// @param _GI Current GI index.
    /// @param _batchId Must be 0.
    /// @param commitHash keccak256(abi.encode(cid, salt, msg.sender, GI, TierKind.Tier2, batchId)).
    function commitT2Aggregation(
        uint _GI,
        uint _batchId,
        bytes32 commitHash
    ) external onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T2AggregationStarted)
            revert TC_T2AggregationNotStarted();
        if (_batchId != 0) revert TC_OnlyOneTier2Batch();
        if (!isTier2Aggregator[_GI][_batchId][msg.sender])
            revert TC_NotBatchAggregator();
        if (!dinvalidatorStakeContract.isValidatorActive(msg.sender)) {
            revert TC_AggregatorNotActive();
        }
        if (commitHash == bytes32(0)) revert TC_T2EmptyCommitHash();
        if (t2Committed[_GI][_batchId][msg.sender])
            revert TC_T2AlreadyCommitted();

        t2CommitHash[_GI][_batchId][msg.sender] = commitHash;
        t2Committed[_GI][_batchId][msg.sender] = true;

        emit T2AggregationCommitted(_GI, _batchId, msg.sender, commitHash);
    }

    /// @notice Closes the T2 commit window and opens the reveal window so
    ///         assigned aggregators can call revealT2Aggregation.
    /// @param _GI Current GI index.
    function startT2AggregationReveal(
        uint _GI
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T2AggregationStarted)
            revert TC_T2RevealCannotBeStarted();
        _setGIstate(GIstates.T2AggregationRevealStarted);
    }

    /// @notice Phase 2 of commit-then-reveal: reveal the (cid, salt) behind a
    ///         prior commitment and have it counted.
    /// @dev _batchId must be 0. Same non-reveal handling as revealT1Aggregation
    ///      (see its NatSpec) -- a committed-but-never-revealed aggregator
    ///      simply never sets t2Submitted, and remains slashable via
    ///      slashAggregators()'s existing "no submission" (S2) check.
    /// @param _GI Current GI index.
    /// @param _batchId Must be 0.
    /// @param _aggregationCID IPFS CID of the final aggregated model, encoded as bytes32.
    /// @param salt Arbitrary value chosen at commit time to prevent hash pre-image search.
    function revealT2Aggregation(
        uint _GI,
        uint _batchId,
        bytes32 _aggregationCID,
        bytes32 salt
    ) external onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T2AggregationRevealStarted)
            revert TC_T2RevealPhaseNotOpen();
        if (_batchId != 0) revert TC_OnlyOneTier2Batch();

        if (!isTier2Aggregator[_GI][_batchId][msg.sender])
            revert TC_NotBatchAggregator();
        if (!dinvalidatorStakeContract.isValidatorActive(msg.sender)) {
            revert TC_AggregatorNotActive();
        }
        if (!t2Committed[_GI][_batchId][msg.sender]) revert TC_T2NoCommitFound();
        if (t2Submitted[_GI][_batchId][msg.sender])
            revert TC_AlreadySubmitted();
        if (_aggregationCID == bytes32(0)) revert TC_ZeroCID();

        bytes32 expectedHash = keccak256(
            abi.encode(_aggregationCID, salt, msg.sender, _GI, TierKind.Tier2, _batchId)
        );
        if (expectedHash != t2CommitHash[_GI][_batchId][msg.sender])
            revert TC_T2RevealHashMismatch();

        t2Submitted[_GI][_batchId][msg.sender] = true;
        t2SubmissionCID[_GI][_batchId][msg.sender] = _aggregationCID;
        emit T2AggregationSubmitted(_GI, _batchId, msg.sender, _aggregationCID);

        // Increment vote count
        t2Votes[_GI][_batchId][_aggregationCID]++;
    }

    /// @notice Closes the Tier-2 reveal window and selects the majority CID.
    /// @dev Reverts if the Tier-2 batch has received no submissions.
    /// @param _GI Current GI index.
    function finalizeT2Aggregation(
        uint _GI
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T2AggregationRevealStarted)
            revert TC_NotReadyToFinalizeT2();

        Tier2Batch[] storage batches = tier2Batches[_GI];

        for (uint i = 0; i < batches.length; i++) {
            Tier2Batch storage b = batches[i];

            // Determine the CID with the most votes
            bytes32 winningCID = "";
            uint maxVotes = 0;
            uint submissionCount = 0;

            for (uint j = 0; j < b.aggregators.length; j++) {
                address aggregator = b.aggregators[j];
                if (t2Submitted[_GI][b.batchId][aggregator]) {
                    submissionCount++;
                    bytes32 cid = t2SubmissionCID[_GI][b.batchId][aggregator];
                    uint votes = t2Votes[_GI][b.batchId][cid];
                    if (votes > maxVotes) {
                        maxVotes = votes;
                        winningCID = cid;
                    }
                }

                // BL-10 (#125): see the matching comment in
                // finalizeT1Aggregation -- an aggregator assigned to both a
                // finalized T1 batch and the finalized T2 batch accrues
                // weight from each, exactly as the pre-#125 duplicate
                // array entry did.
                aggregatorWeight[_GI][aggregator]++;
                totalAggregatorWeight[_GI]++;
            }

            if (winningCID == bytes32(0)) revert TC_NoSubmissions();
            if (submissionCount < T1_AGGREGATORS_PER_BATCH / 2 + 1)
                revert TC_InsufficientSubmissions();
            b.finalized = true;
            b.finalCID = winningCID;
            tier2FinalizedAt[_GI][b.batchId] = uint64(block.timestamp);
            emit T2Finalized(_GI, winningCID);
        }

        _setGIstate(GIstates.T2AggregationDone);
    }

    /// @notice Triggers auditor slashing on the paired DINTaskAuditor contract.
    /// @dev Reverts if DINTaskAuditor.slashAuditors returns false.
    /// @param _GI Current GI index.
    function slashAuditors(uint _GI) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T2AggregationDone)
            revert TC_NotReadyToSlashAuditors();
        bool success = dinTaskAuditorContract.slashAuditors(_GI);
        if (!success) revert TC_FailedToSlashAuditors();
        _setGIstate(GIstates.AuditorsSlashed);
    }

    /// @notice Slashes aggregators in both Tier-1 and Tier-2 batches that failed
    ///         to submit or submitted a CID that did not match the consensus.
    /// @dev No submission (including committed but never revealed) is an S2
    ///      liveness fault slashed at s2SlashFractionBps of minStake(); a CID
    ///      that differs from the batch's finalCID is slashed the full
    ///      minStake(). Each affected aggregator emits an AggregatorSlashed
    ///      event with the actual amount deducted. See _slashBatch.
    /// @param _GI Current GI index.
    function slashAggregators(uint _GI) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.AuditorsSlashed)
            revert TC_NotReadyToSlashAggregators();

        uint256 minStakeAmt = dinvalidatorStakeContract.minStake();
        // S2: partial fraction for liveness fault (no submission); BAD_CONSENSUS keeps full.
        uint256 s2Amount = (minStakeAmt * s2SlashFractionBps) / 10_000;

        Tier1Batch[] storage t1batches = tier1Batches[_GI];
        for (uint i = 0; i < t1batches.length; i++) {
            Tier1Batch storage b = t1batches[i];
            _slashBatch(_GI, b.batchId, b.aggregators, b.finalCID, minStakeAmt, s2Amount, false);
        }
        Tier2Batch[] storage t2batches = tier2Batches[_GI];
        for (uint i = 0; i < t2batches.length; i++) {
            Tier2Batch storage b = t2batches[i];
            _slashBatch(_GI, b.batchId, b.aggregators, b.finalCID, minStakeAmt, s2Amount, true);
        }

        _setGIstate(GIstates.AggregatorsSlashed);
    }

    /// @dev Slashes one T1 or T2 batch's aggregators for slashAggregators
    ///      (one body for both tiers keeps this contract under EIP-170, issue
    ///      #201 Part A). No submission is an S2 liveness fault: partial slash
    ///      plus S5/S6 tracking, skipped when rounding makes s2Amount 0
    ///      (slashPartial reverts InvalidSlashAmount on zero, bricking the GI).
    ///      No S6 recordNoParticipation here: slashPartial already penalises
    ///      the missed submission, and also firing S6 could slash more than
    ///      MIN_STAKE in one event. A submitted CID that differs from the
    ///      batch's finalCID is BAD_CONSENSUS: full-severity slash.
    function _slashBatch(
        uint _GI,
        uint batchId,
        address[] storage aggs,
        bytes32 finalCID,
        uint256 minStakeAmt,
        uint256 s2Amount,
        bool t2
    ) internal {
        bytes32 noSubmission = "AGG_T1_NO_SUBMISSION";
        bytes32 badConsensus = "AGG_T1_BAD_CONSENSUS";
        if (t2) {
            noSubmission = "AGG_T2_NO_SUBMISSION";
            badConsensus = "AGG_T2_BAD_CONSENSUS";
        }
        for (uint j = 0; j < aggs.length; j++) {
            address aggregator = aggs[j];
            bool submitted = t2
                ? t2Submitted[_GI][batchId][aggregator]
                : t1Submitted[_GI][batchId][aggregator];
            if (!submitted) {
                uint256 actualSlashed = s2Amount > 0
                    ? dinvalidatorStakeContract.slashPartial(aggregator, s2Amount, noSubmission, _GI)
                    : 0;
                emit AggregatorSlashed(_GI, batchId, aggregator, noSubmission, s2Amount, actualSlashed);
            } else {
                bytes32 cid = t2
                    ? t2SubmissionCID[_GI][batchId][aggregator]
                    : t1SubmissionCID[_GI][batchId][aggregator];
                if (cid != finalCID) {
                    uint256 actualSlashed = dinvalidatorStakeContract.slash(aggregator, minStakeAmt, badConsensus);
                    emit AggregatorSlashed(_GI, batchId, aggregator, badConsensus, minStakeAmt, actualSlashed);
                }
            }
        }
    }

    /// @notice Records the Tier-2 aggregation quality score for the current GI.
    /// @dev Permitted during T2AggregationDone or GenesisModelCreated states.
    /// @param _GI Current GI index.
    /// @param _score Quality score for the Tier-2 aggregated model.
    function setTier2Score(
        uint _GI,
        uint _score
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (
            GIstate != GIstates.T2AggregationDone &&
            GIstate != GIstates.GenesisModelCreated
        ) revert TC_NotReadyToSetTier2Score();
        tier2Score[_GI] = _score;
    }

    /// @notice Returns the Tier-2 quality score recorded for the given GI.
    /// @param _GI GI index to query.
    /// @return The score set via setTier2Score for that GI.
    function getTier2Score(uint _GI) external view returns (uint) {
        return tier2Score[_GI];
    }

    /// @notice Marks the current Global Iteration as complete and settles
    ///         its reward pool.
    /// @dev Must be called after slashAggregators. Delegates the actual
    ///      client/auditor/aggregator/treasury split computation to
    ///      DINTaskAuditor.settleRewards (task_210726_6 §3) -- that contract
    ///      owns the client/auditor data (lmSubmissions, audit batches) this
    ///      contract doesn't have, and owns the giRewardPool/claimable
    ///      accounting so all three roles claim from one place.
    ///
    ///      This contract owns the T1/T2 aggregator batch data. Rather than
    ///      pass a per-(aggregator, finalized-batch) address list across the
    ///      interface (the pre-#125 shape, whose length was the settlement
    ///      divisor), it now passes only the scalar totalAggregatorWeight[_GI]
    ///      -- accumulated incrementally in finalizeT1Aggregation /
    ///      finalizeT2Aggregation. settleRewards snapshots it; claimReward
    ///      reads each aggregator's own aggregatorWeight[_GI][addr] from this
    ///      contract at claim time. No participant loop runs in either
    ///      settleRewards or endGI (BL-10).
    ///
    ///      The next startGI call will increment GI and transition state to
    ///      GIstarted.
    /// @param _GI Current GI index.
    function endGI(uint _GI) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.AggregatorsSlashed) revert TC_NotReadyToEndGI();

        dinTaskAuditorContract.settleRewards(_GI, totalAggregatorWeight[_GI]);

        _setGIstate(GIstates.GIended);
    }

    /// @notice Decrements the concurrent-registration counter on DinValidatorStake
    ///         for every aggregator and auditor that participated in the given GI.
    /// @dev Separated from endGI (task_100926_12 §#37) to keep endGI O(1) (BL-10).
    ///      Call after endGI for each ended GI. O(n_aggregators + n_auditors), bounded
    ///      by MAX_REGISTERED_AGGREGATORS and MAX_REGISTERED_AUDITORS. Idempotent
    ///      guard: reverts on a second call for the same GI (registrationSlotsReleased).
    /// @param _GI GI whose participants' registration slots should be released.
    ///            Must be a GI that has already ended (< current GI, or == current GI
    ///            with state GIended).
    function releaseGIRegistrationSlots(uint _GI) external onlyOwner {
        bool giEnded = (_GI < GI) ||
            (_GI == GI && GIstate == GIstates.GIended);
        require(giEnded, "GI has not ended");
        require(!registrationSlotsReleased[_GI], "slots already released");
        registrationSlotsReleased[_GI] = true;

        address[] storage aggs = dinAggregators[_GI];
        for (uint256 i = 0; i < aggs.length; i++) {
            dinvalidatorStakeContract.decrementActiveRegistration(aggs[i]);
        }
        dinTaskAuditorContract.decrementAuditorRegistrations(_GI);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Dispute resolution scaffold (task_210726_6 §4c, issue #38, S4)
    // ─────────────────────────────────────────────────────────────────────

    /// @notice Sets the ERC20 token used for dispute bonds.
    /// @param _dinToken Address of the DinToken proxy.
    function setDinToken(address _dinToken) external onlyOwner {
        if (_dinToken == address(0)) revert TC_InvalidAddress();
        dinToken = IERC20(_dinToken);
    }

    /// @notice Sets the four dispute timing/bond parameters.
    /// @param _disputeBond       Token amount a challenger must post to open a dispute.
    /// @param _disputeWindow     Seconds after batch finalization during which a dispute can be opened.
    /// @param _resolutionWindow  Seconds the fresh subgroup has to recompute after being assigned.
    /// @param _disputeSeedDelay  Blocks after openDispute before the seed can be locked (1–256,
    ///                           within the blockhash window).
    function setDisputeParams(
        uint256 _disputeBond,
        uint64 _disputeWindow,
        uint64 _resolutionWindow,
        uint64 _disputeSeedDelay
    ) external onlyOwner {
        if (
            _disputeBond == 0 ||
            _disputeWindow == 0 ||
            _resolutionWindow == 0 ||
            _disputeSeedDelay == 0 ||
            _disputeSeedDelay > 256
        ) revert TC_InvalidDisputeParams();
        disputeBond = _disputeBond;
        disputeWindow = _disputeWindow;
        resolutionWindow = _resolutionWindow;
        disputeSeedDelay = _disputeSeedDelay;
    }

    /// @notice Updates the S2 liveness-fault slash fraction.
    /// @dev Only affects AGG_T*_NO_SUBMISSION slashes. BAD_CONSENSUS slashes
    ///      keep the full minStake() amount regardless of this setting.
    ///      Setting to 10000 restores the previous flat-minStake behavior.
    /// @param bps New fraction in basis points (1–10000).
    function setS2SlashFractionBps(uint256 bps) external onlyOwner {
        if (bps == 0 || bps > 10_000) revert TC_InvalidSlashFraction();
        uint256 old = s2SlashFractionBps;
        s2SlashFractionBps = bps;
        emit S2SlashFractionBpsUpdated(old, bps);
    }

    /// @notice Sets the minimum gas-cost floor (in gas units) each validator must
    ///         be covered for per GI.  The DAO reads the measured number from
    ///         GasSimulation tests and posts it here; model owners should deposit
    ///         enough rewards to cover `networkFeeFloor × nValidators` before GI start.
    /// @param _floor Gas units derived from `commitAuditScore + revealAuditScore`
    ///               measurements (worst-case auditor path per GasSimulation S2).
    function setNetworkFeeFloor(uint256 _floor) external onlyOwner {
        networkFeeFloor = _floor;
    }

    /// @notice Opens a dispute against a finalized Tier-1 or Tier-2 batch.
    /// @dev Caller must be an active validator and post `disputeBond` DIN,
    ///      within `disputeWindow` seconds of the batch's finalization.
    ///      Adjudication happens off-chain today (resolveDispute is
    ///      onlyOwner) -- see the scaffold-wide comment above the state
    ///      declarations for why.
    /// @param _GI GI index the batch belongs to.
    /// @param tierKind Whether the batch is a Tier-1 or Tier-2 batch.
    /// @param batchId Index of the batch within its tier for that GI.
    function openDispute(
        uint _GI,
        TierKind tierKind,
        uint batchId
    ) external nonReentrant {
        if (_GI == 0 || _GI > GI) revert TC_WrongGI();
        if (!dinvalidatorStakeContract.isValidatorActive(msg.sender)) {
            revert TC_AggregatorNotActive();
        }

        bool finalized;
        uint64 finalizedAt;
        if (tierKind == TierKind.Tier1) {
            if (batchId >= tier1Batches[_GI].length) revert TC_InvalidBatch();
            finalized = tier1Batches[_GI][batchId].finalized;
            finalizedAt = tier1FinalizedAt[_GI][batchId];
        } else {
            if (batchId >= tier2Batches[_GI].length) revert TC_InvalidBatch();
            finalized = tier2Batches[_GI][batchId].finalized;
            finalizedAt = tier2FinalizedAt[_GI][batchId];
        }
        if (!finalized) revert TC_BatchNotFinalized();
        if (block.timestamp > finalizedAt + disputeWindow) {
            revert TC_DisputeWindowClosed();
        }
        if (disputes[_GI][tierKind][batchId].challenger != address(0)) {
            revert TC_DisputeAlreadyOpen();
        }

        disputes[_GI][tierKind][batchId] = Dispute({
            challenger: msg.sender,
            bond: disputeBond,
            openedAt: uint64(block.timestamp),
            resolutionDeadline: 0,
            seedBlock: uint64(block.number) + disputeSeedDelay,
            resolved: false,
            upheld: false,
            finalized: false,
            seed: bytes32(0)
        });

        dinToken.safeTransferFrom(msg.sender, address(this), disputeBond);

        emit DisputeOpened(_GI, tierKind, batchId, msg.sender, disputeBond);
    }

    /// @notice Permissionless: locks the entropy seed for an open dispute.
    /// @dev Anyone can call this once `block.number > d.seedBlock`. The seed is
    ///      derived from `blockhash(d.seedBlock)`, which nobody can predict when
    ///      the dispute opens and nobody can choose once the block is mined —
    ///      so neither the model owner nor the challenger can steer the subgroup.
    ///
    ///      256-block edge: if `blockhash(d.seedBlock)` returns 0 (more than 256
    ///      blocks have elapsed since `seedBlock` was set), the function re-anchors
    ///      to a fresh future block instead of recording a zero-derived seed. The
    ///      party who dislikes the eventual draw cannot stop any honest validator
    ///      from locking the seed first, so re-anchoring is not a free re-roll.
    function lockDisputeSeed(
        uint _GI,
        TierKind tierKind,
        uint batchId
    ) external {
        Dispute storage d = disputes[_GI][tierKind][batchId];
        if (d.challenger == address(0)) revert TC_DisputeNotOpen();
        if (d.resolved) revert TC_DisputeAlreadyResolved();
        if (d.seed != bytes32(0)) revert TC_DisputeSeedAlreadyLocked();
        if (block.number <= d.seedBlock) revert TC_DisputeSeedBlockNotMined();

        bytes32 bh = blockhash(d.seedBlock);
        if (bh == bytes32(0)) {
            // >256 blocks since seedBlock — re-anchor to a fresh future block.
            d.seedBlock = uint64(block.number) + disputeSeedDelay;
            emit DisputeSeedReanchored(_GI, tierKind, batchId, d.seedBlock);
            return;
        }

        d.seed = keccak256(abi.encodePacked(bh, _GI, uint8(tierKind), batchId));
        emit DisputeSeedLocked(_GI, tierKind, batchId, d.seed);
    }

    /// @notice Permissionless: locks the entropy seed for the current GI's
    ///         Tier-1/Tier-2 batch assignment (issue #156 H-2).
    /// @dev Same shape as lockDisputeSeed: anyone may call once
    ///      `block.number > aggSeedBlock[_GI]`; the seed derives from
    ///      `blockhash(aggSeedBlock[_GI])`, fixed before autoCreateTier1AndTier2
    ///      could possibly run (anchored in closeLMsubmissionsEvaluation), so
    ///      the model owner cannot pick a favourable block to call it in.
    ///      Re-anchors on the same >256-block edge; never locks a zero seed.
    ///      Trust caveat: as with the dispute seed, this trusts the OP Stack
    ///      sequencer not to grind `blockhash` -- acceptable for DevNet/
    ///      testnet, VRF is the mainnet-grade follow-up.
    function lockAggSeed(uint _GI) external onlyCurrentGI(_GI) {
        uint64 seedBlock = aggSeedBlock[_GI];
        if (seedBlock == 0) revert TC_AggSeedNotAnchored();
        if (aggSeed[_GI] != bytes32(0)) revert TC_AggSeedAlreadyLocked();
        if (block.number <= seedBlock) revert TC_AggSeedBlockNotMined();

        bytes32 bh = blockhash(seedBlock);
        if (bh == bytes32(0)) {
            aggSeedBlock[_GI] = uint64(block.number) + disputeSeedDelay;
            emit AggSeedReanchored(_GI, aggSeedBlock[_GI]);
            return;
        }

        aggSeed[_GI] = keccak256(abi.encodePacked(bh, _GI, "AGG"));
        emit AggSeedLocked(_GI, aggSeed[_GI]);
    }

    /// @notice Permissionless: locks the entropy seed for the current GI's
    ///         auditor batch assignment (issue #156 H-2).
    /// @dev Mirrors lockAggSeed exactly; anchored in closeLMsubmissions since
    ///      that's the transition that gates createAuditorsBatches. The
    ///      locked seed is read by createAuditorsBatches below and passed
    ///      across the interface to DINTaskAuditor.createAuditorsBatches,
    ///      which owns the actual shuffle.
    function lockAuditSeed(uint _GI) external onlyCurrentGI(_GI) {
        uint64 seedBlock = auditSeedBlock[_GI];
        if (seedBlock == 0) revert TC_AuditSeedNotAnchored();
        if (auditSeed[_GI] != bytes32(0)) revert TC_AuditSeedAlreadyLocked();
        if (block.number <= seedBlock) revert TC_AuditSeedBlockNotMined();

        bytes32 bh = blockhash(seedBlock);
        if (bh == bytes32(0)) {
            auditSeedBlock[_GI] = uint64(block.number) + disputeSeedDelay;
            emit AuditSeedReanchored(_GI, auditSeedBlock[_GI]);
            return;
        }

        auditSeed[_GI] = keccak256(abi.encodePacked(bh, _GI, "AUD"));
        emit AuditSeedLocked(_GI, auditSeed[_GI]);
    }

    /// @dev Burns 50% of `amount` and forwards 50% to the platform slash-treasury
    ///      (`dinvalidatorStakeContract.slashTreasury()`). Burns both halves when
    ///      the slash-treasury is unset, mirroring DinValidatorStake.slash() behaviour.
    ///      Also increments `treasuryAccrued` by the full amount for observability.
    function _burnAndForward(uint256 amount) internal {
        if (amount == 0) return;
        uint256 burnAmt = amount / 2;
        uint256 fwdAmt  = amount - burnAmt;
        IBurnableDinToken(address(dinToken)).burn(burnAmt);
        address treasury = dinvalidatorStakeContract.slashTreasury();
        if (treasury != address(0)) {
            dinToken.safeTransfer(treasury, fwdAmt);
        } else {
            IBurnableDinToken(address(dinToken)).burn(fwdAmt);
        }
        treasuryAccrued += amount;
    }

    /// @notice Resolves a dispute, either upholding or rejecting it.
    /// @dev Upheld: a fresh aggregator subgroup is assigned and the
    ///      resolution clock starts; the bond credit is deferred to
    ///      settleRecomputation()/expireDispute() rather than paid here (see
    ///      those functions' NatSpec). Bounty top-up (task_100926_12 #43):
    ///      out of scope — DinTreasury's withdrawERC20 is onlyOwner, so task
    ///      contracts cannot pull a bounty from it. The challenger currently
    ///      only reclaims their bond. Flagged for Umer: the fix requires
    ///      either an authorized-withdrawer role on DinTreasury or an
    ///      alternate bounty source (forfeited-stake pool).
    ///      Rejected (frivolous): fully closed immediately — bond is split
    ///      50% burn / 50% treasury per MECHANISM_DESIGN.md §4.
    ///      treasuryAccrued accumulates the full bond for observability.
    /// @param _GI GI index the disputed batch belongs to.
    /// @param tierKind Whether the batch is a Tier-1 or Tier-2 batch.
    /// @param batchId Index of the disputed batch within its tier.
    /// @param upheld True if the dispute is found valid.
    function resolveDispute(
        uint _GI,
        TierKind tierKind,
        uint batchId,
        bool upheld
    ) external onlyOwner {
        Dispute storage d = disputes[_GI][tierKind][batchId];
        if (d.challenger == address(0)) revert TC_DisputeNotOpen();
        if (d.resolved) revert TC_DisputeAlreadyResolved();

        d.resolved = true;
        d.upheld = upheld;

        if (upheld) {
            // Require a locked seed before assigning the fresh subgroup.
            // lockDisputeSeed must be called first so the subgroup draw
            // cannot be steered by timing resolveDispute to a favourable block.
            if (d.seed == bytes32(0)) revert TC_DisputeSeedNotLocked();

            // Assign fresh subgroup and start the resolution clock.
            // Bond credit is deferred: the challenger gets it back in
            // settleRecomputation(confirmed=true) or expireDispute(). If the
            // fresh subgroup's recomputation clears the original CID the bond
            // is forfeited in settleRecomputation(confirmed=false) instead.
            // (Bounty top-up from treasury: out of scope, see NatSpec above.)
            d.resolutionDeadline = uint64(block.timestamp) + resolutionWindow;

            address[] memory freshSubgroup = _assignFreshSubgroup(
                _GI,
                tierKind,
                batchId,
                d.seed
            );
            reEvaluationAssignees[_GI][tierKind][batchId] = freshSubgroup;
            emit ReEvaluationAssigned(_GI, tierKind, batchId, freshSubgroup);
        } else {
            // Immediate rejection: dispute is fully closed, no Phase-2 needed.
            d.finalized = true;

            // Frivolous forfeiture: 50% burn / 50% platform treasury (MECHANISM_DESIGN §4).
            _burnAndForward(d.bond);
        }

        emit DisputeResolved(_GI, tierKind, batchId, upheld);
    }

    /// @notice Claims a reclaimed dispute bond after an upheld dispute.
    /// @dev Pull payment: zeroes the balance before transferring (CEI).
    function claimDisputeBond() external nonReentrant {
        uint256 amount = disputeBondClaimable[msg.sender];
        if (amount == 0) revert TC_NoBondClaimable();

        disputeBondClaimable[msg.sender] = 0;
        dinToken.safeTransfer(msg.sender, amount);

        emit DisputeBondClaimed(msg.sender, amount);
    }

    /// @notice Final verdict after the fresh subgroup has recomputed.
    ///         Owner calls this as the normal adjudication path (within the
    ///         resolution window) or as a last-resort fallback after it
    ///         (e.g. if the fresh subgroup itself produced no quorum).
    ///         confirmed=true slashes only the original batch's aggregators
    ///         whose own submission matched the disputed `finalCID` --
    ///         dissenters and non-submitters are excluded (the latter are
    ///         already penalized separately via slashAggregators()).
    ///
    /// @param _GI       GI index.
    /// @param tierKind  Tier-1 or Tier-2.
    /// @param batchId   Batch index within its tier.
    /// @param confirmed True if the fresh subgroup's recomputation confirmed
    ///                  the original CID was wrong (dispute stands).
    ///                  False if recomputation matched the original CID
    ///                  (original aggregators were right, dispute dismissed).
    function settleRecomputation(
        uint _GI,
        TierKind tierKind,
        uint batchId,
        bool confirmed
    ) external onlyOwner {
        Dispute storage d = disputes[_GI][tierKind][batchId];
        if (!(d.resolved && d.upheld)) revert TC_DisputeNotAwaitingRecomputation();
        if (d.finalized) revert TC_DisputeAlreadyFinalized();

        d.finalized = true;

        if (confirmed) {
            // Recomputation confirmed the original CID was wrong.
            // Return challenger's bond and slash only the aggregators whose
            // submission actually matched the disputed finalCID -- honest
            // dissenters (submitted a different CID) are not at fault, and
            // non-submitters are already penalized separately via
            // AGG_T1_NO_SUBMISSION/AGG_T2_NO_SUBMISSION in slashAggregators();
            // slashing them again here would double-penalize the same fault.
            disputeBondClaimable[d.challenger] += d.bond;

            address[] memory originalAggs = tierKind == TierKind.Tier1
                ? tier1Batches[_GI][batchId].aggregators
                : tier2Batches[_GI][batchId].aggregators;
            bytes32 disputedCID = tierKind == TierKind.Tier1
                ? tier1Batches[_GI][batchId].finalCID
                : tier2Batches[_GI][batchId].finalCID;
            uint256 slashAmount = dinvalidatorStakeContract.minStake();
            for (uint i = 0; i < originalAggs.length; i++) {
                bytes32 submittedCID = tierKind == TierKind.Tier1
                    ? t1SubmissionCID[_GI][batchId][originalAggs[i]]
                    : t2SubmissionCID[_GI][batchId][originalAggs[i]];
                if (submittedCID != disputedCID) continue;

                uint256 actual = dinvalidatorStakeContract.slash(
                    originalAggs[i],
                    slashAmount,
                    "S4_INVALID_AGGREGATION"
                );
                emit AggregatorSlashed(
                    _GI, batchId, originalAggs[i],
                    "S4_INVALID_AGGREGATION", slashAmount, actual
                );
            }
        } else {
            // Recomputation matched the original CID — dispute was wrong.
            // Forfeit challenger's bond: 50% burn / 50% platform treasury (MECHANISM_DESIGN §4).
            _burnAndForward(d.bond);
        }

        emit RecomputationSettled(_GI, tierKind, batchId, confirmed);
    }

    /// @notice Times out a dispute whose fresh subgroup did not recompute
    ///         within the resolution window.
    ///         Callable by anyone after the resolution deadline — silence is
    ///         not free for the fresh subgroup.
    ///
    ///         Outcome: dispute dismissed (original CID stands); challenger
    ///         bond returned (the fault is the fresh subgroup's, not theirs);
    ///         fresh subgroup slashed for liveness failure.
    function expireDispute(
        uint _GI,
        TierKind tierKind,
        uint batchId
    ) external {
        Dispute storage d = disputes[_GI][tierKind][batchId];
        if (!(d.resolved && d.upheld)) revert TC_DisputeNotAwaitingRecomputation();
        if (d.finalized) revert TC_DisputeAlreadyFinalized();
        if (block.timestamp <= d.resolutionDeadline) revert TC_ResolutionWindowOpen();

        d.finalized = true;

        // Return challenger's bond — they acted in good faith.
        disputeBondClaimable[d.challenger] += d.bond;

        // Slash every member of the fresh subgroup for liveness failure.
        address[] memory freshSubgroup = reEvaluationAssignees[_GI][tierKind][batchId];
        uint256 slashAmount = dinvalidatorStakeContract.minStake();
        for (uint i = 0; i < freshSubgroup.length; i++) {
            uint256 actual = dinvalidatorStakeContract.slash(
                freshSubgroup[i],
                slashAmount,
                "S4_FRESH_SUBGROUP_TIMEOUT"
            );
            emit AggregatorSlashed(
                _GI, batchId, freshSubgroup[i],
                "S4_FRESH_SUBGROUP_TIMEOUT", slashAmount, actual
            );
        }

        emit DisputeExpired(_GI, tierKind, batchId);
    }

    /// @notice Selects a fresh aggregator subgroup for re-evaluation, excluding
    ///         the accused batch's original aggregators.
    /// @dev Shuffles the GI's full registered pool (push-only, closed before any
    ///      dispute can open) with the dispute's locked future-block seed, then
    ///      takes the first T1_AGGREGATORS_PER_BATCH entries that are still
    ///      active and were not in the accused batch. Shuffling the fixed
    ///      registered pool rather than the live active pool means the draw is
    ///      independent of when resolveDispute is called, and an aggregator who
    ///      exits after the seed is public can only remove itself from the draw,
    ///      not re-permute everyone else's position. Bookkeeping
    ///      only -- does not re-open the GI state machine to actually re-run
    ///      aggregation against this subgroup; see the scaffold-wide comment
    ///      above the state declarations.
    function _assignFreshSubgroup(
        uint _GI,
        TierKind tierKind,
        uint batchId,
        bytes32 seed
    ) internal view returns (address[] memory subgroup) {
        address[] memory excluded = tierKind == TierKind.Tier1
            ? tier1Batches[_GI][batchId].aggregators
            : tier2Batches[_GI][batchId].aggregators;
        address[] memory pool = dinAggregators[_GI];

        _shuffleAddressArray(pool, seed);

        subgroup = new address[](T1_AGGREGATORS_PER_BATCH);
        uint ptr;
        for (uint i = 0; i < pool.length && ptr < T1_AGGREGATORS_PER_BATCH; i++) {
            if (
                !_isInArray(pool[i], excluded) &&
                dinvalidatorStakeContract.isValidatorActive(pool[i])
            ) {
                subgroup[ptr++] = pool[i];
            }
        }
        if (ptr < T1_AGGREGATORS_PER_BATCH) {
            revert TC_NotEnoughValidators();
        }
    }

    function _isInArray(
        address needle,
        address[] memory haystack
    ) internal pure returns (bool) {
        for (uint i = 0; i < haystack.length; i++) {
            if (haystack[i] == needle) return true;
        }
        return false;
    }
}
