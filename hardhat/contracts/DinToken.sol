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

    event TokensMinted(address indexed to, uint256 amount);
    event CoordinatorSet(address indexed coordinator);

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    function initialize() public initializer {
        __ERC20_init("DIN Token", "DIN");
        __Ownable_init(msg.sender);
    }

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
