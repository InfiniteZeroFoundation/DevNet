// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol"; // ✅ L2-optimized guard

contract DinValidatorStake is Ownable, ReentrancyGuardTransient {
    error NotDINCoordinator();
    error ValidatorIsBlacklisted();
    error InvalidAddress();
    error NotSlasherContract();
    error AmountLessThanMinStake();
    error NotValidator();
    error InsufficientStake();
    error NotEnoughStake();
    error SlasherContractAlreadyAdded();
    error SlasherContractNotAdded();
    error TransferFailed();

    IERC20 public immutable DIN_TOKEN;
    address public immutable DIN_COORDINATOR;

    using SafeERC20 for IERC20;

    // ✅ Proper decimal scaling: 1M DIN tokens with 18 decimals
    uint256 public constant MIN_STAKE = 1_000_000 * 1e18;
    mapping(address => bool) public slasherContracts;

    struct ValidatorInfo {
        uint256 stake;
        bool registered;
        bool blacklisted;
    }

    event ValidatorStaked(address indexed validator, uint256 amount);
    event ValidatorSlashed(
        address indexed validator,
        uint256 amount,
        address indexed slasher
    );
    event ValidatorUnstaked(address indexed validator, uint256 amount);
    event ValidatorBlacklisted(address indexed validator);
    event SlasherContractAdded(address indexed slasher);
    event SlasherContractRemoved(address indexed slasher);

    mapping(address => ValidatorInfo) public validators;

    constructor(address dinToken, address dinCoordinator) Ownable(msg.sender) {
        if (dinToken == address(0) || dinCoordinator == address(0)) {
            revert InvalidAddress();
        }
        DIN_TOKEN = IERC20(dinToken);
        DIN_COORDINATOR = dinCoordinator;
    }

    /// @notice Modifier: restricts to DinCoordinator only
    modifier onlyDinCoordinator() {
        if (msg.sender != DIN_COORDINATOR) revert NotDINCoordinator();
        _;
    }

    /// @notice Modifier: restricts to Slasher Contracts only
    modifier onlySlasherContract() {
        if (!slasherContracts[msg.sender]) revert NotSlasherContract();
        _;
    }

    /// @notice Stake DIN tokens to become a validator
    /// @param amount The amount of DIN tokens to stake
    function stake(uint256 amount) external nonReentrant {
        if (amount < MIN_STAKE) revert AmountLessThanMinStake();

        ValidatorInfo storage validator = validators[msg.sender];
        if (validator.blacklisted) revert ValidatorIsBlacklisted();

        // ✅ SafeERC20: handles non-standard ERC20 return values + revert on failure
        DIN_TOKEN.safeTransferFrom(msg.sender, address(this), amount);
        validator.stake += amount;
        validator.registered = true;

        emit ValidatorStaked(msg.sender, amount);
    }

    /// @notice Add a new slasher contract
    /// @param slasherContract The address of the slasher contract
    function addSlasherContract(
        address slasherContract
    ) external onlyDinCoordinator {
        if (slasherContract == address(0)) revert InvalidAddress();
        if (slasherContracts[slasherContract])
            revert SlasherContractAlreadyAdded();
        slasherContracts[slasherContract] = true;

        emit SlasherContractAdded(slasherContract);
    }

    /// @notice Remove a slasher contract
    /// @param slasherContract The address of the slasher contract to remove
    function removeSlasherContract(
        address slasherContract
    ) external onlyDinCoordinator {
        if (slasherContract == address(0)) revert InvalidAddress();
        if (!slasherContracts[slasherContract])
            revert SlasherContractNotAdded();
        slasherContracts[slasherContract] = false;

        emit SlasherContractRemoved(slasherContract);
    }

    /// @notice Slash a validator
    /// @param validator The address of the validator to slash
    /// @param amount The amount of DIN tokens to slash
    function slash(
        address validator,
        uint256 amount
    ) external onlySlasherContract nonReentrant {
        if (amount < MIN_STAKE) revert InsufficientStake();

        ValidatorInfo storage v = validators[validator];

        if (!v.registered) revert NotValidator();
        if (v.stake < amount) revert NotEnoughStake();

        v.stake -= amount;
        // v.blacklisted = true;
        // ✅ Auto-unregister if stake falls below minimum
        if (v.stake < MIN_STAKE) {
            v.registered = false;
        }

        // 🔥 TODO: Implement economic slashing logic
        // Option A: Burn tokens (requires ERC20Burnable)
        // DIN_TOKEN.safeTransferFrom(address(this), address(0), amount);
        // Option B: Transfer to reward pool
        // DIN_TOKEN.safeTransfer(rewardAddress, amount);
        // Option C: Keep as logical slash (tokens stay locked)

        emit ValidatorSlashed(validator, amount, msg.sender);
    }

    /// @notice Unstake DIN tokens (validator only)
    function unstake(uint256 amount) external nonReentrant {
        ValidatorInfo storage validator = validators[msg.sender];

        if (validator.stake < amount) revert NotEnoughStake();

        validator.stake -= amount;

        // ✅ Auto-unregister if stake falls below minimum
        if (validator.stake < MIN_STAKE) {
            validator.registered = false;
        }

        // ✅ SafeERC20 transfer back to validator
        DIN_TOKEN.safeTransfer(msg.sender, amount);
        emit ValidatorUnstaked(msg.sender, amount);
    }

    /// @notice Blacklist a validator (DinCoordinator only) - prevents staking/unstaking
    function blacklistValidator(address validator) external onlyDinCoordinator {
        if (validator == address(0)) revert InvalidAddress();
        validators[validator].blacklisted = true;
        emit ValidatorBlacklisted(validator);
    }

    function isValidatorStaked(address validator) public view returns (bool) {
        return
            validators[validator].stake >= MIN_STAKE &&
            !validators[validator].blacklisted;
    }

    function getStake(address validator) public view returns (uint256) {
        return validators[validator].stake;
    }

    function isSlasherContract(
        address slasherContract
    ) public view returns (bool) {
        return slasherContracts[slasherContract];
    }
}
