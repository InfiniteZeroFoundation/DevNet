// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title DIN Model Registry
/// @author InfiniteZero Foundation / Umer Majeed
/// @notice Registry for AI models in the Decentralized Intelligence Network
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
    error NotModelOwner();
    error InvalidModelId();
    error InsufficientProprietaryFee();
    error TaskCoordinatorAlreadyRegistered();
    error TaskAuditorAlreadyRegistered();

    /*//////////////////////////////////////////////////////////////
                                EVENTS
    //////////////////////////////////////////////////////////////*/
    event ModelRegistered(
        uint256 indexed modelId,
        address indexed owner,
        bool isOpenSource,
        bytes32 manifestCID
    );

    event ManifestUpdated(uint256 indexed modelId, bytes32 newManifestCID);

    event ProprietaryFeeUpdated(uint256 newFee);
    event FeesWithdrawn(address indexed to, uint256 amount);

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

    /*//////////////////////////////////////////////////////////////
                            STATE VARIABLES
    //////////////////////////////////////////////////////////////*/
    address public immutable daoAdmin;
    uint256 public proprietaryFee;
    IDinValidatorStake public dinValidatorStake;

    Model[] private models;

    mapping(address => uint256) private _modelIdByTaskCoordinator; // Stores modelId + 1
    mapping(address => uint256) private _modelIdByTaskAuditor; // Stores modelId + 1

    /*//////////////////////////////////////////////////////////////
                              MODIFIERS
    //////////////////////////////////////////////////////////////*/
    modifier onlyModelOwner(uint256 modelId) {
        if (modelId >= models.length) revert InvalidModelId();
        if (models[modelId].owner != msg.sender) revert NotModelOwner();
        _;
    }

    /*//////////////////////////////////////////////////////////////
                              CONSTRUCTOR
    //////////////////////////////////////////////////////////////*/
    constructor(address _dinValidatorStake) {
        daoAdmin = msg.sender; // DIN DAO representative
        proprietaryFee = 0.01 ether;
        dinValidatorStake = IDinValidatorStake(_dinValidatorStake);
    }

    /*//////////////////////////////////////////////////////////////
                          MODEL REGISTRATION
    //////////////////////////////////////////////////////////////*/

    /// @notice Register a new AI model
    /// @param manifestCID IPFS CID containing model manifest & logic pointers
    /// @param isOpenSource Whether the model is open-source or proprietary
    /// @return modelId Assigned model ID (array index)
    function registerModel(
        bytes32 manifestCID,
        address taskCoordinator,
        address taskAuditor,
        bool isOpenSource
    ) external payable returns (uint256 modelId) {
        if (!isOpenSource && msg.value < proprietaryFee) {
            revert InsufficientProprietaryFee();
        }

        modelId = models.length;

        require(
            dinValidatorStake.isSlasherContract(taskCoordinator),
            "Task Coordinator is not a slasher"
        );
        require(
            dinValidatorStake.isSlasherContract(taskAuditor),
            "Task Auditor is not a slasher"
        );

        require(
            taskCoordinator != taskAuditor,
            "Task Coordinator and Task Auditor cannot be the same"
        );

        require(
            taskCoordinator != msg.sender,
            "Task Coordinator cannot be the model owner"
        );

        require(
            taskAuditor != msg.sender,
            "Task Auditor cannot be the model owner"
        );

        require(
            IOwnable(taskCoordinator).owner() == msg.sender,
            "Task Coordinator is not owned by the model owner"
        );

        require(
            IOwnable(taskAuditor).owner() == msg.sender,
            "Task Auditor is not owned by the model owner"
        );

        if (_modelIdByTaskCoordinator[taskCoordinator] != 0)
            revert TaskCoordinatorAlreadyRegistered();
        if (_modelIdByTaskAuditor[taskAuditor] != 0)
            revert TaskAuditorAlreadyRegistered();

        models.push(
            Model({
                owner: msg.sender,
                isOpenSource: isOpenSource,
                manifestCID: manifestCID,
                taskCoordinator: taskCoordinator,
                taskAuditor: taskAuditor,
                createdAt: block.timestamp
            })
        );

        // adding 1 to avoid 0-indexed default value issue

        require(
            _modelIdByTaskCoordinator[taskCoordinator] == 0,
            "Task Coordinator already registered"
        );
        require(
            _modelIdByTaskAuditor[taskAuditor] == 0,
            "Task Auditor already registered"
        );
        _modelIdByTaskCoordinator[taskCoordinator] = modelId + 1;
        _modelIdByTaskAuditor[taskAuditor] = modelId + 1;

        emit ModelRegistered(modelId, msg.sender, isOpenSource, manifestCID);
    }

    /*//////////////////////////////////////////////////////////////
                          MODEL MAINTENANCE
    //////////////////////////////////////////////////////////////*/

    /// @notice Update manifest CID (owner only)
    function updateManifest(
        uint256 modelId,
        bytes32 newManifestCID
    ) external onlyModelOwner(modelId) {
        models[modelId].manifestCID = newManifestCID;

        emit ManifestUpdated(modelId, newManifestCID);
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
            bytes32 manifestoCID,
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

    function getModelIdByTaskCoordinator(
        address taskCoordinator
    ) external view returns (bool exists, uint256 modelId) {
        uint256 val = _modelIdByTaskCoordinator[taskCoordinator];
        if (val == 0) {
            return (false, 0);
        }
        // subtract 1 to convert back to 0-indexed modelId
        return (true, val - 1);
    }

    function getModelIdByTaskAuditor(
        address taskAuditor
    ) external view returns (bool exists, uint256 modelId) {
        uint256 val = _modelIdByTaskAuditor[taskAuditor];
        if (val == 0) {
            return (false, 0);
        }
        // subtract 1 to convert back to 0-indexed modelId
        return (true, val - 1);
    }

    /*//////////////////////////////////////////////////////////////
                        DAO ADMIN FUNCTIONS
    //////////////////////////////////////////////////////////////*/

    /// @notice Update proprietary model network fee
    function setProprietaryFee(uint256 newFee) external {
        require(msg.sender == daoAdmin, "Only DAO admin");
        proprietaryFee = newFee;
        emit ProprietaryFeeUpdated(newFee);
    }

    /// @notice Withdraw accumulated fees
    function withdrawFees(address payable to) external {
        require(msg.sender == daoAdmin, "Only DAO admin");
        uint256 balance = address(this).balance;
        to.transfer(balance);
        emit FeesWithdrawn(to, balance);
    }
}
