// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "./DinToken.sol"; // Import the DINToken contract interface

interface IDinValidatorStake {
    function getStake(address validator) external view returns (uint256);
}


contract DINTaskCoordinator {

    address public owner;  // model owner
    string public genesisModelIpfsHash; // genesis model ipfs hash
    
    uint public GI = 0; // GlobalIteration
    uint256 public minStake = 1_000_000;
    
    GIstates public GIstate;

    mapping (uint => address[]) public dinValidators;

    struct LMSubmission {
        address client;
        string  modelCID;
        bool    evaluated;   // ← set by evaluateLM()
        bool    approved;    // ← set by evaluateLM()
    }
    
    mapping(uint => LMSubmission[]) public lmSubmissions;

    ///  GI  ➜  submitter  ➜  bool
    mapping(uint => mapping(address => bool)) public clientHasSubmitted;

    uint public totalDepositedRewards = 0;

    
    DinToken public dintoken;
    IDinValidatorStake public dinvalidatorStakeContract;

    uint MAX_LM_SUBMISSIONS = 10000;

    event RewardDeposited(address indexed modelOwner, uint256 amount);



    constructor(address dintoken_address, address dinvalidatorStakeContract_address) {
        owner = msg.sender;
        dintoken = DinToken(dintoken_address);
        dinvalidatorStakeContract = IDinValidatorStake(dinvalidatorStakeContract_address);
        GIstate = GIstates.AwaitingGenesisModel;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }


    function depositReward(uint _amount) public onlyOwner {
        require(_amount > 0, "Amount must be greater than 0");

        // Pull DIN tokens from sender (ModelOwner)
        bool success = dintoken.transferFrom(msg.sender, address(this), _amount);
        require(success, "DINToken transfer failed");

        totalDepositedRewards += _amount;
        emit RewardDeposited(msg.sender, _amount);
    }

    function setGenesisModelIpfsHash(string memory _genesisModelIpfsHash) public onlyOwner {
        genesisModelIpfsHash = _genesisModelIpfsHash;
        GIstate = GIstates.GenesisModelCreated;
    }

    function getGenesisModelIpfsHash() public view returns (string memory) {
        return genesisModelIpfsHash;
    }

    function startGI(uint _GI) public onlyOwner {
        require(GIstate == GIstates.GenesisModelCreated || GIstate == GIstates.GIended, "GI can not be started");
        require(_GI == GI+1, "Invalid GlobalIteration");
        GIstate = GIstates.GIstarted;
        GI++;
    }

    function startLMsubmissions(uint _GI) public onlyOwner {
        require(GIstate == GIstates.GIstarted, "GI is not started");
        require(_GI == GI, "Invalid GlobalIteration");
        GIstate = GIstates.LMSstarted;
    }

    function closeLMsubmissions(uint _GI) public onlyOwner {
        require(GIstate == GIstates.LMSstarted, "LM submissions are not started");
        require(_GI == GI, "Invalid GlobalIteration");
        GIstate = GIstates.LMSclosed;
    }

    function registerDINvalidator(uint _GI) public {
        require(GIstate == GIstates.GIstarted, "validators can only be registered when the GI is started");
        uint256 stake = dinvalidatorStakeContract.getStake(msg.sender);
        require(stake >= minStake, "Insufficient stake to register");
        address[] storage validators = dinValidators[_GI];

        // Optional: prevent double registration
        for (uint256 i = 0; i < validators.length; i++) {
            require(validators[i] != msg.sender, "Validator already registered");
        }

        validators.push(msg.sender);

    }

    function getDINtaskValidators(uint _GI) public view returns (address[] memory) {
        return dinValidators[_GI];
    }

    function submitLocalModel(string memory _clientModel, uint _GI) public {
        require(_GI == GI, "Invalid GI");
        require(GIstate == GIstates.LMSstarted, "Submissions not open");
        require(!clientHasSubmitted[_GI][msg.sender], "Already submitted");
        require(lmSubmissions[_GI].length < MAX_LM_SUBMISSIONS, "Max submissions reached");

        lmSubmissions[_GI].push(LMSubmission({
            client:    msg.sender,
            modelCID:  _clientModel,
            evaluated: false,
            approved:  false
        }));
        clientHasSubmitted[_GI][msg.sender] = true;
    }

    function _clearclientHasSubmitted(uint _GI) internal {
        // iterate once over the array to know who to delete
        LMSubmission[] storage list = lmSubmissions[_GI];
        for (uint i = 0; i < list.length; i++) {
            delete clientHasSubmitted[_GI][list[i].client];
        }
    }

    function getClientModels(uint _GI) public view returns (LMSubmission[] memory) {
        return lmSubmissions[_GI];
    }

    function getGI() public view returns (uint) {
        return GI;
    }

    function evaluateLM(
        uint _GI,
        address _client,
        bool _approved            // true = keep, false = drop
    ) external onlyOwner {
        require(GIstate == GIstates.LMSclosed, "Not evaluable");
        require(_GI == GI, "Wrong GI");
        LMSubmission[] storage list = lmSubmissions[_GI];
        bool found = false;
        for (uint i = 0; i < list.length; i++) {
            if (list[i].client == _client) {
                require(!list[i].evaluated, "Already evaluated");
                list[i].evaluated = true;
                list[i].approved = _approved;
                found = true;
                break;
            }
        }
        require(found, "Submission not found");
    }

    // When owner has walked through all clients:
    function finalizeEvaluation(uint _GI) external onlyOwner {
        require(GIstate == GIstates.LMSclosed, "Eval not ready");
        require(_GI == GI, "Wrong GI");
        GIstate = GIstates.LMSevaluationClosed;
    }

    uint8 public constant T1_VALIDATORS_PER_BATCH = 3;
    uint8 public constant T1_MODELS_PER_BATCH     = 3;
    uint8 public constant MIN_T1_MODELS_PER_BATCH = 2;

    enum GIstates {
        AwaitingGenesisModel,
        GenesisModelCreated,
        GIstarted,
        LMSstarted,
        LMSclosed,
        LMSevaluationClosed,
        T1nT2Bcreated,
        T1AggregationStarted,
        T1AggregationDone,
        T2AggregationStarted,
        T2AggregationDone,
        GIended
    }

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

    mapping(uint => mapping(uint => mapping(address => string))) public t2SubmissionCID;
    mapping(uint => mapping(uint => mapping(address => bool  ))) public t2Submitted;
    mapping(uint => mapping(uint => mapping(string  => uint ))) public t2Votes;

    event Tier1BatchAuto(uint indexed GI, uint indexed batchId, address[3] validators, uint[3] modelIdx);
    event Tier2BatchAuto(uint indexed GI, uint indexed batchId, address[] validators);

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
                b.batchId,
                [b.validators[0], b.validators[1], b.validators[2]],
                [
                    b.modelIndexes[0],
                    b.modelIndexes.length > 1 ? b.modelIndexes[1] : 0,
                    b.modelIndexes.length > 2 ? b.modelIndexes[2] : 0
                ]
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

            emit Tier2BatchAuto(_GI, 0, t2.validators);
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
        LMSubmission[] storage list = lmSubmissions[_GI];
        uint count;
        for (uint i = 0; i < list.length; i++)
            if (list[i].evaluated && list[i].approved) count++;

        require(count >= T1_MODELS_PER_BATCH, "Not enough approved models");

        out = new uint[](count);
        uint j;
        for (uint i = 0; i < list.length; i++)
            if (list[i].evaluated && list[i].approved) out[j++] = i;
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
        require(_GI == GI, "Wrong GI");
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
        require(_GI == GI, "Wrong GI");
        Tier2Batch storage b = tier2Batches[_GI][_id];
        return (b.batchId, b.validators, b.finalized, b.finalCID);
    }

    function startT1Aggregation(uint _GI) external onlyOwner {
        require(GIstate == GIstates.T1nT2Bcreated, "Not ready to start T1 aggregation");
        require(_GI == GI, "Wrong GI");
        GIstate = GIstates.T1AggregationStarted;
    }

    function finalizeT1Aggregation(uint _GI) external onlyOwner {
        require(GIstate == GIstates.T1AggregationStarted, "Not ready to finalize T1 aggregation");
        require(_GI == GI, "Wrong GI");
        GIstate = GIstates.T1AggregationDone;
    }

    function startT2Aggregation(uint _GI) external onlyOwner {
        require(GIstate == GIstates.T1AggregationDone, "Not ready to start T2 aggregation");
        require(_GI == GI, "Wrong GI");
        GIstate = GIstates.T2AggregationStarted;
    }   

    function finalizeT2Aggregation(uint _GI) external onlyOwner {
        require(GIstate == GIstates.T2AggregationStarted, "Not ready to finalize T2 aggregation");
        require(_GI == GI, "Wrong GI");
        GIstate = GIstates.T2AggregationDone;
    }   

    function endGI(uint _GI) external onlyOwner {
        require(GIstate == GIstates.T2AggregationDone, "Not ready to end GI");
        require(_GI == GI, "Wrong GI");
        GIstate = GIstates.GIended;
    }   
}
