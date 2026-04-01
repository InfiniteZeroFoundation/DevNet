// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "./DinToken.sol"; // Import the DINToken contract interface
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

interface IDinValidatorStake {
    function add_slasher_contract(address _slasher_contract) external;

    function remove_slasher_contract(address _slasher_contract) external;
}

contract DinCoordinator is Ownable, ReentrancyGuard {
    DinToken public immutable dintoken;
    IDinValidatorStake public dinvalidatorStakeContract;

    uint256 public dinPerEth = 1_000_000 * 1e18; // 1M DIN tokens (with 18 decimals)
    event ethDepositAndDINminted(
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

    constructor() Ownable(msg.sender) {
        // Deploy DINToken
        dintoken = new DinToken(address(this));
    }

    /// @notice User deposits ETH → receives DIN tokens
    function depositAndMint() external payable nonReentrant {
        if (msg.value == 0) revert ZeroValue();

        uint256 mintAmount = (msg.value * dinPerEth) / 1e18; // ✅ Safe decimal math
        dintoken.mint(msg.sender, mintAmount);

        emit ethDepositAndDINminted(msg.sender, msg.value, mintAmount);
    }

    function withdraw() external onlyOwner nonReentrant {
        uint256 balance = address(this).balance;
        if (balance == 0) return; // ✅ No-op if empty
        (bool success, ) = payable(owner()).call{value: balance}("");
        if (!success) revert TransferFailed();
    }

    function addSlasherContract(address slasherContract) external onlyOwner {
        if (slasherContract == address(0)) revert InvalidAddress();
        if (address(dinvalidatorStakeContract) == address(0))
            revert ValidatorStakeContractNotSet();
        dinvalidatorStakeContract.add_slasher_contract(slasherContract);
        emit SlasherContractAdded(slasherContract);
    }

    function removeSlasherContract(address slasherContract) external onlyOwner {
        if (slasherContract == address(0)) revert InvalidAddress();
        if (address(dinvalidatorStakeContract) == address(0))
            revert ValidatorStakeContractNotSet();
        dinvalidatorStakeContract.remove_slasher_contract(slasherContract);
        emit SlasherContractRemoved(slasherContract);
    }

    function updateValidatorStakeContract(
        address validatorStakeContract
    ) external onlyOwner {
        if (validatorStakeContract == address(0)) revert InvalidAddress();
        dinvalidatorStakeContract = IDinValidatorStake(validatorStakeContract);
        emit ValidatorStakeContractUpdated(validatorStakeContract);
    }

    // ✅ Optional: Update exchange rate (with safeguards)
    function updateDinPerEth(uint256 newRate) external onlyOwner {
        if (newRate == 0) revert ZeroValue();
        dinPerEth = newRate;
        emit DinPerEthUpdated(newRate);
    }
}
