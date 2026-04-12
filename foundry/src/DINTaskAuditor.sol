// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "./DINShared.sol";

contract DINTaskAuditor is Ownable {
    using SafeERC20 for IERC20;
    IERC20 public mockusdt;

    IDinValidatorStake public dinvalidatorStakeContract;

    IDINTaskCoordinator public dintaskcoordinatorContract;

    uint public totalDepositedRewards = 0;

    uint256 public minStake = 1_000_000;

    uint MAX_LM_SUBMISSIONS = 10000;

    mapping(uint => address[]) public dinAuditors;

    // Track if an address is registered for a given _GI
    mapping(uint => mapping(address => bool)) public isRegisteredAuditor;

    struct LMSubmission {
        address client;
        bytes32 modelCID;
        uint40 submittedAt;
        bool eligible; // majority vote result (basic conformance)
        bool evaluated; // scoring quorum reached & avg computed
        bool approved; // approvedForAggregation (avg >= passScore)
        uint256 finalAvgScore; // 0..100, signed for future expansions
    }

    // Per-round params (tune for demo vs spec)
    struct Params {
        uint256 auditorsPerBatch; // demo: 3, spec: 10
        uint256 modelsPerBatch; // demo: 3, spec: 100
        uint256 minEligibilityQuorum; // e.g., 2 for demo, 7 for spec(≈2/3)
        uint256 minScoreQuorum; // e.g., 2 for demo, 7 for spec
        uint256 passScore; // 0..100
        uint256 minAuditorStake; // eligibility for auditors
        uint256 MIN_MODELS_PER_BATCH;
    }

    Params public params;

    mapping(uint => LMSubmission[]) public lmSubmissions;

    ///  GI  ➜  submitter  ➜  bool
    mapping(uint => mapping(address => bool)) public clientHasSubmitted;
    mapping(uint => mapping(address => uint)) public clientSubmissionIndex;

    struct AuditBatch {
        uint batchId;
        address[] auditors;
        uint[] modelIndexes;
        bytes32 testDataCID; // shared test data for this batch
    }

    mapping(uint256 => AuditBatch[]) public auditBatches;

    mapping(uint => mapping(uint => mapping(address => bool)))
        public isBatchAuditor;

    mapping(uint => mapping(uint => mapping(uint => bool)))
        public isBatchModelIndex;

    mapping(uint256 => mapping(uint => mapping(address => mapping(uint => uint256)))) // GI // batchId // auditor // modelIndex // score
        public auditScores;

    mapping(uint256 => mapping(uint => mapping(address => mapping(uint => bool)))) // GI // batchId // auditor // modelIndex // eligible
        public LMeligibleVote;

    mapping(uint256 => mapping(uint => mapping(address => mapping(uint => bool)))) // GI // batchId // auditor // modelIndex // has voted
        public hasAuditedLM;

    mapping(uint256 => bool) public Is_testdataCIDs_Assigned;

    modifier onlyAssignedAuditor(
        uint256 gi,
        uint batchId,
        uint modelIndex
    ) {
        if (batchId >= auditBatches[gi].length) revert TA_BatchDoesNotExist();

        // Check that the auditor is in the batch's auditors list
        if (!isBatchAuditor[gi][batchId][msg.sender])
            revert TA_NotAssignedAuditor();

        // Validate modelIndex is in the allowed list
        if (!isBatchModelIndex[gi][batchId][modelIndex])
            revert TA_InvalidModelIndex();

        _;
    }

    modifier onlyCurrentGI(uint _GI) {
        if (_GI != dintaskcoordinatorContract.GI()) revert TA_WrongGI();
        _;
    }

    event RewardDeposited(address indexed modelOwner, uint256 amount);

    event DINAuditorRegistered(uint indexed GI, address indexed auditor);

    event AuditScoreSubmitted(
        uint256 indexed gi,
        uint indexed batchId,
        address indexed auditor,
        uint modelIndex,
        uint256 score
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
        bool eligible,
        uint totalVotes
    ); // eligible: final eligibility decision, totalVotes: number of auditors who voted

    event AuditorsBatchAuto(uint indexed GI, uint indexed batchId);
    event AuditorsBatchesCreated(uint indexed GI, uint batchCount);
    event PassScoreUpdated(uint256 oldScore, uint256 newScore);

    constructor(
        address _mockusdt,
        address _dinvalidatorStakeContract_address,
        address _dintaskcoordinator_contract_address
    ) Ownable(msg.sender) {
        mockusdt = IERC20(_mockusdt);
        dinvalidatorStakeContract = IDinValidatorStake(
            _dinvalidatorStakeContract_address
        );
        dintaskcoordinatorContract = IDINTaskCoordinator(
            _dintaskcoordinator_contract_address
        );

        params = Params({
            auditorsPerBatch: 3,
            modelsPerBatch: 3,
            minEligibilityQuorum: 2,
            minScoreQuorum: 2,
            passScore: 50,
            minAuditorStake: 1_000_000,
            MIN_MODELS_PER_BATCH: 2
        });
    }

    function depositReward(uint _amount) public onlyOwner {
        if (_amount == 0) revert TA_AmountMustBePositive();

        mockusdt.safeTransferFrom(msg.sender, address(this), _amount);

        totalDepositedRewards += _amount;
        emit RewardDeposited(msg.sender, _amount);
    }

    function updatePassScore(
        uint256 newPassScore
    ) external onlyTaskCoordinator {
        if (newPassScore > 100) revert TA_InvalidPassScore();

        uint256 oldScore = params.passScore;
        params.passScore = newPassScore;

        emit PassScoreUpdated(oldScore, newPassScore);
    }

    function registerDINAuditor(uint _GI) public onlyCurrentGI(_GI) {
        if (
            dintaskcoordinatorContract.GIstate() !=
            GIstates.DINauditorsRegistrationStarted
        ) revert TA_AuditorRegistrationNotOpen();
        if (isRegisteredAuditor[_GI][msg.sender])
            revert TA_AuditorAlreadyRegistered();

        uint256 stake = dinvalidatorStakeContract.getStake(msg.sender);
        if (stake < minStake) revert TA_InsufficientStake();

        dinAuditors[_GI].push(msg.sender);
        isRegisteredAuditor[_GI][msg.sender] = true;

        emit DINAuditorRegistered(_GI, msg.sender);
    }

    function getDINtaskAuditors(
        uint _GI
    ) public view returns (address[] memory) {
        return dinAuditors[_GI];
    }

    function submitLocalModel(
        bytes32 _clientModel,
        uint _GI
    ) public onlyCurrentGI(_GI) {
        if (dintaskcoordinatorContract.GIstate() != GIstates.LMSstarted)
            revert TA_LMSubmissionsNotOpen();
        if (clientHasSubmitted[_GI][msg.sender]) revert TA_AlreadySubmitted();
        if (lmSubmissions[_GI].length >= MAX_LM_SUBMISSIONS)
            revert TA_MaxLMSubmissionsReached();

        uint modelIndex = lmSubmissions[_GI].length;
        clientSubmissionIndex[_GI][msg.sender] = modelIndex;

        lmSubmissions[_GI].push(
            LMSubmission({
                client: msg.sender,
                modelCID: _clientModel,
                evaluated: false,
                approved: false,
                eligible: false,
                finalAvgScore: 0,
                submittedAt: uint40(block.timestamp)
            })
        );
        clientHasSubmitted[_GI][msg.sender] = true;
    }

    function getClientModels(
        uint _GI
    ) public view returns (LMSubmission[] memory) {
        return lmSubmissions[_GI];
    }

    modifier onlyTaskCoordinator() {
        if (msg.sender != address(dintaskcoordinatorContract))
            revert TA_NotTaskCoordinator();
        _;
    }

    // ──────────── internal shuffle helpers ────────────
    function _shuffleAddressArray(address[] storage arr) internal {
        for (uint i = arr.length - 1; i > 0; i--) {
            uint j = uint(
                keccak256(
                    abi.encodePacked(blockhash(block.number - 1), i, arr.length)
                )
            ) % (i + 1);
            (arr[i], arr[j]) = (arr[j], arr[i]);
        }
    }

    function _shuffleUintArray(uint[] memory arr) internal view {
        for (uint i = arr.length - 1; i > 0; i--) {
            uint j = uint(
                keccak256(
                    abi.encodePacked(block.timestamp, i, arr.length, msg.sender)
                )
            ) % (i + 1);
            (arr[i], arr[j]) = (arr[j], arr[i]);
        }
    }

    function createAuditorsBatches(
        uint _GI
    ) external onlyTaskCoordinator onlyCurrentGI(_GI) returns (bool) {
        if (dintaskcoordinatorContract.GIstate() != GIstates.LMSclosed)
            revert TA_CannotCreateAuditorsBatches();

        // ▸ 1. Pull and shuffle auditor pool
        address[] storage auditorPool = dinAuditors[_GI];
        uint aLen = auditorPool.length;

        if (aLen < params.auditorsPerBatch) revert TA_NotEnoughAuditors();
        _shuffleAddressArray(auditorPool);

        // ▸ 2. Build list of local model indexes
        LMSubmission[] storage lmlist = lmSubmissions[_GI];
        uint[] memory modelIdx = new uint[](lmlist.length);

        for (uint i = 0; i < lmlist.length; i++) {
            modelIdx[i] = i;
        }
        _shuffleUintArray(modelIdx);

        // ▸ 3. Create batches, Greedily fill Auditors batches
        uint vPtr;
        uint mPtr;
        uint Batchcnt;

        while (
            vPtr + params.auditorsPerBatch <= auditorPool.length &&
            (mPtr + params.modelsPerBatch <= modelIdx.length ||
                (mPtr + params.MIN_MODELS_PER_BATCH <= modelIdx.length &&
                    mPtr + params.modelsPerBatch > modelIdx.length))
        ) {
            AuditBatch storage b = auditBatches[_GI].push();
            b.batchId = Batchcnt++;

            for (uint256 k = 0; k < params.auditorsPerBatch; k++) {
                b.auditors.push(auditorPool[vPtr + k]);
                isBatchAuditor[_GI][b.batchId][auditorPool[vPtr + k]] = true;
            }

            uint modelsToAssign = params.modelsPerBatch;
            if (modelIdx.length - mPtr < params.modelsPerBatch) {
                modelsToAssign = modelIdx.length - mPtr;
            }

            for (uint256 k = 0; k < modelsToAssign; k++) {
                b.modelIndexes.push(modelIdx[mPtr + k]);
                isBatchModelIndex[_GI][b.batchId][modelIdx[mPtr + k]] = true;
            }

            emit AuditorsBatchAuto(_GI, b.batchId);

            vPtr += params.auditorsPerBatch;
            mPtr += modelsToAssign;
        }

        emit AuditorsBatchesCreated(_GI, Batchcnt);
        return true;
    }

    function AuditorsBatchCount(uint _GI) external view returns (uint) {
        if (_GI > dintaskcoordinatorContract.GI()) revert TA_WrongGI();
        return auditBatches[_GI].length;
    }

    function getAuditorsBatch(
        uint _GI,
        uint _batchId
    )
        external
        view
        returns (
            uint batchId,
            address[] memory auditors,
            uint[] memory modelIndexes,
            bytes32 testDataCID
        )
    {
        if (_GI > dintaskcoordinatorContract.GI()) revert TA_WrongGI();
        if (_batchId >= auditBatches[_GI].length) revert TA_BatchDoesNotExist();
        AuditBatch memory batch = auditBatches[_GI][_batchId];
        return (
            batch.batchId,
            batch.auditors,
            batch.modelIndexes,
            batch.testDataCID
        );
    }

    function assignAuditTestDataset(
        uint256 gi,
        uint256 batchId,
        bytes32 testDataCID
    ) external onlyOwner onlyCurrentGI(gi) {
        if (batchId >= auditBatches[gi].length) revert TA_BatchDoesNotExist();
        if (auditBatches[gi][batchId].batchId != batchId)
            revert TA_BatchIDMismatch();

        auditBatches[gi][batchId].testDataCID = testDataCID;
    }

    function setTestDataAssignedFlag(
        uint _GI,
        bool flag
    ) external onlyTaskCoordinator onlyCurrentGI(_GI) returns (bool) {
        if (
            dintaskcoordinatorContract.GIstate() !=
            GIstates.AuditorsBatchesCreated
        ) revert TA_CannotSetTestDataAssignedFlag();
        if (!flag) revert TA_FlagMustBeTrue();
        if (Is_testdataCIDs_Assigned[_GI]) revert TA_FlagAlreadySet();

        Is_testdataCIDs_Assigned[_GI] = flag;
        return true;
    }

    function _tryFinalizeEligibility(
        uint256 gi,
        uint batchId,
        uint modelIndex
    ) internal {
        if (batchId >= auditBatches[gi].length) revert TA_BatchDoesNotExist();
        AuditBatch storage batch = auditBatches[gi][batchId];

        // Get the submission
        LMSubmission storage submission = lmSubmissions[gi][modelIndex];

        // Skip if already eligible
        if (submission.eligible) {
            return;
        }

        uint yesVotes = 0;
        uint totalVotes = 0;

        // Count votes using `hasAuditedLM` to distinguish "no vote" from "voted false"
        for (uint i = 0; i < batch.auditors.length; i++) {
            address auditor = batch.auditors[i];

            // Only count if the auditor has submitted a vote
            if (hasAuditedLM[gi][batchId][auditor][modelIndex]) {
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

        // Majority rule: eligible if yesVotes >= minEligibilityQuorum
        bool majorityEligible = yesVotes >= params.minEligibilityQuorum;

        // Finalize the result
        submission.eligible = majorityEligible;

        emit EligibilityFinalized(
            gi,
            batchId,
            modelIndex,
            majorityEligible,
            totalVotes
        );
    }

    function setAuditScorenEligibility(
        uint256 gi,
        uint batchId,
        uint modelIndex,
        uint256 score,
        bool vote // true = eligible, false = not eligible
    ) public onlyAssignedAuditor(gi, batchId, modelIndex) onlyCurrentGI(gi) {
        if (
            dintaskcoordinatorContract.GIstate() !=
            GIstates.LMSevaluationStarted
        ) revert TA_CannotSetAuditScore();
        if (score > 100) revert TA_ScoreOutOfRange();
        if (hasAuditedLM[gi][batchId][msg.sender][modelIndex])
            revert TA_AlreadyVoted();

        auditScores[gi][batchId][msg.sender][modelIndex] = score;
        // Record the vote
        LMeligibleVote[gi][batchId][msg.sender][modelIndex] = vote;

        hasAuditedLM[gi][batchId][msg.sender][modelIndex] = true;

        emit AuditScoreSubmitted(gi, batchId, msg.sender, modelIndex, score);
        emit EligibilityVoted(gi, batchId, modelIndex, msg.sender, vote);

        // Try to finalize eligibility if quorum is met
        _tryFinalizeEligibility(gi, batchId, modelIndex);
    }

    function finalizeEvaluation(
        uint _GI
    ) public onlyTaskCoordinator onlyCurrentGI(_GI) returns (bool) {
        if (
            dintaskcoordinatorContract.GIstate() !=
            GIstates.LMSevaluationStarted
        ) revert TA_CannotFinalizeEvaluation();

        LMSubmission[] storage submissions = lmSubmissions[_GI];

        uint batches = auditBatches[_GI].length;
        uint finalizedCount;

        for (uint b = 0; b < batches; b++) {
            AuditBatch storage batch = auditBatches[_GI][b];

            // For each model assigned to this batch
            for (uint m = 0; m < batch.modelIndexes.length; m++) {
                uint modelIndex = batch.modelIndexes[m];
                if (modelIndex >= submissions.length) {
                    // Defensive: skip if bad index
                    continue;
                }

                LMSubmission storage sub = submissions[modelIndex];

                // Ensure eligibility is finalized if quorum has been reached
                if (!sub.eligible) {
                    _tryFinalizeEligibility(_GI, b, modelIndex);
                }

                // Compute average score from auditors who actually voted
                uint sum;
                uint votes;

                for (uint a = 0; a < batch.auditors.length; a++) {
                    address auditor = batch.auditors[a];
                    if (hasAuditedLM[_GI][b][auditor][modelIndex]) {
                        sum += auditScores[_GI][b][auditor][modelIndex];
                        votes++;
                    }
                }

                // Only finalize a model's score if score quorum is met
                if (votes >= params.minScoreQuorum) {
                    uint256 avg = sum / votes; // integer division

                    sub.finalAvgScore = avg;
                    sub.evaluated = true;

                    // Approval requires (i) eligible == true and (ii) avg >= passScore
                    sub.approved = (sub.eligible && avg >= params.passScore);

                    finalizedCount++;
                }
            }
        }

        // Return true if at least one model was finalized
        return finalizedCount > 0;
    }

    function approvedModelIndexes(
        uint _GI
    ) public view returns (uint[] memory) {
        LMSubmission[] storage list = lmSubmissions[_GI];
        uint count;
        for (uint i = 0; i < list.length; i++) {
            if (list[i].approved) count++;
        }
        uint[] memory out = new uint[](count);
        uint j;
        for (uint i = 0; i < list.length; i++) {
            if (list[i].approved) out[j++] = i;
        }
        return out;
    }
}
