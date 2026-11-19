// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

// Deploys the platform, then takes one model from registration to local-model submissions in
// GI 1, so an indexer has platform and task-contract events to read. Anvil accounts only:
//   forge script script/NuthatchSpike.s.sol --rpc-url http://127.0.0.1:8545 --sig "spike()" --broadcast --unlocked

import {DeployPlatform} from "./DeployPlatform.s.sol";
import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DINModelRegistry} from "../src/DINModelRegistry.sol";
import {DINTaskCoordinator} from "../src/DINTaskCoordinator.sol";
import {DINTaskAuditor} from "../src/DINTaskAuditor.sol";

contract NuthatchSpike is DeployPlatform {
    string constant MNEMONIC = "test test test test test test test test test test test junk";
    uint256 constant GI = 1;
    uint256 constant POOL = 10_000 ether;

    function account(uint32 i) internal pure returns (address) {
        return vm.addr(vm.deriveKey(MNEMONIC, i));
    }

    function stakeAs(address who, DinCoordinator coordinator, DinToken token, DinValidatorStake stake) internal {
        vm.startBroadcast(who);
        coordinator.depositAndMint{value: 0.001 ether}();
        token.approve(address(stake), type(uint256).max);
        stake.stake(10 ether);
        vm.stopBroadcast();
    }

    function spike() external {
        address admin = account(0);
        address modelOwner = account(1);
        if (block.chainid != 1337) for (uint32 i = 0; i < 14; i++) vm.deal(account(i), 100 ether);
        Deployment memory d = deploy(readTokenomics(), admin);
        if (block.chainid == 1337) _writeDeployments(d, admin);

        DinToken token = DinToken(d.dinToken);
        DinCoordinator coordinator = DinCoordinator(d.dinCoordinator);
        DinValidatorStake stake = DinValidatorStake(d.dinValidatorStake);
        DINModelRegistry registry = DINModelRegistry(d.dinModelRegistry);

        vm.startBroadcast(modelOwner);
        DINTaskCoordinator tc = new DINTaskCoordinator(address(stake), 0);
        DINTaskAuditor ta = new DINTaskAuditor(address(stake), address(tc), 0, address(registry));
        tc.setDINTaskAuditorContract(address(ta));
        tc.setDinToken(address(token));
        ta.setDinToken(address(token));
        vm.stopBroadcast();

        vm.startBroadcast(admin);
        coordinator.addSlasherContract(address(tc));
        coordinator.addSlasherContract(address(ta));
        vm.stopBroadcast();

        vm.startBroadcast(modelOwner);
        tc.setDINTaskCoordinatorAsSlasher();
        tc.setDINTaskAuditorAsSlasher();
        tc.setGenesisModelIpfsHash(bytes32(uint256(1)));
        registry.requestModelRegistration{value: registry.openSourceFee()}(
            bytes32(uint256(0xC1D)), address(tc), address(ta), true
        );
        vm.stopBroadcast();

        vm.broadcast(admin);
        registry.approveModel(0);

        for (uint32 i = 2; i < 11; i++) stakeAs(account(i), coordinator, token, stake);

        vm.startBroadcast(modelOwner);
        coordinator.depositAndMint{value: POOL / 1_000_000 + 1}();
        token.approve(address(ta), type(uint256).max);
        ta.depositRewards(GI, POOL);
        tc.startGI(GI);
        tc.startDINaggregatorsRegistration(GI);
        vm.stopBroadcast();

        for (uint32 i = 2; i < 8; i++) {
            vm.broadcast(account(i));
            tc.registerDINaggregator(GI);
        }

        vm.startBroadcast(modelOwner);
        tc.closeDINaggregatorsRegistration(GI);
        tc.startDINauditorsRegistration(GI);
        vm.stopBroadcast();

        for (uint32 i = 8; i < 11; i++) {
            vm.broadcast(account(i));
            ta.registerDINAuditor(GI);
        }

        vm.startBroadcast(modelOwner);
        tc.closeDINauditorsRegistration(GI);
        tc.startLMsubmissions(GI);
        vm.stopBroadcast();

        for (uint32 i = 11; i < 14; i++) {
            vm.broadcast(account(i));
            ta.submitLocalModel(bytes32(uint256(i) * 100), GI);
        }
    }
}
