// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";

interface IDinValidatorStake {
    function isSlasherContract(
        address slasherContract
    ) external view returns (bool);
}

interface IOwnable {
    function owner() external view returns (address);
}

interface IDinFeeRouter {
    function routeFeeETH(address payer) external payable;
}

/// @title DIN Model Registry
/// @notice Manages model registration requests, manifest updates, and per-model
///         lifecycle controls. Deployed once per network behind a Transparent Proxy.
contract DINModelRegistry is Initializable, OwnableUpgradeable {
    error NotModelOwner();
    error InvalidModelId();
    error InvalidRequestId();
    error AlreadyProcessed();
    error InsufficientFee();
    error TaskCoordinatorEqualsTaskAuditor();
    error NotOwnerOfTaskCoordinator();
    error NotOwnerOfTaskAuditor();
    error ModelIsDisabled(uint256 modelId);
    error TaskCoordinatorAlreadyRegistered();
    error TaskAuditorAlreadyRegistered();
    error ZeroAddress();
    error CoordinatorNoLongerSlasher();
    error AuditorNoLongerSlasher();
    error CoordinatorOwnershipChanged();
    error AuditorOwnershipChanged();
    error FeeRouterNotSet();

    event ModelRegistrationRequested(
        uint256 indexed requestId,
        address indexed requester
    );
    event ModelApproved(uint256 indexed requestId, uint256 indexed modelId);
    event ModelRejected(uint256 indexed requestId);
    event ManifestUpdateRequested(
        uint256 indexed requestId,
        uint256 indexed modelId
    );
    event ManifestUpdated(
        uint256 indexed requestId,
        uint256 indexed modelId,
        bytes32 newCID
    );
    event ManifestUpdateRejected(uint256 indexed requestId);
    event ModelDisabled(uint256 indexed modelId);
    event ModelEnabled(uint256 indexed modelId);
    event OpenSourceFeeUpdated(uint256 newFee);
    event ProprietaryFeeUpdated(uint256 newFee);
    event OpenSourceUpdateFeeUpdated(uint256 newFee);
    event ProprietaryUpdateFeeUpdated(uint256 newFee);
    event FeesUpdated(
        uint256 openSourceFee,
        uint256 proprietaryFee,
        uint256 openSourceUpdateFee,
        uint256 proprietaryUpdateFee
    );
    event FeeRouterUpdated(address indexed feeRouter);
    event FeesSweptToRouter(uint256 amount);

    struct Model {
        address owner;
        bool isOpenSource;
        bytes32 manifestCID;
        address taskCoordinator;
        address taskAuditor;
        uint256 createdAt;
    }

    struct ModelRequest {
        address requester;
        bool isOpenSource;
        bytes32 manifestCID;
        address taskCoordinator;
        address taskAuditor;
        uint256 feePaid;
        bool processed;
        bool approved;
        uint256 createdAt;
    }

    struct ManifestUpdateRequest {
        uint256 modelId;
        bytes32 newManifestCID;
        address requester;
        uint256 feePaid;
        bool processed;
        bool approved;
    }

    IDinValidatorStake public dinValidatorStake;

    uint256 public openSourceFee;
    uint256 public proprietaryFee;
    uint256 public openSourceUpdateFee;
    uint256 public proprietaryUpdateFee;

    Model[] private models;
    ModelRequest[] public modelRequests;
    ManifestUpdateRequest[] public manifestRequests;

    mapping(address => uint256) private _modelIdByTaskCoordinator;
    mapping(address => uint256) private _modelIdByTaskAuditor;
    mapping(uint256 => bool) public modelDisabled;

    IDinFeeRouter public feeRouter;

    // Reserved for future state variables at this inheritance level.
    uint256[50] private __gap;

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /// @notice Initialises the proxy, wires the validator stake contract, and sets
    ///         default registration and update fees.
    /// @param dinValidatorStake_ Address of the DinValidatorStake proxy.
    function initialize(address dinValidatorStake_) external initializer {
        if (dinValidatorStake_ == address(0)) revert ZeroAddress();
        __Ownable_init(msg.sender);
        dinValidatorStake = IDinValidatorStake(dinValidatorStake_);
        openSourceFee = 0.000001 ether;
        proprietaryFee = 0.00001 ether;
        openSourceUpdateFee = 0.0000001 ether;
        proprietaryUpdateFee = 0.000001 ether;
    }

    modifier onlyModelOwner(uint256 modelId) {
        if (modelId >= models.length) revert InvalidModelId();
        if (models[modelId].owner != msg.sender) revert NotModelOwner();
        _;
    }

    modifier notDisabled(uint256 modelId) {
        if (modelDisabled[modelId]) revert ModelIsDisabled(modelId);
        _;
    }

    /// @notice Submits a model registration request for DIN-Representative review.
    /// @dev Both task contracts must be registered slashers and owned by msg.sender
    ///      at submission time. These conditions are re-validated at approval.
    /// @param manifestCID IPFS CID of the model manifest.
    /// @param taskCoordinator Address of the model's DINTaskCoordinator contract.
    /// @param taskAuditor Address of the model's DINTaskAuditor contract.
    /// @param isOpenSource True for open-source fee tier; false for proprietary.
    /// @return requestId Index of the created request in the modelRequests array.
    function requestModelRegistration(
        bytes32 manifestCID,
        address taskCoordinator,
        address taskAuditor,
        bool isOpenSource
    ) external payable returns (uint256 requestId) {
        uint256 requiredFee = isOpenSource ? openSourceFee : proprietaryFee;
        if (msg.value < requiredFee) revert InsufficientFee();

        if (!dinValidatorStake.isSlasherContract(taskCoordinator))
            revert CoordinatorNoLongerSlasher();
        if (!dinValidatorStake.isSlasherContract(taskAuditor))
            revert AuditorNoLongerSlasher();

        if (taskCoordinator == taskAuditor)
            revert TaskCoordinatorEqualsTaskAuditor();

        if (IOwnable(taskCoordinator).owner() != msg.sender)
            revert NotOwnerOfTaskCoordinator();
        if (IOwnable(taskAuditor).owner() != msg.sender)
            revert NotOwnerOfTaskAuditor();

        requestId = modelRequests.length;

        modelRequests.push(
            ModelRequest({
                requester: msg.sender,
                isOpenSource: isOpenSource,
                manifestCID: manifestCID,
                taskCoordinator: taskCoordinator,
                taskAuditor: taskAuditor,
                feePaid: msg.value,
                processed: false,
                approved: false,
                createdAt: block.timestamp
            })
        );

        emit ModelRegistrationRequested(requestId, msg.sender);
    }

    /// @notice Approves a pending registration request and adds the model to the registry.
    /// @dev Re-validates slasher status and ownership at approval time to guard against
    ///      state changes between submission and approval.
    /// @param requestId Index into the modelRequests array.
    function approveModel(uint256 requestId) external onlyOwner {
        if (requestId >= modelRequests.length) revert InvalidRequestId();

        ModelRequest storage req = modelRequests[requestId];
        if (req.processed) revert AlreadyProcessed();

        if (_modelIdByTaskCoordinator[req.taskCoordinator] != 0)
            revert TaskCoordinatorAlreadyRegistered();
        if (_modelIdByTaskAuditor[req.taskAuditor] != 0)
            revert TaskAuditorAlreadyRegistered();

        if (!dinValidatorStake.isSlasherContract(req.taskCoordinator))
            revert CoordinatorNoLongerSlasher();
        if (!dinValidatorStake.isSlasherContract(req.taskAuditor))
            revert AuditorNoLongerSlasher();
        if (IOwnable(req.taskCoordinator).owner() != req.requester)
            revert CoordinatorOwnershipChanged();
        if (IOwnable(req.taskAuditor).owner() != req.requester)
            revert AuditorOwnershipChanged();

        uint256 modelId = models.length;

        models.push(
            Model({
                owner: req.requester,
                isOpenSource: req.isOpenSource,
                manifestCID: req.manifestCID,
                taskCoordinator: req.taskCoordinator,
                taskAuditor: req.taskAuditor,
                createdAt: block.timestamp
            })
        );

        _modelIdByTaskCoordinator[req.taskCoordinator] = modelId + 1;
        _modelIdByTaskAuditor[req.taskAuditor] = modelId + 1;

        req.processed = true;
        req.approved = true;

        emit ModelApproved(requestId, modelId);
    }

    /// @notice Rejects a pending registration request without adding a model.
    /// @param requestId Index into the modelRequests array.
    function rejectModel(uint256 requestId) external onlyOwner {
        if (requestId >= modelRequests.length) revert InvalidRequestId();

        ModelRequest storage req = modelRequests[requestId];
        if (req.processed) revert AlreadyProcessed();

        req.processed = true;
        req.approved = false;

        emit ModelRejected(requestId);
    }

    /// @notice Submits a manifest update request for an existing model.
    /// @param modelId ID of the model to update.
    /// @param newManifestCID IPFS CID of the new manifest.
    /// @return requestId Index of the created request in the manifestRequests array.
    function requestManifestUpdate(
        uint256 modelId,
        bytes32 newManifestCID
    )
        external
        payable
        onlyModelOwner(modelId)
        notDisabled(modelId)
        returns (uint256 requestId)
    {
        Model storage m = models[modelId];

        uint256 requiredFee = m.isOpenSource
            ? openSourceUpdateFee
            : proprietaryUpdateFee;

        if (msg.value < requiredFee) revert InsufficientFee();

        requestId = manifestRequests.length;

        manifestRequests.push(
            ManifestUpdateRequest({
                modelId: modelId,
                newManifestCID: newManifestCID,
                requester: msg.sender,
                feePaid: msg.value,
                processed: false,
                approved: false
            })
        );

        emit ManifestUpdateRequested(requestId, modelId);
    }

    /// @notice Approves a manifest update and writes the new CID to the model record.
    /// @param requestId Index into the manifestRequests array.
    function approveManifestUpdate(uint256 requestId) external onlyOwner {
        if (requestId >= manifestRequests.length) revert InvalidRequestId();

        ManifestUpdateRequest storage req = manifestRequests[requestId];
        if (req.processed) revert AlreadyProcessed();

        if (modelDisabled[req.modelId]) revert ModelIsDisabled(req.modelId);

        models[req.modelId].manifestCID = req.newManifestCID;

        req.processed = true;
        req.approved = true;

        emit ManifestUpdated(requestId, req.modelId, req.newManifestCID);
    }

    /// @notice Rejects a pending manifest update request.
    /// @param requestId Index into the manifestRequests array.
    function rejectManifestUpdate(uint256 requestId) external onlyOwner {
        if (requestId >= manifestRequests.length) revert InvalidRequestId();

        ManifestUpdateRequest storage req = manifestRequests[requestId];
        if (req.processed) revert AlreadyProcessed();

        req.processed = true;
        req.approved = false;

        emit ManifestUpdateRejected(requestId);
    }

    /// @notice Returns the full record for a registered model.
    /// @param modelId ID of the model to query.
    /// @return owner Address of the model owner.
    /// @return isOpenSource True if the model is open-source.
    /// @return manifestCID IPFS CID of the current manifest.
    /// @return createdAt Block timestamp at registration.
    /// @return taskCoordinator Address of the model's DINTaskCoordinator.
    /// @return taskAuditor Address of the model's DINTaskAuditor.
    function getModel(
        uint256 modelId
    )
        external
        view
        returns (
            address owner,
            bool isOpenSource,
            bytes32 manifestCID,
            uint256 createdAt,
            address taskCoordinator,
            address taskAuditor
        )
    {
        if (modelId >= models.length) revert InvalidModelId();
        Model storage m = models[modelId];
        return (
            m.owner,
            m.isOpenSource,
            m.manifestCID,
            m.createdAt,
            m.taskCoordinator,
            m.taskAuditor
        );
    }

    /// @notice Returns the total number of approved models in the registry.
    /// @return Count of registered models.
    function totalModels() external view returns (uint256) {
        return models.length;
    }

    /// @notice Returns the total number of model registration requests submitted.
    /// @return Count of entries in the modelRequests array.
    function totalModelRequests() external view returns (uint256) {
        return modelRequests.length;
    }

    /// @notice Returns the total number of manifest update requests submitted.
    /// @return Count of entries in the manifestRequests array.
    function totalManifestRequests() external view returns (uint256) {
        return manifestRequests.length;
    }

    /// @notice Looks up the model ID associated with a given task coordinator address.
    /// @param taskCoordinator Address to query.
    /// @return exists True if a model is registered for this coordinator.
    /// @return modelId The model's ID (only meaningful if exists is true).
    function getModelIdByTaskCoordinator(
        address taskCoordinator
    ) external view returns (bool exists, uint256 modelId) {
        uint256 val = _modelIdByTaskCoordinator[taskCoordinator];
        if (val == 0) return (false, 0);
        return (true, val - 1);
    }

    /// @notice Looks up the model ID associated with a given task auditor address.
    /// @param taskAuditor Address to query.
    /// @return exists True if a model is registered for this auditor.
    /// @return modelId The model's ID (only meaningful if exists is true).
    function getModelIdByTaskAuditor(
        address taskAuditor
    ) external view returns (bool exists, uint256 modelId) {
        uint256 val = _modelIdByTaskAuditor[taskAuditor];
        if (val == 0) return (false, 0);
        return (true, val - 1);
    }

    /// @notice Disables a model, blocking manifest updates and new GI registrations.
    /// @param modelId ID of the model to disable.
    function disableModel(uint256 modelId) external onlyOwner {
        if (modelId >= models.length) revert InvalidModelId();
        modelDisabled[modelId] = true;
        emit ModelDisabled(modelId);
    }

    /// @notice Re-enables a previously disabled model.
    /// @param modelId ID of the model to enable.
    function enableModel(uint256 modelId) external onlyOwner {
        if (modelId >= models.length) revert InvalidModelId();
        modelDisabled[modelId] = false;
        emit ModelEnabled(modelId);
    }

    /// @notice Updates the registration fee for open-source models.
    /// @param newFee New fee in wei.
    function setOpenSourceFee(uint256 newFee) external onlyOwner {
        openSourceFee = newFee;
        emit OpenSourceFeeUpdated(newFee);
    }

    /// @notice Updates the registration fee for proprietary models.
    /// @param newFee New fee in wei.
    function setProprietaryFee(uint256 newFee) external onlyOwner {
        proprietaryFee = newFee;
        emit ProprietaryFeeUpdated(newFee);
    }

    /// @notice Updates the manifest update fee for open-source models.
    /// @param newFee New fee in wei.
    function setOpenSourceUpdateFee(uint256 newFee) external onlyOwner {
        openSourceUpdateFee = newFee;
        emit OpenSourceUpdateFeeUpdated(newFee);
    }

    /// @notice Updates the manifest update fee for proprietary models.
    /// @param newFee New fee in wei.
    function setProprietaryUpdateFee(uint256 newFee) external onlyOwner {
        proprietaryUpdateFee = newFee;
        emit ProprietaryUpdateFeeUpdated(newFee);
    }

    /// @notice Updates all four fee tiers in a single transaction.
    /// @param _openSourceFee Open-source registration fee in wei.
    /// @param _proprietaryFee Proprietary registration fee in wei.
    /// @param _openSourceUpdateFee Open-source manifest update fee in wei.
    /// @param _proprietaryUpdateFee Proprietary manifest update fee in wei.
    function setFees(
        uint256 _openSourceFee,
        uint256 _proprietaryFee,
        uint256 _openSourceUpdateFee,
        uint256 _proprietaryUpdateFee
    ) external onlyOwner {
        openSourceFee = _openSourceFee;
        proprietaryFee = _proprietaryFee;
        openSourceUpdateFee = _openSourceUpdateFee;
        proprietaryUpdateFee = _proprietaryUpdateFee;

        emit FeesUpdated(
            _openSourceFee,
            _proprietaryFee,
            _openSourceUpdateFee,
            _proprietaryUpdateFee
        );
    }

    /// @notice Sets the fee router used to split and route accumulated ETH fees.
    function setFeeRouter(address feeRouter_) external onlyOwner {
        if (feeRouter_ == address(0)) revert ZeroAddress();
        feeRouter = IDinFeeRouter(feeRouter_);
        emit FeeRouterUpdated(feeRouter_);
    }

    /// @notice Sweeps the contract's entire accumulated ETH balance to the fee
    ///         router in one call, which splits it across treasury/validator-pool/
    ///         storage/public-goods per its configured split.
    /// @dev Fees accrue here per-request (no per-request router call) and get
    ///      batched through this sweep to amortize the router's external-call
    ///      cost across many registrations/updates instead of paying it on each one.
    function sweepFeesToRouter() external onlyOwner {
        if (address(feeRouter) == address(0)) revert FeeRouterNotSet();
        uint256 balance = address(this).balance;
        if (balance == 0) return;
        feeRouter.routeFeeETH{value: balance}(address(this));
        emit FeesSweptToRouter(balance);
    }
}
