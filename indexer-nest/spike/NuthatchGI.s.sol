// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

// Run after NuthatchSpike.s.sol: takes GI 1 from its local-model submissions to GIended, so the
// batches, scores, eligibility, seeds and aggregation have events to be read from. Three stages,
// with blocks mined between them (the seed locks wait disputeSeedDelay blocks):
//   forge script script/NuthatchGI.s.sol --sig "stage1()" ... ; cast rpc anvil_mine 10 ...
// Every account is an anvil account, the spike's own roles: model owner 1, aggregators 2-7,
// auditors 8-10, clients 11-13. The test-data dataset is a placeholder, as in DevNet's own tests.

import {Script} from "forge-std/Script.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DINModelRegistry} from "../src/DINModelRegistry.sol";
import {DINTaskCoordinator} from "../src/DINTaskCoordinator.sol";
import {DINTaskAuditor} from "../src/DINTaskAuditor.sol";
import {auditCommitHash} from "../test/utils/AuditCommitHash.sol";

contract NuthatchGI is Script {
    string constant MNEMONIC = "test test test test test test test test test test test junk";
    uint256 constant GI = 1;
    bytes32 constant SALT = bytes32(uint256(0xC0FFEE));
    bytes32 constant CID_A = bytes32(uint256(0xA1));
    bytes32 constant CID_B = bytes32(uint256(0xB2));

    DinValidatorStake constant stake = DinValidatorStake(0xA51c1fc2f0D1a1b8494Ed1FE312d7C3a78Ed91C0);
    DINModelRegistry constant registry = DINModelRegistry(0x959922bE3CAee4b8Cd9a407cc3ac1C251C2007B1);

    function account(uint32 i) internal pure returns (address) {
        return vm.addr(vm.deriveKey(MNEMONIC, i));
    }

    function tasks() internal view returns (DINTaskCoordinator tc, DINTaskAuditor ta) {
        (, , , , address a, address b) = registry.getModel(0);
        tc = DINTaskCoordinator(a);
        ta = DINTaskAuditor(b);
    }

    function stage1() external {
        (DINTaskCoordinator tc, ) = tasks();
        vm.broadcast(account(1));
        tc.closeLMsubmissions(GI);
    }

    function stage2() external {
        (DINTaskCoordinator tc, DINTaskAuditor ta) = tasks();
        address owner_ = account(1);

        vm.broadcast(account(0));
        tc.lockAuditSeed(GI);
        vm.broadcast(owner_);
        tc.createAuditorsBatches(GI);

        for (uint32 i = 8; i < 11; i++) {
            vm.broadcast(account(i));
            stake.registerEncryptionKey(abi.encodePacked(bytes32(uint256(0x1000 + i))));
        }
        uint256 n = ta.AuditorsBatchCount(GI);
        vm.startBroadcast(owner_);
        for (uint256 b = 0; b < n; b++) {
            (, address[] memory aud, , ) = ta.getAuditorsBatch(GI, b);
            ta.assignAuditTestDataset(GI, b, hex"01", new bytes[](aud.length), keccak256(abi.encode(GI, b)));
        }
        tc.setTestDataAssignedFlag(GI, true);
        tc.startLMsubmissionsEvaluation(GI);
        vm.stopBroadcast();

        for (uint256 b = 0; b < n; b++) {
            (, address[] memory aud, uint256[] memory idx, ) = ta.getAuditorsBatch(GI, b);
            for (uint256 ai = 0; ai < aud.length; ai++) {
                for (uint256 mi = 0; mi < idx.length; mi++) {
                    vm.broadcast(aud[ai]);
                    ta.commitAuditScore(GI, b, idx[mi], auditCommitHash(80, true, SALT, aud[ai], GI, b, idx[mi]));
                }
            }
        }
        vm.broadcast(owner_);
        tc.startLMsubmissionsEvaluationReveal(GI);
        for (uint256 b = 0; b < n; b++) {
            (, address[] memory aud, uint256[] memory idx, ) = ta.getAuditorsBatch(GI, b);
            for (uint256 ai = 0; ai < aud.length; ai++) {
                for (uint256 mi = 0; mi < idx.length; mi++) {
                    vm.broadcast(aud[ai]);
                    ta.revealAuditScore(GI, b, idx[mi], 80, true, SALT);
                }
            }
        }
        vm.broadcast(owner_);
        tc.closeLMsubmissionsEvaluation(GI);
    }

    function commitT1(DINTaskCoordinator tc, address who, uint256 b, bytes32 cid) internal {
        vm.broadcast(who);
        tc.commitT1Aggregation(GI, b, keccak256(abi.encode(cid, SALT, who, GI, DINTaskCoordinator.TierKind.Tier1, b)));
    }

    function stage3() external {
        (DINTaskCoordinator tc, ) = tasks();
        address owner_ = account(1);

        vm.broadcast(account(0));
        tc.lockAggSeed(GI);
        vm.startBroadcast(owner_);
        tc.autoCreateTier1AndTier2(GI);
        tc.startT1Aggregation(GI);
        vm.stopBroadcast();

        uint256 t1 = tc.tier1BatchCount(GI);
        for (uint256 b = 0; b < t1; b++) {
            (, address[] memory aggs, , , ) = tc.getTier1Batch(GI, b);
            for (uint256 i = 0; i < aggs.length; i++) commitT1(tc, aggs[i], b, CID_A);
        }
        vm.broadcast(owner_);
        tc.startT1AggregationReveal(GI);
        for (uint256 b = 0; b < t1; b++) {
            (, address[] memory aggs, , , ) = tc.getTier1Batch(GI, b);
            for (uint256 i = 0; i < aggs.length; i++) {
                vm.broadcast(aggs[i]);
                tc.revealT1Aggregation(GI, b, CID_A, SALT);
            }
        }
        vm.startBroadcast(owner_);
        tc.finalizeT1Aggregation(GI);
        tc.startT2Aggregation(GI);
        vm.stopBroadcast();

        (, address[] memory t2, , ) = tc.getTier2Batch(GI, 0);
        for (uint256 i = 0; i < t2.length; i++) {
            vm.broadcast(t2[i]);
            tc.commitT2Aggregation(GI, 0, keccak256(abi.encode(CID_B, SALT, t2[i], GI, DINTaskCoordinator.TierKind.Tier2, uint256(0))));
        }
        vm.broadcast(owner_);
        tc.startT2AggregationReveal(GI);
        for (uint256 i = 0; i < t2.length; i++) {
            vm.broadcast(t2[i]);
            tc.revealT2Aggregation(GI, 0, CID_B, SALT);
        }
        vm.startBroadcast(owner_);
        tc.finalizeT2Aggregation(GI);
        tc.slashAuditors(GI);
        tc.slashAggregators(GI);
        tc.endGI(GI);
        vm.stopBroadcast();
    }
}
