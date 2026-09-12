// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";

interface IBurnableERC20 is IERC20 {
    function burn(uint256 amount) external;
}

/// @dev Shared interface used by DINModelRegistry to forward fees.
interface IDinFeeRouter {
    function routeFeeDIN(address payer, uint256 amount) external;
    function routeFeeETH(address payer) external payable;
}

struct DinSplit {
    uint16 validatorPoolBps;
    uint16 treasuryBps;
    uint16 burnBps;
    uint16 storageBps;
    uint16 publicGoodsBps;
}

/// @dev No burnBps field — ETH cannot be burned. This is a compile-time
///      impossibility, not a runtime check (scope boundary #4).
struct EthSplit {
    uint16 validatorPoolBps;
    uint16 treasuryBps;
    uint16 storageBps;
    uint16 publicGoodsBps;
}

/// @title DIN Fee Router
/// @notice Routes protocol fees: splits DIN (with optional burn) and ETH
///         across treasury, validator pool, storage, and public-goods buckets.
///         Deployed once per network behind a Transparent Proxy.
contract DinFeeRouter is Initializable, OwnableUpgradeable, ReentrancyGuardTransient {
    using SafeERC20 for IERC20;
    using SafeERC20 for IBurnableERC20;

    error InvalidAddress();
    error NotFeeSource();
    error FeeSourceAlreadyAdded();
    error FeeSourceNotAdded();
    error InvalidSplit();
    error TreasuryCutExceedsCeiling();
    error ZeroAmount();
    error TransferFailed();

    uint16 public constant BPS_DENOMINATOR = 10000;

    IBurnableERC20 public dinToken;
    address public treasury;
    uint16 public treasuryBpsCeiling; // default 2000 = 20%, per MECHANISM_DESIGN §8
    mapping(address => bool) public feeSources;
    DinSplit public dinSplit;
    EthSplit public ethSplit;

    // Buckets with no live consumer yet — accrued here, swept by future work
    // (P3-5.2 emission/reward pool, RES-1 storage, quadratic-funding module)
    mapping(bytes32 => uint256) public accruedDin;
    mapping(bytes32 => uint256) public accruedEth;

    // Reserved for future state variables at this inheritance level.
    uint256[50] private __gap;

    event FeeSourceAdded(address indexed source);
    event FeeSourceRemoved(address indexed source);
    event TreasuryUpdated(address indexed treasury);
    event TreasuryBpsCeilingUpdated(uint16 ceiling);
    event DinSplitUpdated(DinSplit split);
    event EthSplitUpdated(EthSplit split);
    event FeeRoutedDIN(
        address indexed payer,
        uint256 amount,
        uint256 burned,
        uint256 toTreasury,
        uint256 toValidatorPool,
        uint256 toStorage,
        uint256 toPublicGoods
    );
    event FeeRoutedETH(
        address indexed payer,
        uint256 amount,
        uint256 toTreasury,
        uint256 toValidatorPool,
        uint256 toStorage,
        uint256 toPublicGoods
    );

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /// @notice Initialises the router with the DIN token and treasury addresses.
    ///         Sets the treasury BPS ceiling to 20% and default splits to
    ///         validatorPool=95%, treasury=5%, burn/storage/publicGoods=0%.
    /// @param dinToken_ Address of the DinToken proxy.
    /// @param treasury_ Address of the DinTreasury proxy.
    function initialize(address dinToken_, address treasury_) external initializer {
        if (dinToken_ == address(0) || treasury_ == address(0)) revert InvalidAddress();
        __Ownable_init(msg.sender);
        dinToken = IBurnableERC20(dinToken_);
        treasury = treasury_;
        treasuryBpsCeiling = 2000;
        // Burn starts at 0% per the resolved decision ("start at 0%, keep the hook")
        dinSplit = DinSplit(9500, 500, 0, 0, 0);
        ethSplit = EthSplit(9500, 500, 0, 0);
    }

    modifier onlyFeeSource() {
        if (!feeSources[msg.sender]) revert NotFeeSource();
        _;
    }

    /// @notice Adds an address to the fee-source allowlist.
    /// @param source Address authorised to call routeFeeDIN / routeFeeETH.
    function addFeeSource(address source) external onlyOwner {
        if (source == address(0)) revert InvalidAddress();
        if (feeSources[source]) revert FeeSourceAlreadyAdded();
        feeSources[source] = true;
        emit FeeSourceAdded(source);
    }

    /// @notice Removes an address from the fee-source allowlist.
    function removeFeeSource(address source) external onlyOwner {
        if (!feeSources[source]) revert FeeSourceNotAdded();
        feeSources[source] = false;
        emit FeeSourceRemoved(source);
    }

    /// @notice Updates the treasury destination address.
    function setTreasury(address treasury_) external onlyOwner {
        if (treasury_ == address(0)) revert InvalidAddress();
        treasury = treasury_;
        emit TreasuryUpdated(treasury_);
    }

    /// @notice Sets the maximum BPS that can be allocated to treasury in either split.
    function setTreasuryBpsCeiling(uint16 ceiling) external onlyOwner {
        if (ceiling > BPS_DENOMINATOR) revert InvalidSplit();
        treasuryBpsCeiling = ceiling;
        emit TreasuryBpsCeilingUpdated(ceiling);
    }

    /// @notice Updates the DIN split configuration. All five fields must sum to 10000.
    function setDinSplit(DinSplit calldata s) external onlyOwner {
        uint256 sum = uint256(s.validatorPoolBps) + s.treasuryBps + s.burnBps + s.storageBps + s.publicGoodsBps;
        if (sum != BPS_DENOMINATOR) revert InvalidSplit();
        if (s.treasuryBps > treasuryBpsCeiling) revert TreasuryCutExceedsCeiling();
        dinSplit = s;
        emit DinSplitUpdated(s);
    }

    /// @notice Updates the ETH split configuration. All four fields must sum to 10000.
    function setEthSplit(EthSplit calldata s) external onlyOwner {
        uint256 sum = uint256(s.validatorPoolBps) + s.treasuryBps + s.storageBps + s.publicGoodsBps;
        if (sum != BPS_DENOMINATOR) revert InvalidSplit();
        if (s.treasuryBps > treasuryBpsCeiling) revert TreasuryCutExceedsCeiling();
        ethSplit = s;
        emit EthSplitUpdated(s);
    }

    /// @notice Pulls `amount` DIN from `payer` and routes it per the current DIN split.
    /// @dev Payer must have approved this router for at least `amount`.
    ///      publicGoods absorbs rounding dust — the five buckets always sum exactly to `amount`.
    function routeFeeDIN(address payer, uint256 amount) external onlyFeeSource nonReentrant {
        if (amount == 0) revert ZeroAmount();
        dinToken.safeTransferFrom(payer, address(this), amount);

        DinSplit memory s = dinSplit;
        uint256 burnAmt          = (amount * s.burnBps) / BPS_DENOMINATOR;
        uint256 treasuryAmt      = (amount * s.treasuryBps) / BPS_DENOMINATOR;
        uint256 validatorPoolAmt = (amount * s.validatorPoolBps) / BPS_DENOMINATOR;
        uint256 storageAmt       = (amount * s.storageBps) / BPS_DENOMINATOR;
        uint256 publicGoodsAmt   = amount - burnAmt - treasuryAmt - validatorPoolAmt - storageAmt;

        if (burnAmt > 0) dinToken.burn(burnAmt);
        if (treasuryAmt > 0) dinToken.safeTransfer(treasury, treasuryAmt);
        accruedDin[keccak256("validatorPool")] += validatorPoolAmt;
        accruedDin[keccak256("storage")]       += storageAmt;
        accruedDin[keccak256("publicGoods")]   += publicGoodsAmt;

        emit FeeRoutedDIN(payer, amount, burnAmt, treasuryAmt, validatorPoolAmt, storageAmt, publicGoodsAmt);
    }

    /// @notice Routes msg.value ETH per the current ETH split. No burn bucket —
    ///         ETH is never burned; the no-burn field is compile-time enforced via EthSplit.
    function routeFeeETH(address payer) external payable onlyFeeSource nonReentrant {
        if (msg.value == 0) revert ZeroAmount();
        EthSplit memory s = ethSplit;
        uint256 treasuryAmt      = (msg.value * s.treasuryBps) / BPS_DENOMINATOR;
        uint256 validatorPoolAmt = (msg.value * s.validatorPoolBps) / BPS_DENOMINATOR;
        uint256 storageAmt       = (msg.value * s.storageBps) / BPS_DENOMINATOR;
        uint256 publicGoodsAmt   = msg.value - treasuryAmt - validatorPoolAmt - storageAmt;

        if (treasuryAmt > 0) {
            (bool success, ) = payable(treasury).call{value: treasuryAmt}("");
            if (!success) revert TransferFailed();
        }
        accruedEth[keccak256("validatorPool")] += validatorPoolAmt;
        accruedEth[keccak256("storage")]       += storageAmt;
        accruedEth[keccak256("publicGoods")]   += publicGoodsAmt;

        emit FeeRoutedETH(payer, msg.value, treasuryAmt, validatorPoolAmt, storageAmt, publicGoodsAmt);
    }
}
