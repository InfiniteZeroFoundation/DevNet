// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import "./interfaces/IDinGovernanceStaking.sol";

// ─────────────────────────────────────────────────────────────────────────────
// Custom errors
// ─────────────────────────────────────────────────────────────────────────────

/// @dev Lock amount must be greater than zero.
error GS_ZeroAmount();
/// @dev Caller holds insufficient stDIN to unlock the requested amount.
error GS_InsufficientBalance();
/// @dev stDIN is non-transferable; direct transfers are not permitted.
error GS_NonTransferable();

// ─────────────────────────────────────────────────────────────────────────────
// DinGovernanceStaking
// ─────────────────────────────────────────────────────────────────────────────

/// @title DIN Governance Staking (stDIN)
/// @notice Lock DIN tokens to receive non-transferable, checkpointed voting power
///         for use with DinGovernor. Implements OZ IVotes via ERC20Votes.
/// @dev    Voting power is based on locked DIN, not free balances or validator
///         stake, enforcing the two standing decisions from the governance spec:
///         no free-balance voting, no raw quadratic voting.
///
///         stDIN is 1:1 with locked DIN but non-transferable — `transfer` and
///         `transferFrom` always revert. Accounts must self-delegate or delegate
///         to another address to activate voting power; undelegated stDIN does
///         not count toward Governor quorum.
///
///         Validator stake in DinValidatorStake is explicitly excluded from
///         governance power in v1 to avoid conflicts of interest when governance
///         votes on slashing conditions or blacklisting appeals.
contract DinGovernanceStaking is ERC20, ERC20Votes, ReentrancyGuard, IDinGovernanceStaking {
    using SafeERC20 for IERC20;

    // ─── Immutables ───────────────────────────────────────────────────────────

    IERC20 private immutable _dinToken;

    // ─── Constructor ──────────────────────────────────────────────────────────

    /// @notice Deploy stDIN bound to a specific DIN token address.
    /// @param dinToken_ Address of the DIN ERC-20 token to accept as collateral.
    constructor(address dinToken_)
        ERC20("Staked DIN", "stDIN")
        EIP712("Staked DIN", "1")
    {
        require(dinToken_ != address(0));
        _dinToken = IERC20(dinToken_);
    }

    // ─── Core actions ─────────────────────────────────────────────────────────

    /// @inheritdoc IDinGovernanceStaking
    function lock(uint256 amount) external nonReentrant {
        if (amount == 0) revert GS_ZeroAmount();
        _dinToken.safeTransferFrom(msg.sender, address(this), amount);
        _mint(msg.sender, amount);
        emit Locked(msg.sender, amount);
    }

    /// @inheritdoc IDinGovernanceStaking
    function unlock(uint256 amount) external nonReentrant {
        if (amount == 0) revert GS_ZeroAmount();
        if (balanceOf(msg.sender) < amount) revert GS_InsufficientBalance();
        _burn(msg.sender, amount);
        _dinToken.safeTransfer(msg.sender, amount);
        emit Unlocked(msg.sender, amount);
    }

    // ─── Non-transferability ──────────────────────────────────────────────────

    /// @dev Reverts unconditionally; stDIN cannot be moved between accounts.
    function transfer(address, uint256) public pure override(ERC20, IERC20) returns (bool) {
        revert GS_NonTransferable();
    }

    /// @dev Reverts unconditionally; stDIN cannot be moved between accounts.
    function transferFrom(address, address, uint256)
        public
        pure
        override(ERC20, IERC20)
        returns (bool)
    {
        revert GS_NonTransferable();
    }

    // ─── Views ────────────────────────────────────────────────────────────────

    /// @inheritdoc IDinGovernanceStaking
    function dinToken() external view returns (address) {
        return address(_dinToken);
    }

    /// @inheritdoc IDinGovernanceStaking
    function totalLocked() external view returns (uint256) {
        return _dinToken.balanceOf(address(this));
    }

    // ─── ERC20Votes overrides ─────────────────────────────────────────────────

    /// @dev Required by ERC20Votes to compute voting units from balance.
    function _update(address from, address to, uint256 value)
        internal
        override(ERC20, ERC20Votes)
    {
        super._update(from, to, value);
    }

    /// @dev Required by ERC20Votes; returns the block number as the clock value.
    function clock() public view override returns (uint48) {
        return uint48(block.number);
    }

    /// @dev Declares that this contract uses block numbers as the clock mode.
    // solhint-disable-next-line func-name-mixedcase
    function CLOCK_MODE() public pure override returns (string memory) {
        return "mode=blocknumber&from=default";
    }
}
