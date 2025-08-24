
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";


/**
 * DINTaskAuditingBasicPerGI — ultra-simple auditing with per-GI storage
 * - Clients submit local model CIDs (per GI)
 * - Owner creates batches (validatorsPerBatch : modelsPerBatch)
 * - Validators (staked) vote eligibility (majority-of-quorum) and submit 0..100 scores
 * - On finalize, average score on-chain; approve if avg >= passScore
 *
 * Demo defaults: 3:3, quorum=2, passScore=60
 * Spec-ready: 10:100, quorum ~ 2/3 committee, passScore configurable
 */


interface IDINTaskCoordinator {
    
}

interface IDinValidatorStake {

    function getStake(address validator) external view returns (uint256);
    function slash(address validator, uint256 amount) external;
}

contract DINTaskAuditing is Ownable{


    IDinValidatorStake public immutable validatorStakeC;
    IDINTaskCoordinator public taskCoordinatorC; // optional/loose coupling
    IERC20 public immutable dinTokenC;



    enum AuditState {
        Idle,
        GIStarted,
        ValidatorsRegistered,
        LMOpen,
        LMClosed,
        AuditBatchesCreated,
        AuditingOpen,
        AuditingClosed,
        AuditFinalized
    }

    struct LMSubmission {
        address client;
        string  cid;
        uint40  submittedAt;
        bool    eligible;        // majority vote result (basic conformance)
        bool    evaluated;       // scoring quorum reached & avg computed
        bool    approved;        // approvedForAggregation (avg >= passScore)
        uint8   finalAvgScore;   // 0..100, signed for future expansions
    }


    // Per-round params (tune for demo vs spec)
    struct Params {
        uint8  validatorsPerBatch;   // demo: 3, spec: 10
        uint8  modelsPerBatch;       // demo: 3, spec: 100
        uint8  minEligibilityQuorum; // e.g., 2 for demo, 7 for spec(≈2/3)
        uint8  minScoreQuorum;       // e.g., 2 for demo, 7 for spec
        uint8  passScore;            // 0..100
        uint256 minAuditorStake;     // eligibility for auditors
    }


    Params public params;


    mapping(uint => LMSubmission[]) public lmSubmissions;

    ///  GI  ➜  submitter  ➜  bool
    mapping(uint => mapping(address => bool)) public clientHasSubmitted;


    mapping(uint256 => address[]) public registeredAuditors;               // GI => auditors list
    mapping(uint256 => mapping(address => bool)) public isRegisteredAuditor; // GI => auditor => flag

    struct AuditBatch {
        uint batchId;
        address[] auditors;
        uint[] modelIndexes;
        string  testDataCID;    // shared test data for this batch
    }
    
    mapping(uint256 => AuditBatch[]) public auditBatches;


    mapping(uint256 =>                   // GI
        mapping(uint =>                  // batchId
            mapping(address =>           // auditor
                mapping(uint =>          // modelIndex
                    uint8               // score
                )
            )
        )
    ) public auditScores;

    mapping(uint256 =>                   // GI
        mapping(uint =>                  // batchId
            mapping(address =>           // auditor
                mapping(uint =>          // modelIndex
                    bool               // eligible
                )
            )
        )
    ) public LMeligibleVote;

    mapping(uint256 =>                   // GI
        mapping(uint =>                  // batchId
            mapping(address =>           // auditor
                mapping(uint =>          // modelIndex
                    bool                 // has voted
                )
            )
        )
    ) public hasAuditingLM;


    
    modifier onlyAssignedAuditor(uint256 gi, uint batchId, uint modelIndex) {
        // Get the batch
        require(batchId < auditBatches[gi].length, "AuditBatch: Batch does not exist");

        AuditBatch storage batch = auditBatches[gi][batchId];

        // Check that the auditor is in the batch's auditors list
        bool isAuditor = false;
        for (uint i = 0; i < batch.auditors.length; i++) {
            if (batch.auditors[i] == msg.sender) {
                isAuditor = true;
                break;
            }
        }
        require(isAuditor, "Audit: Not assigned auditor");

        // Optionally: validate modelIndex is in the allowed list
        bool validModelIndex = false;
        for (uint i = 0; i < batch.modelIndexes.length; i++) {
            if (batch.modelIndexes[i] == modelIndex) {
                validModelIndex = true;
                break;
            }
        }
        require(validModelIndex, "Audit: Invalid model index");

        _;
    }

    event AuditScoreSubmitted(
        uint256 indexed gi,
        uint indexed batchId,
        address indexed auditor,
        uint modelIndex,
        uint8 score
    );

    event EligibilityVoted(
        uint256 indexed gi,
        uint indexed batchId,
        uint indexed modelIndex,
        address auditor,    
        bool vote
    );

    event EligibilityFinalized(
        uint256 indexed gi,
        uint indexed batchId,
        uint indexed modelIndex,
        bool eligible,        // final eligibility decision
        uint totalVotes       // number of auditors who voted
    );
    
    constructor(address _validatorStakeC, address _taskCoordinatorC, address _dinTokenC)
        Ownable(msg.sender)
    {
        require(_validatorStakeC != address(0) && _taskCoordinatorC != address(0) && _dinTokenC != address(0), "zero addr");
        validatorStakeC = IDinValidatorStake(_validatorStakeC);
        taskCoordinatorC = IDINTaskCoordinator(_taskCoordinatorC);
        dinTokenC = IERC20(_dinTokenC);

        params = Params({
            validatorsPerBatch: 3,
            modelsPerBatch: 3,
            minEligibilityQuorum: 2,
            minScoreQuorum: 2,
            passScore: 0,
            minAuditorStake: 1_000_000
        });
    }

    function _tryFinalizeEligibility(uint256 gi, uint batchId, uint modelIndex) internal {
        // Ensure batch exists
        require(batchId < auditBatches[gi].length, "Batch not found");
        AuditBatch storage batch = auditBatches[gi][batchId];

        // Get the submission
        LMSubmission storage submission = lmSubmissions[gi][modelIndex];

        // Skip if already eligible
        if (submission.eligible) {
            return;
        }

        uint yesVotes = 0;
        uint totalVotes = 0;

        // Count votes using `hasAuditingLM` to distinguish "no vote" from "voted false"
        for (uint i = 0; i < batch.auditors.length; i++) {
            address auditor = batch.auditors[i];

            // Only count if the auditor has submitted a vote
            if (hasAuditingLM[gi][batchId][auditor][modelIndex]) {
                totalVotes++;
                if (LMeligibleVote[gi][batchId][auditor][modelIndex]) {
                    yesVotes++;
                }
            }
        }

        // Check if voting quorum is met
        if (totalVotes < params.minEligibilityQuorum) {
            return; // wait for more votes
        }

        // Majority rule: eligible if yesVotes > 50% of total votes
        
        bool majorityEligible = (yesVotes ) > params.minEligibilityQuorum; 

        // Optional: make threshold configurable
        // bool majorityEligible = (yesVotes * 100) >= (totalVotes * params.eligibilityThreshold);

        // Finalize the result
        submission.eligible = majorityEligible;

        emit EligibilityFinalized(gi, batchId, modelIndex, majorityEligible, totalVotes);
    }
    function setAuditScorenEligibility(
        uint256 gi,
        uint batchId,
        uint modelIndex,
        uint8 score,
        bool vote  // true = eligible, false = not eligible
    ) public onlyAssignedAuditor(gi, batchId, modelIndex) {
        // Score reasonable? (e.g., 0–100)
        require(score <= 100, "Audit: Score must be <= 100");
        require(hasAuditingLM[gi][batchId][msg.sender][modelIndex] == false, "Audit: Already voted");

        auditScores[gi][batchId][msg.sender][modelIndex] = score;
        // Record the vote
        LMeligibleVote[gi][batchId][msg.sender][modelIndex] = vote;

        hasAuditingLM[gi][batchId][msg.sender][modelIndex] = true;

        emit AuditScoreSubmitted(gi, batchId, msg.sender, modelIndex, score);
        emit EligibilityVoted(gi, batchId, modelIndex, msg.sender, vote);

        // Try to finalize eligibility if quorum is met
        _tryFinalizeEligibility(gi, batchId, modelIndex);
    }




}