// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";

contract DinValidatorStake is Ownable, ReentrancyGuardTransient {
    error NotDINCoordinator();
    error ValidatorIsBlacklisted();
    error ValidatorNotBlacklisted();
    error InvalidAddress();
    error NotSlasherContract();
    error AmountLessThanMinStake();
    error NotEnoughStake();
    error SlasherContractAlreadyAdded();
    error SlasherContractNotAdded();
    error InvalidSlashAmount();
    error InvalidUnstakeAmount();
    error PendingWithdrawalExists();
    error NoPendingWithdrawal();
    error WithdrawalNotReady();

    IERC20 public immutable DIN_TOKEN;
    address public immutable DIN_COORDINATOR;

    using SafeERC20 for IERC20;

    uint256 public constant MIN_STAKE = 10 * 1e18;
    uint64 public constant UNBONDING_PERIOD = 7 days;
    mapping(address => bool) public slasherContracts;

    enum ValidatorStatus {
        None,
        Active,
        Exiting,
        Jailed,
        Blacklisted
    }

    struct ValidatorInfo {
        uint256 activeStake;
        uint256 pendingWithdrawals;
        uint64 withdrawAvailableAt;
        uint64 jailedUntil;
        ValidatorStatus status;
    }

    event ValidatorStaked(address indexed validator, uint256 amount);
    event ValidatorSlashed(
        address indexed validator,
        uint256 amount,
        bytes32 indexed reason,
        address indexed slasher
    );
    event ValidatorUnstakeRequested(
        address indexed validator,
        uint256 amount,
        uint64 withdrawAvailableAt
    );
    event ValidatorWithdrawalClaimed(address indexed validator, uint256 amount);
    event ValidatorBlacklisted(address indexed validator);
    event ValidatorUnblacklisted(address indexed validator);
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

    modifier onlyDinCoordinator() {
        if (msg.sender != DIN_COORDINATOR) revert NotDINCoordinator();
        _;
    }

    modifier onlySlasherContract() {
        if (!slasherContracts[msg.sender]) revert NotSlasherContract();
        _;
    }

    function stake(uint256 amount) external nonReentrant {
        if (amount < MIN_STAKE) revert AmountLessThanMinStake();

        ValidatorInfo storage validator = validators[msg.sender];
        if (validator.status == ValidatorStatus.Blacklisted) {
            revert ValidatorIsBlacklisted();
        }

        DIN_TOKEN.safeTransferFrom(msg.sender, address(this), amount);
        validator.activeStake += amount;
        _syncValidatorStatus(validator);

        emit ValidatorStaked(msg.sender, amount);
    }

    function addSlasherContract(
        address slasherContract
    ) external onlyDinCoordinator {
        if (slasherContract == address(0)) revert InvalidAddress();
        if (slasherContracts[slasherContract]) {
            revert SlasherContractAlreadyAdded();
        }
        slasherContracts[slasherContract] = true;

        emit SlasherContractAdded(slasherContract);
    }

    function removeSlasherContract(
        address slasherContract
    ) external onlyDinCoordinator {
        if (slasherContract == address(0)) revert InvalidAddress();
        if (!slasherContracts[slasherContract]) {
            revert SlasherContractNotAdded();
        }
        slasherContracts[slasherContract] = false;

        emit SlasherContractRemoved(slasherContract);
    }

    function slash(
        address validator,
        uint256 amount,
        bytes32 reason
    ) external onlySlasherContract nonReentrant returns (uint256) {
        if (validator == address(0)) revert InvalidAddress();
        if (amount == 0) revert InvalidSlashAmount();

        ValidatorInfo storage v = validators[validator];
        uint256 actualAmount = amount;
        uint256 slashableStake = v.activeStake + v.pendingWithdrawals;
        if (slashableStake < actualAmount) {
            actualAmount = slashableStake;
        }

        if (actualAmount == 0) {
            return 0;
        }

        uint256 activeStake = v.activeStake;
        if (activeStake >= actualAmount) {
            v.activeStake = activeStake - actualAmount;
        } else {
            v.activeStake = 0;
            v.pendingWithdrawals -= (actualAmount - activeStake);
            if (v.pendingWithdrawals == 0) {
                v.withdrawAvailableAt = 0;
            }
        }
        _syncValidatorStatus(v);

        emit ValidatorSlashed(validator, actualAmount, reason, msg.sender);
        return actualAmount;
    }

    function unstake(uint256 amount) external nonReentrant {
        ValidatorInfo storage validator = validators[msg.sender];
        if (validator.status == ValidatorStatus.Blacklisted) {
            revert ValidatorIsBlacklisted();
        }
        if (amount == 0) revert InvalidUnstakeAmount();
        if (validator.pendingWithdrawals > 0) revert PendingWithdrawalExists();
        if (validator.activeStake < amount) revert NotEnoughStake();

        validator.activeStake -= amount;
        validator.pendingWithdrawals = amount;
        validator.withdrawAvailableAt = uint64(
            block.timestamp + UNBONDING_PERIOD
        );
        _syncValidatorStatus(validator);

        emit ValidatorUnstakeRequested(
            msg.sender,
            amount,
            validator.withdrawAvailableAt
        );
    }

    function claimUnstaked() external nonReentrant {
        ValidatorInfo storage validator = validators[msg.sender];
        if (validator.status == ValidatorStatus.Blacklisted) {
            revert ValidatorIsBlacklisted();
        }

        uint256 pendingAmount = validator.pendingWithdrawals;
        if (pendingAmount == 0) revert NoPendingWithdrawal();
        if (block.timestamp < validator.withdrawAvailableAt) {
            revert WithdrawalNotReady();
        }

        validator.pendingWithdrawals = 0;
        validator.withdrawAvailableAt = 0;
        _syncValidatorStatus(validator);

        DIN_TOKEN.safeTransfer(msg.sender, pendingAmount);
        emit ValidatorWithdrawalClaimed(msg.sender, pendingAmount);
    }

    function blacklistValidator(address validator) external onlyOwner {
        if (validator == address(0)) revert InvalidAddress();
        validators[validator].status = ValidatorStatus.Blacklisted;
        emit ValidatorBlacklisted(validator);
    }

    function unblacklistValidator(address validator) external onlyOwner {
        if (validator == address(0)) revert InvalidAddress();

        ValidatorInfo storage info = validators[validator];
        if (info.status != ValidatorStatus.Blacklisted) {
            revert ValidatorNotBlacklisted();
        }

        if (info.jailedUntil > block.timestamp) {
            info.status = ValidatorStatus.Jailed;
        } else {
            info.status = ValidatorStatus.None;
        }
        _syncValidatorStatus(info);

        emit ValidatorUnblacklisted(validator);
    }

    function minStake() external pure returns (uint256) {
        return MIN_STAKE;
    }

    function isValidatorActive(address validator) public view returns (bool) {
        ValidatorInfo storage info = validators[validator];
        return info.status == ValidatorStatus.Active;
    }

    function getStake(address validator) public view returns (uint256) {
        return validators[validator].activeStake;
    }

    function slashableStakeOf(address validator) public view returns (uint256) {
        ValidatorInfo storage info = validators[validator];
        return info.activeStake + info.pendingWithdrawals;
    }

    function isSlasherContract(
        address slasherContract
    ) public view returns (bool) {
        return slasherContracts[slasherContract];
    }

    function _syncValidatorStatus(ValidatorInfo storage validator) internal {
        if (validator.status == ValidatorStatus.Blacklisted) {
            return;
        }

        if (
            validator.status == ValidatorStatus.Jailed &&
            validator.jailedUntil > block.timestamp
        ) {
            return;
        }

        if (validator.pendingWithdrawals > 0) {
            validator.status = ValidatorStatus.Exiting;
        } else if (validator.activeStake >= MIN_STAKE) {
            validator.status = ValidatorStatus.Active;
        } else if (validator.activeStake > 0) {
            validator.status = ValidatorStatus.Exiting;
        } else {
            validator.status = ValidatorStatus.None;
        }
    }
}
