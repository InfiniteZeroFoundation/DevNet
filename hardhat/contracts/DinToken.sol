// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @title DIN Token
/// @notice ERC20-compliant token for the DIN Protocol ecosystem.
/// @dev Minting is restricted to the owner (DinCoordinator), which can be updated through transfer of ownership.

contract DinToken is ERC20 {
    error InvalidAddress();
    error Unauthorized();

    // Event for off-chain indexing
    event TokensMinted(address indexed to, uint256 amount);

    /// @notice Immutable owner - DinCoordinator, set once at deployment
    address public immutable OWNER;

    /// @notice Constructor initializes the token with name and symbol.
    constructor(address owner_) ERC20("DIN Token", "DIN") {
        OWNER = owner_;
        // Optionally mint initial supply to the deployer if needed
        // _mint(owner_, initialSupply * 10 ** decimals());
    }

    /// @notice Modifier: restricts to immutable owner (gas-efficient, no SLOAD)
    modifier onlyOwner() {
        if (msg.sender != OWNER) revert Unauthorized();
        _;
    }

    /// @notice Mint new tokens — callable only by the contract owner.
    /// @param to The address to receive minted tokens.
    /// @param amount The number of tokens to mint (18 decimals).
    function mint(address to, uint256 amount) external onlyOwner {
        if (to == address(0)) revert InvalidAddress();
        _mint(to, amount);
        emit TokensMinted(to, amount);
    }
}
