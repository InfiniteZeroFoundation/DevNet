// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

import {DinTreasury} from "../src/DinTreasury.sol";

/// @dev Minimal ERC20 to prove DinTreasury is asset-agnostic.
contract MockERC20 is ERC20 {
    constructor() ERC20("Mock", "MCK") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

contract DinTreasuryTest is Test {
    DinTreasury treasury;
    MockERC20 mockToken;

    address alice = makeAddr("alice");

    function setUp() public {
        DinTreasury impl = new DinTreasury();
        treasury = DinTreasury(
            payable(
                address(
                    new TransparentUpgradeableProxy(
                        address(impl),
                        address(this),
                        abi.encodeCall(DinTreasury.initialize, ())
                    )
                )
            )
        );

        mockToken = new MockERC20();
    }

    // ── receive() ────────────────────────────────────────────────────────────

    function test_receive_emitsEthReceivedEvent() public {
        vm.deal(alice, 1 ether);
        vm.expectEmit(true, false, false, true, address(treasury));
        emit DinTreasury.EthReceived(alice, 1 ether);
        vm.prank(alice);
        (bool ok, ) = address(treasury).call{value: 1 ether}("");
        assertTrue(ok);
    }

    function test_receive_acceptsEth() public {
        vm.deal(alice, 1 ether);
        vm.prank(alice);
        (bool ok, ) = address(treasury).call{value: 1 ether}("");
        assertTrue(ok);
        assertEq(address(treasury).balance, 1 ether);
    }

    // ── withdrawETH ──────────────────────────────────────────────────────────

    function test_withdrawETH_onlyOwner_revertsForNonOwner() public {
        vm.deal(address(treasury), 1 ether);
        vm.prank(alice);
        vm.expectRevert();
        treasury.withdrawETH(payable(alice), 1 ether);
    }

    function test_withdrawETH_revertsOnInsufficientBalance() public {
        vm.deal(address(treasury), 0.5 ether);
        vm.expectRevert(DinTreasury.InsufficientBalance.selector);
        treasury.withdrawETH(payable(alice), 1 ether);
    }

    function test_withdrawETH_revertsOnZeroAddress() public {
        vm.deal(address(treasury), 1 ether);
        vm.expectRevert(DinTreasury.InvalidAddress.selector);
        treasury.withdrawETH(payable(address(0)), 1 ether);
    }

    function test_withdrawETH_transfersCorrectAmount() public {
        vm.deal(address(treasury), 2 ether);
        uint256 aliceBefore = alice.balance;

        vm.expectEmit(true, false, false, true, address(treasury));
        emit DinTreasury.EthWithdrawn(alice, 1 ether);
        treasury.withdrawETH(payable(alice), 1 ether);

        assertEq(alice.balance, aliceBefore + 1 ether);
        assertEq(address(treasury).balance, 1 ether);
    }

    // ── withdrawERC20 ────────────────────────────────────────────────────────

    function test_withdrawERC20_onlyOwner_revertsForNonOwner() public {
        mockToken.mint(address(treasury), 100e18);
        vm.prank(alice);
        vm.expectRevert();
        treasury.withdrawERC20(address(mockToken), alice, 100e18);
    }

    function test_withdrawERC20_revertsOnZeroToken() public {
        vm.expectRevert(DinTreasury.InvalidAddress.selector);
        treasury.withdrawERC20(address(0), alice, 1);
    }

    function test_withdrawERC20_revertsOnZeroRecipient() public {
        vm.expectRevert(DinTreasury.InvalidAddress.selector);
        treasury.withdrawERC20(address(mockToken), address(0), 1);
    }

    function test_withdrawERC20_transfersTokensToRecipient() public {
        mockToken.mint(address(treasury), 500e18);

        vm.expectEmit(true, true, false, true, address(treasury));
        emit DinTreasury.ERC20Withdrawn(address(mockToken), alice, 500e18);
        treasury.withdrawERC20(address(mockToken), alice, 500e18);

        assertEq(mockToken.balanceOf(alice), 500e18);
        assertEq(mockToken.balanceOf(address(treasury)), 0);
    }

    function test_withdrawERC20_partialWithdrawal() public {
        mockToken.mint(address(treasury), 1000e18);
        treasury.withdrawERC20(address(mockToken), alice, 300e18);

        assertEq(mockToken.balanceOf(alice), 300e18);
        assertEq(mockToken.balanceOf(address(treasury)), 700e18);
    }
}
