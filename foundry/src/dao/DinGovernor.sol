// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "@openzeppelin/contracts/governance/Governor.sol";
import "@openzeppelin/contracts/governance/extensions/GovernorSettings.sol";
import "@openzeppelin/contracts/governance/extensions/GovernorCountingSimple.sol";
import "@openzeppelin/contracts/governance/extensions/GovernorVotes.sol";
import "@openzeppelin/contracts/governance/extensions/GovernorVotesQuorumFraction.sol";
import "@openzeppelin/contracts/governance/extensions/GovernorTimelockControl.sol";

// ─────────────────────────────────────────────────────────────────────────────
// DinGovernor
// ─────────────────────────────────────────────────────────────────────────────

/// @title DIN Governor
/// @notice On-chain token-vote governor for the DIN DAO. Stage C of the
///         progressive-decentralisation rollout (testnet 1.0).
/// @dev    Composition:
///           - GovernorSettings        — votingDelay, votingPeriod, proposalThreshold
///                                       (all governance-settable post-deployment)
///           - GovernorCountingSimple  — For / Against / Abstain counting
///           - GovernorVotes           — voting power from DinGovernanceStaking (IVotes)
///           - GovernorVotesQuorumFraction — quorumNumerator as % of total supply
///           - GovernorTimelockControl — queues and executes through DinTimelock
///
///         Proposal routing: the proposer encodes the target timelock address
///         in the proposal's targets array. Short-delay proposals target
///         DinTimelockShort; long-delay proposals target DinTimelockLong.
///         This avoids two Governor instances while preserving the two-delay model.
///
///         DinMultisig retains CANCELLER_ROLE on both timelocks as a safety
///         brake — it can cancel a queued proposal before execution if the
///         technical team identifies a critical flaw.
///
///         All governance parameters are adjustable by governance itself after
///         deployment. Initial values should be conservative and tightened once
///         token distribution matures.
contract DinGovernor is
    Governor,
    GovernorSettings,
    GovernorCountingSimple,
    GovernorVotes,
    GovernorVotesQuorumFraction,
    GovernorTimelockControl
{
    // ─── Constructor ──────────────────────────────────────────────────────────

    /// @notice Deploy DinGovernor bound to a stDIN voting token and a timelock.
    /// @dev    Pass DinTimelockLong as the primary timelock. Short-delay proposals
    ///         are routed by encoding DinTimelockShort as the call target in the
    ///         proposal's targets array rather than requiring a second Governor.
    /// @param token_             DinGovernanceStaking (stDIN) address — the IVotes source.
    /// @param timelock_          DinTimelockLong address for proposal execution.
    /// @param initialVotingDelay Blocks before voting opens after a proposal is created.
    ///                           Suggested: 7200 (≈ 24 h at 12-second blocks on L1;
    ///                           use 1800 for OP-stack L2 with 2-second blocks).
    /// @param initialVotingPeriod Blocks the voting window stays open.
    ///                           Suggested: 50400 (≈ 7 days on L1; 151200 on OP-stack).
    /// @param initialProposalThreshold Minimum voting power required to submit a proposal.
    /// @param initialQuorumFraction    Quorum as a percentage of total stDIN supply (e.g. 4
    ///                                 for 4%). Upgrade and treasury proposals should be
    ///                                 submitted with a higher quorum target encoded in the
    ///                                 proposal description until per-category quorum is
    ///                                 implemented in a future Governor extension.
    constructor(
        IVotes token_,
        TimelockController timelock_,
        uint48 initialVotingDelay,
        uint32 initialVotingPeriod,
        uint256 initialProposalThreshold,
        uint256 initialQuorumFraction
    )
        Governor("DIN Governor")
        GovernorSettings(initialVotingDelay, initialVotingPeriod, initialProposalThreshold)
        GovernorVotes(token_)
        GovernorVotesQuorumFraction(initialQuorumFraction)
        GovernorTimelockControl(timelock_)
    {}

    // ─── Required overrides ───────────────────────────────────────────────────

    /// @inheritdoc IGovernor
    function votingDelay() public view override(Governor, GovernorSettings) returns (uint256) {
        return super.votingDelay();
    }

    /// @inheritdoc IGovernor
    function votingPeriod() public view override(Governor, GovernorSettings) returns (uint256) {
        return super.votingPeriod();
    }

    /// @inheritdoc IGovernor
    function quorum(uint256 blockNumber)
        public
        view
        override(Governor, GovernorVotesQuorumFraction)
        returns (uint256)
    {
        return super.quorum(blockNumber);
    }

    /// @inheritdoc Governor
    function proposalThreshold()
        public
        view
        override(Governor, GovernorSettings)
        returns (uint256)
    {
        return super.proposalThreshold();
    }

    /// @inheritdoc Governor
    function state(uint256 proposalId)
        public
        view
        override(Governor, GovernorTimelockControl)
        returns (ProposalState)
    {
        return super.state(proposalId);
    }

    /// @inheritdoc Governor
    function proposalNeedsQueuing(uint256 proposalId)
        public
        view
        override(Governor, GovernorTimelockControl)
        returns (bool)
    {
        return super.proposalNeedsQueuing(proposalId);
    }

    /// @inheritdoc Governor
    function _queueOperations(
        uint256 proposalId,
        address[] memory targets,
        uint256[] memory values,
        bytes[] memory calldatas,
        bytes32 descriptionHash
    ) internal override(Governor, GovernorTimelockControl) returns (uint48) {
        return super._queueOperations(proposalId, targets, values, calldatas, descriptionHash);
    }

    /// @inheritdoc Governor
    function _executeOperations(
        uint256 proposalId,
        address[] memory targets,
        uint256[] memory values,
        bytes[] memory calldatas,
        bytes32 descriptionHash
    ) internal override(Governor, GovernorTimelockControl) {
        super._executeOperations(proposalId, targets, values, calldatas, descriptionHash);
    }

    /// @inheritdoc Governor
    function _cancel(
        address[] memory targets,
        uint256[] memory values,
        bytes[] memory calldatas,
        bytes32 descriptionHash
    ) internal override(Governor, GovernorTimelockControl) returns (uint256) {
        return super._cancel(targets, values, calldatas, descriptionHash);
    }

    /// @inheritdoc Governor
    function _executor()
        internal
        view
        override(Governor, GovernorTimelockControl)
        returns (address)
    {
        return super._executor();
    }
}
