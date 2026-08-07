// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";

/// @title DIN Treasury
/// @notice Custodial holding contract for ETH and ERC20 assets. No split logic.
///         Deployed once per network behind a Transparent Proxy.
contract DinTreasury is Initializable, OwnableUpgradeable, ReentrancyGuardTransient {
    using SafeERC20 for IERC20;

    error InvalidAddress();
    error TransferFailed();
    error InsufficientBalance();

    event EthReceived(address indexed from, uint256 amount);
    event EthWithdrawn(address indexed to, uint256 amount);
    event ERC20Withdrawn(address indexed token, address indexed to, uint256 amount);

    // Reserved for future state variables at this inheritance level.
    uint256[50] private __gap;

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    function initialize() external initializer {
        __Ownable_init(msg.sender);
    }

    receive() external payable {
        emit EthReceived(msg.sender, msg.value);
    }

    /// @notice Withdraws a specific ETH amount to the given address.
    /// @param to Destination address.
    /// @param amount Amount in wei.
    function withdrawETH(address payable to, uint256 amount) external onlyOwner nonReentrant {
        if (to == address(0)) revert InvalidAddress();
        if (amount > address(this).balance) revert InsufficientBalance();
        (bool success, ) = to.call{value: amount}("");
        if (!success) revert TransferFailed();
        emit EthWithdrawn(to, amount);
    }

    /// @notice Withdraws ERC20 tokens to the given address.
    /// @param token Token contract address.
    /// @param to Destination address.
    /// @param amount Token amount.
    function withdrawERC20(address token, address to, uint256 amount) external onlyOwner {
        if (token == address(0) || to == address(0)) revert InvalidAddress();
        IERC20(token).safeTransfer(to, amount);
        emit ERC20Withdrawn(token, to, amount);
    }
}
