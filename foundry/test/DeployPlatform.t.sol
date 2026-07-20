// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test, console} from "forge-std/Test.sol";
import {Upgrades, Options} from "@openzeppelin/foundry-upgrades/Upgrades.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DINModelRegistry} from "../src/DINModelRegistry.sol";

import {DinTokenV2} from "../src/upgrade/DinTokenV2.sol";

import {DinCoordinatorV2} from "../src/upgrade/DinCoordinatorV2.sol";
import {DinValidatorStakeV2} from "../src/upgrade/DinValidatorStakeV2.sol";
import {DINModelRegistryV2} from "../src/upgrade/DINModelRegistryV2.sol";

interface IOwnable {
    function owner() external view returns (address);
}

/// @dev Minimal ownable stub used as a stand-in for DINTaskCoordinator /
///      DINTaskAuditor in tests that call requestModelRegistration, which
///      verifies IOwnable(taskCoordinator).owner() == msg.sender.
contract MockTaskContract {
    address private _owner;

    constructor(address owner_) {
        _owner = owner_;
    }

    function owner() external view returns (address) {
        return _owner;
    }
}

// ─── Shared platform fixture ──────────────────────────────────────────────────

struct Platform {
    address deployer;
    address user;
    address other;
    DinToken dinToken;
    DinCoordinator dinCoordinator;
    DinValidatorStake dinValidatorStake;
    DINModelRegistry dinModelRegistry;
}

/// @dev Base contract providing deployPlatform() and mintDin() helpers.
///      All test contracts inherit from this so they share the cheatcode VM.
abstract contract PlatformTest is Test {
    address internal constant USER = address(0xBEEF);
    address internal constant OTHER = address(0xCAFE);

    function _deployPlatform() internal returns (Platform memory p) {
        p.deployer = address(this);
        p.user = USER;
        p.other = OTHER;

        address tokenProxy = Upgrades.deployTransparentProxy(
            "DinToken.sol:DinToken",
            address(this),
            abi.encodeCall(DinToken.initialize, ())
        );
        p.dinToken = DinToken(tokenProxy);

        address coordinatorProxy = Upgrades.deployTransparentProxy(
            "DinCoordinator.sol:DinCoordinator",
            address(this),
            abi.encodeCall(DinCoordinator.initialize, (tokenProxy))
        );
        p.dinCoordinator = DinCoordinator(payable(coordinatorProxy));

        p.dinToken.setCoordinator(coordinatorProxy);

        address stakeProxy = Upgrades.deployTransparentProxy(
            "DinValidatorStake.sol:DinValidatorStake",
            address(this),
            abi.encodeCall(
                DinValidatorStake.initialize,
                (tokenProxy, coordinatorProxy)
            )
        );
        p.dinValidatorStake = DinValidatorStake(stakeProxy);

        p.dinCoordinator.updateValidatorStakeContract(stakeProxy);

        address registryProxy = Upgrades.deployTransparentProxy(
            "DINModelRegistry.sol:DINModelRegistry",
            address(this),
            abi.encodeCall(DINModelRegistry.initialize, (stakeProxy))
        );
        p.dinModelRegistry = DINModelRegistry(registryProxy);
    }

    function _mintDin(
        DinCoordinator coordinator,
        address user_,
        uint256 ethAmount
    ) internal {
        vm.deal(user_, ethAmount);
        vm.prank(user_);
        coordinator.depositAndMint{value: ethAmount}();
    }
}

// ─── §3.2 Proxy wiring ────────────────────────────────────────────────────────

contract ProxyWiringTest is PlatformTest {
    Platform p;

    function setUp() public {
        p = _deployPlatform();
    }

    function test_dinToken_coordinatorWired() public view {
        assertEq(p.dinToken.coordinator(), address(p.dinCoordinator));
    }

    function test_dinCoordinator_tokenWired() public view {
        assertEq(address(p.dinCoordinator.dinToken()), address(p.dinToken));
    }

    function test_dinCoordinator_stakeContractWired() public view {
        assertEq(
            address(p.dinCoordinator.dinValidatorStakeContract()),
            address(p.dinValidatorStake)
        );
    }

    function test_dinValidatorStake_tokenWired() public view {
        assertEq(address(p.dinValidatorStake.DIN_TOKEN()), address(p.dinToken));
    }

    function test_dinValidatorStake_coordinatorWired() public view {
        assertEq(
            p.dinValidatorStake.DIN_COORDINATOR(),
            address(p.dinCoordinator)
        );
    }

    function test_allProxyAdminsOwnedByDeployer() public view {
        // OZ v5 TransparentUpgradeableProxy deploys one ProxyAdmin per proxy,
        // so admin addresses differ. The invariant is that each admin's owner
        // is the deployer (address(this) in the test context).
        assertEq(
            IOwnable(Upgrades.getAdminAddress(address(p.dinToken))).owner(),
            address(this)
        );
        assertEq(
            IOwnable(Upgrades.getAdminAddress(address(p.dinCoordinator)))
                .owner(),
            address(this)
        );
        assertEq(
            IOwnable(Upgrades.getAdminAddress(address(p.dinValidatorStake)))
                .owner(),
            address(this)
        );
        assertEq(
            IOwnable(Upgrades.getAdminAddress(address(p.dinModelRegistry)))
                .owner(),
            address(this)
        );
    }

    function test_depositAndMint_mintsDinViaProxy() public {
        uint256 eth = 0.01 ether;
        _mintDin(p.dinCoordinator, p.user, eth);
        assertGt(p.dinToken.balanceOf(p.user), 0);
    }
}

