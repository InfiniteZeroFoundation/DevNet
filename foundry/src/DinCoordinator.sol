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

/// @title DIN Coordinator
/// @notice Central hub for ETH-to-DIN token exchange and slasher contract
///         administration. Deployed once per network behind a Transparent Proxy.
contract DinCoordinator is
    Initializable,
    OwnableUpgradeable,
    ReentrancyGuardTransient
{
    DinToken public dinToken;
    IDinValidatorStake public dinValidatorStakeContract;

    uint256 public dinPerEth;

    address public treasury;

    // Reserved for future state variables at this inheritance level.
    // Reduced from [50] by 1: treasury
    uint256[49] private __gap;

    event EthDepositAndDINminted(
        address indexed user,
        uint256 ethAmount,
        uint256 mintAmount
    );
    event SlasherContractAdded(address indexed slasher);
    event SlasherContractRemoved(address indexed slasher);
    event ValidatorStakeContractUpdated(address indexed validatorStakeContract);
    event DinPerEthUpdated(uint256 newRate);
    event TreasuryUpdated(address indexed treasury);

    error InvalidAddress();
    error ValidatorStakeContractNotSet();
    error ZeroValue();
    error TransferFailed();
    error TreasuryNotSet();

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /// @notice Initialises the proxy with the DIN token address and sets the
    ///         default exchange rate to 1,000,000 DIN per ETH.
    /// @param dinToken_ Address of the DinToken proxy.
    function initialize(address dinToken_) external initializer {
        if (dinToken_ == address(0)) revert InvalidAddress();
        __Ownable_init(msg.sender);
        dinToken = DinToken(dinToken_);
        dinPerEth = 1_000_000 * 1e18;
    }

    /// @notice Deposits ETH and mints the equivalent amount of DIN tokens to
    ///         the caller at the current exchange rate.
    /// @dev Rate is a fixed-point value scaled by 1e18.
    function depositAndMint() external payable nonReentrant {
        if (msg.value == 0) revert ZeroValue();

        uint256 mintAmount = (msg.value * dinPerEth) / 1e18;
        dinToken.mint(msg.sender, mintAmount);

        emit EthDepositAndDINminted(msg.sender, msg.value, mintAmount);
    }

    /// @notice Withdraws the contract's entire ETH balance to the treasury address.
    /// @dev Reverts if treasury has not been set.
    function withdraw() external onlyOwner nonReentrant {
        if (treasury == address(0)) revert TreasuryNotSet();
        uint256 balance = address(this).balance;
        if (balance == 0) return;
        (bool success, ) = payable(treasury).call{value: balance}("");
        if (!success) revert TransferFailed();
    }

    /// @notice Sets the treasury address. Required before withdraw() can be called.
    function setTreasury(address treasury_) external onlyOwner {
        if (treasury_ == address(0)) revert InvalidAddress();
        treasury = treasury_;
        emit TreasuryUpdated(treasury_);
    }

    /// @notice Registers a task contract as an authorised slasher on the
    ///         validator stake contract.
    /// @param slasherContract Address of the task contract to authorise.
    function addSlasherContract(address slasherContract) external onlyOwner {
        if (slasherContract == address(0)) revert InvalidAddress();
        if (address(dinValidatorStakeContract) == address(0))
            revert ValidatorStakeContractNotSet();
        dinValidatorStakeContract.addSlasherContract(slasherContract);
        emit SlasherContractAdded(slasherContract);
    }

    /// @notice Removes a task contract's slasher authorisation.
    /// @param slasherContract Address of the task contract to deauthorise.
    function removeSlasherContract(address slasherContract) external onlyOwner {
        if (slasherContract == address(0)) revert InvalidAddress();
        if (address(dinValidatorStakeContract) == address(0))
            revert ValidatorStakeContractNotSet();
        dinValidatorStakeContract.removeSlasherContract(slasherContract);
        emit SlasherContractRemoved(slasherContract);
    }

    /// @notice Points the coordinator at the DinValidatorStake proxy address.
    /// @dev Called once during initial deployment wiring. No guard prevents a
    ///      second call; the owner is responsible for operational safety.
    /// @param validatorStakeContract Address of the DinValidatorStake proxy.
    function updateValidatorStakeContract(
        address validatorStakeContract
    ) external onlyOwner {
        if (validatorStakeContract == address(0)) revert InvalidAddress();
        dinValidatorStakeContract = IDinValidatorStake(validatorStakeContract);
        emit ValidatorStakeContractUpdated(validatorStakeContract);
    }

    /// @notice Updates the DIN-per-ETH exchange rate used by depositAndMint.
    /// @param newRate New rate scaled by 1e18 (e.g. 1_000_000 * 1e18 = 1 M DIN per ETH).
    function updateDinPerEth(uint256 newRate) external onlyOwner {
        if (newRate == 0) revert ZeroValue();
        dinPerEth = newRate;
        emit DinPerEthUpdated(newRate);
    }
}
