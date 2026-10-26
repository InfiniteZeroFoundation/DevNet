// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Vm} from "forge-std/Vm.sol";
import {DINTaskAuditor} from "../../src/DINTaskAuditor.sol";
import {IDinValidatorStake} from "../../src/DINShared.sol";

Vm constant VM = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

/// @dev Assigns placeholder test data to every audit batch of `gi`, so
///      setTestDataAssignedFlag's every-batch commitment check
///      (task_061026_21 Part B) passes in tests that don't exercise the
///      encrypted test-data path (EncryptedTestData.t.sol does). Auditor
///      X25519 keys are mocked on `stake` for the duration of the call, not
///      registered. Every call is made as the current caller, so run it as
///      the model owner (under vm.startPrank, or as the owning test contract).
function assignPlaceholderTestData(DINTaskAuditor ta, address stake, uint256 gi) {
    VM.mockCall(
        stake,
        abi.encodeWithSelector(IDinValidatorStake.getEncryptionKey.selector),
        abi.encode(hex"01")
    );
    uint256 n = ta.AuditorsBatchCount(gi);
    for (uint256 b = 0; b < n; b++) {
        (, address[] memory auditors, , ) = ta.getAuditorsBatch(gi, b);
        ta.assignAuditTestDataset(gi, b, hex"01", new bytes[](auditors.length), keccak256(abi.encode(gi, b)));
    }
    VM.clearMockedCalls();
}
