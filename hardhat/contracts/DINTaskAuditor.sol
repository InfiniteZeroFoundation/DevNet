// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";



enum GIstates {
    AwaitingDINTaskAuditorToBeSet, // 0
    AwaitingDINTaskCoordinatorAsSlasher, // 1
    AwaitingDINTaskAuditorAsSlasher, //2
    AwaitingGenesisModel, // 3
    GenesisModelCreated,//4
    GIstarted, // 5
    DINvalidatorRegistrationStarted, //6
    DINvalidatorRegistrationClosed,// 7
    DINauditorRegistrationStarted,// 8
    DINauditorRegistrationClosed, // 9
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
    ValidatorSlashed, // 21
    GIended // 22
}

interface IMockUSDT {

    function transferFrom(address from, address to, uint256 value) external returns (bool);
    
}

interface IDinValidatorStake {
    function getStake(address validator) external view returns (uint256);
    function slash(address validator, uint256 amount) external;
}


interface IDINTaskCoordinator {
    function GI() external view returns (uint256);
    function GIstate() external view returns (uint8); // or an enum getter
}

contract DINTaskAuditor is Ownable {


    IMockUSDT public mockusdt;

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
        string  modelCID;
        uint40  submittedAt;
        bool    eligible;        // majority vote result (basic conformance)
        bool    evaluated;       // scoring quorum reached & avg computed
        bool    approved;        // approvedForAggregation (avg >= passScore)
        uint8   finalAvgScore;   // 0..100, signed for future expansions
    }


    // Per-round params (tune for demo vs spec)
    struct Params {
        uint8  auditorsPerBatch;   // demo: 3, spec: 10
        uint8  modelsPerBatch;       // demo: 3, spec: 100
        uint8  minEligibilityQuorum; // e.g., 2 for demo, 7 for spec(≈2/3)
        uint8  minScoreQuorum;       // e.g., 2 for demo, 7 for spec
        uint8  passScore;            // 0..100
        uint256 minAuditorStake;     // eligibility for auditors
        uint256 MIN_MODELS_PER_BATCH;
    }

    Params public params;


    mapping(uint => LMSubmission[]) public lmSubmissions;

    ///  GI  ➜  submitter  ➜  bool
    mapping(uint => mapping(address => bool)) public clientHasSubmitted;

    struct AuditBatch {
        uint batchId;
        address[] auditors;
        uint[] modelIndexes;
        string  testDataCID;    // shared test data for this batch
    }

    mapping(uint8 => AuditBatch[]) public auditBatches;


    mapping(uint8 =>                   // GI
        mapping(uint =>                  // batchId
            mapping(address =>           // auditor
                mapping(uint =>          // modelIndex
                    uint8               // score
                )
            )
        )
    ) public auditScores;

    mapping(uint8 =>                   // GI
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
    ) public hasAuditedLM;

    mapping(uint8 => bool) public Is_testdataCIDs_Assigned;
    modifier onlyAssignedAuditor(uint8 gi, uint batchId, uint modelIndex) {
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



    event RewardDeposited(address indexed modelOwner, uint256 amount);

    event DINAuditorRegistered(uint indexed GI, address indexed auditor);


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
        bool eligible,        
        uint totalVotes       
    ); // eligible: final eligibility decision, totalVotes: number of auditors who voted

    event AuditorsBatchAuto(uint indexed GI, uint indexed batchId);
    event AuditorsBatchesCreated(uint indexed GI, uint batchCount);
    event PassScoreUpdated(uint8 oldScore, uint8 newScore);



    constructor(address _mockusdt, address _dinvalidatorStakeContract_address, address _dintaskcoordinator_contract_address) Ownable(msg.sender) {
        mockusdt = IMockUSDT(_mockusdt);
        dinvalidatorStakeContract = IDinValidatorStake(_dinvalidatorStakeContract_address);
        dintaskcoordinatorContract = IDINTaskCoordinator(_dintaskcoordinator_contract_address);

        params = Params({auditorsPerBatch: 3, modelsPerBatch: 3, minEligibilityQuorum: 2, minScoreQuorum: 2, passScore: 50, minAuditorStake: 1_000_000, MIN_MODELS_PER_BATCH: 2});
    
    }


    function depositReward(uint _amount) public onlyOwner {
        require(_amount > 0, "Amount must be greater than 0");

        // Pull MockUSDT from sender (ModelOwner)
        bool success = mockusdt.transferFrom(msg.sender, address(this), _amount);
        require(success, "MockUSDT transfer failed");

        totalDepositedRewards += _amount;
        emit RewardDeposited(msg.sender, _amount);
    }


    function updatePassScore(uint8 newPassScore) external onlyTaskCoordinator {
        require(newPassScore <= 100, "Pass score must be between 0 and 100");

        uint8 oldScore = params.passScore;
        params.passScore = newPassScore;

        emit PassScoreUpdated(oldScore, newPassScore);
    }

    function registerDINAuditor(uint _GI) public {
        require(dintaskcoordinatorContract.GIstate() == uint8(GIstates.DINauditorRegistrationStarted), "DINauditor registration not open");
        require(_GI == dintaskcoordinatorContract.GI(), "Invalid GlobalIteration");
        require(!isRegisteredAuditor[_GI][msg.sender], "Auditor already registered");
        uint256 stake = dinvalidatorStakeContract.getStake(msg.sender);
        require(stake >= minStake, "Insufficient stake to register");

        dinAuditors[_GI].push(msg.sender);
        isRegisteredAuditor[_GI][msg.sender] = true;

        emit DINAuditorRegistered(_GI, msg.sender);

    }

    function getDINtaskAuditors(uint _GI) public view returns (address[] memory) {
        return dinAuditors[_GI];
    }


    function submitLocalModel(string memory _clientModel, uint _GI) public {
        require(_GI == dintaskcoordinatorContract.GI(), "Invalid GI");
        require(dintaskcoordinatorContract.GIstate() == uint8(GIstates.LMSstarted), "LM Submissions not open");
        require(!clientHasSubmitted[_GI][msg.sender], "Already submitted");
        require(lmSubmissions[_GI].length < MAX_LM_SUBMISSIONS, "Max LM submissions reached");

        lmSubmissions[_GI].push(LMSubmission({
            client:    msg.sender,
            modelCID:  _clientModel,
            evaluated: false,
            approved:  false,
            eligible:  false,
            finalAvgScore: 0,
            submittedAt: uint40(block.timestamp)
        }));
        clientHasSubmitted[_GI][msg.sender] = true;
    }

    function getClientModels(uint _GI) public view returns (LMSubmission[] memory) {
        return lmSubmissions[_GI];
    }

    modifier onlyTaskCoordinator(){
        require(msg.sender == address(dintaskcoordinatorContract), "DINTaskAuditor: Not task coordinator");
        _;
        
    }


    // ──────────── internal shuffle helpers ────────────
    function _shuffleAddressArray(address[] storage arr) internal {
        for (uint i = arr.length - 1; i > 0; i--) {
            uint j = uint(keccak256(abi.encodePacked(blockhash(block.number-1), i, arr.length))) % (i + 1);
            (arr[i], arr[j]) = (arr[j], arr[i]);
        }
    }

    function _shuffleUintArray(uint[] memory arr) internal view {
        for (uint i = arr.length - 1; i > 0; i--) {
            uint j = uint(keccak256(abi.encodePacked(block.timestamp, i, arr.length, msg.sender))) % (i + 1);
            (arr[i], arr[j]) = (arr[j], arr[i]);
        }
    }


    function createAuditorsBatches(uint _GI) external onlyTaskCoordinator returns (bool) {
        require(_GI == dintaskcoordinatorContract.GI(), "Invalid GI");
        require(dintaskcoordinatorContract.GIstate() == uint8(GIstates.LMSclosed), "can not create Auditors batches now");


        // ▸ 1. Pull and shuffle auditor pool
        address[] storage auditorPool = dinAuditors[_GI];
        uint aLen = auditorPool.length;

        require(aLen >= params.auditorsPerBatch, "Not enough Auditors");
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
            (
                mPtr + params.modelsPerBatch <= modelIdx.length ||
                (
                    mPtr + params.MIN_MODELS_PER_BATCH <= modelIdx.length &&
                    mPtr + params.modelsPerBatch > modelIdx.length
                )
            )
        ) {
            AuditBatch storage b = auditBatches[uint8(_GI)].push();
            b.batchId = Batchcnt++;

            for (uint8 k = 0; k < params.auditorsPerBatch; k++) {
                b.auditors.push(auditorPool[vPtr + k]);
            }

            uint modelsToAssign = params.modelsPerBatch;
            if (modelIdx.length - mPtr < params.modelsPerBatch) {
                modelsToAssign = modelIdx.length - mPtr;
            }

            for (uint8 k = 0; k < modelsToAssign; k++) {
                b.modelIndexes.push(modelIdx[mPtr + k]);
            }

            

            emit AuditorsBatchAuto(
                _GI,
                b.batchId
            );

            vPtr += params.auditorsPerBatch;
            mPtr += modelsToAssign;
        }


        emit AuditorsBatchesCreated(_GI, Batchcnt);
        return true;
        
    }

    function AuditorsBatchCount(uint _GI) external view returns (uint) {
        require(_GI <= dintaskcoordinatorContract.GI(), "Wrong GI");
        return auditBatches[uint8(_GI)].length;
    }

    function getAuditorsBatch(uint _GI, uint _batchId) external view returns (
        uint      batchId,
        address[] memory auditors,
        uint[]    memory modelIndexes,
        string    memory testDataCID
    ) {
        require(_GI <= dintaskcoordinatorContract.GI(), "Wrong GI");
        require(_batchId < auditBatches[uint8(_GI)].length, "Batch not found");
        AuditBatch memory batch = auditBatches[uint8(_GI)][_batchId];
        return (batch.batchId, batch.auditors, batch.modelIndexes, batch.testDataCID);
    }

    function assignAuditTestDataset(
        uint8 gi,
        uint8 batchId,
        string calldata testDataCID
    ) external onlyOwner {
        require(gi == dintaskcoordinatorContract.GI(), "Wrong GI");
        // Ensure the batch exists
        require(batchId < auditBatches[gi].length, "Batch does not exist");

        require(auditBatches[gi][batchId].batchId == batchId, "Batch ID mismatch");

        // Assign the testDataCID
        auditBatches[gi][batchId].testDataCID = testDataCID;

    }

    function setTestDataAssignedFlag ( uint _GI, bool flag ) external onlyTaskCoordinator returns (bool){
        require(_GI == dintaskcoordinatorContract.GI(), "Wrong GI");
        require(dintaskcoordinatorContract.GIstate() == uint8(GIstates.AuditorsBatchesCreated), "TA: can not set TestDataAssignedFlag");
        require(flag == true, "Flag must be true");
        require(Is_testdataCIDs_Assigned[uint8(_GI)] == false, "Flag already set");

        Is_testdataCIDs_Assigned[uint8(_GI)] = flag;
        return true;
    }

        function _tryFinalizeEligibility(uint8 gi, uint batchId, uint modelIndex) internal {
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

        // Majority rule: eligible if yesVotes > 50% of total votes
        
        bool majorityEligible = (yesVotes ) >= params.minEligibilityQuorum; 

        // Optional: make threshold configurable
        // bool majorityEligible = (yesVotes * 100) >= (totalVotes * params.eligibilityThreshold);

        // Finalize the result
        submission.eligible = majorityEligible;

        emit EligibilityFinalized(gi, batchId, modelIndex, majorityEligible, totalVotes);
    }

    function setAuditScorenEligibility(
        uint8 gi,
        uint batchId,
        uint modelIndex,
        uint8 score,
        bool vote  // true = eligible, false = not eligible
    ) public onlyAssignedAuditor(gi, batchId, modelIndex) {
        require(gi == dintaskcoordinatorContract.GI(), "Wrong GI");
        require(dintaskcoordinatorContract.GIstate() == uint8(GIstates.LMSevaluationStarted), "TA: can not set AuditScorenEligibility");
        // Score reasonable? (e.g., 0–100)
        require(score <= 100, "Audit: Score must be <= 100");
        require(hasAuditedLM[gi][batchId][msg.sender][modelIndex] == false, "Audit: Already voted");

        auditScores[gi][batchId][msg.sender][modelIndex] = score;
        // Record the vote
        LMeligibleVote[gi][batchId][msg.sender][modelIndex] = vote;

        hasAuditedLM[gi][batchId][msg.sender][modelIndex] = true;

        emit AuditScoreSubmitted(gi, batchId, msg.sender, modelIndex, score);
        emit EligibilityVoted(gi, batchId, modelIndex, msg.sender, vote);

        // Try to finalize eligibility if quorum is met
        _tryFinalizeEligibility(gi, batchId, modelIndex);
    }

    

    function finalizeEvaluation(uint _GI) public onlyTaskCoordinator returns (bool) {
        require(_GI == dintaskcoordinatorContract.GI(), "Wrong GI");
        require(
            dintaskcoordinatorContract.GIstate() == uint8(GIstates.LMSevaluationStarted),
            "TA: can not finalize Evaluation"
        );

        uint8 gi8 = uint8(_GI);
        LMSubmission[] storage submissions = lmSubmissions[_GI];

        uint batches = auditBatches[gi8].length;
        uint finalizedCount;

        for (uint b = 0; b < batches; b++) {
            AuditBatch storage batch = auditBatches[gi8][b];

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
                    _tryFinalizeEligibility(gi8, b, modelIndex);
                }

                // Compute average score from auditors who actually voted
                uint sum;
                uint votes;

                for (uint a = 0; a < batch.auditors.length; a++) {
                    address auditor = batch.auditors[a];
                    if (hasAuditedLM[gi8][b][auditor][modelIndex]) {
                        sum += auditScores[gi8][b][auditor][modelIndex];
                        votes++;
                    }
                }

                // Only finalize a model's score if score quorum is met
                if (votes >= params.minScoreQuorum) {
                    uint8 avg = uint8(sum / votes); // integer division

                    sub.finalAvgScore = avg;
                    sub.evaluated     = true;

                    // Approval requires (i) eligible == true and (ii) avg >= passScore
                    sub.approved = (sub.eligible && avg >= params.passScore);

                    finalizedCount++;
                }
            }
        }

        // Return true if at least one model was finalized
        return finalizedCount > 0;
    }

    function approvedModelIndexes(uint _GI) public view returns (uint[] memory) {
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