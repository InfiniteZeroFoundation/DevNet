// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

// ─────────────────────────────────────────────────────────────────────────────
// Shared types & interfaces for the DIN protocol
// Imported by DINTaskCoordinator and DINTaskAuditor (and any future contracts).
// ─────────────────────────────────────────────────────────────────────────────

/// @notice Lifecycle states for a single Global Iteration (GI).
enum GIstates {
    AwaitingDINTaskAuditorToBeSet, // 0
    AwaitingDINTaskCoordinatorAsSlasher, // 1
    AwaitingDINTaskAuditorAsSlasher, // 2
    AwaitingGenesisModel, // 3
    GenesisModelCreated, // 4
    GIstarted, // 5
    DINaggregatorsRegistrationStarted, // 6
    DINaggregatorsRegistrationClosed, // 7
    DINauditorsRegistrationStarted, // 8
    DINauditorsRegistrationClosed, // 9
    LMSstarted, // 10
    LMSclosed, // 11
    AuditorsBatchesCreated, // 12
    LMSevaluationStarted, // 13
    // Reveal phase for commit-then-reveal auditor scoring (task_210726_6 §2a).
    // Inserted here, immediately after the commit phase, rather than
    // appended at the end as PR #63's own diff originally did (see git
    // history) -- deliberate deviation, decided 2026-08-27: this ordinal
    // position matches the state's actual place in the GI lifecycle.
    // dincli/cli/utils.py's `states`/`stateDescription` positional mirrors
    // (indexed by this enum's raw ordinals) have been updated to match,
    // shifting every subsequent entry by +1; see that file and
    // Documentation/technical/contracts/DINShared.md §2.1 for the full
    // 24-member table.
    LMSevaluationRevealStarted, // 14
    LMSevaluationClosed, // 15
    T1nT2Bcreated, // 16
    T1AggregationStarted, // 17
    T1AggregationDone, // 18
    T2AggregationStarted, // 19
    T2AggregationDone, // 20
    AuditorsSlashed, // 21
    AggregatorsSlashed, // 22
    GIended // 23
}

// ─────────────────────────────────────────────────────────────────────────────
// Cross-contract interfaces
// ─────────────────────────────────────────────────────────────────────────────

interface IDinValidatorStake {
    function getStake(address validator) external view returns (uint256);

    function minStake() external view returns (uint256);

    function isValidatorActive(address validator) external view returns (bool);

    function slash(
        address validator,
        uint256 amount,
        bytes32 reason
    ) external returns (uint256);

    function isSlasherContract(
        address slasherContract
    ) external view returns (bool);
}

interface IDINTaskCoordinator {
    function GI() external view returns (uint256);

    function GIstate() external view returns (GIstates);
}

interface IDINTaskAuditor {
    function createAuditorsBatches(uint _GI) external returns (bool);

    function setTestDataAssignedFlag(uint _GI, bool flag) external;

    function finalizeEvaluation(uint _GI) external returns (bool);

    function slashAuditors(uint _GI) external returns (bool);

    function approvedModelIndexes(
        uint _GI
    ) external view returns (uint[] memory);

    function updatePassScore(uint256 newPassScore) external;

    function giRewardPool(uint256 gi) external view returns (uint256);

    function settleRewards(
        uint256 gi,
        address[] calldata rewardableAggregators
    ) external;
}

// ─────────────────────────────────────────────────────────────────────────────
// Custom errors — commit-then-reveal auditor scoring (task_210726_6 §2a-2b, DINTaskAuditor)
// ─────────────────────────────────────────────────────────────────────────────

/// @dev GI state does not permit committing an audit score at this time.
error TA_CommitPhaseNotOpen();
/// @dev This auditor has already committed a score for this model.
error TA_AlreadyCommitted();
/// @dev The commit hash must not be zero.
error TA_EmptyCommitHash();
/// @dev GI state does not permit revealing an audit score at this time.
error TA_RevealPhaseNotOpen();
/// @dev This auditor has not committed a score for this model.
error TA_NoCommitFound();
/// @dev The revealed (score, vote, salt) does not hash to the stored commitment.
error TA_RevealHashMismatch();
/// @dev GI state does not permit starting the reveal phase.
error TC_RevealCannotBeStarted();
/// @dev The number of encrypted keys supplied does not match the batch's auditor count.
error TA_EncryptedKeyCountMismatch();

// ─────────────────────────────────────────────────────────────────────────────
// Custom errors — DINTaskAuditor
// ─────────────────────────────────────────────────────────────────────────────

