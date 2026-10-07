// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script, console} from "forge-std/Script.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {Upgrades} from "@openzeppelin/foundry-upgrades/Upgrades.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DINModelRegistry} from "../src/DINModelRegistry.sol";
import {DinTreasury} from "../src/DinTreasury.sol";
import {DinFeeRouter} from "../src/DinFeeRouter.sol";
import {DinEmission} from "../src/DinEmission.sol";

import {DeploymentsPath} from "./DeploymentsPath.sol";

/// @notice Deploys the seven DIN platform contracts behind Transparent Proxies,
///         wires them together, and writes foundry/deployments/<network>.json
///         (see DeploymentsPath: localhost for anvil, sepolia_op_devnet for
///         Optimism Sepolia), which `dincli system import-deployments` reads
///         as-is.
///
/// Tokenomics parameters are read from the environment via vm.envOr, defaulting
/// to today's in-code values so local deploys and existing tests are unchanged.
/// Every key that is not set logs an "[INFO] ... not set" line, so a missed
/// env load is visible in the output.
///
/// NOTE: forge script only auto-loads foundry/.env. The repo-root .env and
/// .env.<network> files (used by dincli) are NOT read. Put overrides
/// in foundry/.env, or export them into the shell before running, e.g.:
///   set -a; source ../.env.sepolia_op_devnet; set +a
///
/// Env keys (see .env.example for full descriptions):
///   DIN_PER_ETH                 — DIN minted per ETH (default: 1_000_000 * 1e18)
///   MINT_CAP                    — max total DIN minted, 0 = uncapped (default: 0)
///   EMISSION_PER_GI             — initial DIN per GI (default: 100e18)
///   EMISSION_DECAY_BPS          — retention fraction bps per epoch (default: 8000)
///   EMISSION_EPOCH_LENGTH       — GIs per epoch (default: 100)
///   EMISSION_MAX_EPOCHS         — total epochs before emission stops (default: 10)
///   MIN_STAKE                   — minimum validator stake in DIN-wei (default: 10e18)
///   S5_RECIDIVISM_WINDOW        — rolling GI window for S5 escalation (default: 5)
///   S5_RECIDIVISM_THRESHOLD     — slashes in window to trigger S5 jail (default: 3)
///   S5_JAIL_DURATION            — jail duration in seconds (default: 604800 = 7 days)
///   S6_NO_PARTICIPATION_THRESHOLD — no-participation events before S6 fires (default: 3)
///
/// Usage (from repo root):
///   ./foundry/anvil.sh &
///   forge clean
///   cd foundry
///   set -a; source ../.env.<network>; set +a   # optional: tokenomics overrides
///   forge script script/DeployPlatform.s.sol \
///     --rpc-url http://127.0.0.1:8545 \
///     --broadcast \
///     --sender 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 \
///     --unlocked
///
/// On Optimism Sepolia, sign with a keystore account instead of --unlocked
/// (--unlocked only works against anvil's dev accounts). SEPOLIA_OP_DEVNET_RPC_URL comes
/// from .env.sepolia_op_devnet (from the repo root: set -a; source .env.sepolia_op_devnet; set +a):
///   cd foundry && forge script script/DeployPlatform.s.sol \
///     --rpc-url "$SEPOLIA_OP_DEVNET_RPC_URL" \
///     --broadcast \
///     --account <keystore_name> \
///     --sender <din_representative_address>
///
/// Then import into dincli (reads foundry/deployments/<network>.json for the
/// active dincli network):
///   dincli system import-deployments
contract DeployPlatform is DeploymentsPath {
    using stdJson for string;

    // ── Tokenomics defaults (match contract initialize values) ────────────────
    uint256 internal constant DEFAULT_DIN_PER_ETH        = 1_000_000 * 1e18;
    uint256 internal constant DEFAULT_MINT_CAP           = 0;
    uint256 internal constant DEFAULT_EMISSION_PER_GI    = 100e18;
    uint256 internal constant DEFAULT_EMISSION_DECAY_BPS = 8000;
    uint256 internal constant DEFAULT_EMISSION_EPOCH_LEN = 100;
    uint256 internal constant DEFAULT_EMISSION_MAX_EPOCHS= 10;
    uint256 internal constant DEFAULT_MIN_STAKE          = 10 * 1e18;
    uint256 internal constant DEFAULT_S5_WINDOW          = 5;
    uint256 internal constant DEFAULT_S5_THRESHOLD       = 3;
    uint256 internal constant DEFAULT_S5_JAIL_DURATION   = 7 days;
    uint256 internal constant DEFAULT_S6_THRESHOLD       = 3;

    /// @notice Tokenomics values the deploy applies; see the env keys in the header.
    struct Tokenomics {
        uint256 dinPerEth;
        uint256 mintCap;
        uint256 emissionPerGI;
        uint256 emissionDecayBps;
        uint256 emissionEpochLength;
        uint256 emissionMaxEpochs;
        uint256 minStake;
        uint256 s5Window;
        uint256 s5Threshold;
        uint256 s5JailDuration;
        uint256 s6Threshold;
    }

    /// @notice Deployed proxy and ProxyAdmin addresses, as written to the deployments JSON.
    struct Deployment {
        address dinTreasury;
        address dinToken;
        address dinCoordinator;
        address dinFeeRouter;
        address dinValidatorStake;
        address dinModelRegistry;
        address dinEmission;
        address proxyAdminTreasury;
        address proxyAdminToken;
        address proxyAdminCoordinator;
        address proxyAdminFeeRouter;
        address proxyAdminStake;
        address proxyAdminRegistry;
        address proxyAdminEmission;
    }

    function run() external {
        Tokenomics memory t = readTokenomics();
        Deployment memory d = deploy(t, msg.sender);

        // 16. Write deployments JSON — read by `dincli system import-deployments`
        _writeDeployments(
            d.dinTreasury,
            d.dinToken,
            d.dinCoordinator,
            d.dinFeeRouter,
            d.dinValidatorStake,
            d.dinModelRegistry,
            d.dinEmission,
            d.proxyAdminTreasury,
            d.proxyAdminToken,
            d.proxyAdminCoordinator,
            d.proxyAdminFeeRouter,
            d.proxyAdminStake,
            d.proxyAdminRegistry,
            d.proxyAdminEmission
        );
    }

    /// @notice The in-code defaults, i.e. what readTokenomics() returns with no env set.
    function defaultTokenomics() public pure returns (Tokenomics memory) {
        return Tokenomics({
            dinPerEth:           DEFAULT_DIN_PER_ETH,
            mintCap:             DEFAULT_MINT_CAP,
            emissionPerGI:       DEFAULT_EMISSION_PER_GI,
            emissionDecayBps:    DEFAULT_EMISSION_DECAY_BPS,
            emissionEpochLength: DEFAULT_EMISSION_EPOCH_LEN,
            emissionMaxEpochs:   DEFAULT_EMISSION_MAX_EPOCHS,
            minStake:            DEFAULT_MIN_STAKE,
            s5Window:            DEFAULT_S5_WINDOW,
            s5Threshold:         DEFAULT_S5_THRESHOLD,
            s5JailDuration:      DEFAULT_S5_JAIL_DURATION,
            s6Threshold:         DEFAULT_S6_THRESHOLD
        });
    }

    /// @notice Reads each tokenomics key from the environment, falling back to
    ///         its default, and logs every key that is not set.
    function readTokenomics() public view returns (Tokenomics memory t) {
        Tokenomics memory dflt = defaultTokenomics();
        t.dinPerEth           = vm.envOr("DIN_PER_ETH",                   dflt.dinPerEth);
        t.mintCap             = vm.envOr("MINT_CAP",                      dflt.mintCap);
        t.emissionPerGI       = vm.envOr("EMISSION_PER_GI",               dflt.emissionPerGI);
        t.emissionDecayBps    = vm.envOr("EMISSION_DECAY_BPS",            dflt.emissionDecayBps);
        t.emissionEpochLength = vm.envOr("EMISSION_EPOCH_LENGTH",         dflt.emissionEpochLength);
        t.emissionMaxEpochs   = vm.envOr("EMISSION_MAX_EPOCHS",           dflt.emissionMaxEpochs);
        t.minStake            = vm.envOr("MIN_STAKE",                     dflt.minStake);
        t.s5Window            = vm.envOr("S5_RECIDIVISM_WINDOW",          dflt.s5Window);
        t.s5Threshold         = vm.envOr("S5_RECIDIVISM_THRESHOLD",       dflt.s5Threshold);
        t.s5JailDuration      = vm.envOr("S5_JAIL_DURATION",              dflt.s5JailDuration);
        t.s6Threshold         = vm.envOr("S6_NO_PARTICIPATION_THRESHOLD", dflt.s6Threshold);

        _logIfUnset("DIN_PER_ETH",                   t.dinPerEth);
        _logIfUnset("MINT_CAP",                      t.mintCap);
        _logIfUnset("EMISSION_PER_GI",               t.emissionPerGI);
        _logIfUnset("EMISSION_DECAY_BPS",            t.emissionDecayBps);
        _logIfUnset("EMISSION_EPOCH_LENGTH",         t.emissionEpochLength);
        _logIfUnset("EMISSION_MAX_EPOCHS",           t.emissionMaxEpochs);
        _logIfUnset("MIN_STAKE",                     t.minStake);
        _logIfUnset("S5_RECIDIVISM_WINDOW",          t.s5Window);
        _logIfUnset("S5_RECIDIVISM_THRESHOLD",       t.s5Threshold);
        _logIfUnset("S5_JAIL_DURATION",              t.s5JailDuration);
        _logIfUnset("S6_NO_PARTICIPATION_THRESHOLD", t.s6Threshold);
    }

    /// @notice Deploys and wires the platform with the given tokenomics (steps
    ///         1-15). Split from run() so tests can deploy with explicit values
    ///         instead of vm.setEnv, which would leak into forge's parallel tests.
    /// @param deployer Broadcasts every call and owns all seven ProxyAdmins (and,
    ///        via each initializer, the proxies). run() passes msg.sender, i.e.
    ///        forge script's --sender; tests pass a fixed address.
    function deploy(Tokenomics memory t, address deployer) public returns (Deployment memory d) {
        vm.startBroadcast(deployer);

        // 1. DinTreasury — no dependencies
        address dinTreasuryProxy = Upgrades.deployTransparentProxy(
            "DinTreasury.sol:DinTreasury",
            deployer,
            abi.encodeCall(DinTreasury.initialize, ())
        );
        console.log("DinTreasury proxy:      ", dinTreasuryProxy);

        // 2. DinToken — no init args
        address dinTokenProxy = Upgrades.deployTransparentProxy(
            "DinToken.sol:DinToken",
            deployer,
            abi.encodeCall(DinToken.initialize, ())
        );
        console.log("DinToken proxy:         ", dinTokenProxy);

        // 3. DinFeeRouter — receives DinToken and DinTreasury proxies
        address dinFeeRouterProxy = Upgrades.deployTransparentProxy(
            "DinFeeRouter.sol:DinFeeRouter",
            deployer,
            abi.encodeCall(DinFeeRouter.initialize, (dinTokenProxy, dinTreasuryProxy))
        );
        console.log("DinFeeRouter proxy:     ", dinFeeRouterProxy);

        // 4. DinCoordinator — receives the DinToken proxy address
        address dinCoordinatorProxy = Upgrades.deployTransparentProxy(
            "DinCoordinator.sol:DinCoordinator",
            deployer,
            abi.encodeCall(DinCoordinator.initialize, (dinTokenProxy))
        );
        console.log("DinCoordinator proxy:   ", dinCoordinatorProxy);

        // 5. Wire DinToken → DinCoordinator (one-shot setter)
        DinToken(dinTokenProxy).setCoordinator(dinCoordinatorProxy);
        console.log("DinToken coordinator wired");

        // 6. Wire DinCoordinator → DinFeeRouter, and authorise it as a fee
        //    source so its sweepFeesToRouter() calls are accepted (onlyFeeSource).
        DinCoordinator(payable(dinCoordinatorProxy)).setFeeRouter(dinFeeRouterProxy);
        DinFeeRouter(dinFeeRouterProxy).addFeeSource(dinCoordinatorProxy);
        console.log("DinCoordinator feeRouter wired");

        // 7. DinValidatorStake — receives both token and coordinator proxies
        address dinValidatorStakeProxy = Upgrades.deployTransparentProxy(
            "DinValidatorStake.sol:DinValidatorStake",
            deployer,
            abi.encodeCall(
                DinValidatorStake.initialize,
                (dinTokenProxy, dinCoordinatorProxy)
            )
        );
        console.log("DinValidatorStake proxy:", dinValidatorStakeProxy);

        // 8. Wire DinCoordinator → DinValidatorStake
        DinCoordinator(payable(dinCoordinatorProxy))
            .updateValidatorStakeContract(dinValidatorStakeProxy);
        console.log("DinCoordinator stake contract wired");

        // 9. Wire DinValidatorStake → DinTreasury for slash distribution
        DinValidatorStake(dinValidatorStakeProxy).setSlashTreasury(dinTreasuryProxy);
        console.log("DinValidatorStake slashTreasury wired");

        // 10. DINModelRegistry — receives the stake proxy
        address dinModelRegistryProxy = Upgrades.deployTransparentProxy(
            "DINModelRegistry.sol:DINModelRegistry",
            deployer,
            abi.encodeCall(
                DINModelRegistry.initialize,
                (dinValidatorStakeProxy)
            )
        );
        console.log("DINModelRegistry proxy: ", dinModelRegistryProxy);

        // 11. Authorise DINModelRegistry as a fee source on DinFeeRouter, so its
        //     later sweepFeesToRouter() calls are accepted (onlyFeeSource).
        DinFeeRouter(dinFeeRouterProxy).addFeeSource(dinModelRegistryProxy);
        console.log("DINModelRegistry added as fee source");

        // 12. Wire DINModelRegistry → DinFeeRouter
        DINModelRegistry(dinModelRegistryProxy).setFeeRouter(dinFeeRouterProxy);
        console.log("DINModelRegistry feeRouter wired");

        // 13. DinEmission — schedule from env overrides (defaults: 100 DIN/GI,
        //     8000 bps retention per epoch, 100 GIs/epoch, 10 epochs).
        address dinEmissionProxy = Upgrades.deployTransparentProxy(
            "DinEmission.sol:DinEmission",
            deployer,
            abi.encodeCall(
                DinEmission.initialize,
                (
                    dinCoordinatorProxy,
                    dinTokenProxy,
                    dinModelRegistryProxy,
                    t.emissionPerGI,
                    t.emissionDecayBps,
                    t.emissionEpochLength,
                    t.emissionMaxEpochs
                )
            )
        );
        console.log("DinEmission proxy:      ", dinEmissionProxy);

        // 14. Wire DinCoordinator → DinEmission
        DinCoordinator(payable(dinCoordinatorProxy)).setEmissionContract(dinEmissionProxy);
        console.log("DinCoordinator emission contract wired");

        // 15. Apply post-deploy tokenomics overrides when they differ from defaults.
        if (t.dinPerEth != DEFAULT_DIN_PER_ETH) {
            DinCoordinator(payable(dinCoordinatorProxy)).updateDinPerEth(t.dinPerEth);
            console.log("DinCoordinator.dinPerEth set to:", t.dinPerEth);
        }
        if (t.mintCap != DEFAULT_MINT_CAP) {
            DinCoordinator(payable(dinCoordinatorProxy)).setMintCap(t.mintCap);
            console.log("DinCoordinator.mintCap set to:", t.mintCap);
        }
        if (t.minStake != DEFAULT_MIN_STAKE) {
            DinValidatorStake(dinValidatorStakeProxy).setMinStake(t.minStake);
            console.log("DinValidatorStake.minStake set to:", t.minStake);
        }
        if (
            t.s5Window     != DEFAULT_S5_WINDOW     ||
            t.s5Threshold  != DEFAULT_S5_THRESHOLD  ||
            t.s5JailDuration != DEFAULT_S5_JAIL_DURATION
        ) {
            DinValidatorStake(dinValidatorStakeProxy).setS5RecidivismParams(
                t.s5Window, t.s5Threshold, t.s5JailDuration
            );
            console.log("DinValidatorStake S5 params updated");
        }
        if (t.s6Threshold != DEFAULT_S6_THRESHOLD) {
            DinValidatorStake(dinValidatorStakeProxy).setS6NoParticipationThreshold(t.s6Threshold);
            console.log("DinValidatorStake.s6NoParticipationThreshold set to:", t.s6Threshold);
        }

        console.log("--- Effective tokenomics ---");
        console.log("dinPerEth:            ", t.dinPerEth);
        console.log("mintCap:              ", t.mintCap);
        console.log("emissionPerGI:        ", t.emissionPerGI);
        console.log("emissionDecayBps:     ", t.emissionDecayBps);
        console.log("emissionEpochLength:  ", t.emissionEpochLength);
        console.log("emissionMaxEpochs:    ", t.emissionMaxEpochs);
        console.log("minStake:             ", t.minStake);
        console.log("s5Window:             ", t.s5Window);
        console.log("s5Threshold:          ", t.s5Threshold);
        console.log("s5JailDuration:       ", t.s5JailDuration);
        console.log("s6Threshold:          ", t.s6Threshold);

        // ProxyAdmin — OZ v5 deploys one ProxyAdmin per proxy; record all seven
        address proxyAdminTreasury    = Upgrades.getAdminAddress(dinTreasuryProxy);
        address proxyAdminToken       = Upgrades.getAdminAddress(dinTokenProxy);
        address proxyAdminCoordinator = Upgrades.getAdminAddress(dinCoordinatorProxy);
        address proxyAdminFeeRouter   = Upgrades.getAdminAddress(dinFeeRouterProxy);
        address proxyAdminStake       = Upgrades.getAdminAddress(dinValidatorStakeProxy);
        address proxyAdminRegistry    = Upgrades.getAdminAddress(dinModelRegistryProxy);
        address proxyAdminEmission    = Upgrades.getAdminAddress(dinEmissionProxy);
        console.log("ProxyAdmin (treasury):  ", proxyAdminTreasury);
        console.log("ProxyAdmin (token):     ", proxyAdminToken);
        console.log("ProxyAdmin (coord):     ", proxyAdminCoordinator);
        console.log("ProxyAdmin (feeRouter): ", proxyAdminFeeRouter);
        console.log("ProxyAdmin (stake):     ", proxyAdminStake);
        console.log("ProxyAdmin (registry):  ", proxyAdminRegistry);
        console.log("ProxyAdmin (emission):  ", proxyAdminEmission);

        vm.stopBroadcast();

        d = Deployment({
            dinTreasury: dinTreasuryProxy,
            dinToken: dinTokenProxy,
            dinCoordinator: dinCoordinatorProxy,
            dinFeeRouter: dinFeeRouterProxy,
            dinValidatorStake: dinValidatorStakeProxy,
            dinModelRegistry: dinModelRegistryProxy,
            dinEmission: dinEmissionProxy,
            proxyAdminTreasury: proxyAdminTreasury,
            proxyAdminToken: proxyAdminToken,
            proxyAdminCoordinator: proxyAdminCoordinator,
            proxyAdminFeeRouter: proxyAdminFeeRouter,
            proxyAdminStake: proxyAdminStake,
            proxyAdminRegistry: proxyAdminRegistry,
            proxyAdminEmission: proxyAdminEmission
        });
    }

    /// @dev Logs when `key` is absent from the environment, so a missed env
    ///      load (e.g. forgetting to source .env.<network>) is visible.
    function _logIfUnset(string memory key, uint256 value) internal view {
        if (!vm.envExists(key)) {
            console.log(string.concat("[INFO] ", key, " not set - using default:"), value);
        }
    }

    function _writeDeployments(
        address dinTreasury,
        address dinToken,
        address dinCoordinator,
        address dinFeeRouter,
        address dinValidatorStake,
        address dinModelRegistry,
        address dinEmission,
        address proxyAdminTreasury,
        address proxyAdminToken,
        address proxyAdminCoordinator,
        address proxyAdminFeeRouter,
        address proxyAdminStake,
        address proxyAdminRegistry,
        address proxyAdminEmission
    ) internal {
        string memory json = "deployments";
        vm.serializeAddress(json, "dinTreasury", dinTreasury);
        vm.serializeAddress(json, "dinToken", dinToken);
        vm.serializeAddress(json, "dinCoordinator", dinCoordinator);
        vm.serializeAddress(json, "dinFeeRouter", dinFeeRouter);
        vm.serializeAddress(json, "dinValidatorStake", dinValidatorStake);
        vm.serializeAddress(json, "dinModelRegistry", dinModelRegistry);
        vm.serializeAddress(json, "dinEmission", dinEmission);
        vm.serializeAddress(json, "proxyAdminTreasury", proxyAdminTreasury);
        vm.serializeAddress(json, "proxyAdminToken", proxyAdminToken);
        vm.serializeAddress(json, "proxyAdminCoordinator", proxyAdminCoordinator);
        vm.serializeAddress(json, "proxyAdminFeeRouter", proxyAdminFeeRouter);
        vm.serializeAddress(json, "proxyAdminStake", proxyAdminStake);
        vm.serializeAddress(json, "proxyAdminRegistry", proxyAdminRegistry);
        string memory finalJson = vm.serializeAddress(
            json,
            "proxyAdminEmission",
            proxyAdminEmission
        );

        string memory outDir = string.concat(vm.projectRoot(), "/deployments");
        vm.createDir(outDir, true);

        string memory outPath = _deploymentsFile("");
        vm.writeJson(finalJson, outPath);
        console.log("Deployments written to:", outPath);
    }
}
