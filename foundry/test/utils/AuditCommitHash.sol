// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @dev The DINTaskAuditor commit hash, in one place for every test that
///      commits audit scores. Must match revealAuditScore exactly: it binds the
///      committing auditor and the (gi, batchId, modelIndex) slot (issue #192),
///      so a hash is valid for one auditor and one model only -- tests must
///      hash per auditor, not reuse one hash across an auditor loop.
function auditCommitHash(
    uint256 score,
    bool vote,
    bytes32 salt,
    address auditor,
    uint256 gi,
    uint256 batchId,
    uint256 modelIndex
) pure returns (bytes32) {
    return keccak256(abi.encode(score, vote, salt, auditor, gi, batchId, modelIndex));
}
