// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";

interface IBurnableToken {
    function burn(uint256 amount) external;
}

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
    error InvalidJailDuration();
    error NotJailed();
    error JailPeriodNotExpired();
    error StakeBelowFloor();
    error InvalidMinStake();
    error InvalidUnbondingPeriod();
    error InvalidStakeBounds();

    IERC20 public DIN_TOKEN;
    address public DIN_COORDINATOR;

    using SafeERC20 for IERC20;

    // Governable parameters — set in initialize(), adjustable via setters
    uint256 public MIN_STAKE;
    uint64 public UNBONDING_PERIOD;
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
    event ValidatorJailed(
        address indexed validator,
        uint64 jailedUntil,
        bytes32 indexed reason,
        address indexed slasher
    );
    event ValidatorReactivated(address indexed validator);
    event MinStakeUpdated(uint256 newMinStake);
    event UnbondingPeriodUpdated(uint64 newPeriod);
    event ModelStakeBoundsUpdated(uint256 indexed modelId, uint256 min, uint256 max);
    event MaxConcurrentRegistrationsPerStakeUnitUpdated(uint256 value);
    event SlashTreasuryUpdated(address indexed treasury);

    mapping(address => ValidatorInfo) public validators;

    struct ModelStakeBounds { uint256 min; uint256 max; }
    mapping(uint256 => ModelStakeBounds) public modelMinStakeBounds;
    uint256 public maxConcurrentRegistrationsPerStakeUnit;
    address public slashTreasury;

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
        MIN_STAKE = 10 * 1e18;
        UNBONDING_PERIOD = 7 days;
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

        validator.activeStake += amount;
        _syncValidatorStatus(validator);
        DIN_TOKEN.safeTransferFrom(msg.sender, address(this), amount);

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

    /// @notice Slashes a validator's stake by the requested amount. . 50% of the slashed amount is burned;
    ///         50% is sent to slashTreasury (if set) or also burned as a fallback.
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

         uint256 burnAmount = actualAmount / 2;
        uint256 treasuryAmount = actualAmount - burnAmount;
        IBurnableToken(address(DIN_TOKEN)).burn(burnAmount);
        if (slashTreasury != address(0)) {
            DIN_TOKEN.safeTransfer(slashTreasury, treasuryAmount);
        } else {
            IBurnableToken(address(DIN_TOKEN)).burn(treasuryAmount);
        }

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

/// @notice Updates the network-wide minimum stake floor required to become an active validator.
    function setMinStake(uint256 newMinStake) external onlyOwner {
        if (newMinStake == 0) revert InvalidMinStake();
        MIN_STAKE = newMinStake;
        emit MinStakeUpdated(newMinStake);
    }
    
    /// @notice Updates the unbonding period applied to new unstake requests.
    /// @dev Does not retroactively affect in-flight withdrawals whose withdrawAvailableAt
    ///      was already computed at the time unstake() was called.
    function setUnbondingPeriod(uint64 newPeriod) external onlyOwner {
        if (newPeriod == 0) revert InvalidUnbondingPeriod();
        UNBONDING_PERIOD = newPeriod;
        emit UnbondingPeriodUpdated(newPeriod);
    }

    
    /// @notice Stores per-model stake bounds (not yet enforced — follow-up task).
    function setModelStakeBounds(uint256 modelId, uint256 min, uint256 max) external onlyOwner {
        if (min > max) revert InvalidStakeBounds();
        modelMinStakeBounds[modelId] = ModelStakeBounds(min, max);
        emit ModelStakeBoundsUpdated(modelId, min, max);
    }

    /// @notice Stores the concurrent-registration cap per stake unit (not yet enforced).
    function setMaxConcurrentRegistrationsPerStakeUnit(uint256 value) external onlyOwner {
        maxConcurrentRegistrationsPerStakeUnit = value;
        emit MaxConcurrentRegistrationsPerStakeUnitUpdated(value);
    }

    /// @notice Sets the treasury address that receives 50% of every slashed amount.
    function setSlashTreasury(address treasury_) external onlyOwner {
        if (treasury_ == address(0)) revert InvalidAddress();
        slashTreasury = treasury_;
        emit SlashTreasuryUpdated(treasury_);
    }

    /// @notice Jails a validator for the given duration preventing GI registration. Callable only by a registered
    ///         slasher contract. Extends an existing jail if the new deadline is later.
    function jailValidator(
        address validator,
        uint64 duration,
        bytes32 reason
    ) external onlySlasherContract {
        if (validator == address(0)) revert InvalidAddress();
        if (duration == 0) revert InvalidJailDuration();
        ValidatorInfo storage v = validators[validator];
        if (v.status == ValidatorStatus.Blacklisted) revert ValidatorIsBlacklisted();
        uint64 newJailedUntil = uint64(block.timestamp) + duration;
        if (newJailedUntil > v.jailedUntil) v.jailedUntil = newJailedUntil;
        v.status = ValidatorStatus.Jailed;
        emit ValidatorJailed(validator, v.jailedUntil, reason, msg.sender);
    }

    /// @notice Allows a jailed validator to exit jail once the period has expired
    ///         and their stake is at or above the current MIN_STAKE.
    function reactivate() external nonReentrant {
        ValidatorInfo storage v = validators[msg.sender];
        if (v.status != ValidatorStatus.Jailed) revert NotJailed();
        if (block.timestamp < v.jailedUntil) revert JailPeriodNotExpired();
        if (v.activeStake < MIN_STAKE) revert StakeBelowFloor();
        v.jailedUntil = 0;
        
        _syncValidatorStatus(v);
        emit ValidatorReactivated(msg.sender);
    }

    /// @notice Returns the minimum token amount required to become an active validator.
    /// @return The current MIN_STAKE value in wei.
    function minStake() external view returns (uint256) {
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
