// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "./DinToken.sol"; // Import the DINToken contract interface

contract DinCoordinator {

    address public owner;  
    
    DinToken public dintoken;

    uint256 public constant DIN_PER_ETH = 1_000_000 ; // 1 ETH = 1 million DIN tokens

    event DepositAndMint(address indexed user, uint256 ethAmount, uint256 mintAmount);

    constructor() {
        owner = msg.sender;

        // Deploy DINToken
        dintoken = new DinToken();
        // Transfer minting rights from DINToken deployer to this contract
        dintoken.updateMinter(address(this));
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }


    function depositAndMint() external payable {
        require(msg.value > 0, "No ETH sent");

        uint256 mintAmount = msg.value * DIN_PER_ETH / 1 ether;
        dintoken.mint(msg.sender, mintAmount);

        emit DepositAndMint(msg.sender, msg.value, mintAmount);
    }

    function withdraw() external onlyOwner {
        payable(owner).transfer(address(this).balance);
    }
    
}    