// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

// Run after NuthatchSpike.s.sol, on the same anvil. It adds the owner-side governance calls the
// spike leaves out, so the views over those events have rows to be checked against: fee and stake
// parameters, model stake bounds, the S5/S6 settings, fee-router sources and splits, a manifest
// update, a rejected request, an unstake, a slasher removal and the task contracts' own settings.
// Anvil accounts only, same addresses as the spike's deploy:
//   forge script script/NuthatchGov.s.sol --sig "gov()" --rpc-url http://127.0.0.1:8545 --broadcast --unlocked

import {Script} from "forge-std/Script.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DINModelRegistry} from "../src/DINModelRegistry.sol";
import {DinFeeRouter, DinSplit, EthSplit} from "../src/DinFeeRouter.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DINTaskCoordinator} from "../src/DINTaskCoordinator.sol";
import {DINTaskAuditor} from "../src/DINTaskAuditor.sol";

contract NuthatchGov is Script {
    string constant MNEMONIC = "test test test test test test test test test test test junk";

    DinValidatorStake constant stake = DinValidatorStake(0xA51c1fc2f0D1a1b8494Ed1FE312d7C3a78Ed91C0);
    DINModelRegistry constant registry = DINModelRegistry(0x959922bE3CAee4b8Cd9a407cc3ac1C251C2007B1);
    DinFeeRouter constant router = DinFeeRouter(0x5FC8d32690cc91D4c39d9d3abcBD16989F875707);
    DinCoordinator constant coordinator = DinCoordinator(0xa513E6E4b8f2a923D98304ec87F64353C4D5C853);

    function account(uint32 i) internal pure returns (address) {
        return vm.addr(vm.deriveKey(MNEMONIC, i));
    }

    function gov() external {
        address admin = account(0);
        address modelOwner = account(1);
        (, , , , address tcAddr, address taAddr) = registry.getModel(0);
        DINTaskCoordinator tc = DINTaskCoordinator(tcAddr);
        DINTaskAuditor ta = DINTaskAuditor(taAddr);

        // account 2 (a staked aggregator) asks to unstake 4 of its 10 DIN
        vm.broadcast(account(2));
        stake.unstake(4 ether);

        vm.startBroadcast(admin);
        stake.setMinStake(20 ether);
        stake.setUnbondingPeriod(14 days);
        stake.setMaxConcurrentRegistrationsPerStakeUnit(3);
        stake.setModelStakeBounds(0, 5 ether, 50 ether);
        stake.setModelStakeBounds(0, 10 ether, 100 ether); // the second one is the row that stands
        stake.setS5GlobalParams(10, 3);
        stake.setS5RecidivismParams(20, 4, 1 days);
        stake.setS6NoParticipationThreshold(5);

        // fee router: one source removed, treasury and ceiling changed, both splits rewritten
        router.removeFeeSource(address(coordinator));
        router.setTreasury(account(30));
        router.setTreasuryBpsCeiling(2500);
        router.setDinSplit(DinSplit(5500, 2200, 1800, 500, 0));
        router.setEthSplit(EthSplit(6000, 2000, 1500, 500));

        // registry fees: four single setters, then the atomic one
        registry.setOpenSourceFee(0.01 ether);
        registry.setProprietaryFee(0.02 ether);
        registry.setOpenSourceUpdateFee(0.003 ether);
        registry.setProprietaryUpdateFee(0.004 ether);
        registry.setFees(0.011 ether, 0.022 ether, 0.0033 ether, 0.0044 ether);
        vm.stopBroadcast();

        // a manifest update the DAO approves, one it rejects, and a second model request it rejects
        vm.startBroadcast(modelOwner);
        registry.requestManifestUpdate{value: registry.openSourceUpdateFee()}(0, bytes32(uint256(0xC1E)));
        registry.requestManifestUpdate{value: registry.openSourceUpdateFee()}(0, bytes32(uint256(0xC1F)));
        registry.requestModelRegistration{value: registry.proprietaryFee()}(
            bytes32(uint256(0xBAD)), address(tc), address(ta), false
        );
        vm.stopBroadcast();

        vm.startBroadcast(admin);
        registry.approveManifestUpdate(0);
        registry.rejectManifestUpdate(1);
        registry.rejectModel(1);
        registry.sweepFeesToRouter();
        vm.stopBroadcast();

        // the model owner's own task-contract settings
        vm.startBroadcast(modelOwner);
        tc.setS2SlashFractionBps(4000);
        ta.setS1SlashFractionBps(2500);
        ta.setS3DeviationThreshold(15);
        ta.setS3SlashingEnabled(true);
        ta.setRewardSplit(DINTaskAuditor.RewardSplit(6000, 2000, 1500, 500));
        vm.stopBroadcast();

        // last: the auditor contract stops being a slasher
        vm.broadcast(admin);
        coordinator.removeSlasherContract(address(ta));
    }
}
