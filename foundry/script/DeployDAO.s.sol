// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script, console} from "forge-std/Script.sol";
import {stdJson} from "forge-std/StdJson.sol";

import {DinMultisig} from "../src/dao/DinMultisig.sol";
import {DinTimelock} from "../src/dao/DinTimelock.sol";
import {DinGovernanceStaking} from "../src/dao/DinGovernanceStaking.sol";
import {DinGovernor} from "../src/dao/DinGovernor.sol";
import {DinGuardian} from "../src/dao/DinGuardian.sol";

/// @notice Deploys the five DIN DAO contracts (Stages A–D) as plain non-upgradeable
///         contracts, wires proposer/canceller roles on the timelocks, and writes
///         foundry/deployments/dao-localhost.json.
///
/// The DAO contracts are intentionally non-upgradeable — the contract guarding
/// upgrades must not itself be upgradeable or the trust problem shifts up a level.
/// Do NOT use Upgrades.deployTransparentProxy here.
///
/// Requires platform contracts to be deployed first:
///   forge script script/DeployPlatform.s.sol ...
///
/// Usage (from repo root):
///   ./foundry/anvil.sh &
///   forge clean
///   cd foundry && MULTISIG_SIGNERS=0xAddr1,0xAddr2 forge script script/DeployDAO.s.sol \
///     --rpc-url http://127.0.0.1:8545 \
///     --broadcast \
///     --sender 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 \
///     --unlocked
///
/// Environment variables (all have devnet defaults):
///
///   MULTISIG_SIGNERS
///     Comma-separated signer addresses for DinMultisig.
///     Defaults to [broadcaster] for local devnet testing only.
///     Production MUST set this explicitly — signer composition is an open
///     decision (DD-3 / discussion #70) and the list is immutable after deploy.
///
///   MULTISIG_THRESHOLD_PARAMETER   (default 1)
///   MULTISIG_THRESHOLD_OPERATIONAL (default 1)
///   MULTISIG_THRESHOLD_TREASURY    (default 1)
///   MULTISIG_THRESHOLD_UPGRADE     (default 1)
///     N-of-M approval thresholds per proposal category.
///
///   PLATFORM_DEPLOYMENTS
///     Path to the platform deployments JSON written by DeployPlatform.s.sol.
///     Default: <projectRoot>/deployments/localhost.json
///
///   GOV_VOTING_DELAY      (default 7200   — ≈ 24 h at 12-second L1 blocks;
///                                           use 1800 for OP-stack 2-second blocks)
///   GOV_VOTING_PERIOD     (default 50400  — ≈  7 d at 12-second L1 blocks;
///                                           use 151200 for OP-stack)
///   GOV_PROPOSAL_THRESHOLD (default 0)    — min stDIN required to submit a proposal
///   GOV_QUORUM_FRACTION    (default 4)    — quorum as % of total stDIN supply
///
///   GUARDIAN_RATIFICATION_WINDOW (default 604800 — 7 days in seconds)
///     Window during which DinGovernor can ratify or reverse a DinGuardian action.
///
/// NOTE: transferOwnership is intentionally NOT scripted here. Stage B activation
/// requires each platform contract's owner() to move via Ownable2Step, initiated
/// from the DIN-Representative EOA and accepted through DinTimelock with a real
/// on-chain delay and manual confirmation between steps. Follow the runbook in
/// Documentation/technical/din-dao/README.md §5a instead.
contract DeployDAO is Script {
    using stdJson for string;

    uint256 constant TIMELOCK_SHORT = 24 hours; // Stage B — parameter + operational proposals
    uint256 constant TIMELOCK_LONG  = 48 hours; // Stage B — treasury + upgrade proposals

    function run() external {
        // ── Multisig configuration ────────────────────────────────────────────
        // Default: sole signer = broadcaster (local devnet testing only).
        // Production: set MULTISIG_SIGNERS — immutable after construction.
        address[] memory defaultSigners = new address[](1);
        defaultSigners[0] = msg.sender;
        address[] memory signers = vm.envOr("MULTISIG_SIGNERS", ",", defaultSigners);

        uint256[4] memory thresholds = [
            vm.envOr("MULTISIG_THRESHOLD_PARAMETER",   uint256(1)),
            vm.envOr("MULTISIG_THRESHOLD_OPERATIONAL", uint256(1)),
            vm.envOr("MULTISIG_THRESHOLD_TREASURY",    uint256(1)),
            vm.envOr("MULTISIG_THRESHOLD_UPGRADE",     uint256(1))
        ];

        // ── Platform deployments — read dinToken for DinGovernanceStaking ─────
        string memory deploymentsPath = vm.envOr(
            "PLATFORM_DEPLOYMENTS",
            string(abi.encodePacked(vm.projectRoot(), "/deployments/localhost.json"))
        );
        string memory deploymentsJson = vm.readFile(deploymentsPath);
        address dinToken = deploymentsJson.readAddress(".dinToken");
        console.log("DinToken (platform):     ", dinToken);

        // ── Governor parameters ───────────────────────────────────────────────
        uint48  votingDelay        = uint48(vm.envOr("GOV_VOTING_DELAY",           uint256(7200)));
        uint32  votingPeriod       = uint32(vm.envOr("GOV_VOTING_PERIOD",          uint256(50400)));
        uint256 proposalThreshold  = vm.envOr("GOV_PROPOSAL_THRESHOLD",            uint256(0));
        uint256 quorumFraction     = vm.envOr("GOV_QUORUM_FRACTION",               uint256(4));
        uint256 ratifWindow        = vm.envOr("GUARDIAN_RATIFICATION_WINDOW",      uint256(7 days));

        vm.startBroadcast();

        // ── Stage A ───────────────────────────────────────────────────────────

        // 1. DinMultisig — N-of-M typed-proposal multisig; shadow-operates at Devnet 2.0.
        DinMultisig multisig = new DinMultisig(signers, thresholds);
        console.log("DinMultisig:             ", address(multisig));

        // ── Stage B ───────────────────────────────────────────────────────────
        // OZ TimelockController grants PROPOSER_ROLE + CANCELLER_ROLE to each entry
        // in the proposers array and EXECUTOR_ROLE to each entry in the executors array.
        // address(0) as executor means anyone can execute a matured proposal.
        // address(0) as admin means the timelock is its own admin after deployment.

        address[] memory proposers = new address[](1);
        proposers[0] = address(multisig);

        address[] memory executors = new address[](1);
        executors[0] = address(0); // open execution

        // 2. DinTimelockShort — 24 h delay; for parameter + operational proposals.
        DinTimelock timelockShort = new DinTimelock(
            TIMELOCK_SHORT,
            proposers,
            executors,
            address(0)
        );
        console.log("DinTimelockShort (24 h): ", address(timelockShort));

        // 3. DinTimelockLong — 48 h delay; for treasury + upgrade proposals.
        DinTimelock timelockLong = new DinTimelock(
            TIMELOCK_LONG,
            proposers,
            executors,
            address(0)
        );
        console.log("DinTimelockLong  (48 h): ", address(timelockLong));

        // ── Stage C ───────────────────────────────────────────────────────────

        // 4. DinGovernanceStaking — lock DIN → non-transferable stDIN (IVotes).
        DinGovernanceStaking govStaking = new DinGovernanceStaking(dinToken);
        console.log("DinGovernanceStaking:    ", address(govStaking));

        // 5. DinGovernor — token-vote governor backed by DinTimelockLong.
        //    Short-delay proposals are routed by encoding DinTimelockShort as the
        //    call target in the proposal's targets array (see DinGovernor NatSpec).
        //    Stage C activation wires DinGovernor as a proposer on both timelocks;
        //    DinMultisig retains CANCELLER_ROLE as a safety brake (already granted
        //    at construction above; not removed at Stage C — see runbook §5b).
        DinGovernor governor = new DinGovernor(
            govStaking,
            timelockLong,
            votingDelay,
            votingPeriod,
            proposalThreshold,
            quorumFraction
        );
        console.log("DinGovernor:             ", address(governor));

        // ── Stage D ───────────────────────────────────────────────────────────

        // 6. DinGuardian — narrow time-limited emergency authority.
        //    Guardian = DinMultisig; governor = DinGovernor (can revoke guardian).
        DinGuardian dinGuardian = new DinGuardian(
            address(multisig),
            address(governor),
            ratifWindow
        );
        console.log("DinGuardian:             ", address(dinGuardian));

        vm.stopBroadcast();

        _writeDeployments(
            address(multisig),
            address(timelockShort),
            address(timelockLong),
            address(govStaking),
            address(governor),
            address(dinGuardian)
        );
    }

    function _writeDeployments(
        address multisig,
        address timelockShort,
        address timelockLong,
        address govStaking,
        address governor,
        address dinGuardian
    ) internal {
        string memory json = "dao";
        vm.serializeAddress(json, "dinMultisig",          multisig);
        vm.serializeAddress(json, "dinTimelockShort",     timelockShort);
        vm.serializeAddress(json, "dinTimelockLong",      timelockLong);
        vm.serializeAddress(json, "dinGovernanceStaking", govStaking);
        vm.serializeAddress(json, "dinGovernor",          governor);
        string memory finalJson = vm.serializeAddress(json, "dinGuardian", dinGuardian);

        string memory outDir = string.concat(vm.projectRoot(), "/deployments");
        vm.createDir(outDir, true);

        string memory outPath = string.concat(outDir, "/dao-localhost.json");
        vm.writeJson(finalJson, outPath);
        console.log("DAO deployments written to:", outPath);
    }
}
