// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title DIN Model Registry (v2 - Request/Approval Based)
/// @author InfiniteZero Foundation
/// @notice Secure registry with approval layer for manifests
/// @dev Minimal, auditable, DAO-controlled primitive

interface IDinValidatorStake {
    function isSlasherContract(
        address slasherContract
    ) external view returns (bool);
}

interface IOwnable {
    function owner() external view returns (address);
}

contract DINModelRegistry {
    /*//////////////////////////////////////////////////////////////
                                ERRORS
    //////////////////////////////////////////////////////////////*/
    error NotDINDAOAdmin();
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
    // Approval-time revalidation errors
    error CoordinatorNoLongerSlasher();
    error AuditorNoLongerSlasher();
    error CoordinatorOwnershipChanged();
    error AuditorOwnershipChanged();

    /*//////////////////////////////////////////////////////////////
                                EVENTS
    //////////////////////////////////////////////////////////////*/
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

    // Kill-switch events
    event ModelDisabled(uint256 indexed modelId);
    event ModelEnabled(uint256 indexed modelId);

    // Individual fee events (granular tracking)
    event OpenSourceFeeUpdated(uint256 newFee);
    event ProprietaryFeeUpdated(uint256 newFee);
    event OpenSourceUpdateFeeUpdated(uint256 newFee);
    event ProprietaryUpdateFeeUpdated(uint256 newFee);

    // Combined fee event (atomic governance proposals)
    event FeesUpdated(
        uint256 openSourceFee,
        uint256 proprietaryFee,
        uint256 openSourceUpdateFee,
        uint256 proprietaryUpdateFee
    );

    event FeesWithdrawn(address indexed to, uint256 amount);
    event DAOAdminUpdated(address indexed oldAdmin, address indexed newAdmin);

    /*//////////////////////////////////////////////////////////////
                                STRUCTS
    //////////////////////////////////////////////////////////////*/
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

    /*//////////////////////////////////////////////////////////////
                            STATE VARIABLES
    //////////////////////////////////////////////////////////////*/
    address public daoAdmin;
    IDinValidatorStake public dinValidatorStake;

    // Registration fees
    uint256 public openSourceFee = 0.000001 ether;
    uint256 public proprietaryFee = 0.00001 ether;

    // Manifest update fees
    uint256 public openSourceUpdateFee = 0.0000001 ether;
    uint256 public proprietaryUpdateFee = 0.000001 ether;

    Model[] private models;
    ModelRequest[] public modelRequests;
    ManifestUpdateRequest[] public manifestRequests;

    mapping(address => uint256) private _modelIdByTaskCoordinator; // Stores modelId + 1
    mapping(address => uint256) private _modelIdByTaskAuditor; // Stores modelId + 1

    // Kill-switch: disabled models cannot have manifests updated or participate
    mapping(uint256 => bool) public modelDisabled;

    /*//////////////////////////////////////////////////////////////
                              MODIFIERS
    //////////////////////////////////////////////////////////////*/
    modifier onlyDAOAdmin() {
        if (msg.sender != daoAdmin) revert NotDINDAOAdmin();
        _;
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

    /*//////////////////////////////////////////////////////////////
                              CONSTRUCTOR
    //////////////////////////////////////////////////////////////*/
    constructor(address _dinValidatorStake) {
        daoAdmin = msg.sender; // DIN DAO representative
        dinValidatorStake = IDinValidatorStake(_dinValidatorStake);
    }

    /*//////////////////////////////////////////////////////////////
                    MODEL REGISTRATION REQUEST
    //////////////////////////////////////////////////////////////*/

    /// @notice Submit a model registration request for DAO review
    /// @param manifestCID IPFS CID (bytes32) containing the model manifest
    /// @param taskCoordinator Address of the registered task coordinator slasher contract
    /// @param taskAuditor    Address of the registered task auditor slasher contract
    /// @param isOpenSource   Whether the model is open-source or proprietary
    /// @return requestId     ID of the pending request
    function requestModelRegistration(
        bytes32 manifestCID,
        address taskCoordinator,
        address taskAuditor,
        bool isOpenSource
    ) external payable returns (uint256 requestId) {
        uint256 requiredFee = isOpenSource ? openSourceFee : proprietaryFee;
        if (msg.value < requiredFee) revert InsufficientFee();

        require(
            dinValidatorStake.isSlasherContract(taskCoordinator),
            "Invalid Coordinator"
        );
        require(
            dinValidatorStake.isSlasherContract(taskAuditor),
            "Invalid Auditor"
        );

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

    /*//////////////////////////////////////////////////////////////
                        APPROVE / REJECT MODEL
    //////////////////////////////////////////////////////////////*/

    /// @notice DAO approves a pending model registration
    function approveModel(uint256 requestId) external onlyDAOAdmin {
        if (requestId >= modelRequests.length) revert InvalidRequestId();

        ModelRequest storage req = modelRequests[requestId];
        if (req.processed) revert AlreadyProcessed();

        // Guard against reusing the same coordinator or auditor across models
        if (_modelIdByTaskCoordinator[req.taskCoordinator] != 0)
            revert TaskCoordinatorAlreadyRegistered();
        if (_modelIdByTaskAuditor[req.taskAuditor] != 0)
            revert TaskAuditorAlreadyRegistered();

        // Revalidate: slasher status or ownership may have changed since the request was submitted
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

        // Store modelId + 1 to distinguish from the zero-value default
        _modelIdByTaskCoordinator[req.taskCoordinator] = modelId + 1;
        _modelIdByTaskAuditor[req.taskAuditor] = modelId + 1;

        req.processed = true;
        req.approved = true;

        emit ModelApproved(requestId, modelId);
    }

    /// @notice DAO rejects a pending model registration (fee is retained)
    function rejectModel(uint256 requestId) external onlyDAOAdmin {
        if (requestId >= modelRequests.length) revert InvalidRequestId();

        ModelRequest storage req = modelRequests[requestId];
        if (req.processed) revert AlreadyProcessed();

        req.processed = true;
        req.approved = false;

        emit ModelRejected(requestId);
    }

    /*//////////////////////////////////////////////////////////////
                    MANIFEST UPDATE REQUEST
    //////////////////////////////////////////////////////////////*/

    /// @notice Submit a manifest update request for DAO review (model owner only)
    /// @param modelId       ID of the model to update
    /// @param newManifestCID New IPFS CID (bytes32) for the model manifest
    /// @return requestId    ID of the pending manifest update request
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

    /*//////////////////////////////////////////////////////////////
                APPROVE / REJECT MANIFEST UPDATE
    //////////////////////////////////////////////////////////////*/

    /// @notice DAO approves a pending manifest update
    function approveManifestUpdate(uint256 requestId) external onlyDAOAdmin {
        if (requestId >= manifestRequests.length) revert InvalidRequestId();

        ManifestUpdateRequest storage req = manifestRequests[requestId];
        if (req.processed) revert AlreadyProcessed();

        // Prevent approving updates for a model that has since been disabled
        if (modelDisabled[req.modelId]) revert ModelIsDisabled(req.modelId);

        models[req.modelId].manifestCID = req.newManifestCID;

        req.processed = true;
        req.approved = true;

        emit ManifestUpdated(requestId, req.modelId, req.newManifestCID);
    }

    /// @notice DAO rejects a pending manifest update (fee is retained)
    function rejectManifestUpdate(uint256 requestId) external onlyDAOAdmin {
        if (requestId >= manifestRequests.length) revert InvalidRequestId();

        ManifestUpdateRequest storage req = manifestRequests[requestId];
        if (req.processed) revert AlreadyProcessed();

        req.processed = true;
        req.approved = false;

        emit ManifestUpdateRejected(requestId);
    }

    /*//////////////////////////////////////////////////////////////
                            VIEW FUNCTIONS
    //////////////////////////////////////////////////////////////*/

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

    /// @notice Look up the model ID registered for a given task coordinator
    function getModelIdByTaskCoordinator(
        address taskCoordinator
    ) external view returns (bool exists, uint256 modelId) {
        uint256 val = _modelIdByTaskCoordinator[taskCoordinator];
        if (val == 0) return (false, 0);
        return (true, val - 1); // subtract 1 to convert back to 0-indexed modelId
    }

    /// @notice Look up the model ID registered for a given task auditor
    function getModelIdByTaskAuditor(
        address taskAuditor
    ) external view returns (bool exists, uint256 modelId) {
        uint256 val = _modelIdByTaskAuditor[taskAuditor];
        if (val == 0) return (false, 0);
        return (true, val - 1); // subtract 1 to convert back to 0-indexed modelId
    }

    /*//////////////////////////////////////////////////////////////
                        DAO ADMIN FUNCTIONS
    //////////////////////////////////////////////////////////////*/

    // ── Kill switch ────────────────────────────────────────────────────────

    /// @notice Immediately disable a model — blocks manifest updates and
    ///         any downstream contract that checks modelDisabled(modelId)
    function disableModel(uint256 modelId) external onlyDAOAdmin {
        if (modelId >= models.length) revert InvalidModelId();
        modelDisabled[modelId] = true;
        emit ModelDisabled(modelId);
    }

    /// @notice Re-enable a previously disabled model
    function enableModel(uint256 modelId) external onlyDAOAdmin {
        if (modelId >= models.length) revert InvalidModelId();
        modelDisabled[modelId] = false;
        emit ModelEnabled(modelId);
    }

    // ── Individual fee setters ─────────────────────────────────────────────

    /// @notice Update the open-source model registration fee
    function setOpenSourceFee(uint256 newFee) external onlyDAOAdmin {
        openSourceFee = newFee;
        emit OpenSourceFeeUpdated(newFee);
    }

    /// @notice Update the proprietary model registration fee
    function setProprietaryFee(uint256 newFee) external onlyDAOAdmin {
        proprietaryFee = newFee;
        emit ProprietaryFeeUpdated(newFee);
    }

    /// @notice Update the open-source manifest update fee
    function setOpenSourceUpdateFee(uint256 newFee) external onlyDAOAdmin {
        openSourceUpdateFee = newFee;
        emit OpenSourceUpdateFeeUpdated(newFee);
    }

    /// @notice Update the proprietary manifest update fee
    function setProprietaryUpdateFee(uint256 newFee) external onlyDAOAdmin {
        proprietaryUpdateFee = newFee;
        emit ProprietaryUpdateFeeUpdated(newFee);
    }

    // ── Combined setter (atomic governance) ────────────────────────────────

    /// @notice Atomically update all four protocol fees in a single transaction
    /// @dev Prefer this for governance proposals to avoid inconsistent fee states
    function setFees(
        uint256 _openSourceFee,
        uint256 _proprietaryFee,
        uint256 _openSourceUpdateFee,
        uint256 _proprietaryUpdateFee
    ) external onlyDAOAdmin {
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

    /// @notice Withdraw accumulated fees to a designated address
    function withdrawFees(address payable to) external onlyDAOAdmin {
        uint256 balance = address(this).balance;
        to.transfer(balance);
        emit FeesWithdrawn(to, balance);
    }

    // ── DAO admin transfer ─────────────────────────────────────────────────

    /// @notice Transfer DAO admin role (multisig / timelock migration path)
    /// @dev Emits DAOAdminUpdated so indexers can track governance handover
    function setDAOAdmin(address newAdmin) external onlyDAOAdmin {
        if (newAdmin == address(0)) revert ZeroAddress();
        address old = daoAdmin;
        daoAdmin = newAdmin;
        emit DAOAdminUpdated(old, newAdmin);
    }
}