/// @dev Caller is not the DINTaskCoordinator contract paired with this auditor.
error TA_NotTaskCoordinator();
/// @dev Slash or fee amount must be greater than zero.
error TA_AmountMustBePositive();
/// @dev Pass score must be in the range [0, 100].
error TA_InvalidPassScore();
/// @dev Auditor registration phase is not currently open.
error TA_AuditorRegistrationNotOpen();
/// @dev The supplied GI index does not match the contract's current GI.
error TA_WrongGI();
/// @dev This address has already registered as an auditor for the current GI.
error TA_AuditorAlreadyRegistered();
/// @dev Caller's active stake is below the minimum required to register.
error TA_InsufficientStake();
/// @dev Local model submission phase is not currently open.
error TA_LMSubmissionsNotOpen();
/// @dev This client has already submitted a local model for the current GI.
error TA_AlreadySubmitted();
/// @dev The maximum number of local model submissions for the current GI has been reached.
error TA_MaxLMSubmissionsReached();
/// @dev Fewer auditors registered than the minimum required to proceed.
error TA_NotEnoughAuditors();
/// @dev GI state does not permit auditor batch creation at this time.
error TA_CannotCreateAuditorsBatches();
/// @dev The specified auditor batch index does not exist.
error TA_BatchNotFound();
/// @dev Batch lookup returned an uninitialised entry.
error TA_BatchDoesNotExist();
/// @dev The provided batch ID does not match the stored batch ID.
error TA_BatchIDMismatch();
/// @dev GI state does not permit setting the test data assigned flag.
error TA_CannotSetTestDataAssignedFlag();
/// @dev The flag value supplied must be true; false is not accepted here.
error TA_FlagMustBeTrue();
/// @dev The test data assigned flag for this batch has already been set.
error TA_FlagAlreadySet();
/// @dev Caller is not assigned to the target auditor batch.
error TA_NotAssignedAuditor();
/// @dev The supplied model index is outside the range of submitted models.
error TA_InvalidModelIndex();
/// @dev GI state does not permit setting an audit score at this time.
error TA_CannotSetAuditScore();
/// @dev Audit score must be in the range [0, 100].
error TA_ScoreOutOfRange();
/// @dev This auditor has already cast a vote for the specified model.
error TA_AlreadyVoted();
/// @dev Evaluation cannot be finalised; not all batches have been scored.
error TA_CannotFinalizeEvaluation();
/// @dev Auditor's validator status is not Active.
error TA_AuditorNotActive();
/// @dev S3 deviation threshold must be in the range [0, 100].
error TA_InvalidDeviationThreshold();
/// @dev _medianOf requires at least one entry to compute a median over.
error TA_EmptyScoreSet();
/// @dev No X25519 encryption key registered for this auditor on DinValidatorStake.
error TA_AuditorEncryptionKeyNotRegistered();
/// @dev Test-data commitment has not been stored for this batch.
error TA_NoCommitmentStored();
/// @dev A dispute is already active for this batch.
error TA_DisputeAlreadyActive();
/// @dev No active dispute exists for this batch.
error TA_NoActiveDispute();
/// @dev The dispute challenge window has closed.
error TA_DisputeWindowClosed();
/// @dev The attached bond does not meet the required minimum.
error TA_InsufficientDisputeBond();
/// @dev Dispute bond amount must be greater than zero.
error TA_InvalidDisputeBond();
/// @dev Batch is blocked pending model owner reassignment after a lost dispute.
error TA_BatchPendingReassignment();

// ─────────────────────────────────────────────────────────────────────────────
// Custom errors — DINTaskCoordinator
// ─────────────────────────────────────────────────────────────────────────────

