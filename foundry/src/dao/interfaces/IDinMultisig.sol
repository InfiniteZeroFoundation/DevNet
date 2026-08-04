// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

/// @notice Risk category of a multisig proposal.
/// @dev Maps to per-category confirmation thresholds stored in DinMultisig.
enum ProposalCategory {
    Parameter,   // 0 — fee updates, rate changes, bounded numeric parameters
    Operational, // 1 — slasher auth, model disable/enable, validator blacklisting
    Treasury,    // 2 — ETH or token withdrawals, grant disbursements
    Upgrade      // 3 — platform contract upgrades, ProxyAdmin transfer
}

/// @notice Lifecycle state of a multisig proposal.
enum ProposalState {
    NotExist,   // 0 — proposal ID not yet allocated
    Open,       // 1 — created; collecting confirmations
    Executable, // 2 — confirmation threshold reached; ready to execute
    Executed,   // 3 — call dispatched successfully
    Cancelled   // 4 — cancelled by any signer before execution
}

/// @title IDinMultisig
/// @notice Interface for the DIN N-of-M multisig with typed, per-category proposals.
interface IDinMultisig {
    // ─── Events ──────────────────────────────────────────────────────────────

    /// @notice Emitted when a new proposal is created.
    /// @param proposalId Auto-incremented proposal identifier.
    /// @param proposer   Signer who submitted the proposal.
    /// @param target     Contract the proposal will call.
    /// @param category   Risk category governing the confirmation threshold.
    event ProposalCreated(
        uint256 indexed proposalId,
        address indexed proposer,
        address target,
        ProposalCategory category
    );

    /// @notice Emitted when a signer confirms a proposal.
    /// @param proposalId   Identifier of the confirmed proposal.
    /// @param signer       Address that added its confirmation.
    /// @param confirmCount Running total of confirmations after this one.
    event ProposalConfirmed(
        uint256 indexed proposalId,
        address indexed signer,
        uint256 confirmCount
    );

    /// @notice Emitted when a signer revokes a previously cast confirmation.
    /// @param proposalId   Identifier of the affected proposal.
    /// @param signer       Address that withdrew its confirmation.
    /// @param confirmCount Running total of confirmations after the revocation.
    event ProposalRevoked(
        uint256 indexed proposalId,
        address indexed signer,
        uint256 confirmCount
    );

    /// @notice Emitted when a proposal transitions from Open to Executable.
    /// @param proposalId Identifier of the proposal that reached its threshold.
    event ProposalExecutable(uint256 indexed proposalId);

    /// @notice Emitted when an executable proposal is successfully dispatched.
    /// @param proposalId Identifier of the executed proposal.
    /// @param executor   Address that triggered execution.
    event ProposalExecuted(uint256 indexed proposalId, address indexed executor);

    /// @notice Emitted when a proposal is cancelled.
    /// @param proposalId Identifier of the cancelled proposal.
    /// @param canceller  Signer who cancelled it.
    event ProposalCancelled(uint256 indexed proposalId, address indexed canceller);

    // ─── Core actions ─────────────────────────────────────────────────────────

    /// @notice Submit a new proposal.
    /// @param target   Contract address to call upon execution.
    /// @param data     ABI-encoded calldata for the target call.
    /// @param value    ETH value to forward with the call.
    /// @param category Risk category that determines the required confirmation count.
    /// @return proposalId Auto-incremented identifier assigned to this proposal.
    function propose(
        address target,
        bytes calldata data,
        uint256 value,
        ProposalCategory category
    ) external returns (uint256 proposalId);

    /// @notice Add the caller's confirmation to an open proposal.
    /// @dev    Automatically transitions state to Executable when the threshold is met.
    /// @param proposalId Identifier of the proposal to confirm.
    function confirm(uint256 proposalId) external;

    /// @notice Withdraw the caller's confirmation from a proposal.
    /// @dev    If the proposal was Executable, it reverts to Open.
    /// @param proposalId Identifier of the proposal to revoke confirmation for.
    function revoke(uint256 proposalId) external;

    /// @notice Dispatch an executable proposal.
    /// @param proposalId Identifier of the proposal to execute.
    function execute(uint256 proposalId) external payable;

    /// @notice Cancel an open or executable proposal.
    /// @param proposalId Identifier of the proposal to cancel.
    function cancel(uint256 proposalId) external;

    // ─── Views ────────────────────────────────────────────────────────────────

    /// @notice Returns the full details of a proposal.
    /// @param proposalId Identifier to query.
    /// @return target       Contract to be called.
    /// @return data         Calldata for the target.
    /// @return value        ETH value attached to the call.
    /// @return category     Risk category of the proposal.
    /// @return state        Current lifecycle state.
    /// @return confirmCount Number of confirmations currently held.
    /// @return createdAt    Block timestamp when the proposal was created.
    function getProposal(uint256 proposalId)
        external
        view
        returns (
            address target,
            bytes memory data,
            uint256 value,
            ProposalCategory category,
            ProposalState state,
            uint256 confirmCount,
            uint256 createdAt
        );

    /// @notice Returns the full signer list.
    function signers() external view returns (address[] memory);

    /// @notice Returns the confirmation threshold for a given category.
    /// @param category Category to query.
    function threshold(ProposalCategory category) external view returns (uint256);

    /// @notice Returns whether the given address is an authorized signer.
    /// @param account Address to check.
    function isSigner(address account) external view returns (bool);

    /// @notice Returns whether a specific signer has confirmed a proposal.
    /// @param proposalId Proposal to query.
    /// @param signer     Signer address to check.
    function hasConfirmed(uint256 proposalId, address signer) external view returns (bool);

    /// @notice Returns the total number of proposals created (including cancelled/executed).
    function proposalCount() external view returns (uint256);
}
