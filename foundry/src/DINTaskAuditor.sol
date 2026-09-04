// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuardTransient} from "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";
import "./DINShared.sol";

/// @title DIN Task Auditor
/// @notice Handles auditor registration, local model submission, scoring, eligibility
///         determination, and auditor slashing for a single federated-learning model.
///         Deployed once per model alongside its paired DINTaskCoordinator.
contract DINTaskAuditor is Ownable, ReentrancyGuardTransient {
    using SafeERC20 for IERC20;

    IDinValidatorStake public dinvalidatorStakeContract;

    IDINTaskCoordinator public dintaskcoordinatorContract;

    // Per-GI reward pool (task_210726_6 §3) -- replaces the old
    // totalDepositedRewards running total, which couldn't support the
    // "funded per-GI, settled per-GI" model MECHANISM_DESIGN §5 describes.
    mapping(uint256 => uint256) public giRewardPool;

    /// @notice DIN token used for reward deposits and payouts.
    /// @dev Deploy-time wiring, mirrors DINModelRegistry.setDinToken (task_210726_5).
    IERC20 public dinToken;

    /// @notice DAO-settable role split for reward distribution, basis points.
    /// @dev Default is the 60/20/15/5 proposal from MECHANISM_DESIGN §5 --
    ///      explicitly not final, pending Umer's P3-5.2 simulation.
    struct RewardSplit {
        uint16 clientBps;
        uint16 auditorBps;
        uint16 aggregatorBps;
        uint16 treasuryBps;
    }

    uint256 private constant BPS_DENOMINATOR = 10000;

    RewardSplit public rewardSplit =
        RewardSplit({
            clientBps: 6000,
            auditorBps: 2000,
            aggregatorBps: 1500,
            treasuryBps: 500
        });

    /// @notice Treasury's accrued share of settled reward pools.
    /// @dev No live consumer yet -- DinTreasury doesn't exist on develop.
    // TODO(task_210726_5): forward to DinTreasury once merged, instead of
    // just accruing here.
    uint256 public treasuryAccrued;

    /// @notice Destination for treasuryAccrued once DinTreasury exists.
    /// @dev Settable now so the wiring is a one-line change later, not a
    ///      redeploy -- see treasuryAccrued's TODO.
    address public treasuryAddress;

    /// @notice Per-address claimable reward balance across all GIs.
    /// @dev Pull-payment only -- settleRewards credits this, claimRewards
    ///      is the only function that ever transfers out of it. No push
    ///      transfers in settlement, matching the gas-DoS class flagged in
    ///      the foundry/src security review (PR #22/#30) for unbounded
    ///      loops elsewhere in these contracts.
    mapping(address => uint256) public claimable;

    uint MAX_LM_SUBMISSIONS = 10000;
    uint256 public constant MAX_REGISTERED_AUDITORS = 300;

    mapping(uint => address[]) public dinAuditors;

    // Track if an address is registered for a given _GI
    mapping(uint => mapping(address => bool)) public isRegisteredAuditor;

    struct LMSubmission {
        address client;
        bytes32 modelCID;
        uint40 submittedAt;
        bool eligible; // majority vote result (basic conformance)
        bool evaluated; // scoring quorum reached & finalMedianScore computed
        bool approved; // approvedForAggregation (finalMedianScore >= passScore)
        uint256 finalMedianScore; // 0..100, Canonical per-model score for both S3 slashing and the reward basis.
    }

    // Per-round params (tune for demo vs spec)
    struct Params {
        uint256 auditorsPerBatch; // demo: 3, spec: 10
        uint256 modelsPerBatch; // demo: 3, spec: 100
        uint256 minEligibilityQuorum; // e.g., 2 for demo, 7 for spec(≈2/3)
        uint256 minScoreQuorum; // e.g., 2 for demo, 7 for spec
        uint256 passScore; // 0..100
        uint256 MIN_MODELS_PER_BATCH;
    }

    Params public params;

    /// @notice S3 auditor-deviation threshold (task_210726_6 §1d), on the
    ///         same 0-100 scale as scores. `|auditorScore - median| >
    ///         s3DeviationThreshold` is computed and emitted via
    ///         AuditorScoreDeviation in finalizeEvaluation. Whether it also
    ///         gates slashing in slashAuditors is controlled separately by
    ///         s3SlashingEnabled -- MECHANISM_DESIGN.md §6: "start with a
    ///         wide threshold + warning-only shadow mode for the first weeks
    ///         of DevNet 2.0, then tighten" once empirically validated. This
    ///         placeholder default (40, i.e. a 40-point swing on a 0-100
    ///         scale) is deliberately wide and is NOT a validated production
    ///         value -- don't treat it as tuned.
    uint256 public s3DeviationThreshold = 40;

    /// @notice Whether S3 (auditor score deviation) actually triggers
    ///         slashing in slashAuditors, as opposed to only being observable
    ///         via AuditorScoreDeviation events. Defaults to false (shadow
    ///         mode): the threshold must be empirically validated before it
    ///         is allowed to cost auditors stake, per MECHANISM_DESIGN.md §6.
    bool public s3SlashingEnabled = false;

    event S3DeviationThresholdUpdated(
        uint256 oldThreshold,
        uint256 newThreshold
    );
    event S3SlashingEnabledUpdated(bool oldValue, bool newValue);
    event AuditorScoreDeviation(
        uint256 indexed gi,
        uint indexed batchId,
        uint modelIndex,
        address indexed auditor,
        uint256 auditorScore,
        uint256 medianScore,
        uint256 deviation,
        bool exceedsThreshold
    );

    /// @notice Updates the S3 shadow-mode deviation threshold.
    /// @dev Changing this does not by itself turn on slashing -- see
    ///      s3SlashingEnabled. While s3SlashingEnabled is false this only
    ///      changes what AuditorScoreDeviation reports as `exceedsThreshold`.
    /// @param newThreshold New deviation threshold, 0..100 scale.
    function setS3DeviationThreshold(uint256 newThreshold) external onlyOwner {
        if (newThreshold > 100) revert TA_InvalidDeviationThreshold();
        uint256 old = s3DeviationThreshold;
        s3DeviationThreshold = newThreshold;
        emit S3DeviationThresholdUpdated(old, newThreshold);
    }

    /// @notice Turns S3 slashing on or off in slashAuditors.
    /// @dev Gate for exiting shadow mode. Enable only once
    ///      s3DeviationThreshold has been empirically validated against real
    ///      audit-score variance (MECHANISM_DESIGN.md §6) -- enabling this
    ///      with an untuned threshold risks slashing honest auditors whose
    ///      scores legitimately vary across audit test sets.
    /// @param enabled True to make deviation beyond s3DeviationThreshold
    ///        slash-worthy in slashAuditors; false to return to shadow mode.
    function setS3SlashingEnabled(bool enabled) external onlyOwner {
        bool old = s3SlashingEnabled;
        s3SlashingEnabled = enabled;
        emit S3SlashingEnabledUpdated(old, enabled);
    }

    mapping(uint => LMSubmission[]) public lmSubmissions;

    ///  GI  ➜  submitter  ➜  bool
    mapping(uint => mapping(address => bool)) public clientHasSubmitted;
    mapping(uint => mapping(address => uint)) public clientSubmissionIndex;

    struct AuditBatch {
        uint batchId;
        address[] auditors;
        uint[] modelIndexes;
        bytes32 testDataCID; // shared test data for this batch
    }

    mapping(uint256 => AuditBatch[]) public auditBatches;

    mapping(uint => mapping(uint => mapping(address => bool)))
        public isBatchAuditor;

    mapping(uint => mapping(uint => mapping(uint => bool)))
        public isBatchModelIndex;

    mapping(uint256 => mapping(uint => mapping(address => mapping(uint => uint256)))) // GI // batchId // auditor // modelIndex // score
        public auditScores;

    mapping(uint256 => mapping(uint => mapping(address => mapping(uint => bool)))) // GI // batchId // auditor // modelIndex // eligible
        public LMeligibleVote;

    mapping(uint256 => mapping(uint => mapping(address => mapping(uint => bool)))) // GI // batchId // auditor // modelIndex // has voted
        public hasAuditedLM;

    // Commit-then-reveal (task_210726_6 §2a). commitHash = keccak256(abi.encodePacked(score, vote, salt)).
    // hasCommittedLM is distinct from hasAuditedLM: hasAuditedLM is set only
    // on a successful reveal and remains the single source of truth for
    // quorum/median counting, exactly as before -- an auditor who commits
    // but never reveals has hasCommittedLM=true, hasAuditedLM=false, and is
    // therefore excluded from quorum/median counting and slashAuditors'
    // "missed vote" check the same way a total non-participant already was,
    // with no extra logic needed to avoid "silently corrupting quorum
    // counting."
    mapping(uint256 => mapping(uint => mapping(address => mapping(uint => bytes32)))) // GI // batchId // auditor // modelIndex // commitHash
        public auditScoreCommits;

    mapping(uint256 => mapping(uint => mapping(address => mapping(uint => bool)))) // GI // batchId // auditor // modelIndex // has committed
        public hasCommittedLM;

    mapping(uint256 => bool) public Is_testdataCIDs_Assigned;

    // §2b: per-validator encrypted test-data key mapping. GI => batchId =>
    // auditor => that auditor's copy of the test-data decryption key,
    // encrypted to their public key off-chain. Populated in
    // assignAuditTestDataset. On-chain plumbing only -- no dincli/Python
    // decryption change, per the task's explicit scope boundary.
    mapping(uint256 => mapping(uint => mapping(address => bytes))) // GI // batchId // auditor // encrypted key
        public encryptedTestDataKey;

    modifier onlyAssignedAuditor(
        uint256 gi,
        uint batchId,
        uint modelIndex
    ) {
        if (batchId >= auditBatches[gi].length) revert TA_BatchDoesNotExist();

        // Check that the auditor is in the batch's auditors list
        if (!isBatchAuditor[gi][batchId][msg.sender])
            revert TA_NotAssignedAuditor();

        // Validate modelIndex is in the allowed list
        if (!isBatchModelIndex[gi][batchId][modelIndex])
            revert TA_InvalidModelIndex();

        _;
    }

    modifier onlyCurrentGI(uint _GI) {
        if (_GI != dintaskcoordinatorContract.GI()) revert TA_WrongGI();
        _;
    }

    event RewardDeposited(
        uint256 indexed gi,
        address indexed depositor,
        uint256 amount
    );
    event DinTokenSet(address indexed dinToken);
    event RewardSplitUpdated(RewardSplit split);
    event TreasuryAddressUpdated(address indexed treasuryAddress);
    event RewardsSettled(
        uint256 indexed gi,
        uint256 clientPool,
        uint256 auditorPool,
        uint256 aggregatorPool,
        uint256 treasuryShare
    );
    event RewardsClaimed(address indexed claimant, uint256 amount);

    event DINAuditorRegistered(uint indexed GI, address indexed auditor);

    event AuditScoreSubmitted(
        uint256 indexed gi,
        uint indexed batchId,
        address indexed auditor,
        uint modelIndex,
        uint256 score
    );

    event AuditScoreCommitted(
        uint256 indexed gi,
        uint indexed batchId,
        address indexed auditor,
        uint modelIndex,
        bytes32 commitHash
    );

    event EncryptedTestDataKeysAssigned(
        uint256 indexed gi,
        uint indexed batchId,
        bytes32 testDataCID,
        uint256 auditorCount
    );

    event EligibilityVoted(
        uint256 indexed gi,
        uint indexed batchId,
        uint indexed modelIndex,
        address auditor,
        bool vote
    );

    event EligibilityFinalized(
        uint256 indexed gi,
        uint indexed batchId,
        uint indexed modelIndex,
        bool eligible,
        uint totalVotes
    ); // eligible: final eligibility decision, totalVotes: number of auditors who voted

    event AuditorsBatchAuto(uint indexed GI, uint indexed batchId);
    event AuditorsBatchesCreated(uint indexed GI, uint batchCount);
    event PassScoreUpdated(uint256 oldScore, uint256 newScore);
    event AuditorSlashed(
        uint256 indexed gi,
        uint indexed batchId,
        address indexed auditor,
        bytes32 reason,
        uint256 requested,
        uint256 actual
    );

    /// @notice Deploys the auditor, wiring it to the validator stake and coordinator contracts.
    /// @dev Batch parameters are set to demo defaults (3 auditors/batch, 3 models/batch,
    ///      quorum of 2, pass score of 50). The model owner can adjust pass score via
    ///      updatePassScore.
    /// @param _dinvalidatorStakeContract_address Address of the DinValidatorStake proxy.
    /// @param _dintaskcoordinator_contract_address Address of the paired DINTaskCoordinator.
    constructor(
        address _dinvalidatorStakeContract_address,
        address _dintaskcoordinator_contract_address
    ) Ownable(msg.sender) {
        dinvalidatorStakeContract = IDinValidatorStake(
            _dinvalidatorStakeContract_address
        );
        dintaskcoordinatorContract = IDINTaskCoordinator(
            _dintaskcoordinator_contract_address
        );

        params = Params({
            auditorsPerBatch: 3,
            modelsPerBatch: 3,
            minEligibilityQuorum: 2,
            minScoreQuorum: 2,
            passScore: 50,
            MIN_MODELS_PER_BATCH: 2
        });
    }

    /// @notice Wires the DIN token used for reward deposits and payouts.
    /// @dev onlyOwner, freely re-settable (mirrors DINModelRegistry.setDinToken
    ///      / the existing setFees-style setters elsewhere in this codebase --
    ///      no one-shot restriction). Must be called before depositRewards or
    ///      claimRewards will work; deploy-time wiring, same operational
    ///      responsibility as DinCoordinator.updateValidatorStakeContract.
    /// @param dinToken_ Address of the DIN token (DinToken proxy).
    function setDinToken(address dinToken_) external onlyOwner {
        if (dinToken_ == address(0)) revert TA_InvalidAddress();
        dinToken = IERC20(dinToken_);
        emit DinTokenSet(dinToken_);
    }

    /// @notice Updates the DAO-settable reward role split.
    /// @dev Sum of all four fields must equal exactly 10000 bps. These
    ///      percentages are explicitly not final (task_210726_6 §3) --
    ///      pending Umer's P3-5.2 simulation at 10-50 validators / 100-500
    ///      clients per model.
    /// @param newSplit New RewardSplit; fields must sum to 10000.
    function setRewardSplit(RewardSplit calldata newSplit) external onlyOwner {
        uint256 sum = uint256(newSplit.clientBps) +
            newSplit.auditorBps +
            newSplit.aggregatorBps +
            newSplit.treasuryBps;
        if (sum != BPS_DENOMINATOR) revert TA_InvalidRewardSplit();
        rewardSplit = newSplit;
        emit RewardSplitUpdated(newSplit);
    }

    /// @notice Sets the address treasuryAccrued will eventually forward to.
    /// @dev No forwarding happens yet -- DinTreasury doesn't exist on develop
    ///      (task_210726_5). This only records the destination so wiring it
    ///      up later is a one-line change, not a redeploy.
    /// @param treasuryAddress_ Destination address for the treasury's reward share.
    function setTreasuryAddress(address treasuryAddress_) external onlyOwner {
        if (treasuryAddress_ == address(0)) revert TA_InvalidAddress();
        treasuryAddress = treasuryAddress_;
        emit TreasuryAddressUpdated(treasuryAddress_);
    }

    /// @notice Funds the reward pool for a specific Global Iteration.
    /// @dev Pulls `amount` DIN from the caller via safeTransferFrom -- caller
    ///      must have approved this contract first. Anyone may fund any GI's
    ///      pool (typically the model owner, but not restricted to them --
    ///      matches the "market-set pool" framing in MECHANISM_DESIGN §5,
    ///      nothing stops a third party topping up a pool they care about).
    ///      DINTaskCoordinator._startGI checks giRewardPool(_GI) > 0 as a
    ///      precondition before that GI can start.
    ///
    ///      `gi` must be the current GI or a future one: GI only ever moves
    ///      forward (DINTaskCoordinator._startGI requires _GI == GI + 1 and
    ///      never allows re-starting an earlier index), so a deposit tagged
    ///      with a `gi` that has already passed could never be started,
    ///      settled, or claimed -- it would just sit in this contract's
    ///      balance forever with no sweep path. Rejecting that case here is
    ///      cheap and catches both a mistyped GI number and a genuinely
    ///      unreachable one.
    /// @param gi GI index to fund. Must be >= the coordinator's current GI.
    /// @param amount DIN amount to deposit, in wei (18 decimals).
    function depositRewards(uint256 gi, uint256 amount) external {
        if (amount == 0) revert TA_AmountMustBePositive();
        if (gi == 0 || gi < dintaskcoordinatorContract.GI())
            revert TA_InvalidRewardGI();
        dinToken.safeTransferFrom(msg.sender, address(this), amount);
        giRewardPool[gi] += amount;
        emit RewardDeposited(gi, msg.sender, amount);
    }

    /// @notice Computes and credits per-GI reward shares across clients,
    ///         auditors, and aggregators, plus the treasury's cut.
    /// @dev Restricted to the paired DINTaskCoordinator, called once from
    ///      endGI() after GIstate reaches AggregatorsSlashed. Only ever
    ///      credits the `claimable` mapping -- no transfers happen here, by
    ///      design (see claimable's NatSpec). `rewardableAggregators` is
    ///      supplied by the coordinator (which owns the T1/T2 batch data)
    ///      rather than re-derived here, one entry per (aggregator,
    ///      finalized batch) pair so an aggregator who completed both a T1
    ///      and the T2 batch gets proportionally more weight, mirroring the
    ///      auditor weighting below.
    ///
    ///      Split basis, per task_210726_6 §3:
    ///      - Clients: proportional to finalMedianScore among approved==true
    ///        submissions. A rejected/ineligible submission earns nothing --
    ///        already enforced by the `approved` gate, not re-implemented
    ///        here (median-bounded score inflation and fold-in duplicate
    ///        discounting, where §1a's mc_marginal_gain_score is used,
    ///        bound this basis upstream in Parts 1-2, not in this function).
    ///      - Auditors: one weight unit per (batchId, modelIndex) they
    ///        actually voted on (hasAuditedLM), NOT a flat per-auditor
    ///        share -- an auditor who completed more assigned votes gets
    ///        proportionally more. Correctness is enforced by slashAuditors
    ///        having already run in this GI, not by re-checking anything
    ///        here (an auditor who missed a vote already lost stake for it;
    ///        they still earn for the votes they DID complete).
    ///      - Aggregators: one weight unit per rewardableAggregators entry.
    ///      - Treasury: the remainder after the other three integer-divided
    ///        shares are subtracted, not a fourth independently-rounded
    ///        share -- absorbs rounding dust so the four shares always sum
    ///        to exactly giRewardPool[gi], mirroring DinFeeRouter's
    ///        publicGoods-absorbs-dust pattern (task_210726_5).
    /// @param gi GI index to settle.
    /// @param rewardableAggregators Aggregators credited for a finalized T1/T2
    ///        batch this GI, one entry per (aggregator, batch) pair.
    function settleRewards(
        uint256 gi,
        address[] calldata rewardableAggregators
    ) external onlyTaskCoordinator onlyCurrentGI(gi) {
        uint256 pool = giRewardPool[gi];

        RewardSplit memory split = rewardSplit;
        uint256 clientPool = (pool * split.clientBps) / BPS_DENOMINATOR;
        uint256 auditorPool = (pool * split.auditorBps) / BPS_DENOMINATOR;
        uint256 aggregatorPool = (pool * split.aggregatorBps) / BPS_DENOMINATOR;
        uint256 treasuryShare = pool - clientPool - auditorPool - aggregatorPool;

        treasuryAccrued += treasuryShare;

        _settleClientRewards(gi, clientPool);
        _settleAuditorRewards(gi, auditorPool);
        _settleAggregatorRewards(rewardableAggregators, aggregatorPool);

        emit RewardsSettled(gi, clientPool, auditorPool, aggregatorPool, treasuryShare);
    }

    function _settleClientRewards(uint256 gi, uint256 clientPool) internal {
        LMSubmission[] storage submissions = lmSubmissions[gi];

        uint256 totalApprovedScore;
        for (uint256 i = 0; i < submissions.length; i++) {
            if (submissions[i].approved) {
                totalApprovedScore += submissions[i].finalMedianScore;
            }
        }
        if (totalApprovedScore == 0) return;

        for (uint256 i = 0; i < submissions.length; i++) {
            if (submissions[i].approved) {
                uint256 share = (clientPool *
                    submissions[i].finalMedianScore) / totalApprovedScore;
                if (share > 0) {
                    claimable[submissions[i].client] += share;
                }
            }
        }
    }

    function _settleAuditorRewards(uint256 gi, uint256 auditorPool) internal {
        AuditBatch[] storage batches = auditBatches[gi];

        uint256 totalWeight;
        for (uint256 b = 0; b < batches.length; b++) {
            AuditBatch storage batch = batches[b];
            for (uint256 a = 0; a < batch.auditors.length; a++) {
                address auditor = batch.auditors[a];
                for (uint256 m = 0; m < batch.modelIndexes.length; m++) {
                    if (hasAuditedLM[gi][b][auditor][batch.modelIndexes[m]]) {
                        totalWeight++;
                    }
                }
            }
        }
        if (totalWeight == 0) return;

        for (uint256 b = 0; b < batches.length; b++) {
            AuditBatch storage batch = batches[b];
            for (uint256 a = 0; a < batch.auditors.length; a++) {
                address auditor = batch.auditors[a];
                uint256 weight;
                for (uint256 m = 0; m < batch.modelIndexes.length; m++) {
                    if (hasAuditedLM[gi][b][auditor][batch.modelIndexes[m]]) {
                        weight++;
                    }
                }
                if (weight > 0) {
                    claimable[auditor] += (auditorPool * weight) / totalWeight;
                }
            }
        }
    }

    function _settleAggregatorRewards(
        address[] calldata rewardableAggregators,
        uint256 aggregatorPool
    ) internal {
        uint256 count = rewardableAggregators.length;
        if (count == 0) return;

        for (uint256 i = 0; i < count; i++) {
            claimable[rewardableAggregators[i]] += aggregatorPool / count;
        }
    }

    /// @notice Claims the caller's full accumulated reward balance.
    /// @dev Pull-payment pattern: zeroes the balance before transferring
    ///      (checks-effects-interactions), reverts on a zero balance rather
    ///      than silently no-op-ing. nonReentrant is defense-in-depth --
    ///      dinToken is a trusted, protocol-deployed ERC20 with no hooks --
    ///      but costs nothing here since ReentrancyGuardTransient uses
    ///      transient storage.
    function claimRewards() external nonReentrant {
        uint256 amount = claimable[msg.sender];
        if (amount == 0) revert TA_NoRewardsToClaim();
        claimable[msg.sender] = 0;
        dinToken.safeTransfer(msg.sender, amount);
        emit RewardsClaimed(msg.sender, amount);
    }

    /// @notice Updates the minimum average score a model must achieve to be approved.
    /// @dev Restricted to the paired DINTaskCoordinator. Called during startGI when
    ///      the two-argument overload is used.
    /// @param newPassScore New pass score in the range [0, 100].
    function updatePassScore(
        uint256 newPassScore
    ) external onlyTaskCoordinator {
        if (newPassScore > 100) revert TA_InvalidPassScore();

        uint256 oldScore = params.passScore;
        params.passScore = newPassScore;

        emit PassScoreUpdated(oldScore, newPassScore);
    }

    /// @notice Registers the caller as an auditor for the current GI.
    /// @dev Caller must be an active validator; duplicate registrations revert.
    ///      The coordinator's GI state must be DINauditorsRegistrationStarted.
    /// @param _GI Current GI index.
    function registerDINAuditor(uint _GI) public onlyCurrentGI(_GI) {
        if (
            dintaskcoordinatorContract.GIstate() !=
            GIstates.DINauditorsRegistrationStarted
        ) revert TA_AuditorRegistrationNotOpen();
        if (isRegisteredAuditor[_GI][msg.sender])
            revert TA_AuditorAlreadyRegistered();
        if (dinAuditors[_GI].length >= MAX_REGISTERED_AUDITORS)
            revert TA_RegistrationCapReached();

        if (!dinvalidatorStakeContract.isValidatorActive(msg.sender)) {
            revert TA_AuditorNotActive();
        }

        dinAuditors[_GI].push(msg.sender);
        isRegisteredAuditor[_GI][msg.sender] = true;

        emit DINAuditorRegistered(_GI, msg.sender);
    }

    /// @notice Returns the list of auditors registered for the given GI.
    /// @param _GI GI index to query.
    /// @return Ordered array of auditor addresses in registration order.
    function getDINtaskAuditors(
        uint _GI
    ) public view returns (address[] memory) {
        return dinAuditors[_GI];
    }

    /// @notice Submits a local model CID for the current GI.
    /// @dev Each address may submit at most once per GI. Reverts if the global
    ///      submission cap (MAX_LM_SUBMISSIONS) has been reached.
    /// @param _clientModel IPFS CID of the locally trained model weights, encoded as bytes32.
    /// @param _GI Current GI index.
    function submitLocalModel(
        bytes32 _clientModel,
        uint _GI
    ) public onlyCurrentGI(_GI) {
        if (dintaskcoordinatorContract.GIstate() != GIstates.LMSstarted)
            revert TA_LMSubmissionsNotOpen();
        if (clientHasSubmitted[_GI][msg.sender]) revert TA_AlreadySubmitted();
        if (lmSubmissions[_GI].length >= MAX_LM_SUBMISSIONS)
            revert TA_MaxLMSubmissionsReached();

        uint modelIndex = lmSubmissions[_GI].length;
        clientSubmissionIndex[_GI][msg.sender] = modelIndex;

        lmSubmissions[_GI].push(
            LMSubmission({
                client: msg.sender,
                modelCID: _clientModel,
                evaluated: false,
                approved: false,
                eligible: false,
                finalMedianScore: 0,
                submittedAt: uint40(block.timestamp)
            })
        );
        clientHasSubmitted[_GI][msg.sender] = true;
    }

    /// @notice Returns all local model submissions for the given GI.
    /// @param _GI GI index to query.
    /// @return Array of LMSubmission structs in submission order.
    function getClientModels(
        uint _GI
    ) public view returns (LMSubmission[] memory) {
        return lmSubmissions[_GI];
    }

    modifier onlyTaskCoordinator() {
        if (msg.sender != address(dintaskcoordinatorContract))
            revert TA_NotTaskCoordinator();
        _;
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

    function _activeAuditorPool(
        uint _GI
    ) internal view returns (address[] memory activePool) {
        address[] storage registeredPool = dinAuditors[_GI];
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
            address auditor = registeredPool[i];
            if (dinvalidatorStakeContract.isValidatorActive(auditor)) {
                activePool[ptr++] = auditor;
            }
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

    /// @notice Computes the median of the first `count` entries of `scores`.
    /// @dev Insertion sort — O(n^2), but n is bounded by params.auditorsPerBatch
    ///      (demo: 3, spec target: up to ~10), so this is cheap in practice and
    ///      avoids pulling in a sorting library for a handful of elements.
    ///      Even-length batches median as the integer-divided average of the
    ///      two middle elements, consistent with this contract's existing
    ///      integer-division-for-scores convention.
    /// @param scores Score array; only indices [0, count) are considered.
    /// @param count Number of valid entries in `scores` (may be < scores.length).
    function _medianOf(
        uint256[] memory scores,
        uint256 count
    ) internal pure returns (uint256) {
        if (count == 0) revert TA_EmptyScoreSet();

        for (uint256 i = 1; i < count; i++) {
            uint256 key = scores[i];
            uint256 j = i;
            while (j > 0 && scores[j - 1] > key) {
                scores[j] = scores[j - 1];
                j--;
            }
            scores[j] = key;
        }

        if (count % 2 == 1) {
            return scores[count / 2];
        }
        return (scores[count / 2 - 1] + scores[count / 2]) / 2;
    }

    /// @notice Partitions active auditors and submitted models into audit batches.
    /// @dev Called by the paired DINTaskCoordinator. Auditors are filtered to those
    ///      still Active at call time, then shuffled with blockhash-based entropy.
    ///      Returns false is never reached; reverts on any failure condition.
    /// @param _GI Current GI index.
    /// @return True on success.
    function createAuditorsBatches(
        uint _GI
    ) external onlyTaskCoordinator onlyCurrentGI(_GI) returns (bool) {
        if (dintaskcoordinatorContract.GIstate() != GIstates.LMSclosed)
            revert TA_CannotCreateAuditorsBatches();

        // Filter the historical registration list down to currently active auditors.
        address[] memory auditorPool = _activeAuditorPool(_GI);
        uint aLen = auditorPool.length;

        if (aLen < params.auditorsPerBatch) revert TA_NotEnoughAuditors();
        _shuffleAddressArray(auditorPool);

        // ▸ 2. Build list of local model indexes
        LMSubmission[] storage lmlist = lmSubmissions[_GI];
        uint[] memory modelIdx = new uint[](lmlist.length);

        for (uint i = 0; i < lmlist.length; i++) {
            modelIdx[i] = i;
        }
        _shuffleUintArray(modelIdx);

        // ▸ 3. Create batches, Greedily fill Auditors batches
        uint vPtr;
        uint mPtr;
        uint Batchcnt;

        while (
            vPtr + params.auditorsPerBatch <= auditorPool.length &&
            (mPtr + params.modelsPerBatch <= modelIdx.length ||
                (mPtr + params.MIN_MODELS_PER_BATCH <= modelIdx.length &&
                    mPtr + params.modelsPerBatch > modelIdx.length))
        ) {
            AuditBatch storage b = auditBatches[_GI].push();
            b.batchId = Batchcnt++;

            for (uint256 k = 0; k < params.auditorsPerBatch; k++) {
                b.auditors.push(auditorPool[vPtr + k]);
                isBatchAuditor[_GI][b.batchId][auditorPool[vPtr + k]] = true;
            }

            uint modelsToAssign = params.modelsPerBatch;
            if (modelIdx.length - mPtr < params.modelsPerBatch) {
                modelsToAssign = modelIdx.length - mPtr;
            }

            for (uint256 k = 0; k < modelsToAssign; k++) {
                b.modelIndexes.push(modelIdx[mPtr + k]);
                isBatchModelIndex[_GI][b.batchId][modelIdx[mPtr + k]] = true;
            }

            emit AuditorsBatchAuto(_GI, b.batchId);

            vPtr += params.auditorsPerBatch;
            mPtr += modelsToAssign;
        }

        emit AuditorsBatchesCreated(_GI, Batchcnt);
        return true;
    }

    /// @notice Returns the number of audit batches created for the given GI.
    /// @param _GI GI index to query.
    /// @return Number of audit batches.
    function AuditorsBatchCount(uint _GI) external view returns (uint) {
        if (_GI > dintaskcoordinatorContract.GI()) revert TA_WrongGI();
        return auditBatches[_GI].length;
    }

    /// @notice Returns the full details of an audit batch.
    /// @param _GI GI index.
    /// @param _batchId Batch index within that GI.
    /// @return batchId Canonical batch identifier.
    /// @return auditors Auditors assigned to this batch.
    /// @return modelIndexes Indexes into lmSubmissions[_GI] assigned to this batch.
    /// @return testDataCID IPFS CID of the test dataset for this batch.
    function getAuditorsBatch(
        uint _GI,
        uint _batchId
    )
        external
        view
        returns (
            uint batchId,
            address[] memory auditors,
            uint[] memory modelIndexes,
            bytes32 testDataCID
        )
    {
        if (_GI > dintaskcoordinatorContract.GI()) revert TA_WrongGI();
        if (_batchId >= auditBatches[_GI].length) revert TA_BatchDoesNotExist();
        AuditBatch memory batch = auditBatches[_GI][_batchId];
        return (
            batch.batchId,
            batch.auditors,
            batch.modelIndexes,
            batch.testDataCID
        );
    }

    /// @notice Records the test dataset CID for a specific audit batch, and
    ///         each assigned auditor's individually-encrypted decryption key.
    /// @dev Must be called once per batch before setTestDataAssignedFlag is
    ///      invoked. `encryptedKeys[i]` must correspond to
    ///      `auditBatches[gi][batchId].auditors[i]` (same order
    ///      createAuditorsBatches populated them in) -- task_210726_6 §2b:
    ///      whitepaper §5.2.3b per-validator key encryption, on-chain
    ///      plumbing only. The model owner is responsible for producing
    ///      `encryptedKeys` off-chain (symmetric test-data key encrypted to
    ///      each auditor's public key); the contract only stores what it's
    ///      given, it does not and cannot validate the encryption itself.
    /// @param gi Current GI index.
    /// @param batchId Batch index to assign the test dataset to.
    /// @param testDataCID IPFS CID of the test dataset, encoded as bytes32.
    /// @param encryptedKeys Per-auditor encrypted test-data keys, ordered to
    ///        match auditBatches[gi][batchId].auditors.
    function assignAuditTestDataset(
        uint256 gi,
        uint256 batchId,
        bytes32 testDataCID,
        bytes[] calldata encryptedKeys
    ) external onlyOwner onlyCurrentGI(gi) {
        if (batchId >= auditBatches[gi].length) revert TA_BatchDoesNotExist();
        AuditBatch storage batch = auditBatches[gi][batchId];
        if (batch.batchId != batchId) revert TA_BatchIDMismatch();
        if (encryptedKeys.length != batch.auditors.length)
            revert TA_EncryptedKeyCountMismatch();

        batch.testDataCID = testDataCID;

        for (uint256 i = 0; i < encryptedKeys.length; i++) {
            encryptedTestDataKey[gi][batchId][batch.auditors[i]] = encryptedKeys[i];
        }

        emit EncryptedTestDataKeysAssigned(gi, batchId, testDataCID, encryptedKeys.length);
    }

    /// @notice Marks test dataset distribution as complete for the given GI.
    /// @dev Restricted to the paired DINTaskCoordinator. flag must be true;
    ///      can only be set once per GI.
    /// @param _GI Current GI index.
    /// @param flag Must be true.
    /// @return True on success.
    function setTestDataAssignedFlag(
        uint _GI,
        bool flag
    ) external onlyTaskCoordinator onlyCurrentGI(_GI) returns (bool) {
        if (
            dintaskcoordinatorContract.GIstate() !=
            GIstates.AuditorsBatchesCreated
        ) revert TA_CannotSetTestDataAssignedFlag();
        if (!flag) revert TA_FlagMustBeTrue();
        if (Is_testdataCIDs_Assigned[_GI]) revert TA_FlagAlreadySet();

        Is_testdataCIDs_Assigned[_GI] = flag;
        return true;
    }

    function _tryFinalizeEligibility(
        uint256 gi,
        uint batchId,
        uint modelIndex
    ) internal {
        if (batchId >= auditBatches[gi].length) revert TA_BatchDoesNotExist();
        AuditBatch storage batch = auditBatches[gi][batchId];

        // Get the submission
        LMSubmission storage submission = lmSubmissions[gi][modelIndex];

        // Skip if already eligible
        if (submission.eligible) {
            return;
        }

        uint yesVotes = 0;
        uint totalVotes = 0;

        // Count votes using `hasAuditedLM` to distinguish "no vote" from "voted false"
        for (uint i = 0; i < batch.auditors.length; i++) {
            address auditor = batch.auditors[i];

            // Only count if the auditor has submitted a vote
            if (hasAuditedLM[gi][batchId][auditor][modelIndex]) {
                totalVotes++;
                if (LMeligibleVote[gi][batchId][auditor][modelIndex]) {
                    yesVotes++;
                }
            }
        }

        // Check if voting quorum is met
        if (totalVotes < params.minEligibilityQuorum) {
            return; // wait for more votes
        }

        // Majority rule: eligible if yesVotes >= minEligibilityQuorum
        bool majorityEligible = yesVotes >= params.minEligibilityQuorum;

        // Finalize the result
        submission.eligible = majorityEligible;

        emit EligibilityFinalized(
            gi,
            batchId,
            modelIndex,
            majorityEligible,
            totalVotes
        );
    }

    /// @notice Phase 1 of commit-then-reveal auditor scoring: lock in a
    ///         hidden (score, vote) pair.
    /// @dev Caller must be the assigned auditor for this batch and model
    ///      index. `commitHash` must equal `keccak256(abi.encodePacked(score,
    ///      vote, salt))` for the values the auditor intends to reveal later
    ///      -- the contract cannot and does not validate this at commit time
    ///      (that's the point; nothing about score/vote is visible yet).
    ///      Open only while GIstate == LMSevaluationStarted (the commit
    ///      window); revealing happens in a separate, later-gated phase
    ///      (LMSevaluationRevealStarted) so no auditor can see another's
    ///      revealed score before committing their own.
    /// @param gi Current GI index.
    /// @param batchId Batch index containing this model.
    /// @param modelIndex Index into lmSubmissions[gi] for the model being scored.
    /// @param commitHash keccak256(abi.encodePacked(score, vote, salt)).
    function commitAuditScore(
        uint256 gi,
        uint batchId,
        uint modelIndex,
        bytes32 commitHash
    ) external onlyAssignedAuditor(gi, batchId, modelIndex) onlyCurrentGI(gi) {
        if (dintaskcoordinatorContract.GIstate() != GIstates.LMSevaluationStarted)
            revert TA_CommitPhaseNotOpen();
        if (!dinvalidatorStakeContract.isValidatorActive(msg.sender)) {
            revert TA_AuditorNotActive();
        }
        if (commitHash == bytes32(0)) revert TA_EmptyCommitHash();
        if (hasCommittedLM[gi][batchId][msg.sender][modelIndex])
            revert TA_AlreadyCommitted();

        auditScoreCommits[gi][batchId][msg.sender][modelIndex] = commitHash;
        hasCommittedLM[gi][batchId][msg.sender][modelIndex] = true;

        emit AuditScoreCommitted(gi, batchId, msg.sender, modelIndex, commitHash);
    }

    /// @notice Phase 2 of commit-then-reveal: reveal the (score, vote, salt)
    ///         behind a prior commitment and have it counted.
    /// @dev Reverts unless the caller committed in this same (gi, batchId,
    ///      modelIndex) and the revealed values hash to that commitment.
    ///      Open only while GIstate == LMSevaluationRevealStarted, strictly
    ///      after the commit window has been closed by the model owner --
    ///      see DINTaskCoordinator.startLMsubmissionsEvaluationReveal.
    ///      An auditor who committed but never reveals simply never sets
    ///      hasAuditedLM, so they are excluded from quorum/median counting
    ///      exactly like a non-participant, and remain slashable via the
    ///      existing slashAuditors() "missed vote" check -- no special-casing
    ///      needed for the non-reveal case.
    /// @param gi Current GI index.
    /// @param batchId Batch index containing this model.
    /// @param modelIndex Index into lmSubmissions[gi] for the model being scored.
    /// @param score Audit score in the range [0, 100] -- must match the committed hash.
    /// @param vote True if the auditor deems the model eligible, false otherwise -- must match the committed hash.
    /// @param salt Arbitrary value chosen at commit time to prevent hash pre-image search.
    function revealAuditScore(
        uint256 gi,
        uint batchId,
        uint modelIndex,
        uint256 score,
        bool vote,
        bytes32 salt
    ) external onlyAssignedAuditor(gi, batchId, modelIndex) onlyCurrentGI(gi) {
        if (dintaskcoordinatorContract.GIstate() != GIstates.LMSevaluationRevealStarted)
            revert TA_RevealPhaseNotOpen();
        if (!dinvalidatorStakeContract.isValidatorActive(msg.sender)) {
            revert TA_AuditorNotActive();
        }
        if (score > 100) revert TA_ScoreOutOfRange();
        if (!hasCommittedLM[gi][batchId][msg.sender][modelIndex])
            revert TA_NoCommitFound();
        if (hasAuditedLM[gi][batchId][msg.sender][modelIndex])
            revert TA_AlreadyVoted();

        bytes32 expectedHash = keccak256(abi.encodePacked(score, vote, salt));
        if (expectedHash != auditScoreCommits[gi][batchId][msg.sender][modelIndex])
            revert TA_RevealHashMismatch();

        auditScores[gi][batchId][msg.sender][modelIndex] = score;
        LMeligibleVote[gi][batchId][msg.sender][modelIndex] = vote;
        hasAuditedLM[gi][batchId][msg.sender][modelIndex] = true;

        emit AuditScoreSubmitted(gi, batchId, msg.sender, modelIndex, score);
        emit EligibilityVoted(gi, batchId, modelIndex, msg.sender, vote);

        // Try to finalize eligibility if quorum is met
        _tryFinalizeEligibility(gi, batchId, modelIndex);
    }

    /// @notice Computes final median scores and approval status for all submitted models.
    /// @dev Iterates all batches and models; a model is approved if eligible and its
    ///      median score meets or exceeds passScore. Returns true if at least one
    ///      model was finalised; reverts if GI state is not LMSevaluationRevealStarted
    ///      (i.e. the commit-then-reveal reveal window, task_210726_6 §2a).
    /// @param _GI Current GI index.
    /// @return True if at least one model reached score quorum and was finalised.
    function finalizeEvaluation(
        uint _GI
    ) public onlyTaskCoordinator onlyCurrentGI(_GI) returns (bool) {
        if (
            dintaskcoordinatorContract.GIstate() !=
            GIstates.LMSevaluationRevealStarted
        ) revert TA_CannotFinalizeEvaluation();

        LMSubmission[] storage submissions = lmSubmissions[_GI];

        uint batches = auditBatches[_GI].length;
        uint finalizedCount;

        for (uint b = 0; b < batches; b++) {
            AuditBatch storage batch = auditBatches[_GI][b];

            // For each model assigned to this batch
            for (uint m = 0; m < batch.modelIndexes.length; m++) {
                uint modelIndex = batch.modelIndexes[m];
                if (modelIndex >= submissions.length) {
                    // Defensive: skip if bad index
                    continue;
                }

                LMSubmission storage sub = submissions[modelIndex];

                // Ensure eligibility is finalized if quorum has been reached
                if (!sub.eligible) {
                    _tryFinalizeEligibility(_GI, b, modelIndex);
                }

                // Collect scores from auditors who actually voted. Bounded by
                // batch.auditors.length (params.auditorsPerBatch, demo: 3,
                // spec: up to 10), so an in-memory sort here is cheap.
                uint256[] memory votedScores = new uint256[](
                    batch.auditors.length
                );
                address[] memory votedAuditors = new address[](
                    batch.auditors.length
                );
                uint votes;

                for (uint a = 0; a < batch.auditors.length; a++) {
                    address auditor = batch.auditors[a];
                    if (hasAuditedLM[_GI][b][auditor][modelIndex]) {
                        votedScores[votes] = auditScores[_GI][b][auditor][
                            modelIndex
                        ];
                        votedAuditors[votes] = auditor;
                        votes++;
                    }
                }

                // Only finalize a model's score if score quorum is met
                if (votes >= params.minScoreQuorum) {
                    // MECHANISM_DESIGN.md §6 / task_210726_6 §1c: the canonical
                    // per-model score is the MEDIAN across the auditor batch,
                    // not a mean — a mean lets a single dishonest auditor drag
                    // the score arbitrarily far; a median tolerates < 50%
                    // dishonest auditors (BlockFlow Algorithm 1).
                    // _medianOf sorts votedScores in place, which would break
                    // its index alignment with votedAuditors -- compute the
                    // median first, then re-read each auditor's raw score
                    // from the source-of-truth mapping (not the now-sorted
                    // array) when emitting deviations below.
                    uint256 median = _medianOf(votedScores, votes);

                    sub.finalMedianScore = median;
                    sub.evaluated = true;

                    // Approval requires (i) eligible == true and (ii) median >= passScore
                    sub.approved = (sub.eligible && median >= params.passScore);

                    finalizedCount++;

                    // §1d: S3 deviation, shadow mode -- computed and emitted
                    // for every auditor who voted on this model, but does not
                    // gate approval or trigger any slashing. See
                    // s3DeviationThreshold's NatSpec.
                    for (uint i = 0; i < votes; i++) {
                        address votedAuditor = votedAuditors[i];
                        uint256 auditorScore = auditScores[_GI][b][
                            votedAuditor
                        ][modelIndex];
                        uint256 deviation = auditorScore > median
                            ? auditorScore - median
                            : median - auditorScore;
                        emit AuditorScoreDeviation(
                            _GI,
                            b,
                            modelIndex,
                            votedAuditor,
                            auditorScore,
                            median,
                            deviation,
                            deviation > s3DeviationThreshold
                        );
                    }
                }
            }
        }

        // Return true if at least one model was finalized
        return finalizedCount > 0;
    }

    /// @notice Slashes auditors who either (S1) failed to vote on at least one
    ///         model in their batch, or (S3) voted on every model but had a
    ///         score deviate beyond s3DeviationThreshold from that model's
    ///         finalMedianScore, when s3SlashingEnabled is true.
    /// @dev Slash amount equals minStake() at call time for both reasons --
    ///      see MECHANISM_DESIGN.md §9 item 2 on the still-open flat-vs-partial
    ///      slash-fraction question, which applies equally to S1 and S3 and is
    ///      out of scope here. S1 takes priority: an auditor who missed a vote
    ///      is slashed once for that (AUD_NO_VOTE) and not re-evaluated for
    ///      S3 in the same batch. An auditor who voted on everything is
    ///      slashed at most once per batch for S3 (AUD_SCORE_DEVIATION), even
    ///      if multiple of their votes deviated. Each slashed auditor emits an
    ///      AuditorSlashed event. Always returns true; individual slash
    ///      failures do not halt the loop.
    /// @param _GI Current GI index.
    /// @return True on completion.
    function slashAuditors(
        uint _GI
    ) external onlyTaskCoordinator onlyCurrentGI(_GI) returns (bool) {
        if (dintaskcoordinatorContract.GIstate() != GIstates.T2AggregationDone)
            revert TA_CannotSlashAuditors();
        uint256 slashAmount = dinvalidatorStakeContract.minStake();
        uint batchCount = auditBatches[_GI].length;
        LMSubmission[] storage submissions = lmSubmissions[_GI];

        for (uint b = 0; b < batchCount; b++) {
            AuditBatch storage batch = auditBatches[_GI][b];
            for (uint a = 0; a < batch.auditors.length; a++) {
                address auditor = batch.auditors[a];
                bool missedVote = false;
                bool exceededDeviation = false;

                for (uint m = 0; m < batch.modelIndexes.length; m++) {
                    uint modelIndex = batch.modelIndexes[m];
                    if (!hasAuditedLM[_GI][b][auditor][modelIndex]) {
                        missedVote = true;
                        break;
                    }

                    if (
                        s3SlashingEnabled && submissions[modelIndex].evaluated
                    ) {
                        uint256 auditorScore = auditScores[_GI][b][auditor][
                            modelIndex
                        ];
                        uint256 median = submissions[modelIndex]
                            .finalMedianScore;
                        uint256 deviation = auditorScore > median
                            ? auditorScore - median
                            : median - auditorScore;
                        if (deviation > s3DeviationThreshold) {
                            exceededDeviation = true;
                        }
                    }
                }

                if (missedVote) {
                    uint256 actualSlashed = dinvalidatorStakeContract.slash(
                        auditor,
                        slashAmount,
                        "AUD_NO_VOTE"
                    );
                    emit AuditorSlashed(
                        _GI,
                        b,
                        auditor,
                        "AUD_NO_VOTE",
                        slashAmount,
                        actualSlashed
                    );
                } else if (exceededDeviation) {
                    uint256 actualSlashed = dinvalidatorStakeContract.slash(
                        auditor,
                        slashAmount,
                        "AUD_SCORE_DEVIATION"
                    );
                    emit AuditorSlashed(
                        _GI,
                        b,
                        auditor,
                        "AUD_SCORE_DEVIATION",
                        slashAmount,
                        actualSlashed
                    );
                }
            }
        }

        return true;
    }

    /// @notice Returns the indexes of all models approved for aggregation in the given GI.
    /// @dev A model is approved when both eligible == true and finalMedianScore >= passScore.
    /// @param _GI GI index to query.
    /// @return Array of approved model indexes into lmSubmissions[_GI].
    function approvedModelIndexes(
        uint _GI
    ) public view returns (uint[] memory) {
        LMSubmission[] storage list = lmSubmissions[_GI];
        uint count;
        for (uint i = 0; i < list.length; i++) {
            if (list[i].approved) count++;
        }
        uint[] memory out = new uint[](count);
        uint j;
        for (uint i = 0; i < list.length; i++) {
            if (list[i].approved) out[j++] = i;
        }
        return out;
    }
}
