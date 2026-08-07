// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken} from "../src/DinToken.sol";

contract DinTokenTest is Test {
    DinToken token;
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");

    function setUp() public {
        DinToken impl = new DinToken();
        token = DinToken(
            address(
                new TransparentUpgradeableProxy(
                    address(impl),
                    address(this),
                    abi.encodeCall(DinToken.initialize, ())
                )
            )
        );
        // Set the test contract as coordinator so we can mint directly in tests
        token.setCoordinator(address(this));
    }

    // ── burn() ────────────────────────────────────────────────────────────────

    function test_burn_decreasesTotalSupply() public {
        token.mint(alice, 1000e18);
        uint256 supplyBefore = token.totalSupply();

        vm.prank(alice);
        token.burn(400e18);

        assertEq(token.totalSupply(), supplyBefore - 400e18);
        assertEq(token.balanceOf(alice), 600e18);
    }

    function test_burn_revertsOnInsufficientBalance() public {
        token.mint(alice, 100e18);

        vm.prank(alice);
        vm.expectRevert();
        token.burn(101e18);
    }

    function test_burn_emitsTokensBurnedEvent() public {
        token.mint(alice, 500e18);

        vm.expectEmit(true, false, false, true, address(token));
        emit DinToken.TokensBurned(alice, 200e18);
        vm.prank(alice);
        token.burn(200e18);
    }

    function test_burn_callableByAnyHolder() public {
        token.mint(alice, 50e18);
        token.mint(bob, 50e18);

        vm.prank(alice);
        token.burn(10e18);

        vm.prank(bob);
        token.burn(10e18);

        assertEq(token.totalSupply(), 80e18);
    }

    function test_burn_doesNotRequireSpecialRole() public {
        // Neither coordinator nor owner — just a random holder
        address holder = makeAddr("holder");
        token.mint(holder, 1e18);

        vm.prank(holder);
        token.burn(1e18); // must not revert

        assertEq(token.balanceOf(holder), 0);
    }

    function test_burn_fullBalance_setsBalanceToZero() public {
        token.mint(alice, 1e18);

        vm.prank(alice);
        token.burn(1e18);

        assertEq(token.balanceOf(alice), 0);
        assertEq(token.totalSupply(), 0);
    }
}
