// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

/// @title IDinGovernanceStaking
/// @notice Interface for the DIN Governance Staking contract (stDIN).
///         Locking DIN mints non-transferable stDIN that carries checkpointed
///         voting power for DinGovernor.
interface IDinGovernanceStaking {
    // ─── Events ──────────────────────────────────────────────────────────────

    /// @notice Emitted when a user locks DIN and receives stDIN.
    /// @param account Address that performed the lock.
    /// @param amount  DIN amount locked (and stDIN minted).
    event Locked(address indexed account, uint256 amount);

    /// @notice Emitted when a user unlocks DIN by burning stDIN.
    /// @param account Address that performed the unlock.
    /// @param amount  DIN amount returned (and stDIN burned).
    event Unlocked(address indexed account, uint256 amount);

    // ─── Core actions ─────────────────────────────────────────────────────────

    /// @notice Lock DIN and receive an equivalent amount of stDIN voting power.
    /// @dev    Caller must have approved this contract for at least `amount` DIN.
    ///         stDIN is non-transferable; voting power is immediately checkpointed.
    ///         Caller must call `delegate(self)` to activate their own votes.
    /// @param amount DIN amount to lock.
    function lock(uint256 amount) external;

    /// @notice Unlock DIN by burning an equivalent amount of stDIN.
    /// @dev    Voting power is immediately reduced. Any active delegation is
    ///         automatically adjusted by the underlying ERC20Votes checkpoint.
    /// @param amount stDIN amount to burn (equal to DIN returned).
    function unlock(uint256 amount) external;

    // ─── Views ────────────────────────────────────────────────────────────────

    /// @notice Returns the address of the underlying DIN ERC-20 token.
    function dinToken() external view returns (address);

    /// @notice Returns the total DIN currently held in this contract.
    function totalLocked() external view returns (uint256);
}