// ─── §3.4 Re-initializer protection ──────────────────────────────────────────

contract ReInitializerProtectionTest is PlatformTest {
    Platform p;

    function setUp() public {
        p = _deployPlatform();
    }

    // Proxy cannot be initialized a second time
    function test_proxy_rejectsDoubleInitialize_DinToken() public {
        vm.expectRevert();
        p.dinToken.initialize();
    }

    function test_proxy_rejectsDoubleInitialize_DinCoordinator() public {
        vm.expectRevert();
        p.dinCoordinator.initialize(address(p.dinToken));
    }

    function test_proxy_rejectsDoubleInitialize_DinValidatorStake() public {
        vm.expectRevert();
        p.dinValidatorStake.initialize(
            address(p.dinToken),
            address(p.dinCoordinator)
        );
    }

    function test_proxy_rejectsDoubleInitialize_DINModelRegistry() public {
        vm.expectRevert();
        p.dinModelRegistry.initialize(address(p.dinValidatorStake));
    }

    // Implementation contract cannot be initialized directly (_disableInitializers)
    function test_impl_rejectsDirectInitialize_DinToken() public {
        DinToken impl = new DinToken();
        vm.expectRevert();
        impl.initialize();
    }

    function test_impl_rejectsDirectInitialize_DinCoordinator() public {
        DinCoordinator impl = new DinCoordinator();
        vm.expectRevert();
        impl.initialize(address(1));
    }

    function test_impl_rejectsDirectInitialize_DinValidatorStake() public {
        DinValidatorStake impl = new DinValidatorStake();
        vm.expectRevert();
        impl.initialize(address(1), address(2));
    }

    function test_impl_rejectsDirectInitialize_DINModelRegistry() public {
        DINModelRegistry impl = new DINModelRegistry();
        vm.expectRevert();
        impl.initialize(address(1));
    }
}

// ─── §3.4 DinToken upgrade ────────────────────────────────────────────────────

contract DinTokenUpgradeTest is PlatformTest {
    Platform p;

    function setUp() public {
        p = _deployPlatform();
    }

    function test_preservesBalancesAndWiringAcrossUpgrade() public {
        _mintDin(p.dinCoordinator, p.user, 0.01 ether);
        uint256 balBefore = p.dinToken.balanceOf(p.user);

        Options memory opts;
        opts.referenceContract = "DinToken.sol:DinToken";
        Upgrades.upgradeProxy(
            address(p.dinToken),
            "DinTokenV2.sol:DinTokenV2",
            "",
            opts
        );
        DinTokenV2 upgraded = DinTokenV2(address(p.dinToken));

        assertEq(upgraded.coordinator(), address(p.dinCoordinator));
        assertEq(upgraded.balanceOf(p.user), balBefore);
        assertEq(upgraded.version(), 2);

        // Minting still works via the coordinator after upgrade
        _mintDin(p.dinCoordinator, p.user, 0.001 ether);
        assertGt(upgraded.balanceOf(p.user), balBefore);
    }

    function test_keepsMintRestrictedToCoordinatorAfterUpgrade() public {
        Options memory opts;
        opts.referenceContract = "DinToken.sol:DinToken";
        Upgrades.upgradeProxy(
            address(p.dinToken),
            "DinTokenV2.sol:DinTokenV2",
            "",
            opts
        );

        vm.expectRevert(DinToken.Unauthorized.selector);
        vm.prank(p.user);
        p.dinToken.mint(p.user, 1);
    }

    function test_keepsCoordinatorSetupRestrictedToOwnerAfterUpgrade() public {
        Options memory opts;
        opts.referenceContract = "DinToken.sol:DinToken";
        Upgrades.upgradeProxy(
            address(p.dinToken),
            "DinTokenV2.sol:DinTokenV2",
            "",
            opts
        );

        vm.expectRevert();
        vm.prank(p.other);
        p.dinToken.setCoordinator(address(p.dinCoordinator));
    }
}

