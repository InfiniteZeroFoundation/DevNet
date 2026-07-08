// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "./interfaces/IDinGuardian.sol";

// ─────────────────────────────────────────────────────────────────────────────
// Custom errors
// ─────────────────────────────────────────────────────────────────────────────

/// @dev Caller is not the designated guardian (DinMultisig).
error DG_NotGuardian();
/// @dev Caller is not the designated governor (DinGovernor).
error DG_NotGovernor();
/// @dev The action ID does not correspond to any existing emergency action.
error DG_InvalidActionId();
/// @dev The action is not in the Active state and cannot be ratified.
error DG_ActionNotActive();
/// @dev The ratification window has not elapsed; the action cannot be expired yet.
error DG_WindowNotElapsed();
/// @dev The action was already ratified or expired; it cannot be expired again.
error DG_ActionNotExpirable();
/// @dev The emergency call dispatched to the target reverted.
error DG_ActionCallFailed();
/// @dev The reversal call dispatched on expiry reverted.
error DG_ReversalCallFailed();
/// @dev The supplied address is the zero address.
error DG_ZeroAddress();

// ─────────────────────────────────────────────────────────────────────────────
// DinGuardian
// ─────────────────────────────────────────────────────────────────────────────

/// @title DIN Guardian
/// @notice Narrow-scope emergency authority for the DIN platform. Stage D of
///         the progressive-decentralisation rollout (testnet 1.0 alongside Stage C).
/// @dev    Every emergency action has a fixed ratification window. If DinGovernor
///         does not ratify within the window, any address may call `expireAction`
///         to dispatch the stored reversal calldata and undo the original action.
///
///         Scope is deliberately limited to protective operations:
///         - disable a malicious model in DINModelRegistry
///         - deauthorize a dangerous slasher contract in DinCoordinator
///         - trigger a guardian-gated pause on any platform contract that
///           exposes one
///
///         Restorative actions (re-enable model, re-authorize slasher,
///         unblacklist validator) are never permitted as emergency actions —
///         they must always go through normal governance.
///
///         Platform contracts must expose an `onlyGuardian` path for each
///         emergency-eligible function before Stage D activation. That integration
///         is tracked as a separate follow-up task.
///
///         The guardian role is held by DinMultisig and is revocable by governance
///         via a standard Upgrade-category proposal that deploys a new guardian and
///         transfers the guardian address on each platform contract.
contract DinGuardian is IDinGuardian {
    // ─── Storage ──────────────────────────────────────────────────────────────

    struct Action {
        address target;
        bytes data;
        bytes reversalData;
        string description;
        ActionState state;
        uint256 expiry;
    }

    address private _guardian;
    address private _governor;
    uint256 private immutable _ratificationWindow;
    uint256 private _actionCount;
    mapping(uint256 => Action) private _actions;

    // ─── Constructor ──────────────────────────────────────────────────────────

    /// @notice Deploy the guardian with a fixed guardian address and ratification window.
    /// @dev    `governor_` may be address(0) at deployment if Stage C is not yet live.
    ///         Call `setGovernor` once DinGovernor is deployed.
    /// @param guardian_           Address of DinMultisig (holds the guardian role).
    /// @param governor_           Address of DinGovernor (permitted to ratify actions).
    /// @param ratificationWindow_ Seconds after an action is performed during which
    ///                            governance must ratify it. 7 days is the recommended
    ///                            initial value — long enough for a governance vote to
    ///                            complete, short enough to avoid indefinitely suspended
    ///                            emergency state.
    constructor(address guardian_, address governor_, uint256 ratificationWindow_) {
        if (guardian_ == address(0)) revert DG_ZeroAddress();
        _guardian            = guardian_;
        _governor            = governor_;
        _ratificationWindow  = ratificationWindow_;
    }

    // ─── Modifiers ────────────────────────────────────────────────────────────

    modifier onlyGuardian() {
        if (msg.sender != _guardian) revert DG_NotGuardian();
        _;
    }

    modifier onlyGovernor() {
        if (msg.sender != _governor) revert DG_NotGovernor();
        _;
    }

    // ─── Core actions ─────────────────────────────────────────────────────────

    /// @inheritdoc IDinGuardian
    function performAction(
        address target,
        bytes calldata data,
        bytes calldata reversalData,
        string calldata description
    ) external onlyGuardian returns (uint256 actionId) {
        if (target == address(0)) revert DG_ZeroAddress();

        actionId = _actionCount++;
        uint256 expiry = block.timestamp + _ratificationWindow;

        _actions[actionId] = Action({
            target:       target,
            data:         data,
            reversalData: reversalData,
            description:  description,
            state:        ActionState.Active,
            expiry:       expiry
        });

        (bool ok, ) = target.call(data);
        if (!ok) revert DG_ActionCallFailed();

        emit EmergencyActionPerformed(actionId, target, data, expiry, description);
    }

    /// @inheritdoc IDinGuardian
    function ratifyAction(uint256 actionId) external onlyGovernor {
        Action storage a = _actions[actionId];
        if (a.state == ActionState.NotExist) revert DG_InvalidActionId();
        if (a.state != ActionState.Active)   revert DG_ActionNotActive();

        a.state = ActionState.Ratified;
        emit ActionRatified(actionId);
    }

    /// @inheritdoc IDinGuardian
    function expireAction(uint256 actionId) external {
        Action storage a = _actions[actionId];
        if (a.state == ActionState.NotExist) revert DG_InvalidActionId();
        if (a.state != ActionState.Active)   revert DG_ActionNotExpirable();
        if (block.timestamp < a.expiry)      revert DG_WindowNotElapsed();

        a.state = ActionState.Expired;

        bytes memory reversal = a.reversalData;
        if (reversal.length > 0) {
            (bool ok, ) = a.target.call(reversal);
            if (!ok) revert DG_ReversalCallFailed();
        }

        emit ActionExpired(actionId, reversal);
    }

    // ─── Admin ────────────────────────────────────────────────────────────────

    /// @inheritdoc IDinGuardian
    function setGovernor(address newGovernor) external onlyGuardian {
        if (newGovernor == address(0)) revert DG_ZeroAddress();
        _governor = newGovernor;
        emit GovernorUpdated(newGovernor);
    }

    // ─── Views ────────────────────────────────────────────────────────────────

    /// @inheritdoc IDinGuardian
    function guardian() external view returns (address) {
        return _guardian;
    }

    /// @inheritdoc IDinGuardian
    function governor() external view returns (address) {
        return _governor;
    }

    /// @inheritdoc IDinGuardian
    function ratificationWindow() external view returns (uint256) {
        return _ratificationWindow;
    }

    /// @inheritdoc IDinGuardian
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
        )
    {
        if (actionId >= _actionCount) revert DG_InvalidActionId();
        Action storage a = _actions[actionId];
        return (a.target, a.data, a.reversalData, a.description, a.state, a.expiry);
    }

    /// @inheritdoc IDinGuardian
    function actionCount() external view returns (uint256) {
        return _actionCount;
    }
}
