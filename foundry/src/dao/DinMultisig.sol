// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "./interfaces/IDinMultisig.sol";

// ─────────────────────────────────────────────────────────────────────────────
// Custom errors
// ─────────────────────────────────────────────────────────────────────────────

/// @dev Caller is not an authorised signer on this multisig.
error MS_NotSigner();
/// @dev The proposal is not in the Open state; confirmation cannot be added.
error MS_ProposalNotOpen();
/// @dev The proposal is not in the Executable state; it cannot be dispatched.
error MS_ProposalNotExecutable();
/// @dev The proposal is not in a cancellable state (Open or Executable).
error MS_ProposalNotCancellable();
/// @dev This signer has already confirmed the proposal.
error MS_AlreadyConfirmed();
/// @dev This signer has not confirmed the proposal; nothing to revoke.
error MS_NotConfirmed();
/// @dev The supplied address is the zero address.
error MS_ZeroAddress();
/// @dev The signer list must contain at least one address.
error MS_EmptySignerList();
/// @dev The signer list contains a duplicate address.
error MS_DuplicateSigner();
/// @dev A confirmation threshold must be at least 1 and at most the signer count.
error MS_InvalidThreshold();
/// @dev The proposal ID does not correspond to any existing proposal.
error MS_InvalidProposalId();
/// @dev The low-level call dispatched by execute() reverted.
error MS_ExecutionFailed();

// ─────────────────────────────────────────────────────────────────────────────
// DinMultisig
// ─────────────────────────────────────────────────────────────────────────────

