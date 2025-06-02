// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "./DinToken.sol"; // Import the DINToken contract interface

contract DINTaskCoordinator {

    address public owner;  // model owner
    string public genesisModelIpfsHash; // genesis model ipfs hash
    uint public GI = 0; // GlobalIteration

    mapping (uint => mapping(address => string)) public clientModels;
    mapping (uint => address[]) public clientAddresses;

    uint public totalDepositedRewards = 0;

    DinToken public dintoken;

    event RewardDeposited(address indexed modelOwner, uint256 amount);

    constructor(address dintoken_address) {
        owner = msg.sender;
        dintoken = DinToken(dintoken_address);
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
        GI = 1;
    }

    function getGenesisModelIpfsHash() public view returns (string memory) {
        return genesisModelIpfsHash;
    }

    function submitLocalModel(string memory _clientModel, uint _GI) public {
        require(_GI == GI, "Invalid GlobalIteration");
        require(bytes(clientModels[_GI][msg.sender]).length == 0, "Already submitted a model");
        clientModels[_GI][msg.sender] = _clientModel;
        clientAddresses[_GI].push(msg.sender);
    }

    function getClientModel(uint _GI, address _clientAddress) public view returns (string memory) {
        return clientModels[_GI][_clientAddress];
    }

    function getClientAddresses(uint _GI) public view returns (address[] memory) {
        return clientAddresses[_GI];
    }

    function getGI() public view returns (uint) {
        return GI;
    }

}