/// @dev The task auditor contract has already been set for this deployment.
error TC_TaskAuditorContractCannotBeSet();
/// @dev GI state does not permit registering the coordinator as a slasher.
error TC_CoordinatorCannotBeSetAsSlasher();
/// @dev The coordinator contract is not yet registered as a slasher.
error TC_CoordinatorIsNotSlasher();
/// @dev GI state does not permit registering the auditor as a slasher.
error TC_AuditorCannotBeSetAsSlasher();
/// @dev The auditor contract is not yet registered as a slasher.
error TC_AuditorIsNotSlasher();
/// @dev GI state does not permit setting the genesis model hash.
error TC_GenesisModelHashCannotBeSet();
/// @dev GI state does not permit starting a new Global Iteration.
error TC_GICannotBeStarted();
/// @dev The supplied GI index does not match the contract's current GI.
error TC_WrongGI();
/// @dev GI state does not permit opening aggregator registration.
error TC_AggregatorsRegistrationCannotBeStarted();
/// @dev Aggregator registration phase is not currently open.
error TC_AggregatorsRegistrationNotOpen();
/// @dev Caller's active stake is below the minimum required to register.
error TC_InsufficientStake();
/// @dev This address has already registered as an aggregator for the current GI.
error TC_AggregatorAlreadyRegistered();
/// @dev GI state does not permit closing aggregator registration.
error TC_AggregatorsRegistrationCannotBeFinished();
/// @dev GI state does not permit opening auditor registration.
error TC_AuditorsRegistrationCannotBeStarted();
/// @dev GI state does not permit closing auditor registration.
error TC_AuditorsRegistrationCannotBeFinished();
/// @dev GI state does not permit opening local model submissions.
error TC_LMSubmissionsCannotBeStarted();
/// @dev Local model submission phase has not been opened.
error TC_LMSubmissionsNotStarted();
/// @dev GI state does not permit starting the LMS evaluation phase.
error TC_LMEvalCannotBeStarted();
/// @dev GI state does not permit closing the LMS evaluation phase.
error TC_LMEvalCannotBeFinished();
/// @dev The call to DINTaskAuditor.createAuditorsBatches() returned false.
error TC_FailedToCreateAuditorsBatches();
/// @dev GI state does not permit setting the test data assigned flag.
error TC_CannotSetTestDataAssignedFlag();
/// @dev LMS evaluation phase has not been closed yet.
error TC_EvalPhaseNotClosed();
/// @dev Fewer active validators registered than required to form T1 batches.
error TC_NotEnoughValidators();
/// @dev Fewer models passed evaluation than the minimum required for T2 aggregation.
error TC_NotEnoughApprovedModels();
/// @dev The requested batch index does not exist.
error TC_BatchNotFound();
/// @dev T2 always produces exactly one batch; index must be 0.
error TC_OnlyOneTier2Batch();
/// @dev GI state does not permit starting T1 aggregation.
error TC_NotReadyForT1Aggregation();
/// @dev T1 aggregation phase has not been started.
error TC_T1AggregationNotStarted();
/// @dev The batch index or aggregator assignment is invalid.
error TC_InvalidBatch();
/// @dev Caller is not the assigned aggregator for this batch.
error TC_NotBatchAggregator();
/// @dev This aggregator has already submitted a result for this batch.
error TC_AlreadySubmitted();
/// @dev No aggregation submissions have been received for this batch.
error TC_NoSubmissions();
/// @dev Not all T1 batches have been finalised; cannot close T1 phase.
error TC_NotReadyToFinalizeT1();
/// @dev GI state does not permit starting T2 aggregation.
error TC_NotReadyForT2Aggregation();
/// @dev T2 aggregation phase has not been started.
error TC_T2AggregationNotStarted();
/// @dev The T2 batch has not received its submission yet.
error TC_NotReadyToFinalizeT2();
/// @dev GI state does not permit slashing auditors.
error TC_NotReadyToSlashAuditors();
/// @dev GI state does not permit slashing aggregators.
error TC_NotReadyToSlashAggregators();
/// @dev GI state does not permit recording the tier-2 score.
error TC_NotReadyToSetTier2Score();
/// @dev GI state does not permit ending the Global Iteration.
error TC_NotReadyToEndGI();
/// @dev The call to DINTaskAuditor.finalizeEvaluation() returned false.
error TC_FailedToFinalizeEvaluation();
/// @dev Aggregator's validator status is not Active.
error TC_AggregatorNotActive();
/// @dev The call to DINTaskAuditor.slashAuditors() returned false.
error TC_FailedToSlashAuditors();
/// @dev The upcoming GI's reward pool has not been funded via depositRewards.
error TC_GIRewardPoolNotFunded();

// ─────────────────────────────────────────────────────────────────────────────
// Custom errors — rewards (task_210726_6 §3, DINTaskAuditor)
// ─────────────────────────────────────────────────────────────────────────────

/// @dev A required address argument was the zero address.
error TA_InvalidAddress();
/// @dev The four RewardSplit fields must sum to exactly 10000 bps.
error TA_InvalidRewardSplit();
/// @dev Caller has no claimable reward balance.
error TA_NoRewardsToClaim();
/// @dev depositRewards was called for a GI that has already passed and can
///      never be started (or re-started) again, so the deposit could never
///      be settled or claimed.
error TA_InvalidRewardGI();

// ─────────────────────────────────────────────────────────────────────────────
// Custom errors — dispute resolution (task_210726_6 §4c, DINTaskCoordinator)
// ─────────────────────────────────────────────────────────────────────────────

/// @dev A required address argument was the zero address.
error TC_InvalidAddress();
/// @dev Dispute bond and window must both be greater than zero.
error TC_InvalidDisputeParams();
/// @dev The batch being disputed has not been finalized yet.
error TC_BatchNotFinalized();
/// @dev The dispute window for this batch has already elapsed.
error TC_DisputeWindowClosed();
/// @dev A dispute has already been opened against this batch.
error TC_DisputeAlreadyOpen();
/// @dev No dispute exists for this batch.
error TC_DisputeNotOpen();
/// @dev This dispute has already been resolved.
error TC_DisputeAlreadyResolved();
/// @dev Caller has no claimable dispute-bond balance.
error TC_NoBondClaimable();
