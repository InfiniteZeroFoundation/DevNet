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
    GIended // 22
}

// ─────────────────────────────────────────────────────────────────────────────
// Cross-contract interfaces
// ─────────────────────────────────────────────────────────────────────────────

interface IDinValidatorStake {
    function getStake(address validator) external view returns (uint256);

    function slash(address validator, uint256 amount) external;

    function is_slasher_contract(
        address slasher_contract
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

    function approvedModelIndexes(
        uint _GI
    ) external view returns (uint[] memory);

    function updatePassScore(uint256 newPassScore) external;
}

// ─────────────────────────────────────────────────────────────────────────────
// Custom errors — DINTaskAuditor
// ─────────────────────────────────────────────────────────────────────────────
error TA_NotTaskCoordinator(); // "Audit: Not task coordinator"
error TA_AmountMustBePositive(); // "Audit: Amount must be positive"
error TA_InvalidPassScore(); // "Audit: Invalid pass score, Pass score must be between 0 and 100"
error TA_AuditorRegistrationNotOpen(); // "Audit: Auditor registration not open"
error TA_WrongGI(); // "Audit: Invalid Global Iteration"
error TA_AuditorAlreadyRegistered(); // "Audit: Auditor already registered"
error TA_InsufficientStake(); // "Audit: Insufficient stake"
error TA_LMSubmissionsNotOpen(); // "Audit: LM submissions not open"
error TA_AlreadySubmitted(); // "Audit: Already submitted"
error TA_MaxLMSubmissionsReached(); // "Audit: Max LM submissions reached"
error TA_NotEnoughAuditors(); // "Audit: Not enough auditors"
error TA_CannotCreateAuditorsBatches(); // "Audit: Cannot create auditors batches"
error TA_BatchNotFound(); // "AuditBatch: Batch not found"
error TA_BatchDoesNotExist(); // "AuditBatch: Batch does not exist"
error TA_BatchIDMismatch(); // "AuditBatch: Batch ID mismatch"
error TA_CannotSetTestDataAssignedFlag(); // "AuditBatch: Cannot set test data assigned flag"
error TA_FlagMustBeTrue(); // " Flag must be true"
error TA_FlagAlreadySet(); // "Flag already set"
error TA_NotAssignedAuditor(); // "Audit: Not assigned auditor"
error TA_InvalidModelIndex(); // "Audit: Invalid model index"
error TA_CannotSetAuditScore(); // "Audit: Cannot set audit score"
error TA_ScoreOutOfRange(); // "Audit: Score out of range"
error TA_AlreadyVoted(); // "Audit: Already voted"
error TA_CannotFinalizeEvaluation(); // "Audit: Cannot finalize evaluation"

// ─────────────────────────────────────────────────────────────────────────────
// Custom errors — DINTaskCoordinator
// ─────────────────────────────────────────────────────────────────────────────
error TC_TaskAuditorContractCannotBeSet(); // "Task Coordinator: Task auditor contract cannot be set"
error TC_CoordinatorCannotBeSetAsSlasher(); // "Task Coordinator cannot be set as slasher"
error TC_CoordinatorIsNotSlasher(); // "Task Coordinator is not slasher"
error TC_AuditorCannotBeSetAsSlasher(); // "Task Auditor cannot be set as slasher"
error TC_AuditorIsNotSlasher(); // "Task Auditor is not slasher"
error TC_GenesisModelHashCannotBeSet(); // "Task Coordinator: Genesis model hash cannot be set"
error TC_GICannotBeStarted(); // "Task Coordinator: GI cannot be started"
error TC_WrongGI(); // "Task Coordinator: Wrong GI"
error TC_AggregatorsRegistrationCannotBeStarted(); // "Task Coordinator: Aggregators registration cannot be started"
error TC_AggregatorsRegistrationNotOpen(); // "Task Coordinator: Aggregators registration not open"
error TC_InsufficientStake(); // "Task Coordinator: Insufficient stake"
error TC_ValidatorAlreadyRegistered(); // "Task Coordinator: Validator already registered"
error TC_AggregatorsRegistrationCannotBeFinished(); // "Task Coordinator: Aggregators registration cannot be finished"
error TC_AuditorsRegistrationCannotBeStarted(); // "Task Coordinator: Auditors registration cannot be started"
error TC_AuditorsRegistrationCannotBeFinished(); // "Task Coordinator: Auditors registration cannot be finished"
error TC_LMSubmissionsCannotBeStarted(); // "Task Coordinator: LM submissions cannot be started"
error TC_LMSubmissionsNotStarted(); // "Task Coordinator: LM submissions not started"
error TC_LMEvalCannotBeStarted(); // "Task Coordinator: LM eval cannot be started"
error TC_LMEvalCannotBeFinished(); // "Task Coordinator: LM eval cannot be finished"
error TC_FailedToCreateAuditorsBatches(); // "Task Coordinator: Failed to create auditors batches"
error TC_CannotSetTestDataAssignedFlag(); // "Task Coordinator: Cannot set test data assigned flag"
error TC_EvalPhaseNotClosed(); // "Task Coordinator: Eval phase not closed"
error TC_NotEnoughValidators(); // "Task Coordinator: Not enough validators"
error TC_NotEnoughApprovedModels(); // "Task Coordinator: Not enough approved models"
error TC_BatchNotFound(); // "Task Coordinator: Batch not found"
error TC_OnlyOneTier2Batch(); // "Task Coordinator: Only one tier 2 batch"
error TC_NotReadyForT1Aggregation(); // "Task Coordinator: Not ready for T1 aggregation"
error TC_T1AggregationNotStarted(); // "Task Coordinator: T1 aggregation not started"
error TC_InvalidBatch(); // "Task Coordinator: Invalid batch"
error TC_NotBatchAggregator(); // "Task Coordinator: Not batch aggregator"
error TC_AlreadySubmitted(); // "Task Coordinator: Already submitted"
error TC_NoSubmissions(); // "Task Coordinator: No submissions"
error TC_NotReadyToFinalizeT1(); // "Task Coordinator: Not ready to finalize T1"
error TC_NotReadyForT2Aggregation(); // "Task Coordinator: Not ready for T2 aggregation"
error TC_T2AggregationNotStarted(); // "Task Coordinator: T2 aggregation not started"
error TC_NotReadyToFinalizeT2(); // "Task Coordinator: Not ready to finalize T2"
error TC_NotReadyToSlashAuditors(); // "Task Coordinator: Not ready to slash auditors"
error TC_NotReadyToSlashAggregators(); // "Task Coordinator: Not ready to slash Aggregators"
error TC_NotReadyToSetTier2Score(); // "Task Coordinator: Not ready to set tier 2 score"
error TC_NotReadyToEndGI(); // "Task Coordinator: Not ready to end GI"
error TC_FailedToFinalizeEvaluation(); // "Task Coordinator: Failed to finalize LMS evaluation"
