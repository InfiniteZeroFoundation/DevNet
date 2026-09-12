// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";

/// @title DIN Validator Stake
/// @notice Manages validator staking, unbonding, slashing, and blacklisting for
///         the DIN protocol. Deployed once per network behind a Transparent Proxy.
contract DinValidatorStake is
    Initializable,
    OwnableUpgradeable,
    ReentrancyGuardTransient
{
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

    IERC20 public DIN_TOKEN;
    address public DIN_COORDINATOR;

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

    // Reserved for future state variables at this inheritance level.
    uint256[50] private __gap;

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /// @notice Initialises the proxy with the token and coordinator addresses.
    /// @param dinToken Address of the DinToken proxy.
    /// @param dinCoordinator Address of the DinCoordinator proxy.
    function initialize(
        address dinToken,
        address dinCoordinator
    ) external initializer {
        if (dinToken == address(0) || dinCoordinator == address(0)) {
            revert InvalidAddress();
        }
        __Ownable_init(msg.sender);
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

    /// @notice Stakes DIN tokens and registers the caller as an active validator.
    /// @param amount Token amount to stake, must be at least MIN_STAKE.
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

    /// @notice Registers a contract as authorised to call slash().
    /// @dev Restricted to the DIN_COORDINATOR address. Called via DinCoordinator.addSlasherContract.
    /// @param slasherContract Address of the task contract to authorise.
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

    /// @notice Removes a contract's slasher authorisation.
    /// @param slasherContract Address of the task contract to deauthorise.
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

    /// @notice Slashes a validator's stake by the requested amount.
    /// @dev Active stake is consumed first; any remainder is taken from pending
    ///      withdrawals. If total slashable stake is less than amount, the actual
    ///      slashed amount is capped and returned rather than reverting.
    /// @param validator Address of the validator to slash.
    /// @param amount Maximum token amount to slash.
    /// @param reason Arbitrary identifier for the slash event, emitted on-chain.
    /// @return The actual amount slashed (may be less than amount if stake is insufficient).
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

    /// @notice Moves stake into a pending withdrawal subject to the unbonding period.
    /// @dev Only one pending withdrawal can exist at a time. The withdrawn amount
    ///      remains slashable during the unbonding window.
    /// @param amount Token amount to unstake.
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

    /// @notice Transfers a matured pending withdrawal back to the caller.
    /// @dev Reverts if the unbonding period has not elapsed since unstake() was called.
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

    /// @notice Permanently prevents a validator from staking or unstaking.
    /// @param validator Address to blacklist.
    function blacklistValidator(address validator) external onlyOwner {
        if (validator == address(0)) revert InvalidAddress();
        validators[validator].status = ValidatorStatus.Blacklisted;
        emit ValidatorBlacklisted(validator);
    }

    /// @notice Lifts a blacklist, restoring the validator's prior status.
    /// @dev If the validator was jailed before being blacklisted and the jail
    ///      period has not expired, status is restored to Jailed, not Active.
    /// @param validator Address to unblacklist.
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

    /// @notice Returns the minimum token amount required to become an active validator.
    /// @return The MIN_STAKE constant in wei.
    function minStake() external pure returns (uint256) {
        return MIN_STAKE;
    }

    /// @notice Returns true if the validator's status is Active.
    /// @param validator Address to query.
    /// @return True if the validator is currently in the Active state.
    function isValidatorActive(address validator) public view returns (bool) {
        ValidatorInfo storage info = validators[validator];
        return info.status == ValidatorStatus.Active;
    }

    /// @notice Returns a validator's current active stake.
    /// @param validator Address to query.
    /// @return Active stake balance in wei.
    function getStake(address validator) public view returns (uint256) {
        return validators[validator].activeStake;
    }

    /// @notice Returns the total amount that can be slashed from a validator,
    ///         including both active stake and any pending withdrawals.
    /// @param validator Address to query.
    /// @return Sum of activeStake and pendingWithdrawals in wei.
    function slashableStakeOf(address validator) public view returns (uint256) {
        ValidatorInfo storage info = validators[validator];
        return info.activeStake + info.pendingWithdrawals;
    }

    /// @notice Returns true if the given address is a registered slasher contract.
    /// @param slasherContract Address to query.
    /// @return True if the address has slasher authorisation.
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
