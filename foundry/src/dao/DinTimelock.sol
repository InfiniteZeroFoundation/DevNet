// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "@openzeppelin/contracts/governance/TimelockController.sol";

// ─────────────────────────────────────────────────────────────────────────────
// DinTimelock
// ─────────────────────────────────────────────────────────────────────────────

/// @title DIN Timelock
/// @notice Thin instantiation of OZ TimelockController for DIN DAO governance.
/// @dev    Deployed as two independent instances with different minimum delays:
///
///         - DinTimelockShort (24 h) — Parameter and Operational proposals.
///           Bounded parameter changes whose blast radius is limited; a wrong
///           fee can be corrected in the next proposal cycle.
///
///         - DinTimelockLong (48 h) — Treasury and Upgrade proposals.
///           Higher blast radius; 48 h gives DIN participants (validators,
///           clients, aggregators) adequate time to observe a pending upgrade
///           and exit if they disagree.
///
///         Both instances should be deployed with:
///           - proposers   = [DinMultisig]
///           - executors   = [address(0)]  (open execution — anyone can execute
///                                          once the delay has elapsed)
///           - admin       = address(0)    (renounce DEFAULT_ADMIN_ROLE at
///                                          construction; no post-deploy admin)
///
///         At Stage C, DinGovernor is added as an additional proposer on both
///         instances via a governance proposal routed through the existing multisig.
///
///         The governance contracts themselves (Governor, Timelock) are
///         non-upgradeable — the contract guarding upgrades must not itself be
///         upgradeable or the trust problem shifts up a level.
contract DinTimelock is TimelockController {
    /// @notice Deploy a DIN Timelock instance.
    /// @param minDelay_   Minimum seconds between scheduling and execution.
    ///                    Pass 86400 (24 h) for the short instance or
    ///                    172800 (48 h) for the long instance.
    /// @param proposers_  Addresses granted PROPOSER_ROLE (initially DinMultisig).
    /// @param executors_  Addresses granted EXECUTOR_ROLE. Pass [address(0)] for
    ///                    open execution (anyone may execute after the delay).
    /// @param admin_      Address granted DEFAULT_ADMIN_ROLE. Pass address(0) to
    ///                    renounce all admin authority at construction.
    constructor(
        uint256 minDelay_,
        address[] memory proposers_,
        address[] memory executors_,
        address admin_
    ) TimelockController(minDelay_, proposers_, executors_, admin_) {}
}
