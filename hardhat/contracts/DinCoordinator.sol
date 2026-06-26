// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "./DinToken.sol";
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";

interface IDinValidatorStake {
    function addSlasherContract(address slasherContract) external;

    function removeSlasherContract(address slasherContract) external;
}

contract DinCoordinator is
    Initializable,
    OwnableUpgradeable,
    ReentrancyGuardTransient
{
    DinToken public dinToken;
    IDinValidatorStake public dinValidatorStakeContract;

    uint256 public dinPerEth;

    // Reserved for future state variables at this inheritance level.
    uint256[50] private __gap;

    event EthDepositAndDINminted(
        address indexed user,
        uint256 ethAmount,
        uint256 mintAmount
    );
    event SlasherContractAdded(address indexed slasher);
    event SlasherContractRemoved(address indexed slasher);
    event ValidatorStakeContractUpdated(address indexed validatorStakeContract);
    event DinPerEthUpdated(uint256 newRate);

    error InvalidAddress();
    error ValidatorStakeContractNotSet();
    error ZeroValue();
    error TransferFailed();

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    function initialize(address dinToken_) external initializer {
        if (dinToken_ == address(0)) revert InvalidAddress();
        __Ownable_init(msg.sender);
        dinToken = DinToken(dinToken_);
        dinPerEth = 1_000_000 * 1e18;
    }

    function depositAndMint() external payable nonReentrant {
        if (msg.value == 0) revert ZeroValue();

        uint256 mintAmount = (msg.value * dinPerEth) / 1e18;
        dinToken.mint(msg.sender, mintAmount);

        emit EthDepositAndDINminted(msg.sender, msg.value, mintAmount);
    }

    function withdraw() external onlyOwner nonReentrant {
        uint256 balance = address(this).balance;
        if (balance == 0) return;
        (bool success, ) = payable(owner()).call{value: balance}("");
        if (!success) revert TransferFailed();
    }

    function addSlasherContract(address slasherContract) external onlyOwner {
        if (slasherContract == address(0)) revert InvalidAddress();
        if (address(dinValidatorStakeContract) == address(0))
            revert ValidatorStakeContractNotSet();
        dinValidatorStakeContract.addSlasherContract(slasherContract);
        emit SlasherContractAdded(slasherContract);
    }

    function removeSlasherContract(address slasherContract) external onlyOwner {
        if (slasherContract == address(0)) revert InvalidAddress();
        if (address(dinValidatorStakeContract) == address(0))
            revert ValidatorStakeContractNotSet();
        dinValidatorStakeContract.removeSlasherContract(slasherContract);
        emit SlasherContractRemoved(slasherContract);
    }

    function updateValidatorStakeContract(
        address validatorStakeContract
    ) external onlyOwner {
        if (validatorStakeContract == address(0)) revert InvalidAddress();
        dinValidatorStakeContract = IDinValidatorStake(validatorStakeContract);
        emit ValidatorStakeContractUpdated(validatorStakeContract);
    }

    function updateDinPerEth(uint256 newRate) external onlyOwner {
        if (newRate == 0) revert ZeroValue();
        dinPerEth = newRate;
        emit DinPerEthUpdated(newRate);
    }
}
