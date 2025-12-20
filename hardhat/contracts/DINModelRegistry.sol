// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title DIN Model Registry
/// @author InfiniteZero Foundation / Umer Majeed
/// @notice Registry for AI models in the Decentralized Intelligence Network
/// @dev Minimal, auditable, DAO-controlled primitive

interface IDinValidatorStake {
    function is_slasher_contract(
        address slasher_contract
    ) external view returns (bool);
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
        string manifestoCID
    );

    event ManifestoUpdated(uint256 indexed modelId, string newManifestoCID);

    event ProprietaryFeeUpdated(uint256 newFee);
    event FeesWithdrawn(address indexed to, uint256 amount);

    /*//////////////////////////////////////////////////////////////
                                STRUCTS
    //////////////////////////////////////////////////////////////*/
    struct Model {
        address owner;
        bool isOpenSource;
        string manifestoCID;
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
    /// @param manifestoCID IPFS CID containing model manifesto & logic pointers
    /// @param isOpenSource Whether the model is open-source or proprietary
    /// @return modelId Assigned model ID (array index)
    function registerModel(
        string calldata manifestoCID,
        address taskCoordinator,
        address taskAuditor,
        bool isOpenSource
    ) external payable returns (uint256 modelId) {
        if (!isOpenSource && msg.value < proprietaryFee) {
            revert InsufficientProprietaryFee();
        }

        modelId = models.length;

        require(
            dinValidatorStake.is_slasher_contract(taskCoordinator),
            "Task Coordinator is not a slasher"
        );
        require(
            dinValidatorStake.is_slasher_contract(taskAuditor),
            "Task Auditor is not a slasher"
        );

        if (_modelIdByTaskCoordinator[taskCoordinator] != 0)
            revert TaskCoordinatorAlreadyRegistered();
        if (_modelIdByTaskAuditor[taskAuditor] != 0)
            revert TaskAuditorAlreadyRegistered();

        models.push(
            Model({
                owner: msg.sender,
                isOpenSource: isOpenSource,
                manifestoCID: manifestoCID,
                taskCoordinator: taskCoordinator,
                taskAuditor: taskAuditor,
                createdAt: block.timestamp
            })
        );

        // adding 1 to avoid 0-indexed default value issue
        _modelIdByTaskCoordinator[taskCoordinator] = modelId + 1;
        _modelIdByTaskAuditor[taskAuditor] = modelId + 1;

        emit ModelRegistered(modelId, msg.sender, isOpenSource, manifestoCID);
    }

    /*//////////////////////////////////////////////////////////////
                          MODEL MAINTENANCE
    //////////////////////////////////////////////////////////////*/

    /// @notice Update manifesto CID (owner only)
    function updateManifesto(
        uint256 modelId,
        string calldata newManifestoCID
    ) external onlyModelOwner(modelId) {
        models[modelId].manifestoCID = newManifestoCID;

        emit ManifestoUpdated(modelId, newManifestoCID);
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
            string memory manifestoCID,
            uint256 createdAt
        )
    {
        if (modelId >= models.length) revert InvalidModelId();
        Model storage m = models[modelId];
        return (m.owner, m.isOpenSource, m.manifestoCID, m.createdAt);
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
