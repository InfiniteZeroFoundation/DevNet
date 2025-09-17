// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;


import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

interface IDinValidatorStake {
    function getStake(address validator) external view returns (uint256);
    function slash(address validator, uint256 amount) external;
    function is_slasher_contract(address slasher_contract) external view returns (bool);
}

interface IDINTaskAuditor {
    function createAuditorsBatches(uint _GI) external returns (bool);
    function setTestDataAssignedFlag(uint _GI, bool flag) external;
    function finalizeEvaluation(uint _GI) external returns (bool);
    function approvedModelIndexes(uint _GI) external view returns (uint[] memory);
    function updatePassScore(uint8 newPassScore) external;
}
    


contract DINTaskCoordinator is Ownable {

    

    enum GIstates {
        AwaitingDINTaskAuditorToBeSet,
        AwaitingDINTaskCoordinatorAsSlasher,
        AwaitingDINTaskAuditorAsSlasher,
        AwaitingGenesisModel,
        GenesisModelCreated,
        GIstarted,
        DINvalidatorRegistrationStarted,
        DINvalidatorRegistrationClosed,
        DINauditorRegistrationStarted,
        DINauditorRegistrationClosed,
        LMSstarted,
        LMSclosed,
        AuditorsBatchesCreated,
        LMSevaluationStarted,
        LMSevaluationClosed,
        T1nT2Bcreated,
        T1AggregationStarted,
        T1AggregationDone,
        T2AggregationStarted,
        T2AggregationDone,
        AuditorsSlashed,
        ValidatorSlashed,
        GIended
    }



    IDinValidatorStake public dinvalidatorStakeContract;
    IDINTaskAuditor public dinTaskAuditorContract;

    uint public GI = 0; // GlobalIteration

    GIstates public GIstate;

    string public genesisModelIpfsHash; // genesis model ipfs hash

    uint256 public minStake = 1_000_000;

    mapping(uint => address[]) public dinValidators;

    // Track if an address is registered for a given _GI
    mapping(uint => mapping(address => bool)) public isDINValidator;

    uint8 public constant T1_VALIDATORS_PER_BATCH = 3;
    uint8 public constant T1_MODELS_PER_BATCH     = 3;
    uint8 public constant MIN_T1_MODELS_PER_BATCH = 2;

    struct Tier1Batch {
        uint           batchId;             // Unique inside round
        address[]      validators;          // Validators assigned
        uint[]         modelIndexes;        // Indexes into approvedModels[GI]
        bool           finalized;           // True after majority
        string         finalCID;            // Majority‐agreed CID
    }
    
    mapping(uint => Tier1Batch[]) public tier1Batches;

    // Audit & voting maps            GI  ➜  batchId ➜ validator  ➜  …
    mapping(uint => mapping(uint => mapping(address => string))) public t1SubmissionCID;
    mapping(uint => mapping(uint => mapping(address => bool  ))) public t1Submitted;
    mapping(uint => mapping(uint => mapping(string  => uint ))) public t1Votes;   // CID ➜ votes

    struct Tier2Batch {
        uint      batchId;
        address[] validators;     // Tier‑2 validators
        bool      finalized;
        string    finalCID;
    }
    
    mapping(uint => Tier2Batch[]) public tier2Batches;
    mapping(uint => uint) public tier2Score;

    mapping(uint => mapping(uint => mapping(address => string))) public t2SubmissionCID;
    mapping(uint => mapping(uint => mapping(address => bool  ))) public t2Submitted;
    mapping(uint => mapping(uint => mapping(string  => uint ))) public t2Votes;

  
    event DINValidatorRegistered(uint indexed GI, address indexed validator);
    event Tier1BatchAuto(uint indexed GI, uint indexed batchId);
    event Tier2BatchAuto(uint indexed GI, uint indexed batchId);

    constructor(address dinvalidatorStakeContract_address) Ownable(msg.sender) {

        dinvalidatorStakeContract = IDinValidatorStake(dinvalidatorStakeContract_address);
        GIstate = GIstates.AwaitingDINTaskAuditorToBeSet;
    }



    function setDINTaskAuditorContract(address _dintaskauditor_contract_address) public onlyOwner {
        require(GIstate == GIstates.AwaitingDINTaskAuditorToBeSet, "DINTaskAuditor contract can not be set");
        dinTaskAuditorContract = IDINTaskAuditor(_dintaskauditor_contract_address);
        GIstate = GIstates.AwaitingDINTaskCoordinatorAsSlasher;
    }

    function setDINTaskCoordinatorAsSlasher() public onlyOwner {
        require(GIstate == GIstates.AwaitingDINTaskCoordinatorAsSlasher, "DINTaskCoordinator can not be set as slasher");
        require(dinvalidatorStakeContract.is_slasher_contract(address(this)), "DINTaskCoordinator is not a slasher");
        GIstate = GIstates.AwaitingDINTaskAuditorAsSlasher;
    }

    function setDINTaskAuditorAsSlasher() public onlyOwner {
        require(GIstate == GIstates.AwaitingDINTaskAuditorAsSlasher, "DINTaskAuditor can not be set as slasher");
        require(dinvalidatorStakeContract.is_slasher_contract(address(dinTaskAuditorContract)), "DINTaskAuditor is not a slasher");
        GIstate = GIstates.AwaitingGenesisModel;
    }

    function setGenesisModelIpfsHash(string memory _genesisModelIpfsHash) public onlyOwner {
        require(GIstate == GIstates.AwaitingGenesisModel, "Genesis model ipfs hash can not be set");
        genesisModelIpfsHash = _genesisModelIpfsHash;
        GIstate = GIstates.GenesisModelCreated;
    }

    function startGI(uint _GI, uint score) public onlyOwner {
        require(GIstate == GIstates.GenesisModelCreated || GIstate == GIstates.GIended, "GI can not be started");
        require(_GI == GI+1, "Invalid GlobalIteration");
        dinTaskAuditorContract.updatePassScore(uint8(score));
        GIstate = GIstates.GIstarted;
        GI++;
    }

    function startDINvalidatorRegistration(uint _GI) public onlyOwner {
        require(GIstate == GIstates.GIstarted, "DINvalidator registration can not be started");
        require(_GI == GI, "Invalid GlobalIteration");
        GIstate = GIstates.DINvalidatorRegistrationStarted;
    }

    function registerDINvalidator(uint _GI) public {
        require(GIstate == GIstates.DINvalidatorRegistrationStarted, "validators registration not open");
        uint256 stake = dinvalidatorStakeContract.getStake(msg.sender);
        require(stake >= minStake, "Insufficient stake to register");
        // Check if already registered using O(1) lookup
        require(!isDINValidator[_GI][msg.sender], "Validator already registered");

        // Add to list and mark as registered
        dinValidators[_GI].push(msg.sender);
        isDINValidator[_GI][msg.sender] = true;

        emit DINValidatorRegistered(_GI, msg.sender);

    }

    

    function closeDINvalidatorRegistration(uint _GI) public onlyOwner {
        require(GIstate == GIstates.DINvalidatorRegistrationStarted, "DINvalidator registration can not be finished");
        require(_GI == GI, "Invalid GlobalIteration");
        GIstate = GIstates.DINvalidatorRegistrationClosed;
    }


    function getDINtaskValidators(uint _GI) public view returns (address[] memory) {
        return dinValidators[_GI];
    }

    function startDINauditorRegistration(uint _GI) public onlyOwner {
        require(GIstate == GIstates.DINvalidatorRegistrationClosed, "DINauditor registration can not be started");
        require(_GI == GI, "Invalid GlobalIteration");
        GIstate = GIstates.DINauditorRegistrationStarted;
    }

    function closeDINauditorRegistration(uint _GI) public onlyOwner {
        require(GIstate == GIstates.DINauditorRegistrationStarted, "DINauditor registration can not be finished");
        require(_GI == GI, "Invalid GlobalIteration");
        GIstate = GIstates.DINauditorRegistrationClosed;
    }

    function startLMsubmissions(uint _GI) public onlyOwner {
        require(GIstate == GIstates.DINauditorRegistrationClosed, "LM submissions can not be started");
        require(_GI == GI, "Invalid GlobalIteration");
        GIstate = GIstates.LMSstarted;
    }

    function closeLMsubmissions(uint _GI) public onlyOwner {
        require(GIstate == GIstates.LMSstarted, "LM submissions are not started");
        require(_GI == GI, "Invalid GlobalIteration");
        GIstate = GIstates.LMSclosed;
    }


    function createAuditorsBatches(uint _GI) public onlyOwner {
        require(GIstate == GIstates.LMSclosed, "LM submissions evaluation can not be started");
        require(_GI == GI, "Invalid GlobalIteration");


        bool success = dinTaskAuditorContract.createAuditorsBatches(_GI);
        require(success, "Failed to create auditors batches");
        
        GIstate = GIstates.AuditorsBatchesCreated;
        
    }

    function setTestDataAssignedFlag ( uint _GI, bool flag ) external onlyOwner {
        require(_GI == GI, "Wrong GI");
        require(GIstate == GIstates.AuditorsBatchesCreated, "TC: can not set TestDataAssignedFlag");

        dinTaskAuditorContract.setTestDataAssignedFlag(_GI, flag);


    }


    function startLMsubmissionsEvaluation(uint _GI) public onlyOwner {
        require(GIstate == GIstates.AuditorsBatchesCreated, "LM submissions evaluation can not be started");
        require(_GI == GI, "Invalid GlobalIteration");

        GIstate = GIstates.LMSevaluationStarted;
    }

    function closeLMsubmissionsEvaluation(uint _GI) public onlyOwner {
        require(GIstate == GIstates.LMSevaluationStarted, "LM submissions evaluation can not be finished");
        require(_GI == GI, "Invalid GlobalIteration");
        bool success = dinTaskAuditorContract.finalizeEvaluation(_GI);
        require(success, "Failed to finalize evaluation");
        GIstate = GIstates.LMSevaluationClosed;
    }

     /// @notice Build Tier‑1 and Tier‑2 batches automatically.
    /// @dev  REQUIRES: LM evaluation closed.  Validators must already be registered in dinValidators[_GI].
    function autoCreateTier1AndTier2(uint _GI) external onlyOwner {
        require(GIstate == GIstates.LMSevaluationClosed, "Eval phase not closed");
        require(_GI == GI, "Wrong GI");

        // ▸ 1. Pull and shuffle validator pool
        address[] storage valPool = dinValidators[_GI];
        uint vLen = valPool.length;
        require(vLen >= T1_VALIDATORS_PER_BATCH, "Not enough validators");
        _shuffleAddressArray(valPool);

        // ▸ 2. Build list of approved model indexes
        uint[] memory modelIdx = _collectApprovedModelIndexes(_GI);
        _shuffleUintArray(modelIdx);

        // ▸ 3. Greedily fill Tier-1 batches
        uint vPtr;
        uint mPtr;
        uint t1cnt;
        while (
            vPtr + T1_VALIDATORS_PER_BATCH <= valPool.length &&
            (
                mPtr + T1_MODELS_PER_BATCH <= modelIdx.length ||
                (
                    mPtr + MIN_T1_MODELS_PER_BATCH <= modelIdx.length &&
                    mPtr + T1_MODELS_PER_BATCH > modelIdx.length
                )
            )
        ) {
            Tier1Batch storage b = tier1Batches[_GI].push();
            b.batchId = t1cnt++;

            for (uint8 k = 0; k < T1_VALIDATORS_PER_BATCH; k++) {
                b.validators.push(valPool[vPtr + k]);
            }

            uint modelsToAssign = T1_MODELS_PER_BATCH;
            if (modelIdx.length - mPtr < T1_MODELS_PER_BATCH) {
                modelsToAssign = modelIdx.length - mPtr;
            }

            for (uint8 k = 0; k < modelsToAssign; k++) {
                b.modelIndexes.push(modelIdx[mPtr + k]);
            }

            emit Tier1BatchAuto(
                _GI,
                b.batchId
            );

            vPtr += T1_VALIDATORS_PER_BATCH;
            mPtr += modelsToAssign;
        }

        // ▸ 4. Create Tier-2 batch with EXACTLY T1_VALIDATORS_PER_BATCH validators if enough remain
        if (valPool.length - vPtr >= T1_VALIDATORS_PER_BATCH) {
            Tier2Batch storage t2 = tier2Batches[_GI].push();
            t2.batchId = 0;
            for (uint8 k = 0; k < T1_VALIDATORS_PER_BATCH; k++) {
                t2.validators.push(valPool[vPtr + k]);
            }

            emit Tier2BatchAuto(_GI, t2.batchId);
        }

        GIstate = GIstates.T1nT2Bcreated;
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

    function _collectApprovedModelIndexes(uint _GI)
        internal
        view
        returns (uint[] memory out)
    {
        out = dinTaskAuditorContract.approvedModelIndexes(_GI);
        require(out.length >= T1_MODELS_PER_BATCH, "Not enough approved models");
    }

    // ──────────── read helpers (optional UX) ────────────
    function tier1BatchCount(uint _GI) external view returns (uint) {
        return tier1Batches[_GI].length;
    }


    // read one Tier‑1 batch by index
    function getTier1Batch(uint _GI, uint _id)
        external
        view
        returns (
            uint      batchId,
            address[] memory validators,
            uint[]    memory modelIndexes,
            bool      finalized,
            string    memory finalCID
        )
    {
        require(_GI <= GI, "Wrong GI");
        require(_id < tier1Batches[_GI].length, "Batch not found");
        Tier1Batch storage b = tier1Batches[_GI][_id];
        return (b.batchId, b.validators, b.modelIndexes, b.finalized, b.finalCID);
    }

    function getTier2Batch(uint _GI, uint _id)
        external
        view
        returns (
            uint      batchId,
            address[] memory validators,
            bool      finalized,
            string    memory finalCID
        )
    {
        require(_id == 0, "Only one Tier 2 batch");
        require(_GI <= GI, "Wrong GI");
        Tier2Batch storage b = tier2Batches[_GI][_id];
        return (b.batchId, b.validators, b.finalized, b.finalCID);
    }



    function startT1Aggregation(uint _GI) external onlyOwner {
        require(GIstate == GIstates.T1nT2Bcreated, "Not ready to start T1 aggregation");
        require(_GI == GI, "Wrong GI");
        GIstate = GIstates.T1AggregationStarted;
    }


    function submitT1Aggregation(
        uint _GI,
        uint _batchId,
        string memory _aggregationCID
    ) external {
        require(GIstate == GIstates.T1AggregationStarted, "T1 aggregation not started");
        require(_GI == GI, "Wrong GI");
        require(_batchId < tier1Batches[_GI].length, "Invalid batch");

        Tier1Batch storage b = tier1Batches[_GI][_batchId];

        // Verify sender is an assigned validator
        bool isValidator = false;
        for (uint i = 0; i < b.validators.length; i++) {
            if (b.validators[i] == msg.sender) {
                isValidator = true;
                break;
            }
        }
        require(isValidator, "Not a batch validator");

        require(!t1Submitted[_GI][_batchId][msg.sender], "Already submitted");

        t1Submitted[_GI][_batchId][msg.sender] = true;
        t1SubmissionCID[_GI][_batchId][msg.sender] = _aggregationCID;

        // Increment vote count
        t1Votes[_GI][_batchId][_aggregationCID]++;
    }


    function finalizeT1Aggregation(uint _GI) external onlyOwner {
        require(GIstate == GIstates.T1AggregationStarted, "Not ready to finalize T1 aggregation");
        require(_GI == GI, "Wrong GI");

        Tier1Batch[] storage batches = tier1Batches[_GI];

        for (uint i = 0; i < batches.length; i++) {
            Tier1Batch storage b = batches[i];

            // Determine the CID with the most votes
            string memory winningCID = "";
            uint maxVotes = 0;

            // Enumerate unique CIDs
            for (uint j = 0; j < b.validators.length; j++) {
                address validator = b.validators[j];
                if (t1Submitted[_GI][b.batchId][validator]) {
                    string memory cid = t1SubmissionCID[_GI][b.batchId][validator];
                    uint votes = t1Votes[_GI][b.batchId][cid];
                    if (votes > maxVotes) {
                        maxVotes = votes;
                        winningCID = cid;
                    }
                }
            }

            require(bytes(winningCID).length > 0, "No submissions");
            b.finalized = true;
            b.finalCID = winningCID;
        }

        GIstate = GIstates.T1AggregationDone;
    }

    function startT2Aggregation(uint _GI) external onlyOwner {
        require(GIstate == GIstates.T1AggregationDone, "Not ready to start T2 aggregation");
        require(_GI == GI, "Wrong GI");
        GIstate = GIstates.T2AggregationStarted;
    }   


    function submitT2Aggregation(uint _GI, uint _batchId, string memory _aggregationCID) external {
        require(GIstate == GIstates.T2AggregationStarted, "T2 aggregation not started");
        require(_GI == GI, "Wrong GI");
        require(_batchId == 0, "Only one Tier 2 batch");

        Tier2Batch storage b = tier2Batches[_GI][_batchId];

        // Verify sender is an assigned validator
        bool isValidator = false;
        for (uint i = 0; i < b.validators.length; i++) {
            if (b.validators[i] == msg.sender) {
                isValidator = true;
                break;
            }
        }
        require(isValidator, "Not a batch validator");

        require(!t2Submitted[_GI][_batchId][msg.sender], "Already submitted");

        t2Submitted[_GI][_batchId][msg.sender] = true;
        t2SubmissionCID[_GI][_batchId][msg.sender] = _aggregationCID;

        // Increment vote count
        t2Votes[_GI][_batchId][_aggregationCID]++;
    }

    function finalizeT2Aggregation(uint _GI) external onlyOwner {
        require(GIstate == GIstates.T2AggregationStarted, "Not ready to finalize T2 aggregation");
        require(_GI == GI, "Wrong GI");

        Tier2Batch[] storage batches = tier2Batches[_GI];

        for (uint i = 0; i < batches.length; i++) {
            Tier2Batch storage b = batches[i];

            // Determine the CID with the most votes
            string memory winningCID = "";
            uint maxVotes = 0;

            // Enumerate unique CIDs
            for (uint j = 0; j < b.validators.length; j++) {
                address validator = b.validators[j];
                if (t2Submitted[_GI][b.batchId][validator]) {
                    string memory cid = t2SubmissionCID[_GI][b.batchId][validator];
                    uint votes = t2Votes[_GI][b.batchId][cid];
                    if (votes > maxVotes) {
                        maxVotes = votes;
                        winningCID = cid;
                    }
                }
            }

            require(bytes(winningCID).length > 0, "No submissions");
            b.finalized = true;
            b.finalCID = winningCID;
        }

        GIstate = GIstates.T2AggregationDone;
    }   

    function slashAuditors(uint _GI) external onlyOwner {
        require(GIstate == GIstates.T2AggregationDone, "Not ready to slash auditors");
        require(_GI == GI, "Wrong GI");
        // The Actual Slashing logic maybe implemented here
        GIstate = GIstates.AuditorsSlashed;
    }

    function slashValidators(uint _GI) external onlyOwner {
        require(GIstate == GIstates.AuditorsSlashed, "Not ready to slash validators");
        require(_GI == GI, "Wrong GI");

        uint256 slashAmount = minStake;

        // 1. Tier 1 batches
        Tier1Batch[] storage t1batches = tier1Batches[_GI];
        for (uint i = 0; i < t1batches.length; i++) {
            Tier1Batch storage b = t1batches[i];
            for (uint j = 0; j < b.validators.length; j++) {
                address validator = b.validators[j];

                bool submitted = t1Submitted[_GI][b.batchId][validator];
                bool submittedMatching = false;
                if (submitted) {
                    string memory cid = t1SubmissionCID[_GI][b.batchId][validator];
                    submittedMatching = (keccak256(bytes(cid)) == keccak256(bytes(b.finalCID)));
                }
                if (!submitted || !submittedMatching) {
                    dinvalidatorStakeContract.slash(validator, slashAmount);
                }
            }
        }

         // 2. Tier 2 batches
        Tier2Batch[] storage t2batches = tier2Batches[_GI];
        for (uint i = 0; i < t2batches.length; i++) {
            Tier2Batch storage b = t2batches[i];
            for (uint j = 0; j < b.validators.length; j++) {
                address validator = b.validators[j];

                bool submitted = t2Submitted[_GI][b.batchId][validator];
                bool submittedMatching = false;
                if (submitted) {
                    string memory cid = t2SubmissionCID[_GI][b.batchId][validator];
                    submittedMatching = (keccak256(bytes(cid)) == keccak256(bytes(b.finalCID)));
                }
                if (!submitted || !submittedMatching) {
                    dinvalidatorStakeContract.slash(validator, slashAmount);
                }
            }
        }

        GIstate = GIstates.ValidatorSlashed;
        
    }

    function setTier2Score(uint _GI, uint _score) external onlyOwner {
        require(_GI == GI, "Wrong GI");
        require(GIstate == GIstates.T2AggregationDone || GIstate == GIstates.GenesisModelCreated, "Not ready to set Tier 2 score");
        tier2Score[_GI] = _score;
    }

    function getTier2Score(uint _GI) external view returns (uint) {
        return tier2Score[_GI];
    }

    function endGI(uint _GI) external onlyOwner {
        require(GIstate == GIstates.ValidatorSlashed, "Not ready to end GI");
        require(_GI == GI, "Wrong GI");
        GIstate = GIstates.GIended;
    }   

    




}