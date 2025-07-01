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
    enum GIstates {
        AwaitingGenesisModel,
        GenesisModelCreated,
        GIstarted,
        LMsubmissionsStarted,
        LMsubmissionsClosed,
        LMsubmissionsEvaluated,
        Tier1BatchCreated,
        Tier1AggregationDone,
        Tier2BatchCreated,
        Tier2AggregationDone,
        GIended
    }
    GIstates public GIstate;

    mapping (uint => address[]) public dinValidators;

    mapping (uint => mapping(address => string)) public clientModels;
    mapping (uint => address[]) public clientAddresses;

    struct ApprovedModel {
        address client;
        string  modelCID;           // The approved local model
    }

    mapping(uint => ApprovedModel[])              public approvedModels;   // GI  ➜ list
    
    uint public totalDepositedRewards = 0;

    DinToken public dintoken;
    IDinValidatorStake public dinvalidatorStakeContract;

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
        GIstate = GIstates.LMsubmissionsStarted;
    }

    function closeLMsubmissions(uint _GI) public onlyOwner {
        require(GIstate == GIstates.LMsubmissionsStarted, "LM submissions are not started");
        require(_GI == GI, "Invalid GlobalIteration");
        GIstate = GIstates.LMsubmissionsClosed;
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
        require(_GI == GI, "Invalid GlobalIteration");
        require(GIstate == GIstates.LMsubmissionsStarted, "LM submissions can only be submitted when the GI is started");
        require(bytes(clientModels[_GI][msg.sender]).length == 0, "Already submitted a model");
        clientModels[_GI][msg.sender] = _clientModel;
        clientAddresses[_GI].push(msg.sender);
    }

    

    function getClientAddresses(uint _GI) public view returns (address[] memory) {
        return clientAddresses[_GI];
    }

    function getGI() public view returns (uint) {
        return GI;
    }

    function evaluateLM(
        uint _GI,
        address _client,
        bool _approved            // true = keep, false = drop
    ) external onlyOwner {
        require(GIstate == GIstates.LMsubmissionsClosed, "Not evaluable");
        require(_GI == GI, "Wrong GI");
        string memory cid = clientModels[_GI][_client];
        require(bytes(cid).length > 0, "No submission");

        if (_approved) {
            approvedModels[_GI].push(ApprovedModel(_client, cid));
        }
        // else: nothing – rejected models are ignored
    }

    // When owner has walked through all clients:
    function finalizeEvaluation(uint _GI) external onlyOwner {
        require(GIstate == GIstates.LMsubmissionsClosed, "Eval not ready");
        require(_GI == GI, "Wrong GI");
        GIstate = GIstates.LMsubmissionsEvaluated;
    }

    function getApprovedModels(uint _GI) external view returns (ApprovedModel[] memory) {
        return approvedModels[_GI];
    }

}