// ─── §3.4 DinCoordinator upgrade ─────────────────────────────────────────────

contract DinCoordinatorUpgradeTest is PlatformTest {
    Platform p;

    function setUp() public {
        p = _deployPlatform();
    }

    function test_preservesExchangeRateAndTokenWiringAcrossUpgrade() public {
        uint256 newRate = 2_000_000 * 1e18;
        p.dinCoordinator.updateDinPerEth(newRate);
        _mintDin(p.dinCoordinator, p.user, 0.01 ether);
        uint256 balBefore = p.dinToken.balanceOf(p.user);

        Options memory opts;
        opts.referenceContract = "DinCoordinator.sol:DinCoordinator";
        Upgrades.upgradeProxy(
            address(p.dinCoordinator),
            "DinCoordinatorV2.sol:DinCoordinatorV2",
            "",
            opts
        );
        DinCoordinatorV2 upgraded = DinCoordinatorV2(
            payable(address(p.dinCoordinator))
        );

        assertEq(address(upgraded.dinToken()), address(p.dinToken));
        assertEq(upgraded.dinPerEth(), newRate);
        assertEq(upgraded.version(), 2);
        assertEq(p.dinToken.balanceOf(p.user), balBefore);
    }

    function test_keepsOwnerOnlyFunctionsRestrictedAfterUpgrade() public {
        Options memory opts;
        opts.referenceContract = "DinCoordinator.sol:DinCoordinator";
        Upgrades.upgradeProxy(
            address(p.dinCoordinator),
            "DinCoordinatorV2.sol:DinCoordinatorV2",
            "",
            opts
        );

        vm.expectRevert();
        vm.prank(p.other);
        p.dinCoordinator.updateDinPerEth(1);
    }

    function test_keepsSlasherManagementWiredToStakeContractAfterUpgrade()
        public
    {
        address slasher = address(0xDEAD);
        p.dinCoordinator.addSlasherContract(slasher);
        assertTrue(p.dinValidatorStake.isSlasherContract(slasher));

        Options memory opts;
        opts.referenceContract = "DinCoordinator.sol:DinCoordinator";
        Upgrades.upgradeProxy(
            address(p.dinCoordinator),
            "DinCoordinatorV2.sol:DinCoordinatorV2",
            "",
            opts
        );

        assertTrue(p.dinValidatorStake.isSlasherContract(slasher));
    }
}

// ─── §3.4 DinValidatorStake upgrade ──────────────────────────────────────────

contract DinValidatorStakeUpgradeTest is PlatformTest {
    uint256 constant MIN_STAKE = 10 * 1e18;
    uint256 constant STAKE_DEPOSIT_ETH = 0.01 ether;

    Platform p;

    function setUp() public {
        p = _deployPlatform();

        _mintDin(p.dinCoordinator, p.user, STAKE_DEPOSIT_ETH);
        vm.prank(p.user);
        p.dinToken.approve(address(p.dinValidatorStake), type(uint256).max);
    }

    function test_preservesStakeBalancesAcrossUpgrade() public {
        vm.prank(p.user);
        p.dinValidatorStake.stake(MIN_STAKE);
        uint256 stakeBefore = p.dinValidatorStake.getStake(p.user);

        Options memory opts;
        opts.referenceContract = "DinValidatorStake.sol:DinValidatorStake";
        Upgrades.upgradeProxy(
            address(p.dinValidatorStake),
            "DinValidatorStakeV2.sol:DinValidatorStakeV2",
            "",
            opts
        );
        DinValidatorStakeV2 upgraded = DinValidatorStakeV2(
            address(p.dinValidatorStake)
        );

        assertEq(upgraded.getStake(p.user), stakeBefore);
        assertTrue(upgraded.isValidatorActive(p.user));
        assertEq(upgraded.version(), 2);
    }

    function test_keepsSlasherRegistrationRestrictedToCoordinatorAfterUpgrade()
        public
    {
        Options memory opts;
        opts.referenceContract = "DinValidatorStake.sol:DinValidatorStake";
        Upgrades.upgradeProxy(
            address(p.dinValidatorStake),
            "DinValidatorStakeV2.sol:DinValidatorStakeV2",
            "",
            opts
        );

        vm.expectRevert(DinValidatorStake.NotDINCoordinator.selector);
        vm.prank(p.other);
        p.dinValidatorStake.addSlasherContract(address(0xABCD));
    }

    function test_keepsBlacklistControlWithOwnerAfterUpgrade() public {
        vm.prank(p.user);
        p.dinValidatorStake.stake(MIN_STAKE);

        Options memory opts;
        opts.referenceContract = "DinValidatorStake.sol:DinValidatorStake";
        Upgrades.upgradeProxy(
            address(p.dinValidatorStake),
            "DinValidatorStakeV2.sol:DinValidatorStakeV2",
            "",
            opts
        );

        p.dinValidatorStake.blacklistValidator(p.user);
        assertFalse(p.dinValidatorStake.isValidatorActive(p.user));

        vm.expectRevert();
        vm.prank(p.other);
        p.dinValidatorStake.unblacklistValidator(p.user);
    }
}