/// @title DIN Multisig
/// @notice N-of-M multisig with per-category typed proposals for DAO governance
///         of the DIN platform. Stage A of the progressive-decentralisation rollout.
/// @dev    Proposal categories carry independent confirmation thresholds so that
///         high-risk actions (treasury withdrawals, contract upgrades) require broader
///         signer consensus than routine parameter changes. After Stage B is deployed,
///         this contract holds PROPOSER_ROLE and CANCELLER_ROLE on DinTimelock.
///
///         Signers and per-category thresholds are immutable after construction.
///         To change signers, deploy a new DinMultisig and transfer roles on the
///         timelocks via an Upgrade-category proposal through the existing instance.
contract DinMultisig is IDinMultisig {
    // ─── Storage ──────────────────────────────────────────────────────────────

    struct Proposal {
        address target;
        bytes data;
        uint256 value;
        ProposalCategory category;
        ProposalState state;
        uint256 confirmCount;
        uint256 createdAt;
    }

    address[] private _signers;
    mapping(address => bool) private _isSigner;
    mapping(ProposalCategory => uint256) private _threshold;

    uint256 private _proposalCount;
    mapping(uint256 => Proposal) private _proposals;
    mapping(uint256 => mapping(address => bool)) private _confirmed;

    // ─── Constructor ──────────────────────────────────────────────────────────

    /// @notice Deploy the multisig with a fixed signer set and per-category thresholds.
    /// @dev    Thresholds are supplied as a fixed-length array indexed by
    ///         `ProposalCategory`: [Parameter, Operational, Treasury, Upgrade].
    ///         Each threshold must be in [1, signers.length].
    /// @param signers_    Ordered list of authorised signer addresses (no duplicates).
    /// @param thresholds_ Confirmation counts required per category (4-element array).
    constructor(address[] memory signers_, uint256[4] memory thresholds_) {
        uint256 n = signers_.length;
        if (n == 0) revert MS_EmptySignerList();

        for (uint256 i; i < n; ++i) {
            address s = signers_[i];
            if (s == address(0)) revert MS_ZeroAddress();
            if (_isSigner[s]) revert MS_DuplicateSigner();
            _isSigner[s] = true;
            _signers.push(s);
        }

        for (uint256 c; c < 4; ++c) {
            uint256 t = thresholds_[c];
            if (t == 0 || t > n) revert MS_InvalidThreshold();
            _threshold[ProposalCategory(c)] = t;
        }
    }

    // ─── Modifiers ────────────────────────────────────────────────────────────

    modifier onlySigner() {
        if (!_isSigner[msg.sender]) revert MS_NotSigner();
        _;
    }

    // ─── Core actions ─────────────────────────────────────────────────────────

    /// @inheritdoc IDinMultisig
    function propose(
        address target,
        bytes calldata data,
        uint256 value,
        ProposalCategory category
    ) external onlySigner returns (uint256 proposalId) {
        if (target == address(0)) revert MS_ZeroAddress();

        proposalId = _proposalCount++;

        Proposal storage p = _proposals[proposalId];
        p.target = target;
        p.data = data;
        p.value = value;
        p.category = category;
        p.state = ProposalState.Open;
        p.createdAt = block.timestamp;

        emit ProposalCreated(proposalId, msg.sender, target, category);
    }

    /// @inheritdoc IDinMultisig
    function confirm(uint256 proposalId) external onlySigner {
        Proposal storage p = _proposals[proposalId];
        if (p.state != ProposalState.Open) revert MS_ProposalNotOpen();
        if (_confirmed[proposalId][msg.sender]) revert MS_AlreadyConfirmed();

        _confirmed[proposalId][msg.sender] = true;
        uint256 count = ++p.confirmCount;

        emit ProposalConfirmed(proposalId, msg.sender, count);

        if (count >= _threshold[p.category]) {
            p.state = ProposalState.Executable;
            emit ProposalExecutable(proposalId);
        }
    }

    /// @inheritdoc IDinMultisig
    function revoke(uint256 proposalId) external onlySigner {
        Proposal storage p = _proposals[proposalId];
        if (p.state != ProposalState.Open && p.state != ProposalState.Executable) {
            revert MS_ProposalNotCancellable();
        }
        if (!_confirmed[proposalId][msg.sender]) revert MS_NotConfirmed();

        _confirmed[proposalId][msg.sender] = false;
        uint256 count = --p.confirmCount;

        emit ProposalRevoked(proposalId, msg.sender, count);

        if (p.state == ProposalState.Executable && count < _threshold[p.category]) {
            p.state = ProposalState.Open;
        }
    }

    /// @inheritdoc IDinMultisig
    function execute(uint256 proposalId) external payable onlySigner {
        Proposal storage p = _proposals[proposalId];
        if (p.state != ProposalState.Executable) revert MS_ProposalNotExecutable();

        p.state = ProposalState.Executed;

        (bool success, ) = p.target.call{value: p.value}(p.data);
        if (!success) revert MS_ExecutionFailed();

        emit ProposalExecuted(proposalId, msg.sender);
    }

    /// @inheritdoc IDinMultisig
    function cancel(uint256 proposalId) external onlySigner {
        Proposal storage p = _proposals[proposalId];
        if (p.state != ProposalState.Open && p.state != ProposalState.Executable) {
            revert MS_ProposalNotCancellable();
        }

        p.state = ProposalState.Cancelled;
        emit ProposalCancelled(proposalId, msg.sender);
    }

    // ─── Views ────────────────────────────────────────────────────────────────

    /// @inheritdoc IDinMultisig
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
        )
    {
        if (proposalId >= _proposalCount) revert MS_InvalidProposalId();
        Proposal storage p = _proposals[proposalId];
        return (p.target, p.data, p.value, p.category, p.state, p.confirmCount, p.createdAt);
    }

    /// @inheritdoc IDinMultisig
    function signers() external view returns (address[] memory) {
        return _signers;
    }

    /// @inheritdoc IDinMultisig
    function threshold(ProposalCategory category) external view returns (uint256) {
        return _threshold[category];
    }

    /// @inheritdoc IDinMultisig
    function isSigner(address account) external view returns (bool) {
        return _isSigner[account];
    }

    /// @inheritdoc IDinMultisig
    function hasConfirmed(uint256 proposalId, address signer) external view returns (bool) {
        return _confirmed[proposalId][signer];
    }

    /// @inheritdoc IDinMultisig
    function proposalCount() external view returns (uint256) {
        return _proposalCount;
    }

    // ─── ETH receiver ─────────────────────────────────────────────────────────

    /// @notice Allows the multisig to receive ETH (e.g. for value-bearing proposals).
    receive() external payable {}
}
