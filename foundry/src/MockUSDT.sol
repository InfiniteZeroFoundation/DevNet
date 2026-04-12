// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockUSDT is ERC20 {
    constructor(uint256 initialSupply) ERC20("MockUSDT", "USDT") {
        _mint(msg.sender, initialSupply);
    }

    // Override decimals to 6 (like real USDT)
    function decimals() public view virtual override returns (uint8) {
        return 6;
    }
}
