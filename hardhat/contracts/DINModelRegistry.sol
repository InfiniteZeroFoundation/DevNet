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
    error TransferFailed();

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
    event FeesWithdrawn(address indexed to, uint256 amount);
    event DAOAdminUpdated(address indexed oldAdmin, address indexed newAdmin);

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

    // Reserved for future state variables at this inheritance level.
    uint256[50] private __gap;

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

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

    function rejectModel(uint256 requestId) external onlyOwner {
        if (requestId >= modelRequests.length) revert InvalidRequestId();

        ModelRequest storage req = modelRequests[requestId];
        if (req.processed) revert AlreadyProcessed();

        req.processed = true;
        req.approved = false;

        emit ModelRejected(requestId);
    }

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

    function rejectManifestUpdate(uint256 requestId) external onlyOwner {
        if (requestId >= manifestRequests.length) revert InvalidRequestId();

        ManifestUpdateRequest storage req = manifestRequests[requestId];
        if (req.processed) revert AlreadyProcessed();

        req.processed = true;
        req.approved = false;

        emit ManifestUpdateRejected(requestId);
    }

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

    function totalModels() external view returns (uint256) {
        return models.length;
    }

    function totalModelRequests() external view returns (uint256) {
        return modelRequests.length;
    }

    function totalManifestRequests() external view returns (uint256) {
        return manifestRequests.length;
    }

    function getModelIdByTaskCoordinator(
        address taskCoordinator
    ) external view returns (bool exists, uint256 modelId) {
        uint256 val = _modelIdByTaskCoordinator[taskCoordinator];
        if (val == 0) return (false, 0);
        return (true, val - 1);
    }

    function getModelIdByTaskAuditor(
        address taskAuditor
    ) external view returns (bool exists, uint256 modelId) {
        uint256 val = _modelIdByTaskAuditor[taskAuditor];
        if (val == 0) return (false, 0);
        return (true, val - 1);
    }

    function disableModel(uint256 modelId) external onlyOwner {
        if (modelId >= models.length) revert InvalidModelId();
        modelDisabled[modelId] = true;
        emit ModelDisabled(modelId);
    }

    function enableModel(uint256 modelId) external onlyOwner {
        if (modelId >= models.length) revert InvalidModelId();
        modelDisabled[modelId] = false;
        emit ModelEnabled(modelId);
    }

    function setOpenSourceFee(uint256 newFee) external onlyOwner {
        openSourceFee = newFee;
        emit OpenSourceFeeUpdated(newFee);
    }

    function setProprietaryFee(uint256 newFee) external onlyOwner {
        proprietaryFee = newFee;
        emit ProprietaryFeeUpdated(newFee);
    }

    function setOpenSourceUpdateFee(uint256 newFee) external onlyOwner {
        openSourceUpdateFee = newFee;
        emit OpenSourceUpdateFeeUpdated(newFee);
    }

    function setProprietaryUpdateFee(uint256 newFee) external onlyOwner {
        proprietaryUpdateFee = newFee;
        emit ProprietaryUpdateFeeUpdated(newFee);
    }

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

    function withdrawFees(address payable to) external onlyOwner {
        uint256 balance = address(this).balance;
        (bool success, ) = to.call{value: balance}("");
        if (!success) revert TransferFailed();
        emit FeesWithdrawn(to, balance);
    }

    // Backward-compat shims — dincli calls daoAdmin() / setDAOAdmin().
    // Underlying auth model is OwnableUpgradeable; these are read-through facades.
    function daoAdmin() external view returns (address) {
        return owner();
    }

    function setDAOAdmin(address newAdmin) external onlyOwner {
        address old = owner();
        transferOwnership(newAdmin);
        emit DAOAdminUpdated(old, newAdmin);
    }
}
