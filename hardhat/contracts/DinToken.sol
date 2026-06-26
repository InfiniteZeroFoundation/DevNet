// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "@openzeppelin/contracts-upgradeable/token/ERC20/ERC20Upgradeable.sol";
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";

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

    function initialize() external initializer {
        __ERC20_init("DIN Token", "DIN");
        __Ownable_init(msg.sender);
    }

    // One-shot: coordinator is set to the proxy address once and never changed.
    // DinCoordinator is behind a Transparent Proxy so its address is stable
    // across implementation upgrades; a coordinator address change would require
    // deploying a new proxy, which is an intentional design constraint.
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

    function mint(address to, uint256 amount) external onlyCoordinator {
        if (to == address(0)) revert InvalidAddress();
        _mint(to, amount);
        emit TokensMinted(to, amount);
    }
}