// ─── §3.4 DINModelRegistry upgrade ───────────────────────────────────────────

contract DINModelRegistryUpgradeTest is PlatformTest {
    Platform p;

    // Minimal slasher stubs — coordinator and auditor must be registered slashers
    address taskCoordinator;
    address taskAuditor;

    function setUp() public {
        p = _deployPlatform();

        // Deploy mock task contracts owned by p.user — requestModelRegistration
        // calls IOwnable(taskCoordinator).owner() and requires it equals msg.sender.
        taskCoordinator = address(new MockTaskContract(p.user));
        taskAuditor = address(new MockTaskContract(p.user));
        p.dinCoordinator.addSlasherContract(taskCoordinator);
        p.dinCoordinator.addSlasherContract(taskAuditor);
    }

    function test_preservesFeeSettingsAndModelStateAcrossUpgrade() public {
        uint256 newFee = 42;
        p.dinModelRegistry.setProprietaryFee(newFee);

        uint256 fee = p.dinModelRegistry.proprietaryFee();
        bytes32 manifestCID = keccak256("manifest-v1");
        vm.deal(p.user, fee);
        vm.prank(p.user);
        p.dinModelRegistry.requestModelRegistration{value: fee}(
            manifestCID,
            taskCoordinator,
            taskAuditor,
            false
        );
        p.dinModelRegistry.approveModel(0);

        Options memory opts;
        opts.referenceContract = "DINModelRegistry.sol:DINModelRegistry";
        Upgrades.upgradeProxy(
            address(p.dinModelRegistry),
            "DINModelRegistryV2.sol:DINModelRegistryV2",
            "",
            opts
        );
        DINModelRegistryV2 upgraded = DINModelRegistryV2(
            address(p.dinModelRegistry)
        );

        assertEq(upgraded.proprietaryFee(), newFee);
        assertEq(upgraded.totalModels(), 1);
        assertEq(upgraded.version(), 2);

        (address owner, , , , , ) = upgraded.getModel(0);
        assertEq(owner, p.user);
    }

    function test_keepsOwnerOnlyGovernanceRestrictedAfterUpgrade() public {
        Options memory opts;
        opts.referenceContract = "DINModelRegistry.sol:DINModelRegistry";
        Upgrades.upgradeProxy(
            address(p.dinModelRegistry),
            "DINModelRegistryV2.sol:DINModelRegistryV2",
            "",
            opts
        );

        vm.expectRevert();
        vm.prank(p.other);
        p.dinModelRegistry.setProprietaryFee(1);
    }

    function test_keepsPendingRequestsReadableAfterUpgrade() public {
        uint256 fee = p.dinModelRegistry.openSourceFee();
        vm.deal(p.user, fee);
        vm.prank(p.user);
        p.dinModelRegistry.requestModelRegistration{value: fee}(
            keccak256("manifest-pending"),
            taskCoordinator,
            taskAuditor,
            true
        );

        Options memory opts;
        opts.referenceContract = "DINModelRegistry.sol:DINModelRegistry";
        Upgrades.upgradeProxy(
            address(p.dinModelRegistry),
            "DINModelRegistryV2.sol:DINModelRegistryV2",
            "",
            opts
        );

        assertEq(p.dinModelRegistry.totalModelRequests(), 1);

        (address requester, , , , , , bool processed, , ) = p
            .dinModelRegistry
            .modelRequests(0);
        assertEq(requester, p.user);
        assertFalse(processed);

        p.dinModelRegistry.approveModel(0);
        assertEq(p.dinModelRegistry.totalModels(), 1);
    }
}
