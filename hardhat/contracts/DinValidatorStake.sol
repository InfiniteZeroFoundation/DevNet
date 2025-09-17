// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract DinValidatorStake is Ownable {
    
    IERC20 public dintoken;
    uint256 public constant MIN_STAKE = 1000000;
    mapping(address => bool) public slasher_contracts;

    address public dincoordinator_address;

    struct ValidatorInfo {
        uint256 stake;
        bool registered;
        bool blacklisted;
    }

    event ValidatorStaked(address indexed validator, uint256 amount);
    event ValidatorSlashed(address indexed validator, uint256 amount);
    event ValidatorUnstaked(address indexed validator, uint256 amount);

    mapping(address => ValidatorInfo) public validators;

    constructor(address dintoken_address, address _dincoordinator_address) Ownable(msg.sender) {
        dintoken = IERC20(dintoken_address);
        dincoordinator_address = _dincoordinator_address;
    }

    modifier only_dincoordinator() {
        require(msg.sender == dincoordinator_address, "Not DINCoordinator");
        _;
    }

    function stake(uint256 amount) external {
        require(amount >= MIN_STAKE, "Insufficient stake");
        require(!validators[msg.sender].blacklisted, "Blacklisted");

        dintoken.transferFrom(msg.sender, address(this), amount);
        validators[msg.sender].stake += amount;
        validators[msg.sender].registered = true;

        emit ValidatorStaked(msg.sender, amount);
    }

    function add_slasher_contract(address _slasher_contract) external only_dincoordinator {
        require(slasher_contracts[_slasher_contract] == false, "Slasher contract already added");
        require(_slasher_contract != address(0), "Invalid slasher contract");
        slasher_contracts[_slasher_contract] = true;
    }

    function remove_slasher_contract(address _slasher_contract) external only_dincoordinator {
        require(slasher_contracts[_slasher_contract] == true, "Slasher contract not added");
        require(_slasher_contract != address(0), "Invalid slasher contract");
        slasher_contracts[_slasher_contract] = false;
    }

    modifier only_slasher_contract() {
        require(slasher_contracts[msg.sender], "Not a slasher contract");
        _;
    }

    function slash(address validator, uint256 amount) external only_slasher_contract {
        require(amount >= MIN_STAKE, "Insufficient stake to be slashed");
        require(validators[validator].registered, "Not a validator");
        require(validators[validator].stake >= amount, "Not enough stake");

        validators[validator].stake -= amount;
        // validators[validator].blacklisted = true;
        if (validators[validator].stake < MIN_STAKE) {
            validators[validator].registered = false;
        }

        emit ValidatorSlashed(validator, amount);
        // Optionally burn or redistribute slashed tokens
    }

    function unstake(uint256 amount) external {
        require(validators[msg.sender].stake >= amount, "Insufficient stake");

        validators[msg.sender].stake -= amount;
        dintoken.transfer(msg.sender, amount);

        if (validators[msg.sender].stake < MIN_STAKE) {
            validators[msg.sender].registered = false;
        }

        emit ValidatorUnstaked(msg.sender, amount);
    }

    function isValidatorStaked(address validator) public view returns (bool) {
        return validators[validator].stake >= MIN_STAKE;
    }

    function getStake(address validator) public view returns (uint256) {
        return validators[validator].stake;
    }

    function is_slasher_contract(address slasher_contract) public view returns (bool) {
        return slasher_contracts[slasher_contract];
    }


}