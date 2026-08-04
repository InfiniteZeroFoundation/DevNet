// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

/// @notice Lifecycle state of an emergency action.
enum ActionState {
    NotExist,  // 0 — action ID not allocated
    Active,    // 1 — action dispatched; ratification window open
    Ratified,  // 2 — DinGovernor ratified the action; no reversal needed
    Expired    // 3 — window elapsed without ratification; action reversed
}

/// @title IDinGuardian
/// @notice Interface for the DIN Guardian emergency authority contract.
///         Emergency actions are narrow, time-limited, and require governance
///         ratification within a fixed window or the action is reversed.
interface IDinGuardian {
    // ─── Events ──────────────────────────────────────────────────────────────

    /// @notice Emitted when an emergency action is dispatched.
    /// @param actionId   Auto-incremented action identifier.
    /// @param target     Contract the emergency call was made against.
    /// @param data       ABI-encoded calldata that was dispatched.
    /// @param expiry     Timestamp by which governance must ratify the action.
    /// @param description Human-readable description of the emergency.
    event EmergencyActionPerformed(
        uint256 indexed actionId,
        address indexed target,
        bytes data,
        uint256 expiry,
        string description
    );

    /// @notice Emitted when DinGovernor ratifies an active emergency action.
    /// @param actionId Identifier of the ratified action.
    event ActionRatified(uint256 indexed actionId);

    /// @notice Emitted when an action expires without ratification and is reversed.
    /// @param actionId    Identifier of the expired action.
    /// @param reversalData Calldata dispatched to reverse the original action.
    event ActionExpired(uint256 indexed actionId, bytes reversalData);

    /// @notice Emitted when the governor address is updated.
    /// @param newGovernor Address of the new DinGovernor.
    event GovernorUpdated(address indexed newGovernor);

    // ─── Core actions ─────────────────────────────────────────────────────────

    /// @notice Dispatch an emergency protective action.
    /// @dev    Only callable by the guardian (DinMultisig). The action is
    ///         recorded and a ratification window starts. If governance does
    ///         not ratify within the window, `expireAction` may be called to
    ///         reverse it.
    ///
    ///         Scope is deliberately narrow — protective actions only:
    ///         - disable a model in DINModelRegistry
    ///         - deauthorize a slasher in DinCoordinator
    ///         - pause a dangerous flow (any contract exposing a guardian-gated pause)
    ///
    ///         The reversal calldata must undo the original action exactly.
    ///         Platform contracts must expose an `onlyGuardian` path for each
    ///         emergency-eligible function (tracked as a follow-up integration task).
    ///
    /// @param target        Contract to call.
    /// @param data          ABI-encoded calldata for the emergency call.
    /// @param reversalData  ABI-encoded calldata that undoes the action if not ratified.
    /// @param description   Human-readable description (emitted in event for indexers).
    /// @return actionId     Auto-incremented identifier assigned to this action.
    function performAction(
        address target,
        bytes calldata data,
        bytes calldata reversalData,
        string calldata description
    ) external returns (uint256 actionId);

    /// @notice Ratify an active emergency action, preventing reversal.
    /// @dev    Only callable by DinGovernor (after a successful governance vote
    ///         confirming the emergency action was appropriate).
    /// @param actionId Identifier of the action to ratify.
    function ratifyAction(uint256 actionId) external;

    /// @notice Reverse an emergency action that was not ratified within the window.
    /// @dev    Callable by anyone after the ratification window has elapsed.
    ///         Dispatches the stored reversal calldata against the original target.
    /// @param actionId Identifier of the expired action to reverse.
    function expireAction(uint256 actionId) external;

    // ─── Admin ────────────────────────────────────────────────────────────────

    /// @notice Update the DinGovernor address that is permitted to ratify actions.
    /// @dev    Only callable by the guardian (DinMultisig). Should be called once
    ///         Stage C (DinGovernor) is deployed. Revocable by governance via a
    ///         standard governance proposal.
    /// @param newGovernor Address of the deployed DinGovernor.
    function setGovernor(address newGovernor) external;

    // ─── Views ────────────────────────────────────────────────────────────────

    /// @notice Returns the guardian address (DinMultisig).
    function guardian() external view returns (address);

    /// @notice Returns the DinGovernor address authorised to ratify actions.
    function governor() external view returns (address);

    /// @notice Returns the ratification window in seconds.
    function ratificationWindow() external view returns (uint256);

    /// @notice Returns the full details of an emergency action.
    /// @param actionId Identifier to query.
    /// @return target       Contract the emergency call was dispatched to.
    /// @return data         Calldata that was dispatched.
    /// @return reversalData Calldata to undo the action if not ratified.
    /// @return description  Human-readable description.
    /// @return state        Current action lifecycle state.
    /// @return expiry       Timestamp after which expireAction may be called.
    function getAction(uint256 actionId)
        external
        view
        returns (
            address target,
            bytes memory data,
            bytes memory reversalData,
            string memory description,
            ActionState state,
            uint256 expiry
        );

    /// @notice Returns the total number of emergency actions created.
    function actionCount() external view returns (uint256);
}
