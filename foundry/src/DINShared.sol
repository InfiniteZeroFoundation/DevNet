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
    LMSevaluationClosed, // 14
    T1nT2Bcreated, // 15
    T1AggregationStarted, // 16
    T1AggregationDone, // 17
    T2AggregationStarted, // 18
    T2AggregationDone, // 19
    AuditorsSlashed, // 20
    AggregatorsSlashed, // 21
    GIended, // 22
    // Reveal phase for commit-then-reveal auditor scoring (task_210726_6 §2a).
    // Chronologically this sits BETWEEN LMSevaluationStarted (13, now the
    // commit phase) and LMSevaluationClosed (14) -- appended here instead of
    // inserted in sequence deliberately: dincli/cli/utils.py's `states` list
    // is a hand-maintained positional mirror of this enum's raw ordinals
    // (`states[GIstate]`), and dincli/cli/context.py's
    // `validate_GIstate_LTE_given_GIstate` compares raw ordinals directly.
    // Inserting a new member between existing ones would silently shift
    // every subsequent state's integer value and desync every state name
    // dincli displays from that point on -- exactly the kind of breakage
    // "no dincli changes required" (task notes) is telling us to avoid.
    // Appending is not fully ordinal-monotonic with chronological order (an
    // LTE check against a threshold between 13 and 22, e.g. "T1nT2Bcreated"
    // (15), would not treat this state as "before" it) -- audited that this
    // doesn't break anything today: no dincli LTE check uses a threshold in
    // that range, and the ones that do (T1nT2Bcreated, checked from
    // aggregator.py) gate purely read-only "show batches" queries whose
    // underlying on-chain data doesn't exist yet during this window anyway.
    LMSevaluationRevealStarted // 23
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
