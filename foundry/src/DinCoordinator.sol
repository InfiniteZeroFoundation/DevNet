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

interface IDinFeeRouter {
    function routeFeeETH(address payer) external payable;
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

    bool public faucetRetired;    // one-way flag
    uint256 public mintCap;       // 0 = uncapped (DevNet default)
    uint256 public totalMinted;
    IDinFeeRouter public feeRouter;

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
    event MintCapUpdated(uint256 newCap);
    event FaucetRetiredEvent();
    event FeeRouterUpdated(address indexed feeRouter);
    event FeesSweptToRouter(uint256 amount);

    error InvalidAddress();
    error ValidatorStakeContractNotSet();
    error ZeroValue();
    error FaucetRetired();
    error MintCapExceeded();
    error FeeRouterNotSet();

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
    /// @dev Rate is a fixed-point value scaled by 1e18. Reverts if the faucet
    ///      has been retired or if minting would exceed the cap (when set).
    function depositAndMint() external payable nonReentrant {
        if (faucetRetired) revert FaucetRetired();
        if (msg.value == 0) revert ZeroValue();
        uint256 mintAmount = (msg.value * dinPerEth) / 1e18;
        if (mintCap > 0 && totalMinted + mintAmount > mintCap) revert MintCapExceeded();
        totalMinted += mintAmount;
        dinToken.mint(msg.sender, mintAmount);
        emit EthDepositAndDINminted(msg.sender, msg.value, mintAmount);
    }

    /// @notice Sweeps the contract's entire accumulated ETH balance to the fee
    ///         router in one call, which splits it across treasury/validator-pool/
    ///         storage/public-goods per its configured split.
    function sweepFeesToRouter() external onlyOwner nonReentrant {
        if (address(feeRouter) == address(0)) revert FeeRouterNotSet();
        uint256 balance = address(this).balance;
        if (balance == 0) return;
        feeRouter.routeFeeETH{value: balance}(address(this));
        emit FeesSweptToRouter(balance);
    }

     /// @notice Sets a cap on the total DIN that can be minted via depositAndMint.
    ///         0 = uncapped. Cannot be changed after retireFaucet().
    function setMintCap(uint256 newCap) external onlyOwner {
        if (faucetRetired) revert FaucetRetired();
        mintCap = newCap;
        emit MintCapUpdated(newCap);
    }

    /// @notice Permanently disables depositAndMint. Cannot be undone.
    function retireFaucet() external onlyOwner {
        if (faucetRetired) revert FaucetRetired();
        faucetRetired = true;
        emit FaucetRetiredEvent();
    }

    /// @notice Sets the fee router used to split and route accumulated ETH.
    function setFeeRouter(address feeRouter_) external onlyOwner {
        if (feeRouter_ == address(0)) revert InvalidAddress();
        feeRouter = IDinFeeRouter(feeRouter_);
        emit FeeRouterUpdated(feeRouter_);
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
