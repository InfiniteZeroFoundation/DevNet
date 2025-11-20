// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @title DIN Token
/// @notice ERC20-compliant token for the DIN Protocol ecosystem.
/// @dev Minting is restricted to the owner (DinCoordinator), which can be updated through transfer of ownership.

contract DinToken is ERC20, Ownable {

    /// @notice Constructor initializes the token with name and symbol.
    constructor() ERC20("DIN Token", "DIN") Ownable(msg.sender){
        // Optionally mint initial supply to the deployer if needed
        // _mint(msg.sender, initialSupply * 10 ** decimals());
    }

    /// @notice Mint new tokens — callable only by the contract owner.
    /// @param to The address to receive minted tokens.
    /// @param amount The number of tokens to mint (18 decimals).
    function mint(address to, uint256 amount) external onlyOwner {
        require(to != address(0), "Invalid address");
        _mint(to, amount);
    }

    /// @notice Update ownership to another contract (e.g., DinCoordinator) for minting rights.
    /// @param newOwner The new minter/owner contract address.
    function updateMinter(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Invalid address");
        transferOwnership(newOwner);
    }
}