// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuardTransient} from "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";
import "./DINShared.sol";

/// @title DIN Task Coordinator
/// @notice Orchestrates the full Global Iteration (GI) lifecycle for a single
///         federated-learning model: slasher setup, validator registration,
///         local model submissions, auditing, Tier-1/Tier-2 aggregation, and
///         validator slashing. Deployed once per model by the model owner.
contract DINTaskCoordinator is Ownable, ReentrancyGuardTransient {
    using SafeERC20 for IERC20;

    IDinValidatorStake public dinvalidatorStakeContract;
    IDINTaskAuditor public dinTaskAuditorContract;

    uint public GI = 0; // GlobalIteration

    GIstates public GIstate;

    bytes32 public genesisModelIpfsHash; // genesis model ipfs hash

    mapping(uint => address[]) public dinAggregators;

    // Track if an address is registered for a given _GI as an aggregator
    mapping(uint => mapping(address => bool)) public isDINAggregator;

    uint256 public constant T1_AGGREGATORS_PER_BATCH = 3;
    uint256 public constant T1_MODELS_PER_BATCH = 3;
    uint256 public constant MIN_T1_MODELS_PER_BATCH = 2;

    struct Tier1Batch {
        uint batchId; // Unique inside round
        address[] aggregators; // Aggregators assigned
        uint[] modelIndexes; // Indexes into approvedModels[GI]
        bool finalized; // True after majority
        bytes32 finalCID; // Majority‐agreed CID
    }

    mapping(uint => Tier1Batch[]) public tier1Batches;
    mapping(uint => mapping(uint => mapping(address => bool))) isTier1Aggregator;

    // Audit & voting maps            GI  ➜  batchId ➜ validator  ➜  …
    mapping(uint => mapping(uint => mapping(address => bytes32)))
        public t1SubmissionCID;
    mapping(uint => mapping(uint => mapping(address => bool)))
        public t1Submitted;
    mapping(uint => mapping(uint => mapping(bytes32 => uint))) public t1Votes; // CID ➜ votes

    struct Tier2Batch {
        uint batchId;
        address[] aggregators; // Tier‑2 aggregators
        bool finalized;
        bytes32 finalCID;
    }

    mapping(uint => Tier2Batch[]) public tier2Batches;
    mapping(uint => mapping(uint => mapping(address => bool))) isTier2Aggregator;
    mapping(uint => uint) public tier2Score;

    mapping(uint => mapping(uint => mapping(address => bytes32)))
        public t2SubmissionCID;
    mapping(uint => mapping(uint => mapping(address => bool)))
        public t2Submitted;
    mapping(uint => mapping(uint => mapping(bytes32 => uint))) public t2Votes;

    // ─────────────────────────────────────────────────────────────────────
    // Dispute resolution scaffold (task_210726_6 §4c, issue #38, S4)
    //
    // Bond custody, window enforcement, and fresh-subgroup reassignment are
    // real on-chain mechanics. Adjudication (was the disputed CID actually
    // wrong?) is NOT on-chain here -- verifying a T1/T2 aggregation CID
    // requires re-running aggregation over model weights, which isn't
    // something a contract can or should do. resolveDispute is onlyOwner
    // for now; see Developer/design/slashing-taxonomy.md's S4 section for
    // why, and what a future on-chain adjudication mechanism would need.
    //
    // Bounty/bond-forfeiture payouts are stubbed the same way Part 3's
    // reward engine stubs its treasury share: accrued locally, not
    // forwarded anywhere, because DinTreasury doesn't exist on develop yet.
    // ─────────────────────────────────────────────────────────────────────

    enum TierKind {
        Tier1,
        Tier2
    }

    struct Dispute {
        address challenger;
        uint256 bond;
        uint64 openedAt;
        bool resolved;
        bool upheld;
    }

    IERC20 public dinToken;
    uint256 public disputeBond = 100 * 1e18; // placeholder default, DAO-settable
    uint64 public disputeWindow = 1 days; // placeholder default, DAO-settable
    address public treasuryAddress;
    uint256 public treasuryAccrued; // TODO(task_210726_5): forward to DinTreasury once merged

    mapping(uint => mapping(uint => uint64)) public tier1FinalizedAt;
    mapping(uint => mapping(uint => uint64)) public tier2FinalizedAt;
    mapping(uint => mapping(TierKind => mapping(uint => Dispute)))
        public disputes;
    mapping(uint => mapping(TierKind => mapping(uint => address[])))
        public reEvaluationAssignees;
    mapping(address => uint256) public disputeBondClaimable;

    event DisputeOpened(
        uint indexed GI,
        TierKind tierKind,
        uint indexed batchId,
        address indexed challenger,
        uint256 bond
    );
    event DisputeResolved(
        uint indexed GI,
        TierKind tierKind,
        uint indexed batchId,
        bool upheld
    );
    event ReEvaluationAssigned(
        uint indexed GI,
        TierKind tierKind,
        uint indexed batchId,
        address[] freshAggregators
    );
    event DisputeBondClaimed(address indexed challenger, uint256 amount);

    modifier onlyCurrentGI(uint _GI) {
        if (_GI != GI) revert TC_WrongGI();
        _;
    }

    event DINValidatorRegistered(uint indexed GI, address indexed validator);
    event Tier1BatchAuto(uint indexed GI, uint indexed batchId);
    event Tier2BatchAuto(uint indexed GI, uint indexed batchId);
    event AggregatorSlashed(
        uint indexed GI,
        uint indexed batchId,
        address indexed aggregator,
        bytes32 reason,
        uint256 requested,
        uint256 actual
    );

    /// @notice Deploys the coordinator and sets the validator stake contract.
    /// @dev GI state is initialised to AwaitingDINTaskAuditorToBeSet; the model
    ///      owner must call setDINTaskAuditorContract before any other setup step.
    /// @param dinvalidatorStakeContract_address Address of the DinValidatorStake proxy.
    constructor(address dinvalidatorStakeContract_address) Ownable(msg.sender) {
        dinvalidatorStakeContract = IDinValidatorStake(
            dinvalidatorStakeContract_address
        );
        GIstate = GIstates.AwaitingDINTaskAuditorToBeSet;
    }

    /// @notice Sets the paired DINTaskAuditor contract for this model.
    /// @dev One-shot: reverts if called after the initial setup step.
    /// @param _dintaskauditor_contract_address Address of the DINTaskAuditor contract.
    function setDINTaskAuditorContract(
        address _dintaskauditor_contract_address
    ) public onlyOwner {
        if (GIstate != GIstates.AwaitingDINTaskAuditorToBeSet)
            revert TC_TaskAuditorContractCannotBeSet();
        dinTaskAuditorContract = IDINTaskAuditor(
            _dintaskauditor_contract_address
        );
        GIstate = GIstates.AwaitingDINTaskCoordinatorAsSlasher;
    }

    /// @notice Confirms that this coordinator is registered as a slasher on the
    ///         validator stake contract, advancing the GI state.
    /// @dev The DIN-Representative must have called DinCoordinator.addSlasherContract
    ///      for this address before this function is called.
    function setDINTaskCoordinatorAsSlasher() public onlyOwner {
        if (GIstate != GIstates.AwaitingDINTaskCoordinatorAsSlasher)
            revert TC_CoordinatorCannotBeSetAsSlasher();
        if (!dinvalidatorStakeContract.isSlasherContract(address(this)))
            revert TC_CoordinatorIsNotSlasher();
        GIstate = GIstates.AwaitingDINTaskAuditorAsSlasher;
    }

    /// @notice Confirms that the paired DINTaskAuditor is registered as a slasher,
    ///         completing the setup sequence and enabling model registration.
    /// @dev The DIN-Representative must have called DinCoordinator.addSlasherContract
    ///      for the auditor address before this function is called.
    function setDINTaskAuditorAsSlasher() public onlyOwner {
        if (GIstate != GIstates.AwaitingDINTaskAuditorAsSlasher)
            revert TC_AuditorCannotBeSetAsSlasher();
        if (
            !dinvalidatorStakeContract.isSlasherContract(
                address(dinTaskAuditorContract)
            )
        ) revert TC_AuditorIsNotSlasher();
        GIstate = GIstates.AwaitingGenesisModel;
    }

    /// @notice Records the genesis model IPFS hash, enabling GI 1 to be started.
    /// @param _genesisModelIpfsHash CID of the genesis model weights, encoded as bytes32.
    function setGenesisModelIpfsHash(
        bytes32 _genesisModelIpfsHash
    ) public onlyOwner {
        if (GIstate != GIstates.AwaitingGenesisModel)
            revert TC_GenesisModelHashCannotBeSet();
        genesisModelIpfsHash = _genesisModelIpfsHash;
        GIstate = GIstates.GenesisModelCreated;
    }

    /// @notice Starts the next Global Iteration and updates the auditor pass score.
    /// @param _GI Expected next GI index (must equal current GI + 1).
    /// @param score New pass score to set on the paired DINTaskAuditor.
    function startGI(uint _GI, uint score) public onlyOwner {
        _startGI(_GI, score, true);
    }

    /// @notice Starts the next Global Iteration, retaining the existing pass score.
    /// @param _GI Expected next GI index (must equal current GI + 1).
    function startGI(uint _GI) public onlyOwner {
        _startGI(_GI, 0, false);
    }

    function _startGI(uint _GI, uint score, bool updatePassScore) internal {
        if (
            GIstate != GIstates.GenesisModelCreated &&
            GIstate != GIstates.GIended
        ) revert TC_GICannotBeStarted();
        if (_GI != GI + 1) revert TC_WrongGI();
        // task_210726_6 §3: a GI cannot start unless its reward pool has
        // been funded via DINTaskAuditor.depositRewards(_GI, ...) first.
        // Prevents a GI running to completion with nothing to settle/claim.
        if (dinTaskAuditorContract.giRewardPool(_GI) == 0)
            revert TC_GIRewardPoolNotFunded();
        if (updatePassScore) {
            dinTaskAuditorContract.updatePassScore(score);
        }
        GIstate = GIstates.GIstarted;
        GI++;
    }

    /// @notice Opens the aggregator registration window for the current GI.
    /// @param _GI Current GI index, used to guard against stale calls.
    function startDINaggregatorsRegistration(
        uint _GI
    ) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.GIstarted)
            revert TC_AggregatorsRegistrationCannotBeStarted();
        GIstate = GIstates.DINaggregatorsRegistrationStarted;
    }

    /// @notice Registers the caller as an aggregator for the current GI.
    /// @dev Caller must be an active validator; duplicate registrations revert.
    /// @param _GI Current GI index.
    function registerDINaggregator(uint _GI) public {
        if (GIstate != GIstates.DINaggregatorsRegistrationStarted)
            revert TC_AggregatorsRegistrationNotOpen();

        if (!dinvalidatorStakeContract.isValidatorActive(msg.sender)) {
            revert TC_AggregatorNotActive();
        }
        if (isDINAggregator[_GI][msg.sender])
            revert TC_AggregatorAlreadyRegistered();

        // Add to list and mark as registered
        dinAggregators[_GI].push(msg.sender);
        isDINAggregator[_GI][msg.sender] = true;

        emit DINValidatorRegistered(_GI, msg.sender);
    }

    /// @notice Closes the aggregator registration window.
    /// @param _GI Current GI index.
    function closeDINaggregatorsRegistration(
        uint _GI
    ) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.DINaggregatorsRegistrationStarted)
            revert TC_AggregatorsRegistrationCannotBeFinished();
        GIstate = GIstates.DINaggregatorsRegistrationClosed;
    }

    /// @notice Returns the list of aggregators registered for the given GI.
    /// @param _GI GI index to query.
    /// @return Ordered array of aggregator addresses in registration order.
    function getDINtaskAggregators(
        uint _GI
    ) public view returns (address[] memory) {
        return dinAggregators[_GI];
    }

    /// @notice Opens the auditor registration window on the paired DINTaskAuditor.
    /// @param _GI Current GI index.
    function startDINauditorsRegistration(
        uint _GI
    ) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.DINaggregatorsRegistrationClosed)
            revert TC_AuditorsRegistrationCannotBeStarted();
        GIstate = GIstates.DINauditorsRegistrationStarted;
    }

    /// @notice Closes the auditor registration window.
    /// @param _GI Current GI index.
    function closeDINauditorsRegistration(
        uint _GI
    ) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.DINauditorsRegistrationStarted)
            revert TC_AuditorsRegistrationCannotBeFinished();
        GIstate = GIstates.DINauditorsRegistrationClosed;
    }

    /// @notice Opens the local model submission window for the current GI.
    /// @param _GI Current GI index.
    function startLMsubmissions(uint _GI) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.DINauditorsRegistrationClosed)
            revert TC_LMSubmissionsCannotBeStarted();
        GIstate = GIstates.LMSstarted;
    }

    /// @notice Closes the local model submission window.
    /// @param _GI Current GI index.
    function closeLMsubmissions(uint _GI) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.LMSstarted) revert TC_LMSubmissionsNotStarted();
        GIstate = GIstates.LMSclosed;
    }

    /// @notice Delegates auditor batch creation to DINTaskAuditor and advances GI state.
    /// @dev Reverts if the auditor contract returns false (e.g. insufficient auditors).
    /// @param _GI Current GI index.
    function createAuditorsBatches(
        uint _GI
    ) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.LMSclosed) revert TC_LMEvalCannotBeStarted();

        bool success = dinTaskAuditorContract.createAuditorsBatches(_GI);
        if (!success) revert TC_FailedToCreateAuditorsBatches();

        GIstate = GIstates.AuditorsBatchesCreated;
    }

    /// @notice Propagates the test data assignment flag to DINTaskAuditor.
    /// @dev Must be called while GI state is AuditorsBatchesCreated.
    /// @param _GI Current GI index.
    /// @param flag True once test datasets have been distributed to auditors.
    function setTestDataAssignedFlag(
        uint _GI,
        bool flag
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.AuditorsBatchesCreated)
            revert TC_CannotSetTestDataAssignedFlag();

        dinTaskAuditorContract.setTestDataAssignedFlag(_GI, flag);
    }

    /// @notice Opens the LMS evaluation COMMIT phase so auditors can begin
    ///         committing (hidden) scores via DINTaskAuditor.commitAuditScore.
    /// @param _GI Current GI index.
    function startLMsubmissionsEvaluation(
        uint _GI
    ) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.AuditorsBatchesCreated)
            revert TC_LMEvalCannotBeStarted();
        GIstate = GIstates.LMSevaluationStarted;
    }

    /// @notice Closes the commit phase and opens the REVEAL phase (task_210726_6
    ///         §2a) so auditors can call DINTaskAuditor.revealAuditScore.
    /// @dev Must run strictly after commits close and before any reveal is
    ///      accepted -- see DINTaskAuditor.revealAuditScore's GIstate gate.
    /// @param _GI Current GI index.
    function startLMsubmissionsEvaluationReveal(
        uint _GI
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.LMSevaluationStarted)
            revert TC_RevealCannotBeStarted();
        GIstate = GIstates.LMSevaluationRevealStarted;
    }

    /// @notice Closes the LMS evaluation reveal phase and finalises audit
    ///         results on the paired DINTaskAuditor.
    /// @dev Calls DINTaskAuditor.finalizeEvaluation; reverts if it returns false.
    /// @param _GI Current GI index.
    function closeLMsubmissionsEvaluation(
        uint _GI
    ) public onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.LMSevaluationRevealStarted)
            revert TC_LMEvalCannotBeFinished();
        bool success = dinTaskAuditorContract.finalizeEvaluation(_GI);
        if (!success) revert TC_FailedToFinalizeEvaluation();
        GIstate = GIstates.LMSevaluationClosed;
    }

    /// @notice Partitions active aggregators and approved models into Tier-1 batches
    ///         and creates a single Tier-2 batch from the remaining validators.
    /// @dev Aggregators are filtered to those still Active at call time and shuffled
    ///      using blockhash-based entropy. Reverts if fewer than T1_AGGREGATORS_PER_BATCH
    ///      active validators remain, or if fewer than T1_MODELS_PER_BATCH models passed.
    /// @param _GI Current GI index.
    function autoCreateTier1AndTier2(
        uint _GI
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.LMSevaluationClosed)
            revert TC_EvalPhaseNotClosed();

        // Filter the historical registration list down to currently active validators.
        address[] memory valPool = _activeAggregatorPool(_GI);
        uint vLen = valPool.length;
        if (vLen < T1_AGGREGATORS_PER_BATCH) revert TC_NotEnoughValidators();
        _shuffleAddressArray(valPool);

        // ▸ 2. Build list of approved model indexes
        uint[] memory modelIdx = _collectApprovedModelIndexes(_GI);
        _shuffleUintArray(modelIdx);

        // ▸ 3. Greedily fill Tier-1 batches
        uint vPtr;
        uint mPtr;
        uint t1cnt;
        while (
            vPtr + T1_AGGREGATORS_PER_BATCH <= valPool.length &&
            (mPtr + T1_MODELS_PER_BATCH <= modelIdx.length ||
                (mPtr + MIN_T1_MODELS_PER_BATCH <= modelIdx.length &&
                    mPtr + T1_MODELS_PER_BATCH > modelIdx.length))
        ) {
            Tier1Batch storage b = tier1Batches[_GI].push();
            b.batchId = t1cnt++;

            for (uint256 k = 0; k < T1_AGGREGATORS_PER_BATCH; k++) {
                b.aggregators.push(valPool[vPtr + k]);
                isTier1Aggregator[_GI][b.batchId][valPool[vPtr + k]] = true;
            }

            uint modelsToAssign = T1_MODELS_PER_BATCH;
            if (modelIdx.length - mPtr < T1_MODELS_PER_BATCH) {
                modelsToAssign = modelIdx.length - mPtr;
            }

            for (uint256 k = 0; k < modelsToAssign; k++) {
                b.modelIndexes.push(modelIdx[mPtr + k]);
            }

            emit Tier1BatchAuto(_GI, b.batchId);

            vPtr += T1_AGGREGATORS_PER_BATCH;
            mPtr += modelsToAssign;
        }

        // ▸ 4. Create Tier-2 batch with EXACTLY T1_AGGREGATORS_PER_BATCH validators if enough remain
        if (valPool.length - vPtr >= T1_AGGREGATORS_PER_BATCH) {
            Tier2Batch storage t2 = tier2Batches[_GI].push();
            t2.batchId = 0;
            for (uint256 k = 0; k < T1_AGGREGATORS_PER_BATCH; k++) {
                t2.aggregators.push(valPool[vPtr + k]);
                isTier2Aggregator[_GI][t2.batchId][valPool[vPtr + k]] = true;
            }

            emit Tier2BatchAuto(_GI, t2.batchId);
        }

        GIstate = GIstates.T1nT2Bcreated;
    }

    // ──────────── internal shuffle helpers ────────────
    function _shuffleAddressArray(address[] memory arr) internal view {
        if (arr.length < 2) return;
        for (uint i = arr.length - 1; i > 0; i--) {
            uint j = uint(
                keccak256(
                    abi.encodePacked(blockhash(block.number - 1), i, arr.length)
                )
            ) % (i + 1);
            (arr[i], arr[j]) = (arr[j], arr[i]);
        }
    }

    function _shuffleUintArray(uint[] memory arr) internal view {
        for (uint i = arr.length - 1; i > 0; i--) {
            uint j = uint(
                keccak256(
                    abi.encodePacked(block.timestamp, i, arr.length, msg.sender)
                )
            ) % (i + 1);
            (arr[i], arr[j]) = (arr[j], arr[i]);
        }
    }

    function _collectApprovedModelIndexes(
        uint _GI
    ) internal view returns (uint[] memory out) {
        out = dinTaskAuditorContract.approvedModelIndexes(_GI);
        if (out.length < T1_MODELS_PER_BATCH)
            revert TC_NotEnoughApprovedModels();
    }

    function _activeAggregatorPool(
        uint _GI
    ) internal view returns (address[] memory activePool) {
        address[] storage registeredPool = dinAggregators[_GI];
        uint activeCount;

        for (uint i = 0; i < registeredPool.length; i++) {
            if (
                dinvalidatorStakeContract.isValidatorActive(registeredPool[i])
            ) {
                activeCount++;
            }
        }

        activePool = new address[](activeCount);
        uint ptr;
        for (uint i = 0; i < registeredPool.length; i++) {
            address validator = registeredPool[i];
            if (dinvalidatorStakeContract.isValidatorActive(validator)) {
                activePool[ptr++] = validator;
            }
        }
    }

    // ──────────── read helpers ────────────
    /// @notice Returns the number of Tier-1 batches created for the given GI.
    /// @param _GI GI index to query.
    /// @return Number of Tier-1 batches.
    function tier1BatchCount(uint _GI) external view returns (uint) {
        return tier1Batches[_GI].length;
    }

    /// @notice Returns the full details of a Tier-1 batch.
    /// @param _GI GI index.
    /// @param _id Batch index within that GI.
    /// @return batchId Canonical batch identifier.
    /// @return validators Aggregators assigned to this batch.
    /// @return modelIndexes Indexes into the approved model list assigned to this batch.
    /// @return finalized True once a majority CID has been determined.
    /// @return finalCID The consensus aggregation CID.
    function getTier1Batch(
        uint _GI,
        uint _id
    )
        external
        view
        returns (
            uint batchId,
            address[] memory validators,
            uint[] memory modelIndexes,
            bool finalized,
            bytes32 finalCID
        )
    {
        if (_GI > GI) revert TC_WrongGI();
        if (_id >= tier1Batches[_GI].length) revert TC_BatchNotFound();
        Tier1Batch storage b = tier1Batches[_GI][_id];
        return (
            b.batchId,
            b.aggregators,
            b.modelIndexes,
            b.finalized,
            b.finalCID
        );
    }

    /// @notice Returns the details of the single Tier-2 batch for the given GI.
    /// @dev _id must be 0; there is always exactly one Tier-2 batch per GI.
    /// @param _GI GI index.
    /// @param _id Must be 0.
    /// @return batchId Canonical batch identifier (always 0).
    /// @return validators Aggregators assigned to the Tier-2 batch.
    /// @return finalized True once a majority CID has been determined.
    /// @return finalCID The consensus aggregation CID.
    function getTier2Batch(
        uint _GI,
        uint _id
    )
        external
        view
        returns (
            uint batchId,
            address[] memory validators,
            bool finalized,
            bytes32 finalCID
        )
    {
        if (_id != 0) revert TC_OnlyOneTier2Batch();
        if (_GI > GI) revert TC_WrongGI();
        Tier2Batch storage b = tier2Batches[_GI][_id];
        return (b.batchId, b.aggregators, b.finalized, b.finalCID);
    }

    /// @notice Transitions GI state to T1AggregationStarted, opening the
    ///         Tier-1 submission window for assigned aggregators.
    /// @param _GI Current GI index.
    function startT1Aggregation(
        uint _GI
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T1nT2Bcreated)
            revert TC_NotReadyForT1Aggregation();
        GIstate = GIstates.T1AggregationStarted;
    }

    /// @notice Submits an aggregation result CID for a Tier-1 batch.
    /// @dev Caller must be an assigned, active aggregator who has not already submitted.
    ///      Votes are tallied per CID; the majority CID is selected at finalization.
    /// @param _GI Current GI index.
    /// @param _batchId Tier-1 batch index.
    /// @param _aggregationCID IPFS CID of the aggregated model weights, encoded as bytes32.
    function submitT1Aggregation(
        uint _GI,
        uint _batchId,
        bytes32 _aggregationCID
    ) external onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T1AggregationStarted)
            revert TC_T1AggregationNotStarted();
        if (_batchId >= tier1Batches[_GI].length) revert TC_InvalidBatch();

        // Verify sender is an assigned aggregator
        if (!isTier1Aggregator[_GI][_batchId][msg.sender])
            revert TC_NotBatchAggregator();
        if (!dinvalidatorStakeContract.isValidatorActive(msg.sender)) {
            revert TC_AggregatorNotActive();
        }
        if (t1Submitted[_GI][_batchId][msg.sender])
            revert TC_AlreadySubmitted();

        t1Submitted[_GI][_batchId][msg.sender] = true;
        t1SubmissionCID[_GI][_batchId][msg.sender] = _aggregationCID;

        // Increment vote count
        t1Votes[_GI][_batchId][_aggregationCID]++;
    }

    /// @notice Closes the Tier-1 submission window and selects the majority CID
    ///         for every batch.
    /// @dev Iterates all T1 batches; reverts on the first batch that has no submissions.
    /// @param _GI Current GI index.
    function finalizeT1Aggregation(
        uint _GI
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T1AggregationStarted)
            revert TC_NotReadyToFinalizeT1();

        Tier1Batch[] storage batches = tier1Batches[_GI];

        for (uint i = 0; i < batches.length; i++) {
            Tier1Batch storage b = batches[i];

            // Determine the CID with the most votes
            bytes32 winningCID = "";
            uint maxVotes = 0;

            for (uint j = 0; j < b.aggregators.length; j++) {
                address aggregator = b.aggregators[j];
                if (t1Submitted[_GI][b.batchId][aggregator]) {
                    bytes32 cid = t1SubmissionCID[_GI][b.batchId][aggregator];
                    uint votes = t1Votes[_GI][b.batchId][cid];
                    if (votes > maxVotes) {
                        maxVotes = votes;
                        winningCID = cid;
                    }
                }
            }

            if (winningCID == bytes32(0)) revert TC_NoSubmissions();
            b.finalized = true;
            b.finalCID = winningCID;
            tier1FinalizedAt[_GI][b.batchId] = uint64(block.timestamp);
        }

        GIstate = GIstates.T1AggregationDone;
    }

    /// @notice Opens the Tier-2 aggregation submission window.
    /// @param _GI Current GI index.
    function startT2Aggregation(
        uint _GI
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T1AggregationDone)
            revert TC_NotReadyForT2Aggregation();
        GIstate = GIstates.T2AggregationStarted;
    }

    /// @notice Submits an aggregation result CID for the Tier-2 batch.
    /// @dev _batchId must be 0. Caller must be an assigned, active aggregator who
    ///      has not already submitted.
    /// @param _GI Current GI index.
    /// @param _batchId Must be 0.
    /// @param _aggregationCID IPFS CID of the final aggregated model, encoded as bytes32.
    function submitT2Aggregation(
        uint _GI,
        uint _batchId,
        bytes32 _aggregationCID
    ) external onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T2AggregationStarted)
            revert TC_T2AggregationNotStarted();
        if (_batchId != 0) revert TC_OnlyOneTier2Batch();

        if (!isTier2Aggregator[_GI][_batchId][msg.sender])
            revert TC_NotBatchAggregator();
        if (!dinvalidatorStakeContract.isValidatorActive(msg.sender)) {
            revert TC_AggregatorNotActive();
        }
        if (t2Submitted[_GI][_batchId][msg.sender])
            revert TC_AlreadySubmitted();

        t2Submitted[_GI][_batchId][msg.sender] = true;
        t2SubmissionCID[_GI][_batchId][msg.sender] = _aggregationCID;

        // Increment vote count
        t2Votes[_GI][_batchId][_aggregationCID]++;
    }

    /// @notice Closes the Tier-2 submission window and selects the majority CID.
    /// @dev Reverts if the Tier-2 batch has received no submissions.
    /// @param _GI Current GI index.
    function finalizeT2Aggregation(
        uint _GI
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T2AggregationStarted)
            revert TC_NotReadyToFinalizeT2();

        Tier2Batch[] storage batches = tier2Batches[_GI];

        for (uint i = 0; i < batches.length; i++) {
            Tier2Batch storage b = batches[i];

            // Determine the CID with the most votes
            bytes32 winningCID = "";
            uint maxVotes = 0;

            for (uint j = 0; j < b.aggregators.length; j++) {
                address aggregator = b.aggregators[j];
                if (t2Submitted[_GI][b.batchId][aggregator]) {
                    bytes32 cid = t2SubmissionCID[_GI][b.batchId][aggregator];
                    uint votes = t2Votes[_GI][b.batchId][cid];
                    if (votes > maxVotes) {
                        maxVotes = votes;
                        winningCID = cid;
                    }
                }
            }

            if (winningCID == bytes32(0)) revert TC_NoSubmissions();
            b.finalized = true;
            b.finalCID = winningCID;
            tier2FinalizedAt[_GI][b.batchId] = uint64(block.timestamp);
        }

        GIstate = GIstates.T2AggregationDone;
    }

    /// @notice Triggers auditor slashing on the paired DINTaskAuditor contract.
    /// @dev Reverts if DINTaskAuditor.slashAuditors returns false.
    /// @param _GI Current GI index.
    function slashAuditors(uint _GI) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.T2AggregationDone)
            revert TC_NotReadyToSlashAuditors();
        bool success = dinTaskAuditorContract.slashAuditors(_GI);
        if (!success) revert TC_FailedToSlashAuditors();
        GIstate = GIstates.AuditorsSlashed;
    }

    /// @notice Slashes aggregators in both Tier-1 and Tier-2 batches that failed
    ///         to submit or submitted a CID that did not match the consensus.
    /// @dev Slash amount equals minStake() at call time. Each affected aggregator
    ///      emits an AggregatorSlashed event with the actual amount deducted.
    /// @param _GI Current GI index.
    function slashAggregators(uint _GI) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.AuditorsSlashed)
            revert TC_NotReadyToSlashAggregators();

        uint256 slashAmount = dinvalidatorStakeContract.minStake();

        // 1. Tier 1 batches
        Tier1Batch[] storage t1batches = tier1Batches[_GI];
        for (uint i = 0; i < t1batches.length; i++) {
            Tier1Batch storage b = t1batches[i];
            for (uint j = 0; j < b.aggregators.length; j++) {
                address aggregator = b.aggregators[j];

                bool submitted = t1Submitted[_GI][b.batchId][aggregator];
                bool submittedMatching = false;
                bytes32 reason = "AGG_T1_NO_SUBMISSION";
                if (submitted) {
                    bytes32 cid = t1SubmissionCID[_GI][b.batchId][aggregator];
                    submittedMatching = (cid == b.finalCID);
                    if (!submittedMatching) {
                        reason = "AGG_T1_BAD_CONSENSUS";
                    }
                }
                if (!submitted || !submittedMatching) {
                    uint256 actualSlashed = dinvalidatorStakeContract.slash(
                        aggregator,
                        slashAmount,
                        reason
                    );
                    emit AggregatorSlashed(
                        _GI,
                        b.batchId,
                        aggregator,
                        reason,
                        slashAmount,
                        actualSlashed
                    );
                }
            }
        }

        // 2. Tier 2 batches
        Tier2Batch[] storage t2batches = tier2Batches[_GI];
        for (uint i = 0; i < t2batches.length; i++) {
            Tier2Batch storage b = t2batches[i];
            for (uint j = 0; j < b.aggregators.length; j++) {
                address aggregator = b.aggregators[j];

                bool submitted = t2Submitted[_GI][b.batchId][aggregator];
                bool submittedMatching = false;
                bytes32 reason = "AGG_T2_NO_SUBMISSION";
                if (submitted) {
                    bytes32 cid = t2SubmissionCID[_GI][b.batchId][aggregator];
                    submittedMatching = (cid == b.finalCID);
                    if (!submittedMatching) {
                        reason = "AGG_T2_BAD_CONSENSUS";
                    }
                }
                if (!submitted || !submittedMatching) {
                    uint256 actualSlashed = dinvalidatorStakeContract.slash(
                        aggregator,
                        slashAmount,
                        reason
                    );
                    emit AggregatorSlashed(
                        _GI,
                        b.batchId,
                        aggregator,
                        reason,
                        slashAmount,
                        actualSlashed
                    );
                }
            }
        }

        GIstate = GIstates.AggregatorsSlashed;
    }

    /// @notice Records the Tier-2 aggregation quality score for the current GI.
    /// @dev Permitted during T2AggregationDone or GenesisModelCreated states.
    /// @param _GI Current GI index.
    /// @param _score Quality score for the Tier-2 aggregated model.
    function setTier2Score(
        uint _GI,
        uint _score
    ) external onlyOwner onlyCurrentGI(_GI) {
        if (
            GIstate != GIstates.T2AggregationDone &&
            GIstate != GIstates.GenesisModelCreated
        ) revert TC_NotReadyToSetTier2Score();
        tier2Score[_GI] = _score;
    }

    /// @notice Returns the Tier-2 quality score recorded for the given GI.
    /// @param _GI GI index to query.
    /// @return The score set via setTier2Score for that GI.
    function getTier2Score(uint _GI) external view returns (uint) {
        return tier2Score[_GI];
    }

    /// @notice Marks the current Global Iteration as complete and settles
    ///         its reward pool.
    /// @dev Must be called after slashAggregators. Delegates the actual
    ///      client/auditor/aggregator/treasury split computation to
    ///      DINTaskAuditor.settleRewards (task_210726_6 §3) -- that contract
    ///      owns the client/auditor data (lmSubmissions, audit batches) this
    ///      contract doesn't have, and owns the giRewardPool/claimable
    ///      accounting so all three roles claim from one place. This
    ///      contract owns the T1/T2 aggregator batch data settleRewards
    ///      needs but doesn't have, hence _collectFinalizedBatchAggregators
    ///      building that list here rather than extending the cross-contract
    ///      interface to expose T1/T2 batch internals for a read only used
    ///      once, at end-of-GI.
    ///      settleRewards only credits a `claimable` mapping -- no transfers
    ///      happen in this call, so this stays a bounded-cost state
    ///      transition regardless of pool size (the iteration cost of
    ///      collecting/crediting scales with participant count, same
    ///      already-known-and-documented class of cost as
    ///      slashAggregators/finalizeEvaluation elsewhere in these
    ///      contracts, not a new unbounded-loop risk this task introduces).
    ///      The next startGI call will increment GI and transition state to
    ///      GIstarted.
    /// @param _GI Current GI index.
    function endGI(uint _GI) external onlyOwner onlyCurrentGI(_GI) {
        if (GIstate != GIstates.AggregatorsSlashed) revert TC_NotReadyToEndGI();

        address[]
            memory rewardableAggregators = _collectFinalizedBatchAggregators(
                _GI
            );
        dinTaskAuditorContract.settleRewards(_GI, rewardableAggregators);

        GIstate = GIstates.GIended;
    }

    /// @notice Builds the list of aggregators credited for a finalized T1/T2
    ///         batch this GI, one entry per (aggregator, finalized batch) pair.
    /// @dev "Per finalized T1/T2 batch" (task_210726_6 §3): an aggregator who
    ///      completed both a T1 batch and the T2 batch appears twice, earning
    ///      proportionally more weight in DINTaskAuditor.settleRewards.
    ///      Correctness (did they submit the matching CID) is enforced by
    ///      slashAggregators having already run this GI, not re-checked here
    ///      -- mirrors the "correctness enforced by slashing, not reward
    ///      weighting" principle task_210726_6 §3 states explicitly for
    ///      auditors; an aggregator assigned to a finalized batch is
    ///      rewardable for it regardless of whether they personally matched
    ///      consensus, since a mismatch already cost them stake.
    /// @param _GI GI index to collect for.
    /// @return Flat address list, ordered T1 batches then the T2 batch.
    function _collectFinalizedBatchAggregators(
        uint _GI
    ) internal view returns (address[] memory) {
        Tier1Batch[] storage t1batches = tier1Batches[_GI];
        Tier2Batch[] storage t2batches = tier2Batches[_GI];

        uint256 count;
        for (uint i = 0; i < t1batches.length; i++) {
            if (t1batches[i].finalized)
                count += t1batches[i].aggregators.length;
        }
        for (uint i = 0; i < t2batches.length; i++) {
            if (t2batches[i].finalized)
                count += t2batches[i].aggregators.length;
        }

        address[] memory result = new address[](count);
        uint256 ptr;
        for (uint i = 0; i < t1batches.length; i++) {
            if (t1batches[i].finalized) {
                address[] storage aggs = t1batches[i].aggregators;
                for (uint j = 0; j < aggs.length; j++) {
                    result[ptr++] = aggs[j];
                }
            }
        }
        for (uint i = 0; i < t2batches.length; i++) {
            if (t2batches[i].finalized) {
                address[] storage aggs = t2batches[i].aggregators;
                for (uint j = 0; j < aggs.length; j++) {
                    result[ptr++] = aggs[j];
                }
            }
        }
        return result;
    }

    // ─────────────────────────────────────────────────────────────────────
    // Dispute resolution scaffold (task_210726_6 §4c, issue #38, S4)
    // ─────────────────────────────────────────────────────────────────────

    /// @notice Sets the ERC20 token used for dispute bonds.
    /// @param _dinToken Address of the DinToken proxy.
    function setDinToken(address _dinToken) external onlyOwner {
        if (_dinToken == address(0)) revert TC_InvalidAddress();
        dinToken = IERC20(_dinToken);
    }

    /// @notice Sets the dispute bond amount and dispute window duration.
    /// @dev Both values are DAO-settable placeholders; the numbers shipped
    ///      here are not final, per this task's brief.
    /// @param _disputeBond Token amount a challenger must post to open a dispute.
    /// @param _disputeWindow Seconds after batch finalization during which a dispute can be opened.
    function setDisputeParams(
        uint256 _disputeBond,
        uint64 _disputeWindow
    ) external onlyOwner {
        if (_disputeBond == 0 || _disputeWindow == 0)
            revert TC_InvalidDisputeParams();
        disputeBond = _disputeBond;
        disputeWindow = _disputeWindow;
    }

    /// @notice Sets the address forfeited dispute bonds will eventually be forwarded to.
    /// @dev Storage only -- no forwarding happens yet since DinTreasury doesn't
    ///      exist on develop. See treasuryAccrued.
    /// @param _treasuryAddress Address of the future DinTreasury deployment.
    function setTreasuryAddress(address _treasuryAddress) external onlyOwner {
        if (_treasuryAddress == address(0)) revert TC_InvalidAddress();
        treasuryAddress = _treasuryAddress;
    }

    /// @notice Opens a dispute against a finalized Tier-1 or Tier-2 batch.
    /// @dev Caller must be an active validator and post `disputeBond` DIN,
    ///      within `disputeWindow` seconds of the batch's finalization.
    ///      Adjudication happens off-chain today (resolveDispute is
    ///      onlyOwner) -- see the scaffold-wide comment above the state
    ///      declarations for why.
    /// @param _GI GI index the batch belongs to.
    /// @param tierKind Whether the batch is a Tier-1 or Tier-2 batch.
    /// @param batchId Index of the batch within its tier for that GI.
    function openDispute(
        uint _GI,
        TierKind tierKind,
        uint batchId
    ) external nonReentrant {
        if (_GI == 0 || _GI > GI) revert TC_WrongGI();
        if (!dinvalidatorStakeContract.isValidatorActive(msg.sender)) {
            revert TC_AggregatorNotActive();
        }

        bool finalized;
        uint64 finalizedAt;
        if (tierKind == TierKind.Tier1) {
            if (batchId >= tier1Batches[_GI].length) revert TC_InvalidBatch();
            finalized = tier1Batches[_GI][batchId].finalized;
            finalizedAt = tier1FinalizedAt[_GI][batchId];
        } else {
            if (batchId >= tier2Batches[_GI].length) revert TC_InvalidBatch();
            finalized = tier2Batches[_GI][batchId].finalized;
            finalizedAt = tier2FinalizedAt[_GI][batchId];
        }
        if (!finalized) revert TC_BatchNotFinalized();
        if (block.timestamp > finalizedAt + disputeWindow) {
            revert TC_DisputeWindowClosed();
        }
        if (disputes[_GI][tierKind][batchId].challenger != address(0)) {
            revert TC_DisputeAlreadyOpen();
        }

        disputes[_GI][tierKind][batchId] = Dispute({
            challenger: msg.sender,
            bond: disputeBond,
            openedAt: uint64(block.timestamp),
            resolved: false,
            upheld: false
        });

        dinToken.safeTransferFrom(msg.sender, address(this), disputeBond);

        emit DisputeOpened(_GI, tierKind, batchId, msg.sender, disputeBond);
    }

    /// @notice Resolves a dispute, either upholding or rejecting it.
    /// @dev Upheld: bond becomes claimable by the challenger (pull payment)
    ///      and a fresh aggregator subgroup is assigned, excluding the
    ///      accused batch's original aggregators. The bounty top-up from
    ///      treasury is stubbed (TODO below) since DinTreasury doesn't exist
    ///      yet. Rejected (frivolous): bond is forfeited to treasuryAccrued,
    ///      same stub pattern as Part 3's reward engine.
    /// @param _GI GI index the disputed batch belongs to.
    /// @param tierKind Whether the batch is a Tier-1 or Tier-2 batch.
    /// @param batchId Index of the disputed batch within its tier.
    /// @param upheld True if the dispute is found valid.
    function resolveDispute(
        uint _GI,
        TierKind tierKind,
        uint batchId,
        bool upheld
    ) external onlyOwner {
        Dispute storage d = disputes[_GI][tierKind][batchId];
        if (d.challenger == address(0)) revert TC_DisputeNotOpen();
        if (d.resolved) revert TC_DisputeAlreadyResolved();

        d.resolved = true;
        d.upheld = upheld;

        if (upheld) {
            // TODO(task_210726_5): top up with a bounty from DinTreasury
            // once it exists; for now the challenger only reclaims their bond.
            disputeBondClaimable[d.challenger] += d.bond;

            address[] memory freshSubgroup = _assignFreshSubgroup(
                _GI,
                tierKind,
                batchId
            );
            reEvaluationAssignees[_GI][tierKind][batchId] = freshSubgroup;
            emit ReEvaluationAssigned(_GI, tierKind, batchId, freshSubgroup);
        } else {
            // TODO(task_210726_5): forward to DinTreasury (50% burn / 50%
            // treasury per MECHANISM_DESIGN.md §4) once it exists.
            treasuryAccrued += d.bond;
        }

        emit DisputeResolved(_GI, tierKind, batchId, upheld);
    }

    /// @notice Claims a reclaimed dispute bond after an upheld dispute.
    /// @dev Pull payment: zeroes the balance before transferring (CEI).
    function claimDisputeBond() external nonReentrant {
        uint256 amount = disputeBondClaimable[msg.sender];
        if (amount == 0) revert TC_NoBondClaimable();

        disputeBondClaimable[msg.sender] = 0;
        dinToken.safeTransfer(msg.sender, amount);

        emit DisputeBondClaimed(msg.sender, amount);
    }

    /// @notice Selects a fresh aggregator subgroup for re-evaluation, excluding
    ///         the accused batch's original aggregators.
    /// @dev Draws from the same active-aggregator pool autoCreateTier1AndTier2
    ///      uses, shuffled with the same blockhash-based entropy. Bookkeeping
    ///      only -- does not re-open the GI state machine to actually re-run
    ///      aggregation against this subgroup; see the scaffold-wide comment
    ///      above the state declarations.
    function _assignFreshSubgroup(
        uint _GI,
        TierKind tierKind,
        uint batchId
    ) internal view returns (address[] memory subgroup) {
        address[] memory excluded = tierKind == TierKind.Tier1
            ? tier1Batches[_GI][batchId].aggregators
            : tier2Batches[_GI][batchId].aggregators;
        address[] memory pool = _activeAggregatorPool(_GI);

        uint eligibleCount;
        for (uint i = 0; i < pool.length; i++) {
            if (!_isInArray(pool[i], excluded)) eligibleCount++;
        }

        address[] memory eligible = new address[](eligibleCount);
        uint ptr;
        for (uint i = 0; i < pool.length; i++) {
            if (!_isInArray(pool[i], excluded)) {
                eligible[ptr++] = pool[i];
            }
        }
        if (eligible.length < T1_AGGREGATORS_PER_BATCH) {
            revert TC_NotEnoughValidators();
        }

        _shuffleAddressArray(eligible);

        subgroup = new address[](T1_AGGREGATORS_PER_BATCH);
        for (uint i = 0; i < T1_AGGREGATORS_PER_BATCH; i++) {
            subgroup[i] = eligible[i];
        }
    }

    function _isInArray(
        address needle,
        address[] memory haystack
    ) internal pure returns (bool) {
        for (uint i = 0; i < haystack.length; i++) {
            if (haystack[i] == needle) return true;
        }
        return false;
    }
}
