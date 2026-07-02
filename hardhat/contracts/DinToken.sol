// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "@openzeppelin/contracts-upgradeable/token/ERC20/ERC20Upgradeable.sol";
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";

/// @title DIN Token
/// @notice ERC-20 token minted exclusively by the DinCoordinator in exchange
///         for ETH deposits. Deployed behind a Transparent Proxy.
contract DinToken is Initializable, ERC20Upgradeable, OwnableUpgradeable {
    error InvalidAddress();
    error Unauthorized();
    error CoordinatorAlreadySet();

    address public coordinator;

    // Reserved for future state variables at this inheritance level.
    uint256[50] private __gap;

    event TokensMinted(address indexed to, uint256 amount);
    event CoordinatorSet(address indexed coordinator);

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /// @notice Initialises the proxy, registering the token as "DIN Token" (DIN).
    function initialize() external initializer {
        __ERC20_init("DIN Token", "DIN");
        __Ownable_init(msg.sender);
    }

    /// @notice Wires the DinCoordinator proxy as the sole authorised minter.
    /// @dev One-shot: reverts if called a second time. The coordinator sits behind
    ///      a Transparent Proxy so its address is stable across upgrades; changing
    ///      it would require deploying a new proxy, which is an intentional constraint.
    /// @param coordinator_ Address of the DinCoordinator proxy.
    function setCoordinator(address coordinator_) external onlyOwner {
        if (coordinator != address(0)) revert CoordinatorAlreadySet();
        if (coordinator_ == address(0)) revert InvalidAddress();
        coordinator = coordinator_;
        emit CoordinatorSet(coordinator_);
    }

    modifier onlyCoordinator() {
        if (msg.sender != coordinator) revert Unauthorized();
        _;
    }

    /// @notice Mints DIN tokens to the specified address.
    /// @dev Restricted to the coordinator. Called by DinCoordinator.depositAndMint.
    /// @param to Recipient address.
    /// @param amount Token amount in wei (18 decimals).
    function mint(address to, uint256 amount) external onlyCoordinator {
        if (to == address(0)) revert InvalidAddress();
        _mint(to, amount);
        emit TokensMinted(to, amount);
    }
}
